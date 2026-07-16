# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Client for invoking WIG's deterministic business-logic tools."""
import os
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

_MCP_TOOLS_URL = os.environ.get(
    "WIG_MCP_TOOLS_URL", "http://wig-mcp-tools:8020/mcp"
)
_TOOL_PREFIX = "wig-tools__"
_DEFAULT_TIMEOUT = 120.0


class OpenClawToolError(RuntimeError):
    """Raised when a tool call transport-fails or the tool itself errors."""


def _bare_tool_name(tool: str) -> str:
    return tool[len(_TOOL_PREFIX) :] if tool.startswith(_TOOL_PREFIX) else tool


async def invoke_tool(
    tool: str, args: dict[str, Any], *, timeout: Optional[float] = None
) -> Any:
    """Call one MCP tool on wig-mcp-tools and return its structured result."""
    bare_name = _bare_tool_name(tool)
    async with streamablehttp_client(
        _MCP_TOOLS_URL, timeout=timeout or _DEFAULT_TIMEOUT
    ) as (
        read_stream,
        write_stream,
        _get_session_id,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(bare_name, args)
            if result.isError:
                message = result.structuredContent or (
                    result.content[0].text
                    if result.content
                    else "unknown tool error"
                )
                raise OpenClawToolError(f"{tool}: {message}")
            # FastMCP wraps non-object-schema return values as {"result": <value>}
            # when the tool has no explicit structured output type declared.
            structured = result.structuredContent
            if isinstance(structured, dict) and set(structured.keys()) == {
                "result"
            }:
                return structured["result"]
            return structured
