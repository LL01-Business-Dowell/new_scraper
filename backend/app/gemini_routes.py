"""
gemini_routes.py  —  drop this file into backend/app/
then in main.py add:  from .gemini_routes import router as gemini_router
                      app.include_router(gemini_router)
"""

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
import json
import re
import uuid
import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── In-memory task store (shared with main.py tasks dict via import) ────────
# We keep a local store here so this file is self-contained.
# If you prefer, import `tasks` from main.py instead.
gemini_tasks: dict = {}

# ─── Gemini client ────────────────────────────────────────────────────────────
# Uses GEMINI_KEY_1 env var automatically — do NOT pass api_key= argument
try:
    from google import genai
    import os
    if not os.getenv("GEMINI_KEY_1"):
        raise Exception("GEMINI_KEY_1 environment variable not set")
    gemini_client = genai.Client()
    GEMINI_AVAILABLE = True
    logger.info("Gemini client initialised successfully")
except Exception as e:
    logger.warning(f"Gemini client init failed: {e}")
    GEMINI_AVAILABLE = False
    gemini_client = None


# ─── Pydantic models ──────────────────────────────────────────────────────────
class GenerateFromPromptsRequest(BaseModel):
    prompts: List[str]          # the 30 prompt strings from generate_prompts_task
    keyword: str
    city: str
    country: str
    results_per_call: int = 100  # how many businesses to request per Gemini call
    batch_size: int = 5          # how many prompts to combine into one Gemini call
                                 # 30 prompts / 5 = 6 Gemini calls  (well within 20/day)


