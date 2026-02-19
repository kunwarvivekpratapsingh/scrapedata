"""FastAPI backend for the Eval-DAG UI.

Endpoints:
  GET /api/files              — list result JSON files in project root
  GET /api/results/{filename} — return parsed JSON content for a result file
  GET /{full_path:path}       — serve frontend/dist SPA (production fallback)

Dev mode: Vite dev server (localhost:5173) proxies /api/* to this server.
Production: run `npm run build` in frontend/, then this server serves dist/.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Project root is one level up from this file (eval/)
PROJECT_ROOT = Path(__file__).parent.parent

# Frontend built assets (only present after `npm run build`)
DIST_DIR = Path(__file__).parent.parent / "frontend" / "dist"

app = FastAPI(title="Eval-DAG API", version="1.0.0")

# Allow Vite dev server (port 5173) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── API routes ──────────────────────────────────────────────────────────────


@app.get("/api/files")
def list_result_files():
    """Return a list of result JSON filenames in the project root."""
    patterns = [
        "eval_results*.json",
        "single_question*.json",
        "single_question_result*.json",
    ]
    found: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for p in sorted(PROJECT_ROOT.glob(pattern)):
            if p.name not in seen:
                found.append(p.name)
                seen.add(p.name)
    return {"files": found}


@app.get("/api/results/{filename}")
def get_result_file(filename: str):
    """Return the parsed JSON content of a result file."""
    # Security: only allow filenames, no path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = PROJECT_ROOT / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")

    return JSONResponse(content=data)


# ─── SPA fallback (production) ───────────────────────────────────────────────

if DIST_DIR.exists():
    # Serve static assets (JS/CSS/etc.)
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """Serve the SPA index.html for all non-API routes."""
        index = DIST_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built")
