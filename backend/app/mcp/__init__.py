"""
Phase 4: MCP server and the five registered DevOps tools (Section 12).

Scope boundary (STATUS.md Phase 4 Boundary): this package is ONLY the MCP
server and tool definitions. It does not implement the LangChain agent
(Phase 6), the Security Gateway — auth/validation/policy/risk/decision
(Phase 7+), or ML (Semester 2).

No FastAPI route is exposed here. `backend/app/main.py` and the
POST /mcp/tools/execute endpoint (Section 17) do not exist yet in this
repo (only a .gitkeep in backend/app/api/) — wiring MCP behind an actual
HTTP route is deferred to whichever phase bootstraps the FastAPI app and
adds the Gateway in front of it. `mcp.server.execute_tool()` is the
importable dispatch entrypoint for that future route to call.

Per FR-15, MCP should accept execution only from the trusted Gateway
path in the finished system. The Gateway doesn't exist yet, so
`execute_tool()` is directly callable for Phase 4 testing purposes. This
is expected and temporary (STATUS.md), not the final trust boundary.
"""