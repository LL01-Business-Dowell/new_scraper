"""
csv_routes.py
-------------
Handles the CSV processing flow:

  1. POST /process-csv/
       Accept a CSV file + natural-language prompt.
       Process via Gemini (using the shared gemini_rotator from main.py).
       Return task_id immediately; client polls for completion.

  2. GET /process-csv-progress/{task_id}
       Poll endpoint — returns running, ready, error, row_count, preview_rows.

  3. POST /refine-csv/{task_id}
       Accept a new prompt and apply it to the CURRENT processed output
       (iterative refinement — each pass builds on the previous result).
       Returns a new task_id; client polls the same progress endpoint.

  4. GET /download-processed-csv/{task_id}
       Stream the final output CSV to the browser.

Register in main.py:
    from .csv_routes import router as csv_router
    app.include_router(csv_router)
"""

from fastapi import APIRouter, File, Form, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional
import pandas as pd
import json
import re
import uuid
import time
import os
import io
import logging
import traceback

from .gemini_rotator import gemini_rotator

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory task store
# Each entry:
#   running       bool     — True while Gemini call / file write is in progress
#   error         str|None
#   file_path     str|None — path to the output CSV on disk
#   row_count     int
#   columns       list[str] — column names for the preview table
#   preview_rows  list[dict] — first PREVIEW_ROW_COUNT rows for the table
#   started_at    float    — unix timestamp
#   original_task_id  str|None — points to the task this was refined from
# ---------------------------------------------------------------------------
csv_tasks: dict = {}

PREVIEW_ROW_COUNT = 50   # rows shown in the frontend preview table
TMP_DIR           = "/tmp"


# ---------------------------------------------------------------------------
# Helper: build the prompt sent to Gemini
# ---------------------------------------------------------------------------

def _build_csv_prompt(csv_text: str, user_prompt: str) -> str:
    """
    Construct the full prompt sent to Gemini for CSV processing.

    The prompt is deliberately strict to prevent Gemini from inventing
    values that were not present in the original data.
    """
    return f"""You are a precise data transformation assistant.

TASK
----
{user_prompt}

RULES — YOU MUST FOLLOW ALL OF THEM
-------------------------------------
1. Work ONLY with the data provided below. Do NOT invent, hallucinate,
   or fill in missing values with plausible-sounding data.
2. If a value is missing or unknown, keep the cell empty ("") or use the
   original value — never substitute synthetic content.
3. Return ONLY a JSON array of objects. Each object is one output row.
   Use the column names as keys.
4. Do not include any explanation, markdown fences, or text outside the
   JSON array. The very first character of your response must be "[" and
   the very last must be "]".
5. Preserve every row from the input unless the task explicitly says to
   remove certain rows. Do not silently drop rows.
6. If the task asks you to add a new column, add it to every row. If the
   value for that column cannot be determined from the existing data,
   leave the field as an empty string.

INPUT CSV
---------
{csv_text}
"""


# ---------------------------------------------------------------------------
# Helper: call Gemini and parse JSON array response into a DataFrame
# ---------------------------------------------------------------------------

def _call_gemini_and_parse(csv_text: str, user_prompt: str, task_id: str) -> pd.DataFrame:
    """
    Build the full prompt, send to Gemini via the shared rotator,
    parse the JSON array response, and return a DataFrame.

    Raises RuntimeError on Gemini failure or parse failure so the
    caller can set the task error state cleanly.
    """
    full_prompt = _build_csv_prompt(csv_text, user_prompt)
    logger.info(
        f"[CSV {task_id}] Sending prompt to Gemini "
        f"({len(full_prompt)} chars total)"
    )

    if gemini_rotator is None:
        raise RuntimeError(
            "Gemini rotator is not available. "
            "Check that GEMINI_KEY_1 is set and main.py imported correctly."
        )

    # Call Gemini — rotator handles key rotation on 429 automatically
    try:
        raw_response = gemini_rotator.call(full_prompt, temperature=0.0)
    except RuntimeError as exc:
        logger.error(f"[CSV {task_id}] Gemini rotator error: {exc}")
        raise

    logger.info(f"[CSV {task_id}] Gemini responded ({len(raw_response)} chars)")

    # Strip markdown code fences if Gemini added them
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()

    # Parse JSON array
    try:
        rows = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting just the array if there's surrounding text
        start = cleaned.find("[")
        end   = cleaned.rfind("]")
        if start != -1 and end != -1:
            try:
                rows = json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError as exc:
                logger.error(f"[CSV {task_id}] JSON parse failed: {exc}")
                raise RuntimeError(
                    "The AI returned a response that could not be parsed as JSON. "
                    "Try rephrasing your prompt to be more specific."
                ) from exc
        else:
            raise RuntimeError(
                "The AI did not return a JSON array. "
                "Try rephrasing your prompt to be more specific."
            )

    if not isinstance(rows, list):
        raise RuntimeError(
            f"Expected a JSON array but got {type(rows).__name__}."
        )

    logger.info(f"[CSV {task_id}] Parsed {len(rows)} output rows from Gemini")

    # Build DataFrame and sanitise
    out_df = pd.DataFrame(rows)
    out_df = out_df.fillna("")   # replace None with empty string

    return out_df


