import json
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from app.core.config import get_settings
from app.observability import MCP_TOOL_CALLS, genai_span


class MCPToolError(RuntimeError):
    """A tool error with the server-provided, auditable rejection reason."""


def validate_mcp_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("MCP endpoint must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("MCP endpoint must not contain credentials or fragments")
    if parsed.hostname.lower() not in get_settings().mcp_allowed_host_list:
        raise ValueError("MCP endpoint host is not in SUPPLYMIND_MCP_ALLOWED_HOSTS")
    return endpoint


def stdio_catalog() -> dict[str, dict]:
    try:
        payload = json.loads(get_settings().mcp_stdio_catalog_json)
    except json.JSONDecodeError as exc:
        raise ValueError("SUPPLYMIND_MCP_STDIO_CATALOG_JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("MCP stdio catalog must be a JSON object")
    return payload


class MCPClientManager:
    @asynccontextmanager
    async def session(
        self,
        *,
        transport: str,
        endpoint: str | None = None,
        stdio_catalog_key: str | None = None,
        auth_token: str | None = None,
    ):
        if transport == "streamable_http":
            if not endpoint:
                raise ValueError("HTTP MCP server requires an endpoint")
            headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
            http_client = create_mcp_http_client(headers=headers)
            async with http_client:
                async with streamable_http_client(
                    validate_mcp_endpoint(endpoint), http_client=http_client
                ) as streams:
                    read_stream, write_stream = streams[0], streams[1]
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        yield session
            return
        if transport == "stdio":
            catalog = stdio_catalog()
            definition = catalog.get(stdio_catalog_key or "")
            if not isinstance(definition, dict) or not isinstance(definition.get("command"), str):
                raise ValueError("Unknown MCP stdio catalog entry")
            parameters = StdioServerParameters(
                command=definition["command"],
                args=list(definition.get("args", [])),
                env=definition.get("env"),
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
            return
        raise ValueError("Unsupported MCP transport")

    async def discover(self, **connection) -> list[dict]:
        async with self.session(**connection) as session:
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema,
                }
                for tool in result.tools
            ]

    async def call(self, name: str, arguments: dict, **connection) -> dict:
        try:
            with genai_span(
                "mcp.tool.call",
                {
                    "rpc.system": "mcp",
                    "rpc.method": name,
                    "mcp.transport": connection.get("transport", "unknown"),
                },
            ):
                async with self.session(**connection) as session:
                    result = await session.call_tool(name, arguments=arguments)
                    if result.isError:
                        details = "; ".join(
                            block.text
                            for block in result.content
                            if isinstance(getattr(block, "text", None), str)
                        )
                        message = f"MCP tool failed: {name}"
                        raise MCPToolError(f"{message}: {details}" if details else message)
                    if result.structuredContent:
                        payload = dict(result.structuredContent)
                    else:
                        payload = {}
                        for block in result.content:
                            block_text = getattr(block, "text", None)
                            if block_text:
                                try:
                                    value = json.loads(block_text)
                                except json.JSONDecodeError:
                                    payload = {"text": block_text}
                                else:
                                    payload = (
                                        value if isinstance(value, dict) else {"result": value}
                                    )
                                break
            MCP_TOOL_CALLS.labels(name, "success").inc()
            return payload
        except Exception as exc:
            MCP_TOOL_CALLS.labels(name, "error").inc()
            # AnyIO task-group cleanup can wrap a server rejection in nested
            # ExceptionGroups. Preserve the typed tool error for SQL repair.
            rejection = exc
            while isinstance(rejection, BaseExceptionGroup) and len(rejection.exceptions) == 1:
                rejection = rejection.exceptions[0]
            if isinstance(rejection, MCPToolError) and rejection is not exc:
                raise rejection from exc
            raise
