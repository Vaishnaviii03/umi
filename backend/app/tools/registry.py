"""Phase 3 — tool registry.

A single place where tools are registered and looked up by name. Adding a new
tool is a one-file change (define a ``Tool`` subclass, decorate with
``@tool_registry.register``); the orchestrator, permission layer and LLM
tool-calling glue all read from here unchanged.
"""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool_cls: type[Tool]) -> type[Tool]:
        instrumented: Tool = object.__new__(tool_cls)  # skip __init__, tools are stateless
        self._tools[instrumented.name] = instrumented
        return tool_cls

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]


tool_registry = ToolRegistry()