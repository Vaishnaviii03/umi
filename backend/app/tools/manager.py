"""Phase 3 — tool manager.

Central enforcement point between the LLM and tool execution:

    Tool Request → resolve → permission check → confirmation gate →
    input validation → execute → output validation → structured result

The manager is where "reasoning does not equal authorization" lives: the LLM
may propose a tool, but this layer decides whether it actually runs, against
the permission ceiling and owner policy from config.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.tools.base import (
    ConfirmationRequired,
    PermissionDenied,
    Tool,
    ToolContext,
    ToolExecutionError,
    ToolError,
    ToolInputError,
    ToolNotFound,
    ToolResult,
)
from app.tools.registry import ToolRegistry, tool_registry

logger = logging.getLogger("umi.tools")


class ToolManager:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "permission_level": tool.permission_level,
                "owner_only": tool.owner_only,
                "requires_confirmation": tool.requires_confirmation,
            }
            for tool in self._registry.all()
        ]

    def execute_tool(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if not settings.tools_enabled:
            return ToolResult.failure("tools are disabled", "UMI_TOOLS_ENABLED is off")
        tool = self._registry.get(name)
        if tool is None:
            logger.warning("[tool] requested unknown tool '%s'", name)
            raise ToolNotFound(f"unknown tool '{name}'")

        self._authorize(tool, ctx)
        self._check_confirmation(tool, args, ctx)

        validated = tool.validate_input(args)  # also builds the kwargs dict
        try:
            result = tool.run(ctx, **validated.model_dump())
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 — tools may raise anything; we normalize
            logger.exception("[tool] %s failed with unexpected error", name)
            raise ToolExecutionError(f"tool '{name}' failed") from exc

        result = tool.validate_output(result)
        logger.info(
            "[tool] called name=%s status=%s args=%s",
            name,
            result.status,
            _compact(args),
        )
        return result

    def _authorize(self, tool: Tool, ctx: ToolContext) -> None:
        if settings.tools_enabled and tool.permission_level > settings.tools_max_permission_level:
            logger.warning(
                "[tool] denied name=%s reason=above_permission_ceiling level=%s ceiling=%s",
                tool.name,
                tool.permission_level,
                settings.tools_max_permission_level,
            )
            raise PermissionDenied(f"tool '{tool.name}' is above the allowed permission level")
        if tool.owner_only and ctx.user_id is not None and ctx.user_id != str(settings.owner_id):
            logger.warning(
                "[tool] denied name=%s reason=non_owner user=%s", tool.name, ctx.user_id
            )
            raise PermissionDenied(f"tool '{tool.name}' is restricted to Umi's owner")

    def _check_confirmation(self, tool: Tool, args: dict[str, Any], ctx: ToolContext) -> None:
        if not tool.requires_confirmation:
            return
        if ctx.extra.get("confirmed") is not True:
            logger.info(
                "[tool] confirmation required name=%s args=%s", tool.name, _compact(args)
            )
            raise ConfirmationRequired(
                f"tool '{tool.name}' requires explicit user confirmation"
            )


def _compact(args: dict[str, Any]) -> str:
    """Short, log-safe rendering of tool arguments (no secrets expected yet)."""
    text = str(args)
    return text if len(text) <= 200 else text[:200] + "..."


tool_manager = ToolManager(tool_registry)