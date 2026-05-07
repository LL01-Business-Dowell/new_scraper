"""
raw_gemini_routes.py  —  drop into backend/app/
Then in main.py add:
    from .raw_gemini_routes import router as raw_gemini_router
    app.include_router(raw_gemini_router)
"""

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import uuid
import datetime
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter()

raw_gemini_tasks: dict = {}

# ── Gemini client (same pattern as gemini_routes.py) ─────────────────────────
try:
    from google import genai
    if not os.getenv("GEMINI_KEY_1"):
        raise Exception("GEMINI_KEY_1 not set")
    raw_gemini_client = genai.Client(api_key=os.getenv("GEMINI_KEY_1"))
    RAW_GEMINI_AVAILABLE = True
    logger.info("Raw Gemini client initialised")
except Exception as e:
    logger.warning(f"Raw Gemini client init failed: {e}")
    RAW_GEMINI_AVAILABLE = False
    raw_gemini_client = None


# ── Models ────────────────────────────────────────────────────────────────────
class RawGeminiRequest(BaseModel):
    keyword: str
    city: str
    country: str
    prompt_count: int = 6          # how many prompts to run (default 6 to stay within quota)
    prompts: Optional[List[str]] = None   # optional: pass existing prompt strings


# ── Single raw Gemini call — NO formatting, NO JSON parsing ───────────────────
def call_gemini_raw(prompt_text: str) -> dict:
    """
    Fire a single prompt at Gemini and return the raw text response.
    No parsing, no filtering, no structure imposed.
    """
    result = {
        "prompt":        prompt_text,
        "raw_response":  "",
        "char_count":    0,
        "word_count":    0,
        "status":        "pending",
        "error":         None,
    }

    if not RAW_GEMINI_AVAILABLE:
        # Mock response for testing
        result["raw_response"] = (
            f"[MOCK] Here are some results for: {prompt_text[:80]}...\n\n"
            "1. Dr. Jane Smith - Director of Surgical Services\n"
            "   NewYork-Presbyterian Hospital\n"
            "   Phone: +1-212-555-0101\n"
            "   Email: j.smith@nyp.org\n"
            "   LinkedIn: linkedin.com/in/jane-smith-md\n\n"
            "2. Dr. John Doe - Director of Surgical Services\n"
            "   NYU Langone Health\n"
            "   Phone: +1-212-555-0102\n"
            "   Email: john.doe@nyulangone.org\n"
            "   LinkedIn: linkedin.com/in/john-doe-surgical\n"
        )
        result["status"] = "mock"
        result["char_count"] = len(result["raw_response"])
        result["word_count"] = len(result["raw_response"].split())
        return result

    try:
        response = raw_gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_text   # ← raw prompt, no system instruction, no format forcing
        )
        raw_text = response.text.strip() if response.text else ""
        result["raw_response"] = raw_text
        result["char_count"]   = len(raw_text)
        result["word_count"]   = len(raw_text.split())
        result["status"]       = "done"
        logger.info(f"Raw Gemini call done: {len(raw_text)} chars")

    except Exception as e:
        result["status"] = "error"
        result["error"]  = str(e)
        logger.error(f"Raw Gemini call failed: {e}")

    return result


# ── Background task ───────────────────────────────────────────────────────────
def run_raw_gemini_task(task_id: str, prompts: List[str]):
    task = raw_gemini_tasks[task_id]
    total = len(prompts)
    results = []

    logger.info(f"[RAW GEMINI {task_id}] Starting {total} raw prompts")

    for idx, prompt_text in enumerate(prompts):
        if not raw_gemini_tasks.get(task_id, {}).get("running", False):
            logger.info(f"[RAW GEMINI {task_id}] Cancelled at prompt {idx + 1}")
            break

        logger.info(f"[RAW GEMINI {task_id}] Prompt {idx + 1}/{total}")
        task["current_prompt"] = idx + 1
        task["current_prompt_text"] = prompt_text[:120] + "..." if len(prompt_text) > 120 else prompt_text

        result = call_gemini_raw(prompt_text)
        result["prompt_number"] = idx + 1

        results.append(result)
        task["results"]  = results
        task["progress"] = round(((idx + 1) / total) * 100, 1)

    task["running"]      = False
    task["progress"]     = 100
    task["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    logger.info(f"[RAW GEMINI {task_id}] Done. {len(results)} prompts processed")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/raw-gemini/")
async def start_raw_gemini(request: RawGeminiRequest, background_tasks: BackgroundTasks):
    """
    Start raw Gemini exploration.
    If `prompts` are passed, use those directly.
    Otherwise build simple prompts from keyword/city/country.
    """
    # Build simple prompts if none provided
    if request.prompts and len(request.prompts) > 0:
        # Use passed prompts but cap at prompt_count to save quota
        prompts_to_run = request.prompts[:request.prompt_count]
    else:
        # Build one simple prompt per "call" — no coordinates, just the keyword
        prompts_to_run = [
            f"find name, email, phone number, linkedin profile and hospital details "
            f"of 100 \"{request.keyword}\" in {request.city}, {request.country}"
        ] * min(request.prompt_count, 3)   # cap at 3 if no prompts provided

    if not prompts_to_run:
        return JSONResponse(status_code=400, content={"error": "No prompts to run"})

    task_id = str(uuid.uuid4())
    raw_gemini_tasks[task_id] = {
        "running":              True,
        "progress":             0,
        "results":              [],
        "error":                None,
        "total_prompts":        len(prompts_to_run),
        "current_prompt":       0,
        "current_prompt_text":  "",
        "keyword":              request.keyword,
        "city":                 request.city,
        "country":              request.country,
        "started_at":           datetime.datetime.utcnow().isoformat() + "Z",
    }

    background_tasks.add_task(run_raw_gemini_task, task_id, prompts_to_run)
    logger.info(f"[RAW GEMINI] Task {task_id} queued: {len(prompts_to_run)} prompts")

    return {"task_id": task_id, "total_prompts": len(prompts_to_run)}


@router.get("/raw-gemini-progress/{task_id}")
async def raw_gemini_progress(task_id: str):
    task = raw_gemini_tasks.get(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return {
        "running":             task.get("running", False),
        "progress":            task.get("progress", 0),
        "results":             task.get("results", []),
        "error":               task.get("error"),
        "total_prompts":       task.get("total_prompts", 0),
        "current_prompt":      task.get("current_prompt", 0),
        "current_prompt_text": task.get("current_prompt_text", ""),
        "keyword":             task.get("keyword", ""),
        "city":                task.get("city", ""),
        "country":             task.get("country", ""),
    }


@router.post("/cancel-raw-gemini/{task_id}")
async def cancel_raw_gemini(task_id: str):
    task = raw_gemini_tasks.get(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    task["running"] = False
    return {"message": f"Task {task_id} cancelled"}