"""RunManager — bridges the synchronous LangGraph eval pipeline to async SSE.

Architecture:
  - POST /api/run creates a RunJob with a UUID and an asyncio.Queue
  - The pipeline runs in a ThreadPoolExecutor (never blocks the event loop)
  - Progress callbacks use asyncio.run_coroutine_threadsafe to enqueue events
  - GET /api/run/{id}/events drains the queue and yields SSE frames
  - A None sentinel in the queue signals stream end
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable

# Add src/ to path so pipeline can be imported from api/ directory
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Dataset cache: loaded once at startup
_DATASET_CACHE: dict[str, Any] | None = None
_METADATA_CACHE: dict[str, Any] | None = None

# Project root (one level above api/)
PROJECT_ROOT = Path(__file__).parent.parent


def load_dataset_cached() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load dataset and metadata from disk, cached after first call."""
    global _DATASET_CACHE, _METADATA_CACHE
    if _DATASET_CACHE is None:
        data_path = PROJECT_ROOT / "dataset" / "data.json"
        meta_path = PROJECT_ROOT / "dataset" / "metadata.json"
        _DATASET_CACHE = json.loads(data_path.read_text(encoding="utf-8"))
        _METADATA_CACHE = (
            json.loads(meta_path.read_text(encoding="utf-8"))
            if meta_path.exists()
            else {}
        )
    return _DATASET_CACHE, _METADATA_CACHE


# ── Job model ─────────────────────────────────────────────────────────────────

@dataclass
class RunJob:
    run_id: str
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    status: str = "pending"   # pending | running | done | error
    output_file: str = ""


# ── Job registry ──────────────────────────────────────────────────────────────

class RunManager:
    """Thread-safe job registry. One RunJob per run_id."""

    def __init__(self):
        self._jobs: dict[str, RunJob] = {}

    def create(self, run_id: str, loop: asyncio.AbstractEventLoop) -> RunJob:
        job = RunJob(run_id=run_id, queue=asyncio.Queue(), loop=loop)
        self._jobs[run_id] = job
        return job

    def get(self, run_id: str) -> RunJob | None:
        return self._jobs.get(run_id)

    def delete(self, run_id: str) -> None:
        self._jobs.pop(run_id, None)


run_manager = RunManager()


# ── Progress callback factory ─────────────────────────────────────────────────

def make_progress_cb(job: RunJob) -> Callable[[str, dict], None]:
    """Return a thread-safe event emitter for the given job.

    Nodes call: cb("dag_built", {"question_id": ..., ...})
    The callback schedules a put on the asyncio queue from any thread.
    """
    def emit(event_type: str, payload: dict) -> None:
        event = {
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        asyncio.run_coroutine_threadsafe(
            job.queue.put(json.dumps(event, default=str)),
            job.loop,
        )

    return emit


# ── Synchronous pipeline runner (runs in ThreadPoolExecutor) ──────────────────

def run_pipeline_sync(
    job: RunJob,
    config: dict,
    dataset: dict,
    metadata: dict,
) -> None:
    """Execute the eval pipeline synchronously in a worker thread.

    Emits SSE events via the job's queue throughout execution.
    Always puts a None sentinel at the end to signal stream close.
    """
    emit = make_progress_cb(job)

    try:
        from eval_dag.graphs.orchestrator import orchestrator

        job.status = "running"
        emit("run_started", {
            "run_id": job.run_id,
            "num_questions": config["num_questions"],
            "difficulty": config["difficulty"],
        })

        initial_state = {
            "dataset": dataset,
            "metadata": metadata,
            "questions": [],
            "completed_results": [],
            "failed_questions": [],
            "question_traces": [],
            "final_report": {},
            "messages": [],
            # Progress hooks consumed by nodes
            "_progress_cb": emit,
            "_difficulty": config["difficulty"],
            "_num_questions": config["num_questions"],
        }

        final_state = orchestrator.invoke(initial_state)

        # Write result to disk
        outfile = f"eval_results_{job.run_id[:8]}.json"
        out_path = PROJECT_ROOT / outfile
        report = final_state.get("final_report", {})
        out_path.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )
        job.output_file = outfile
        job.status = "done"

        s = report.get("summary", {})
        emit("run_complete", {
            "output_file": outfile,
            "summary": {
                "total": s.get("total_questions", 0),
                "passed": s.get("successful_executions", 0),
                "failed": s.get("execution_failures", 0),
                "pass_rate": s.get("pass_rate", 0.0),
            },
        })

    except Exception as exc:
        job.status = "error"
        emit("error", {"message": str(exc)})

    finally:
        # Sentinel — tells stream_events() to stop iterating
        asyncio.run_coroutine_threadsafe(job.queue.put(None), job.loop)


# ── Async SSE generator ───────────────────────────────────────────────────────

async def stream_events(job: RunJob) -> AsyncIterator[str]:
    """Async generator that drains the job queue and yields SSE-formatted strings."""
    try:
        while True:
            item = await job.queue.get()
            if item is None:   # sentinel — pipeline finished
                break
            yield f"data: {item}\n\n"
    finally:
        # Clean up job after a short grace period (allow reconnect within 60s)
        await asyncio.sleep(60)
        run_manager.delete(job.run_id)
