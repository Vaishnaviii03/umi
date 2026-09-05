"""Phase 3 — tool system core types.

The LLM never executes anything itself. Tools declare a name, description,
permission level, input/output schemas and their execution behavior here; the
``ToolManager`` validates, checks permissions and runs them on the backend's
behalf, then returns a structured ``ToolResult``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("umi.tools")


class ToolError(Exception):
    """Base class for all tool-system errors (name is always safe to expose)."""


class ToolInputError(ToolError):
    """The arguments supplied to a tool failed its input schema."""


class ToolNotFound(ToolError):
    """No tool with the requested name is registered."""


class ToolExecutionError(ToolError):
    """The tool itself failed while running."""


class ToolOutputError(ToolError):
    """The tool produced a result that failed its output schema."""


class PermissionDenied(ToolError):
    """The current user/level is not allowed to run this tool."""


class ConfirmationRequired(ToolError):
    """The tool needs explicit user confirmation before it may run."""


class EmptyArgs(BaseModel):
    """Default input schema for tools that take no arguments."""


@dataclass
class ToolContext:
    """Everything a tool may need while running.

    ``user_id`` is who is asking; the permission layer compares it against the
    configured owner. ``db``/``conversation_id`` are optional plumbing for tool
    kinds that read or write persisted state (none of the Phase 3 tools use
    them). ``extra`` is a free-form bag for future integrations.
    """

    user_id: str | None = None
    db: Any = None
    conversation_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Standardized result handed back to the LLM.

    ``status`` is ``"success"`` or ``"error"``. For success, ``data`` is a
    JSON-serializable dict; for errors, ``error`` holds a short human/LLM-safe
    message plus the original ``detail`` for logs.
    """

    status: str
    data: dict[str, Any] | None = None
    error: str | None = None
    detail: str | None = None

    @classmethod
    def success(cls, data: dict[str, Any]) -> "ToolResult":
        return cls(status="success", data=data)

    @classmethod
    def failure(cls, error: str, detail: str | None = None) -> "ToolResult":
        return cls(status="error", error=error, detail=detail)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.data is not None:
            payload["data"] = self.data
        if self.error is not None:
            payload["error"] = self.error
        return payload

    def to_json(self) -> str:
        import json

        return json.dumps(self.as_dict())


class Tool:
    """Base class for every tool.

    Subclasses set the class attributes and implement ``run``. All validation
    and permission checks are performed by the ``ToolManager`` before ``run``
    is called, so tools never have to re-validate trust.
    """

    name: str = ""
    description: str = ""
    permission_level: int = 1  # 1 = read/compute, up to 5 = high-risk
    owner_only: bool = True    # Phase 3 tools run only for the owner account
    requires_confirmation: bool = False
    args_model: type[BaseModel] = EmptyArgs
    output_model: type[BaseModel] | None = None

    def schema(self) -> dict[str, Any]:
        """OpenAI-compatible function definition for the LLM."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    def validate_input(self, args: dict[str, Any]) -> BaseModel:
        try:
            return self.args_model.model_validate(args)
        except ValidationError as exc:
            raise ToolInputError(
                f"invalid arguments for '{self.name}'",
            ) from exc

    def validate_output(self, result: ToolResult) -> ToolResult:
        if result.status != "success" or self.output_model is None:
            return result
        try:
            self.output_model.model_validate(result.data or {})
        except ValidationError as exc:
            logger.error("tool %s output validation failed: %s", self.name, exc)
            raise ToolOutputError(f"tool '{self.name}' produced an invalid result")
        return result

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        raise NotImplementedError