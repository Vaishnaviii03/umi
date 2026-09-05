"""Phase 3 — first simple tools.

Both are LEVEL 1 (read/compute only, no side effects, no external calls):
they exist to prove the tool pipeline (registry → validation → permission →
execute → structured result) end to end and give the LLM deterministic,
safe capabilities. Gmail/Calendar/Search stay out of scope by design.
"""

from __future__ import annotations

import ast
import operator
from datetime import datetime

from pydantic import BaseModel, Field

from app.services.local_time import local_time_description
from app.tools.base import EmptyArgs, Tool, ToolContext, ToolExecutionError, ToolResult

MAX_EXPRESSION_CHARS = 200
MAX_POW_EXPONENT = 1_000

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalculateArgs(BaseModel):
    """A pure arithmetic expression, e.g. ``(42 + 9) * 3``."""

    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_CHARS)


class CalculateOutput(BaseModel):
    expression: str
    result: float


class CalculateTool(Tool):
    name = "calculate"
    description = (
        "Evaluate a safe arithmetic expression and return the numeric result. "
        "Supports + - * / // % ** and parentheses, e.g. '3 * (4 + 5)'."
    )
    permission_level = 1
    owner_only = True
    args_model = CalculateArgs
    output_model = CalculateOutput

    def run(self, ctx: ToolContext, expression: str, **kwargs) -> ToolResult:
        try:
            tree = ast.parse(expression, mode="eval")
            _guard(tree)
            value = _evaluate(tree.body)
        except (SyntaxError, _EvalGuard) as exc:
            raise ToolExecutionError(str(exc)) from exc
        except (ZeroDivisionError, OverflowError, ValueError, TypeError) as exc:
            raise ToolExecutionError("the expression could not be evaluated") from exc
        return ToolResult.success(
            {"expression": expression, "result": float(value) if isinstance(value, int) else value}
        )


class GetTimeOutput(BaseModel):
    iso: str
    description: str


class GetTimeTool(Tool):
    name = "get_time"
    description = (
        "Return the user's current local date and time, including the weekday. "
        "Use this when asked for the time, date, or day of the week."
    )
    permission_level = 1
    owner_only = True
    args_model = EmptyArgs
    output_model = GetTimeOutput

    def run(self, ctx: ToolContext, **kwargs) -> ToolResult:
        now = datetime.now().astimezone()
        return ToolResult.success(
            {
                "iso": now.isoformat(),
                "description": local_time_description(),
            }
        )


class _EvalGuard(Exception):
    """Raised internally when an expression exceeds safety limits."""


def _guard(tree: ast.AST) -> None:
    allowed = (
        ast.Expression,
        ast.Constant,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.operator,
        ast.unaryop,
        ast.boolop,
        ast.cmpop,
        ast.Load,
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            right = node.right
            safe = (
                isinstance(right, ast.Constant)
                and isinstance(right.value, (int, float))
                and abs(right.value) <= MAX_POW_EXPONENT
            )
            if not safe:
                raise _EvalGuard("the exponent is too large")
        elif not isinstance(node, allowed):
            raise _EvalGuard("only arithmetic expressions are allowed")


def _evaluate(node: ast.AST) -> int | float | bool:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise _EvalGuard("only numbers are allowed")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise _EvalGuard("unsupported operator")
        return op(_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise _EvalGuard("unsupported operator")
        return op(_evaluate(node.operand))
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_evaluate(v) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_evaluate(v) for v in node.values)
    if isinstance(node, ast.Compare):
        ops = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
        }
        op = ops.get(type(node.ops[0]))
        if op is None:
            raise _EvalGuard("unsupported comparison")
        return op(_evaluate(node.left), _evaluate(node.comparators[0]))
    raise _EvalGuard("only arithmetic expressions are allowed")