# ---------------------------------------------------------------------------
# Background task: process CSV and write output file
# ---------------------------------------------------------------------------

def _run_csv_task(
    task_id:        str,
    csv_bytes:      bytes,
    user_prompt:    str,
    source_task_id: Optional[str] = None,
) -> None:
    """
    Background worker:
      1. Parse the input CSV (bytes)
      2. Call Gemini via the shared rotator
      3. Write the output CSV to /tmp
      4. Update the task store with results or error

    source_task_id is set for refinement tasks — it points to the
    previous task whose output was used as this task's input.
    """
    logger.info(f"[CSV {task_id}] Task started (source={source_task_id})")
    csv_tasks[task_id]["running"] = True

    try:
        # Parse uploaded / previous-output CSV
        try:
            df = pd.read_csv(io.BytesIO(csv_bytes))
        except Exception as exc:
            logger.error(f"[CSV {task_id}] CSV parse error: {exc}")
            csv_tasks[task_id]["error"]   = f"Could not parse CSV: {exc}"
            csv_tasks[task_id]["running"] = False
            return

        row_count = len(df)
        col_count = len(df.columns)
        logger.info(f"[CSV {task_id}] Input: {row_count} rows, {col_count} columns")

        if row_count == 0:
            csv_tasks[task_id]["error"]   = "The CSV file has no data rows."
            csv_tasks[task_id]["running"] = False
            return

        # Serialise to plain text for Gemini
        csv_text = df.to_csv(index=False)

        # Call Gemini and parse response
        out_df = _call_gemini_and_parse(csv_text, user_prompt, task_id)

        # Write output CSV to disk
        output_path = os.path.join(TMP_DIR, f"processed_csv_{task_id}.csv")
        out_df.to_csv(output_path, index=False)
        logger.info(
            f"[CSV {task_id}] Output written to {output_path} "
            f"({len(out_df)} rows, {len(out_df.columns)} columns)"
        )

        # Build preview (first N rows as list of dicts)
        preview = out_df.head(PREVIEW_ROW_COUNT).to_dict(orient="records")

        # Update task store
        csv_tasks[task_id]["file_path"]    = output_path
        csv_tasks[task_id]["row_count"]    = len(out_df)
        csv_tasks[task_id]["columns"]      = list(out_df.columns)
        csv_tasks[task_id]["preview_rows"] = preview
        csv_tasks[task_id]["running"]      = False

        logger.info(f"[CSV {task_id}] Completed successfully — {len(out_df)} rows")

    except RuntimeError as exc:
        # Expected errors from Gemini / parsing
        logger.error(f"[CSV {task_id}] Error: {exc}")
        csv_tasks[task_id]["error"]   = str(exc)
        csv_tasks[task_id]["running"] = False

    except Exception:
        logger.error(f"[CSV {task_id}] Unexpected error:\n{traceback.format_exc()}")
        csv_tasks[task_id]["error"]   = "An unexpected error occurred. Check server logs."
        csv_tasks[task_id]["running"] = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/process-csv/")
async def process_csv(
    background_tasks: BackgroundTasks,
    file:   UploadFile = File(...),
    prompt: str        = Form(...),
):
    """
    Accept a CSV file and a natural-language prompt.
    Starts background processing and returns task_id immediately.
    Client polls GET /process-csv-progress/{task_id}.
    """
    if not prompt.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Prompt must not be empty."},
        )

    csv_bytes = await file.read()
    if not csv_bytes:
        return JSONResponse(
            status_code=400,
            content={"error": "Uploaded file is empty."},
        )

    task_id = str(uuid.uuid4())
    logger.info(
        f"[/process-csv/] New task {task_id} — "
        f"file={file.filename}, prompt_len={len(prompt)}"
    )

    csv_tasks[task_id] = {
        "running":          False,   # set True inside background task
        "error":            None,
        "file_path":        None,
        "row_count":        0,
        "columns":          [],
        "preview_rows":     [],
        "started_at":       time.time(),
        "original_task_id": None,
    }

    background_tasks.add_task(
        _run_csv_task,
        task_id,
        csv_bytes,
        prompt.strip(),
        None,
    )

    return {"task_id": task_id}


