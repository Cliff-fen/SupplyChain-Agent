import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class SideEffect(StrEnum):
    read = "read"
    export = "export"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    minimum_roles: frozenset[str]
    side_effect: SideEffect
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    timeout_seconds: int


ToolHandler = Callable[[BaseModel], Awaitable[BaseModel]]


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "description": item.description,
                "minimum_roles": sorted(item.minimum_roles),
                "side_effect": item.side_effect,
                "timeout_seconds": item.timeout_seconds,
                "input_schema": item.input_model.model_json_schema(),
                "output_schema": item.output_model.model_json_schema(),
            }
            for item in self._definitions.values()
        ]

    async def call(self, name: str, role: str, payload: dict[str, Any]) -> BaseModel:
        definition = self._definitions.get(name)
        if not definition:
            raise KeyError(f"Unknown tool: {name}")
        if role not in definition.minimum_roles:
            raise PermissionError(f"Role {role} cannot call {name}")
        input_value = definition.input_model.model_validate(payload)
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return await asyncio.wait_for(
                    self._handlers[name](input_value), definition.timeout_seconds
                )
            except (TimeoutError, OSError, RuntimeError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0)
        raise RuntimeError(f"MCP tool failed: {name}") from last_error
