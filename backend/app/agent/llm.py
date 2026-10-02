"""Gemini chat model factory (decisions.md #16, #26). Imported lazily so
tests and app import do not need the package or an API key."""
import os

from dotenv import load_dotenv

# Placeholder default -- verify against what your AI Studio free tier
# currently offers; override with GEMINI_MODEL in backend/.env.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def build_gemini_llm():
    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY not set. Check backend/.env.")
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        temperature=0,
    )