# ─── Core Gemini function ─────────────────────────────────────────────────────
def call_gemini_batch(prompts_batch: List[str], keyword: str, city: str, country: str, results_per_call: int) -> List[dict]:
    """
    Combine multiple coordinate-based prompts into ONE Gemini API call.
    Asks for `results_per_call` businesses covering all coordinates in the batch.
    """

    # Build a compact location list from the prompts
    # Each prompt already contains lat/lon — we extract just the coordinate part
    location_hints = []
    for p in prompts_batch:
        # prompts look like: "find ... of 100 {keyword} in {lat} {lng}, {city}, {country} ..."
        match = re.search(r'in\s+([-\d.]+)\s+([-\d.]+),', p)
        if match:
            location_hints.append(f"({match.group(1)}, {match.group(2)})")

    locations_str = "\n".join(location_hints) if location_hints else f"{city}, {country}"

    prompt = f"""You are a professional healthcare executive research API with access to hospital directories, LinkedIn, and industry databases.

Find {results_per_call} individual people with the title or role of "{keyword}" working at hospitals, health systems, and medical centers in {city}, {country}.

Focus areas in this batch (coordinate zones within {city}):
{locations_str}

Return ONLY a JSON array. Each item represents ONE real individual person, not a hospital or department.

[
  {{
    "name": "Full Name (First Last)",
    "title": "Exact job title e.g. Director of Surgical Services",
    "hospital": "Hospital or health system name",
    "address": "Hospital street address, city, state, zip",
    "phone": "Direct or department phone number",
    "email": "Professional email address",
    "linkedin": "https://linkedin.com/in/their-profile",
    "website": "Hospital or department webpage URL"
  }}
]

Critical rules:
- Each result must be a NAMED INDIVIDUAL PERSON, not a hospital or department
- Use real names of actual people who hold or have held this role in {city}
- Include their specific hospital/health system affiliation
- Spread results across major hospital systems: NYU Langone, NewYork-Presbyterian, Mount Sinai, Northwell Health, NYC Health+Hospitals, Memorial Sloan Kettering, Hospital for Special Surgery, Montefiore, etc.
- If direct contact is not public, use the hospital's main switchboard number and format email as firstname.lastname@hospitaldomain.com
- Return ONLY the JSON array, no explanation, no markdown, no commentary
- No duplicate people
"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        text = response.text.strip()

        # Strip markdown code fences if present
        if "```" in text:
            parts = text.split("```")
            # take the content inside the first code block
            text = parts[1] if len(parts) > 1 else parts[0]
            text = re.sub(r'^json\s*', '', text, flags=re.IGNORECASE).strip()

        # Find JSON array boundaries
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            logger.warning("Gemini returned no JSON array")
            return []

        data = json.loads(text[start:end + 1])
        logger.info(f"Gemini batch returned {len(data)} results")

        # Normalise field names
        results = []
        for item in data:
            # Skip anything that looks like a hospital/org rather than a person
            name = item.get("name", "")
            if not name or any(word in name.lower() for word in [
                "hospital", "medical center", "health system", "clinic",
                "institute", "surgery center", "department", "services"
            ]):
                logger.warning(f"Skipping non-person result: {name}")
                continue
            results.append({
                "name":     name,
                "title":    item.get("title", ""),
                "hospital": item.get("hospital", ""),
                "address":  item.get("address", ""),
                "phone":    item.get("phone", ""),
                "email":    item.get("email", ""),
                "website":  item.get("website", ""),
                "linkedin": item.get("linkedin", ""),
                "city":     city,
                "country":  country,
            })
        return results

    except json.JSONDecodeError as e:
        logger.error(f"Gemini JSON parse error: {e}")
        return []
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return []


# ─── Background task ──────────────────────────────────────────────────────────
def run_gemini_task(task_id: str, prompts: List[str], keyword: str, city: str, country: str, results_per_call: int, batch_size: int):
    task = gemini_tasks[task_id]
    all_results = []
    total_batches = max(1, len(prompts) // batch_size + (1 if len(prompts) % batch_size else 0))
    completed_batches = 0

    logger.info(f"[GEMINI {task_id}] Starting: {len(prompts)} prompts → {total_batches} Gemini calls")

    try:
        # Split prompts into batches
        for i in range(0, len(prompts), batch_size):
            if not gemini_tasks.get(task_id, {}).get("running", False):
                logger.info(f"[GEMINI {task_id}] Cancelled")
                break

            batch = prompts[i:i + batch_size]
            logger.info(f"[GEMINI {task_id}] Batch {completed_batches + 1}/{total_batches} ({len(batch)} prompts)")

            if GEMINI_AVAILABLE:
                batch_results = call_gemini_batch(batch, keyword, city, country, results_per_call)
            else:
                # ── MOCK DATA for testing when Gemini key is not set ──────────
                batch_results = _mock_results(keyword, city, country, min(results_per_call, 10))

            all_results.extend(batch_results)
            completed_batches += 1

            # Deduplicate by name+address
            seen = set()
            deduped = []
            for r in all_results:
                key = (r["name"].lower().strip(), r["address"].lower().strip())
                if key not in seen and r["name"]:
                    seen.add(key)
                    deduped.append(r)
            all_results = deduped

            task["results"] = all_results
            task["progress"] = round((completed_batches / total_batches) * 100, 1)
            task["batch_info"] = f"Completed {completed_batches}/{total_batches} API calls"

            logger.info(f"[GEMINI {task_id}] Running total: {len(all_results)} unique results")

    except Exception as e:
        logger.error(f"[GEMINI {task_id}] Error: {e}")
        task["error"] = str(e)

    finally:
        task["running"] = False
        task["progress"] = 100
        task["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        logger.info(f"[GEMINI {task_id}] Done. Total results: {len(all_results)}")


def _mock_results(keyword: str, city: str, country: str, count: int) -> List[dict]:
    """Returns fake data when Gemini API key is not configured — for UI testing."""
    return [
        {
            "name":     f"{keyword} Business {i + 1}",
            "address":  f"{100 + i} Main Street, {city}",
            "phone":    f"+1-555-{str(i).zfill(3)}-0000",
            "email":    f"contact{i}@example.com",
            "website":  f"https://example{i}.com",
            "linkedin": f"https://linkedin.com/company/example{i}",
            "rating":   str(round(3.5 + (i % 3) * 0.5, 1)),
            "reviews":  str(10 + i * 7),
            "city":     city,
            "country":  country,
        }
        for i in range(count)
    ]


# ─── API endpoints ────────────────────────────────────────────────────────────

@router.post("/generate-from-prompts/")
async def generate_from_prompts(request: GenerateFromPromptsRequest, background_tasks: BackgroundTasks):
    """
    Accept a list of prompt strings, batch them, call Gemini, return task_id.
    Frontend polls /gemini-progress/{task_id} for results.
    """
    if not request.prompts:
        return JSONResponse(status_code=400, content={"error": "No prompts provided"})

    task_id = str(uuid.uuid4())
    gemini_tasks[task_id] = {
        "running": True,
        "progress": 0,
        "results": [],
        "error": None,
        "batch_info": "Starting...",
        "started_at": datetime.datetime.utcnow().isoformat() + "Z",
        "keyword": request.keyword,
        "city": request.city,
        "country": request.country,
    }

    background_tasks.add_task(
        run_gemini_task,
        task_id,
        request.prompts,
        request.keyword,
        request.city,
        request.country,
        request.results_per_call,
        request.batch_size,
    )

    logger.info(f"[GEMINI] Task {task_id} queued: {len(request.prompts)} prompts")
    return {"task_id": task_id}


@router.get("/gemini-progress/{task_id}")
async def gemini_progress(task_id: str):
    task = gemini_tasks.get(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"error": "Task not found"})

    return {
        "running":    task.get("running", False),
        "progress":   task.get("progress", 0),
        "results":    task.get("results", []),
        "error":      task.get("error"),
        "batch_info": task.get("batch_info", ""),
        "total":      len(task.get("results", [])),
        "keyword":    task.get("keyword", ""),
        "city":       task.get("city", ""),
        "country":    task.get("country", ""),
    }


@router.post("/cancel-gemini/{task_id}")
async def cancel_gemini(task_id: str):
    task = gemini_tasks.get(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    task["running"] = False
    return {"message": f"Task {task_id} cancelled"}