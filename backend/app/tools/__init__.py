"""Phase 3 — tool system package.

Importing this package registers the built-in tools on the shared
``tool_registry`` so the LLM tool-calling glue and the API can use them.
"""

from app.tools.base import (  # noqa: F401
    ConfirmationRequired,
    EmptyArgs,
    PermissionDenied,
    Tool,
    ToolContext,
    ToolError,
    ToolExecutionError,
    ToolInputError,
    ToolNotFound,
    ToolOutputError,
    ToolResult,
)

from app.tools.registry import tool_registry  # noqa: F401
from app.tools.manager import tool_manager  # noqa: F401  (re-export for routes/llm)
from app.tools.builtin import CalculateTool, GetTimeTool  # noqa: F401  (register side effects)

tool_registry.register(CalculateTool)
tool_registry.register(GetTimeTool)