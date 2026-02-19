"""FastAPI backend for the Eval-DAG UI.

Endpoints:
  GET  /api/files                  — list result JSON files in project root
  GET  /api/results/{filename}     — return parsed JSON content for a result file
  POST /api/run                    — start a new eval run (returns run_id)
  GET  /api/run/{run_id}/events    — SSE stream of real-time progress events
  GET  /{full_path:path}           — serve frontend/dist SPA (production fallback)

Dev mode: Vite dev server (localhost:5173) proxies /api/* to this server.
Production: run `npm run build` in frontend/, then this server serves dist/.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from runner import (
    load_dataset_cached,
    run_manager,
    run_pipeline_sync,
    stream_events,
)

# Project root is one level up from this file (eval/)
PROJECT_ROOT = Path(__file__).parent.parent

# Frontend built assets (only present after `npm run build`)
DIST_DIR = Path(__file__).parent.parent / "frontend" / "dist"

# Dedicated thread pool for pipeline runs (isolates long-running threads)
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="eval-run")

app = FastAPI(title="Eval-DAG API", version="2.0.0")

# Allow Vite dev server (port 5173) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response models ────────────────────────────────────────────────


class RunConfig(BaseModel):
    difficulty: str = Field(default="all", description="easy | medium | hard | all")
    num_questions: int = Field(default=5, ge=1, le=10, description="1–10")


# ─── Existing API routes ──────────────────────────────────────────────────────


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
    # Security: only allow plain filenames, no path traversal
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


# ─── Run API routes ───────────────────────────────────────────────────────────


@app.post("/api/run", status_code=202)
async def start_run(body: RunConfig) -> dict[str, str]:
    """Validate config, start the eval pipeline in a background thread, return run_id.

    The pipeline is synchronous (LangGraph + blocking LLM calls) so it MUST
    run in a ThreadPoolExecutor — never on the event loop thread directly.
    """
    if body.difficulty not in ("easy", "medium", "hard", "all"):
        raise HTTPException(
            status_code=400,
            detail="difficulty must be one of: easy, medium, hard, all",
        )

    # Load dataset (cached after first call)
    try:
        dataset, metadata = load_dataset_cached()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Dataset not found: {e}. Ensure dataset/data.json exists.",
        )

    run_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    job = run_manager.create(run_id, loop)

    config = {"difficulty": body.difficulty, "num_questions": body.num_questions}

    # Submit to dedicated thread pool — non-blocking
    loop.run_in_executor(
        _EXECUTOR,
        run_pipeline_sync,
        job,
        config,
        dataset,
        metadata,
    )

    return {"run_id": run_id}


@app.get("/api/run/{run_id}/events")
async def stream_run_events(run_id: str) -> StreamingResponse:
    """Open an SSE stream for real-time progress of the given run.

    The client should call this immediately after POST /api/run.
    The stream closes automatically when the pipeline finishes.
    """
    job = run_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    return StreamingResponse(
        stream_events(job),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # disable nginx/reverse-proxy buffering
            "Connection": "keep-alive",
        },
    )


@app.get("/api/run/{run_id}/status")
def get_run_status(run_id: str) -> dict[str, Any]:
    """Return the current status of a run (for polling fallback)."""
    job = run_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return {
        "run_id": run_id,
        "status": job.status,
        "output_file": job.output_file or None,
    }


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
