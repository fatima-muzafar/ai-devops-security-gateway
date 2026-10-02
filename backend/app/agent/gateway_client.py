"""
The agent's only way to act on infrastructure: submit a structured request
to POST /api/gateway/tool-request (Section 7, decisions.md #26).

This module must never import app.mcp or app.api.gateway.
"""
import os
from dataclasses import dataclass
from typing import Any

import httpx

GATEWAY_PATH = "/api/gateway/tool-request"


@dataclass(frozen=True)
class GatewayResponse:
    status_code: int
    body: dict[str, Any]


class GatewayClient:
    """Wraps any httpx-compatible client (httpx.Client, or Starlette's
    TestClient in tests)."""

    def __init__(self, http_client: Any, path: str = GATEWAY_PATH):
        self._http = http_client
        self._path = path

    def submit(self, tool_request: dict[str, Any]) -> GatewayResponse:
        response = self._http.post(self._path, json=tool_request)
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text}
        if not isinstance(body, dict):
            body = {"detail": body}
        return GatewayResponse(status_code=response.status_code, body=body)


def build_default_http_client() -> httpx.Client:
    return httpx.Client(
        base_url=os.getenv("GATEWAY_BASE_URL", "http://127.0.0.1:8000"),
        timeout=15.0,
    )