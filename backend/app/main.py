"""
FastAPI application bootstrap.

Pure bootstrap as of Phase 6 (decisions.md #25): create the app and mount
routers. No route logic lives here.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import approvals, auth, chat, gateway, mcp, mock, security

DEFAULT_CORS_ORIGIN = "http://localhost:3000"


def _cors_origins() -> list[str]:
    """Allowed browser origins (decisions.md #96, #101). Never '*': a wildcard entry is dropped.
    Read once at import; the app imports above have already run load_dotenv()."""
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",")]
    origins = [o for o in origins if o and o != "*"]
    return origins or [DEFAULT_CORS_ORIGIN]


CORS_ORIGINS = _cors_origins()

app = FastAPI(title="Security Gateway FYP")

# Phase 12 (#96): bearer header only, no cookies, so no credentials. GET/POST only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(gateway.router)
app.include_router(chat.router)
app.include_router(mcp.router)
app.include_router(auth.router)
app.include_router(approvals.router)
app.include_router(security.router)
app.include_router(mock.router)