@router.post("/refine-csv/{task_id}")
async def refine_csv(
    task_id:          str,
    background_tasks: BackgroundTasks,
    prompt:           str = Form(...),
):
    """
    Apply a new prompt to the CURRENT processed output of an existing task.
    This is iterative — each refinement builds on the previous result.

    Returns a new task_id for the refinement task.
    Client polls GET /process-csv-progress/{new_task_id}.
    """
    if not prompt.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Refinement prompt must not be empty."},
        )

    # Retrieve the source task
    source_task = csv_tasks.get(task_id)
    if not source_task:
        return JSONResponse(
            status_code=404,
            content={"error": "Source task not found."},
        )

    if source_task.get("running"):
        return JSONResponse(
            status_code=409,
            content={"error": "Source task is still running. Wait for it to complete."},
        )

    if source_task.get("error"):
        return JSONResponse(
            status_code=400,
            content={"error": "Cannot refine a task that ended in error."},
        )

    source_file = source_task.get("file_path")
    if not source_file or not os.path.exists(source_file):
        return JSONResponse(
            status_code=404,
            content={"error": "Source output file not found on disk."},
        )

    # Read the current output as bytes to pass to the new task
    with open(source_file, "rb") as fh:
        csv_bytes = fh.read()

    new_task_id = str(uuid.uuid4())
    logger.info(
        f"[/refine-csv/] New refinement task {new_task_id} "
        f"from source {task_id}, prompt_len={len(prompt)}"
    )

    csv_tasks[new_task_id] = {
        "running":          False,
        "error":            None,
        "file_path":        None,
        "row_count":        0,
        "columns":          [],
        "preview_rows":     [],
        "started_at":       time.time(),
        "original_task_id": task_id,   # track refinement chain
    }

    background_tasks.add_task(
        _run_csv_task,
        new_task_id,
        csv_bytes,
        prompt.strip(),
        task_id,
    )

    return {"task_id": new_task_id}


@router.get("/process-csv-progress/{task_id}")
async def process_csv_progress(task_id: str):
    """
    Poll endpoint for CSV processing and refinement tasks.

    Returns:
      running          bool
      error            str | null
      ready            bool   — True once the output file is available
      row_count        int
      columns          list[str]
      preview_rows     list[dict] — first 50 rows for the preview table
      runtime_seconds  int
      original_task_id str | null
    """
    task = csv_tasks.get(task_id)
    if not task:
        return JSONResponse(
            status_code=404,
            content={"error": "Task not found."},
        )

    runtime = int(time.time() - task.get("started_at", time.time()))

    return {
        "running":          task["running"],
        "error":            task["error"],
        "ready":            task["file_path"] is not None,
        "row_count":        task["row_count"],
        "columns":          task["columns"],
        "preview_rows":     task["preview_rows"],
        "runtime_seconds":  runtime,
        "original_task_id": task["original_task_id"],
    }


@router.get("/download-processed-csv/{task_id}")
def download_processed_csv(task_id: str):
    """
    Stream the processed CSV to the browser.
    Only available once the task is complete and ready.
    """
    task = csv_tasks.get(task_id)

    if not task:
        return JSONResponse(
            status_code=404,
            content={"error": "Task not found."},
        )
    if task.get("error"):
        return JSONResponse(
            status_code=500,
            content={"error": task["error"]},
        )
    if not task.get("file_path"):
        return JSONResponse(
            status_code=202,
            content={"error": "File not ready yet. Keep polling."},
        )

    file_path = task["file_path"]
    if not os.path.exists(file_path):
        logger.error(f"[/download-processed-csv/] File missing: {file_path}")
        return JSONResponse(
            status_code=404,
            content={"error": "Output file not found on disk."},
        )

    logger.info(f"[/download-processed-csv/] Serving {file_path} for task {task_id}")
    return FileResponse(
        path=file_path,
        filename=f"processed_{task_id}.csv",
        media_type="text/csv",
    )