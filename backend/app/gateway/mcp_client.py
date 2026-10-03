"""
The Gateway's only way to reach MCP: POST /mcp/tools/execute with the internal
token (Section 17, FR-15; decisions.md #37, #40). Mirrors agent/gateway_client.py
(#26).

This module must never import app.mcp or app.api.mcp: the HTTP seam is the point.
"""
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

MCP_EXECUTE_PATH = "/mcp/tools/execute"
TOKEN_HEADER = "X-Internal-Token"
TOKEN_ENV = "MCP_INTERNAL_TOKEN"
DEFAULT_MCP_BASE_URL = "http://127.0.0.1:8000"


class McpUnavailableError(Exception):
    """MCP could not be reached, or no token is configured. Nothing executed."""


@dataclass(frozen=True)
class McpResponse:
    status_code: int
    body: dict[str, Any]


class McpClient:
    """Wraps any httpx-compatible client (httpx.Client, or Starlette's
    TestClient in tests). The token is read from the environment at CALL time
    unless one is passed explicitly."""

    def __init__(
        self,
        http_client: Any,
        token: str | None = None,
        path: str = MCP_EXECUTE_PATH,
    ):
        self._http = http_client
        self._token = token
        self._path = path

    def execute(
        self, request_id: str, tool: str, arguments: dict[str, Any]
    ) -> McpResponse:
        token = self._token if self._token is not None else os.getenv(TOKEN_ENV, "")
        if not token:
            raise McpUnavailableError(
                f"{TOKEN_ENV} is not configured; refusing to call MCP."
            )

        try:
            response = self._http.post(
                self._path,
                json={"request_id": request_id, "tool": tool, "arguments": arguments},
                headers={TOKEN_HEADER: token},
            )
        except httpx.TransportError as exc:
            raise McpUnavailableError(f"MCP unreachable: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text}
        if not isinstance(body, dict):
            body = {"detail": body}
        return McpResponse(status_code=response.status_code, body=body)


def build_default_http_client() -> httpx.Client:
    # `or`, not a getenv default: .env.example ships MCP_BASE_URL empty.
    return httpx.Client(
        base_url=os.getenv("MCP_BASE_URL") or DEFAULT_MCP_BASE_URL,
        timeout=15.0,
    )


@lru_cache(maxsize=1)
def get_mcp_client() -> McpClient:
    """FastAPI dependency. Tests override it with
    McpClient(TestClient(app), token=...)."""
    return McpClient(build_default_http_client())