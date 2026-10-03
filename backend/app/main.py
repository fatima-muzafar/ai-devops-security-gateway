"""
FastAPI application bootstrap.

Pure bootstrap as of Phase 6 (decisions.md #25): create the app and mount
routers. No route logic lives here.
"""
from fastapi import FastAPI

from app.api import chat, gateway, mcp

app = FastAPI(title="Security Gateway FYP")

app.include_router(gateway.router)
app.include_router(chat.router)
app.include_router(mcp.router)