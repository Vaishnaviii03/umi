"""Phase 3 — tool system tests: registry, manager, permissions, built-ins."""

import pytest

from pydantic import BaseModel, create_model

from app.config import settings
from app.tools import (
    ConfirmationRequired,
    PermissionDenied,
    Tool,
    ToolContext,
    ToolExecutionError,
    ToolInputError,
    ToolNotFound,
    ToolOutputError,
    ToolResult,
    tool_manager,
    tool_registry,
)
from app.tools.builtin import CalculateTool, GetTimeTool

OWNER = str(settings.owner_id)


def ctx(*, user_id=OWNER, **extra):
    kwargs = {"user_id": user_id}
    kwargs.update(extra)
    return ToolContext(**kwargs)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registry_has_builtin_tools_registered():
    assert "calculate" in tool_registry.names()
    assert "get_time" in tool_registry.names()
    assert isinstance(tool_registry.get("calculate"), CalculateTool)
    assert isinstance(tool_registry.get("get_time"), GetTimeTool)


def test_registry_openai_tools_shape():
    tools = tool_registry.openai_tools()
    names = {t["function"]["name"] for t in tools}
    assert names == {"calculate", "get_time"}
    calc = next(t for t in tools if t["function"]["name"] == "calculate")
    assert calc["type"] == "function"
    props = calc["function"]["parameters"]["properties"]
    assert "expression" in props


def test_catalog_contains_metadata_only():
    catalog = tool_manager.catalog()
    by_name = {t["name"]: t for t in catalog}
    assert by_name["calculate"]["permission_level"] == 1
    assert by_name["calculate"]["owner_only"] is True
    assert by_name["calculate"]["requires_confirmation"] is False


# --------------------------------------------------------------------------- #
# calculate
# --------------------------------------------------------------------------- #
def test_calculate_success():
    result = tool_manager.execute_tool("calculate", {"expression": "3 * (4 + 5)"}, ctx())
    assert result.status == "success"
    assert result.data["result"] == 27.0


def test_calculate_supports_basic_ops_and_precedence():
    assert tool_manager.execute_tool("calculate", {"expression": "10 / 4"}, ctx()).data["result"] == 2.5
    assert tool_manager.execute_tool("calculate", {"expression": "2 ** 8"}, ctx()).data["result"] == 256.0
    assert tool_manager.execute_tool("calculate", {"expression": "17 % 5"}, ctx()).data["result"] == 2.0
    assert tool_manager.execute_tool("calculate", {"expression": "-3 + 7"}, ctx()).data["result"] == 4.0


def test_calculate_rejects_non_arithmetic_input():
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool("calculate", {"expression": "__import__('os').system('id')"}, ctx())
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool("calculate", {"expression": "lambda: 1"}, ctx())
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool("calculate", {"expression": "'a' + 'b'"}, ctx())


def test_calculate_rejects_division_by_zero():
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool("calculate", {"expression": "1 / 0"}, ctx())


def test_calculate_rejects_runaway_exponent():
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool("calculate", {"expression": "9 ** (9 ** 9)"}, ctx())


# --------------------------------------------------------------------------- #
# get_time
# --------------------------------------------------------------------------- #
def test_get_time_success():
    result = tool_manager.execute_tool("get_time", {}, ctx())
    assert result.status == "success"
    assert "iso" in result.data
    assert "day" in result.data["description"].lower()


# --------------------------------------------------------------------------- #
# Validation / availability
# --------------------------------------------------------------------------- #
def test_unknown_tool_raises_not_found():
    with pytest.raises(ToolNotFound):
        tool_manager.execute_tool("no_such_tool", {}, ctx())


def test_invalid_args_raises_input_error():
    with pytest.raises(ToolInputError):
        tool_manager.execute_tool("calculate", {"expression": ""}, ctx())
    with pytest.raises(ToolInputError):
        tool_manager.execute_tool("calculate", {"nope": "1"}, ctx())


def test_non_owner_denied():
    with pytest.raises(PermissionDenied):
        tool_manager.execute_tool("calculate", {"expression": "1 + 1"}, ctx(user_id="someone-else"))


def test_permission_ceiling_enforced(monkeypatch):
    monkeypatch.setattr(settings, "tools_max_permission_level", 0)
    with pytest.raises(PermissionDenied):
        tool_manager.execute_tool("calculate", {"expression": "1 + 1"}, ctx())


def test_tools_disabled_enforced(monkeypatch):
    monkeypatch.setattr(settings, "tools_enabled", False)
    result = tool_manager.execute_tool("calculate", {"expression": "1 + 1"}, ctx())
    assert result.status == "error"


# --------------------------------------------------------------------------- #
# Confirmation gate
# --------------------------------------------------------------------------- #
class ConfirmedTool(Tool):
    name = "confirmed_tool"
    description = "test tool that needs confirmation"
    permission_level = 1
    requires_confirmation = True

    def run(self, ctx: ToolContext, **kwargs) -> ToolResult:
        return ToolResult.success({"ok": True})


def test_confirmation_required_without_approval():
    tool_registry._tools["confirmed_tool"] = ConfirmedTool()
    try:
        with pytest.raises(ConfirmationRequired):
            tool_manager.execute_tool("confirmed_tool", {}, ctx())
        result = tool_manager.execute_tool("confirmed_tool", {}, ctx(extra={"confirmed": True}))
        assert result.status == "success"
    finally:
        tool_registry._tools.pop("confirmed_tool", None)


# --------------------------------------------------------------------------- #
# Output validation
# --------------------------------------------------------------------------- #
class BadOutputTool(Tool):
    name = "bad_output_tool"
    description = "test tool whose output fails validation"
    permission_level = 1
    output_model = create_model("BadOut", result=(float, ...))

    def run(self, ctx: ToolContext, **kwargs) -> ToolResult:
        return ToolResult.success({"result": "not-a-number"})


def test_output_validation_failure_is_safe():
    tool_registry._tools["bad_output_tool"] = BadOutputTool()
    try:
        with pytest.raises(ToolOutputError):
            tool_manager.execute_tool("bad_output_tool", {}, ctx())
    finally:
        tool_registry._tools.pop("bad_output_tool", None)