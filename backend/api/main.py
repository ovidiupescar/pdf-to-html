"""PDF Tech → HTML — FastAPI application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router

app = FastAPI(
    title="PDF Tech → HTML",
    description="Convert technical PDFs to faithful HTML — preserving text, tables, and diagrams.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


# ── Serve built frontend as static files ──────────────────────────────
# Must be mounted last so API routes take priority.
_frontend = Path(__file__).resolve().parent.parent.parent / "frontend" / "out"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")

# ── Serve output files (figures, etc.) ─────────────────────────────────
_output = Path(__file__).resolve().parent.parent / "output"
_output.mkdir(parents=True, exist_ok=True)
app.mount("/static-output", StaticFiles(directory=str(_output)), name="static-output")
