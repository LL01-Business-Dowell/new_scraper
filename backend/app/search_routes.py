from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import uuid
import datetime
import logging
import os
import json
import re
import requests
import traceback

logger = logging.getLogger(__name__)
router = APIRouter()


search_tasks: dict = {}

# ---------------------------------------------------------------------------
# External service configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FOLDER = os.path.join(BASE_DIR, "data", "countries")
INSCRIBER_URL = os.getenv("INSCRIBER_URL", "http://inscriber:8002/api/geo-query-cube/")

# ---------------------------------------------------------------------------
# Datacube configuration — for saving search inputs
# ---------------------------------------------------------------------------
CRUD_BASE_URL = os.getenv("CRUD_BASE_URL", "https://datacube.uxlivinglab.online/api/v2")
CRUD_API_KEY = os.getenv("CRUD_API_KEY", "")
SWOT_DATABASE_ID = os.getenv("SWOT_DATABASE_ID", "")
SEARCH_INPUT_COLLECTION = os.getenv("SEARCH_INPUT_COLLECTION", "search_inputs")

CRUD_ENDPOINT = f"{CRUD_BASE_URL.rstrip('/')}/crud"
CRUD_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Api-Key {CRUD_API_KEY}",
}


def _save_search_input(
    task_id, keyword, report_type, city, country, radius_km, place_name
):
    """Save search input to Datacube. Never raises — failures are logged only."""
    if not CRUD_API_KEY or not SWOT_DATABASE_ID:
        logger.warning("[SEARCH] Datacube credentials not set — skipping save.")
        return
    payload = {
        "database_id": SWOT_DATABASE_ID,
        "collection_name": SEARCH_INPUT_COLLECTION,
        "documents": [
            {
                "task_id": task_id,
                "keyword": keyword,
                "report_type": report_type,
                "city": city,
                "country": country,
                "radius_km": radius_km,
                "place_name": place_name or "",
                "created_at": datetime.datetime.utcnow().isoformat() + "Z",
            }
        ],
    }
    try:
        resp = requests.post(
            CRUD_ENDPOINT, json=payload, headers=CRUD_HEADERS, timeout=10
        )
        if resp.status_code in (200, 201):
            logger.info(
                f"[SEARCH] Input saved — task_id={task_id} keyword={keyword} city={city}"
            )
        else:
            logger.warning(
                f"[SEARCH] Datacube save failed {resp.status_code}: {resp.text[:200]}"
            )
    except requests.RequestException as exc:
        logger.error(f"[SEARCH] Datacube save error: {exc}")



try:
    from .gemini_rotator import gemini_rotator

    GEMINI_AVAILABLE = True
    logger.info("search_routes: gemini_rotator imported successfully")
except Exception as exc:
    logger.warning(f"search_routes: could not import gemini_rotator — {exc}")
    GEMINI_AVAILABLE = False
    gemini_rotator = None



KEYWORDS: List[str] = [
    "Cafes",
    "Restaurants",
    "Hospitals",
    "Hotels",
    "Directors of Surgical Services",
    "VPs at MNCs",
    "Schools",
    "Pharmacies",
    "Banks",
    "Gyms",
]



def _extract_place_name_from_url(url: str) -> Optional[str]:
    if not url or not url.strip():
        return None

    url = url.strip()

    # Validate it looks like a Google Maps URL
    if not any(
        domain in url
        for domain in ["google.com/maps", "maps.app.goo.gl", "goo.gl/maps"]
    ):
        logger.warning(f"_extract_place_name: not a recognised Maps URL: '{url[:80]}'")
        return None

    logger.info(f"_extract_place_name: fetching URL '{url[:100]}'")

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        logger.info(
            f"_extract_place_name: HTTP {resp.status_code} "
            f"final_url='{resp.url[:100]}' "
            f"content_length={len(resp.text)}"
        )

        if resp.status_code != 200:
            logger.warning(f"_extract_place_name: non-200 response {resp.status_code}")
            return None

        html = resp.text
        logger.info(
            f"_extract_place_name: HTML snippet (first 500): " f"'{html[:500]}'"
        )

        # Strategy 1: parse <title> tag
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            raw_title = title_match.group(1).strip()
            logger.info(f"_extract_place_name: raw <title> = '{raw_title}'")

            for suffix in [
                " - Google Maps",
                " \u2013 Google Maps",
                " | Google Maps",
                " - Google Karte",
                " - \u041a\u0430\u0440\u0442\u044b Google",
            ]:
                if suffix in raw_title:
                    raw_title = raw_title[: raw_title.index(suffix)].strip()
                    break

            cleaned = re.sub(r",\s+[A-Z][^,]{2,30}$", "", raw_title).strip()
            logger.info(f"_extract_place_name: after cleaning = '{cleaned}'")

            if cleaned and len(cleaned) > 2:
                logger.info(f"_extract_place_name: SUCCESS via title = '{cleaned}'")
                return cleaned
        else:
            logger.warning("_extract_place_name: no <title> tag found in HTML")

        # Strategy 2: parse place name from the final redirected URL
        place_match = re.search(r"/maps/place/([^/@?]+)", resp.url)
        if place_match:
            raw = place_match.group(1)
            name = requests.utils.unquote_plus(raw).strip()
            logger.info(f"_extract_place_name: SUCCESS via URL path = '{name}'")
            if name and len(name) > 2:
                return name
        else:
            logger.warning(
                f"_extract_place_name: no /maps/place/ pattern in "
                f"final URL '{resp.url[:100]}'"
            )

        logger.warning("_extract_place_name: both strategies failed — returning None")
        return None

    except requests.RequestException as exc:
        logger.error(f"_extract_place_name: network error — {exc}")
        return None
    except Exception:
        logger.error(
            f"_extract_place_name: unexpected error — {traceback.format_exc()}"
        )
        return None

REPORT_TYPES: List[dict] = [
    {
        "id": "swot",
        "label": "SWOT Analysis - Based on City",
        "requires_place": True,  # show the establishment name input in frontend
        "description": (
            "Strengths, Weaknesses, Opportunities and Threats analysis "
            "for each geographic quadrant. Optionally compare against your "
            "own establishment by pasting its Google Maps URL."
        ),
        "prompt_template": (
            "You are a senior business intelligence analyst specialising in "
            "urban markets and the food and beverage industry in {country}.\n\n"
            "TASK\n"
            "----\n"
            "Produce a SWOT analysis for {keyword} in the {quadrant_name} quadrant "
            "of {city}, {country} (radius: {radius_km} km).\n\n"
            "THE EXACT COORDINATES IN THIS QUADRANT ARE:\n"
            "{coord_str}\n\n"
            "CRITICAL: You MUST identify the real neighbourhood names that correspond "
            "to these specific coordinates. Do NOT default to Connaught Place or any "
            "central area unless the coordinates actually place you there. "
            "The coordinates span different parts of {city} — use them to name the "
            "correct localities (e.g. for North: Kamla Nagar, GTB Nagar, Civil Lines; "
            "for South: Lajpat Nagar, Saket, Kalkaji; "
            "for East: Laxmi Nagar, Preet Vihar, Mayur Vihar; "
            "for West: Rajouri Garden, Janakpuri, Dwarka). "
            "Match coordinates to actual neighbourhoods before writing.\n\n"
            "{place_section}"
            "RULES\n"
            "-----\n"
            "1. Name actual localities for the given coordinates — not generic Delhi areas.\n"
            "2. Each SWOT category: exactly 3 numbered points, specific to this quadrant.\n"
            "3. Do NOT use phrases like 'based on Google Reviews'.\n"
            "4. Quadrant name in section field must be exactly: {quadrant_name}.\n"
            "5. Return EXACTLY ONE result object.\n\n"
            "CONTENT FORMAT (plain text inside the content field):\n\n"
            "STRENGTHS\n1. ...\n2. ...\n3. ...\n\n"
            "WEAKNESSES\n1. ...\n2. ...\n3. ...\n\n"
            "OPPORTUNITIES\n1. ...\n2. ...\n3. ...\n\n"
            "THREATS\n1. ...\n2. ...\n3. ...\n\n"
            "{comparison_section}"
            "section field: '{quadrant_name} Quadrant — <actual area names from coordinates>'"
        ),
    },
    {
        "id": "competitive_swot",
        "label": "Competitive SWOT Analysis - Based on Nearby Competitors",
        "requires_place": True,  # establishment name is required for this type
        "description": (
            "Analyses your specific establishment against approximately 100 "
            "competitors within the selected radius. Paste your Google Maps URL "
            "to identify your business. No coordinate grid used — Gemini reasons "
            "about the full competitive landscape in the area."
        ),
        # This template uses {place_name}, {keyword}, {city}, {country}, {radius_km}.
        # {quadrant_name} and {coord_str} are NOT used — this type skips the inscriber.
        "prompt_template": (
            "You are a senior competitive intelligence analyst specialising in "
            "the food and beverage industry in {country}.\n\n"
            "TASK\n"
            "----\n"
            "Conduct a comprehensive Competitive SWOT Analysis for "
            "'{place_name}' — a {keyword} located in {city}, {country}.\n\n"
            "COMPETITIVE CONTEXT\n"
            "-------------------\n"
            "The analysis must benchmark '{place_name}' against approximately "
            "100 {keyword} operating within a {radius_km} km radius of its location.\n\n"
            "Draw on your trained knowledge of:\n"
            "- The specific neighbourhood where '{place_name}' operates and its "
            "  immediate competitive environment\n"
            "- Known competitors in the same area — name actual establishments "
            "  if you are confident they exist\n"
            "- Relative positioning: pricing, ambiance, target demographic, "
            "  menu differentiation, brand strength\n"
            "- Area demographics: who lives, works, and passes through the zone\n"
            "- Macro trends affecting {keyword} in {city} (delivery culture, "
            "  premiumisation, health trends, co-working demand, etc.)\n\n"
            "STRICT RULES\n"
            "------------\n"
            "1. The analysis must specifically reference '{place_name}' throughout — "
            "   this is not a generic area analysis, it is about this specific business.\n"
            "2. Compare '{place_name}' directly to its competitors — where does it "
            "   lead, where does it lag, what gaps can it exploit.\n"
            "3. Do NOT fabricate specific review counts or financial data.\n"
            "4. Name real competitor establishments only if you are confident they exist.\n"
            "5. Each SWOT category must have exactly 4 numbered, specific points.\n"
            "6. Return EXACTLY ONE result object.\n\n"
            "CONTENT FORMAT\n"
            "--------------\n"
            "The content field must follow this exact plain-text structure:\n\n"
            "COMPETITIVE POSITION\n"
            "Brief 2-3 sentence summary of where '{place_name}' stands in the "
            "{radius_km} km competitive landscape.\n\n"
            "STRENGTHS\n"
            "1. [competitive strength of '{place_name}']\n"
            "2. [competitive strength]\n"
            "3. [competitive strength]\n"
            "4. [competitive strength]\n\n"
            "WEAKNESSES\n"
            "1. [competitive weakness of '{place_name}']\n"
            "2. [competitive weakness]\n"
            "3. [competitive weakness]\n"
            "4. [competitive weakness]\n\n"
            "OPPORTUNITIES\n"
            "1. [market opportunity for '{place_name}']\n"
            "2. [opportunity]\n"
            "3. [opportunity]\n"
            "4. [opportunity]\n\n"
            "THREATS\n"
            "1. [competitive threat to '{place_name}']\n"
            "2. [threat]\n"
            "3. [threat]\n"
            "4. [threat]\n\n"
            "KEY RECOMMENDATIONS\n"
            "1. [actionable recommendation for '{place_name}']\n"
            "2. [recommendation]\n"
            "3. [recommendation]\n\n"
            "The section field must be: "
            '"Competitive Analysis — {place_name} vs {keyword} in {city} '
            '({radius_km} km radius)"'
        ),
    },
]

# Build a lookup dict for fast access by id
_REPORT_TYPE_BY_ID = {rt["id"]: rt for rt in REPORT_TYPES}


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """
    Parameters sent from the frontend when the user clicks Start Search.

    keyword     : chosen from the KEYWORDS list
    report_type : id string matching one of the REPORT_TYPES entries
    city        : selected city name
    country     : selected country name
    radius_km   : search radius in kilometres
    place_name  : optional name of the user's own establishment typed directly.
                  Required for competitive_swot, optional for swot.
                  Gemini uses the name + city to identify and analyse the business.
    """

    keyword: str
    report_type: str
    city: str
    country: str
    radius_km: float = 5.0
    place_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: resolve city coordinates
# ---------------------------------------------------------------------------


def _get_city_coordinates(country: str, city: str) -> Optional[tuple]:
    try:
        country_files = {
            f.lower(): f for f in os.listdir(JSON_FOLDER) if f.endswith(".json")
        }
        filename = country.lower() + ".json"

        if filename not in country_files:
            logger.warning(f"Country file not found: {filename}")
            return None

        filepath = os.path.join(JSON_FOLDER, country_files[filename])
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        for entry in data:
            if entry.get("ASCII Name", "").lower() == city.lower():
                lat = float(entry.get("latitude"))
                lon = float(entry.get("longitude"))
                logger.info(
                    f"Resolved coordinates for {city}, {country}: ({lat}, {lon})"
                )
                return (lat, lon)

        logger.warning(f"City '{city}' not found in {filename}")
        return None

    except Exception:
        logger.error(f"Error resolving city coordinates: {traceback.format_exc()}")
        return None


def _calculate_bounds(radius_km: float) -> tuple:
    """
    Return the four corners of the bounding box as (lat, lon) offsets from
    the origin (0, 0).  The inscriber adds these to city-center coordinates
    to produce absolute tile positions.

    t = degrees per km (approximate at mid-latitudes)
    """
    t = 0.008993216059187
    d = float(radius_km)
    top_left = (d * t, -d * t)
    top_right = (d * t, d * t)
    bottom_left = (-d * t, -d * t)
    bottom_right = (-d * t, d * t)
    logger.debug(
        f"Bounds for radius {d} km: "
        f"TL={top_left} TR={top_right} BL={bottom_left} BR={bottom_right}"
    )
    return (top_left, top_right, bottom_left, bottom_right)



def _fetch_tiles(bounds: tuple) -> List[tuple]:
    """
    POST the bounding box to the inscriber service and return a flat list of
    (lat_offset, lon_offset) tuples.

    The inscriber wraps its response as:
        {"result": {"raw_coordinates": [[{"latitude": x, "longitude": y}]]}}
    This function unwraps all known response shapes.
    """
    payload = {
        "top_left": list(bounds[0]),
        "top_right": list(bounds[1]),
        "bottom_left": list(bounds[2]),
        "bottom_right": list(bounds[3]),
    }
    logger.info(f"Inscriber request payload: {payload}")

    try:
        resp = requests.post(INSCRIBER_URL, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Inscriber HTTP status: {resp.status_code}")

        # Unwrap {"result": {...}} envelope if present
        if isinstance(data, dict) and "result" in data:
            data = data["result"]

        # Flat list format
        if isinstance(data, list):
            tiles = [(float(p[0]), float(p[1])) for p in data]
            logger.info(f"Inscriber returned {len(tiles)} tiles (list format)")
            return tiles

        # Nested raw_coordinates dict format
        if isinstance(data, dict) and "raw_coordinates" in data:
            flat = []
            for block in data["raw_coordinates"]:
                items = [block] if isinstance(block, dict) else block
                for item in items:
                    if isinstance(item, dict):
                        lat = item.get("latitude")
                        lon = item.get("longitude")
                    elif isinstance(item, (list, tuple)) and len(item) >= 2:
                        lat, lon = item[0], item[1]
                    else:
                        continue
                    if lat is not None and lon is not None:
                        flat.append((float(lat), float(lon)))
            logger.info(
                f"Inscriber returned {len(flat)} tiles (raw_coordinates format)"
            )
            return flat

        logger.warning(f"Unrecognised inscriber response shape: {str(data)[:300]}")
        return []

    except Exception:
        logger.error(f"Inscriber fetch failed: {traceback.format_exc()}")
        return []


def _build_target_coords(center: tuple, tiles: List[tuple]) -> List[tuple]:
    """
    Add each tile offset (from the inscriber) to the city center to produce
    absolute (latitude, longitude) coordinates covering the search area.

    Falls back to just the city center if the inscriber returned no tiles,
    ensuring at least one coordinate is always available.
    """
    if not tiles:
        logger.warning("No tiles received from inscriber — using city center only")
        return [center]
    targets = [(center[0] + d_lat, center[1] + d_lon) for d_lat, d_lon in tiles]
    logger.info(
        f"Built {len(targets)} absolute coordinates from center + {len(tiles)} tiles"
    )
    return targets


# ---------------------------------------------------------------------------
# Helper: split coordinates into geographic quadrants
# ---------------------------------------------------------------------------


def _split_into_quadrants(
    coords: List[tuple],
    center: tuple,
) -> dict[str, List[tuple]]:
    if not coords:
        return {"North": [], "South": [], "East": [], "West": []}

    lats = [p[0] for p in coords]
    lons = [p[1] for p in coords]

    cy = sum(lats) / len(lats)  # mean latitude  (North/South boundary)
    cx = sum(lons) / len(lons)  # mean longitude (East/West boundary)

    logger.info(
        f"Quadrant split center: cy={cy:.6f}, cx={cx:.6f} "
        f"(city center: {center[0]:.6f}, {center[1]:.6f})"
    )

    quadrants: dict[str, List[tuple]] = {
        "North": [],
        "South": [],
        "East": [],
        "West": [],
    }

    for lat, lon in coords:
        dx = lon - cx  # East is positive, West is negative
        dy = lat - cy  # North is positive, South is negative

        if abs(dx) > abs(dy):
            # Point is closer to the E/W axis — longitude dominates
            quadrants["East" if dx > 0 else "West"].append((lat, lon))
        else:
            # Point is closer to the N/S axis — latitude dominates
            # Ties (dx == dy) go to North/South, matching the original code
            quadrants["North" if dy > 0 else "South"].append((lat, lon))

    for name, pts in quadrants.items():
        logger.info(f"Quadrant {name}: {len(pts)} coordinates")

    return quadrants


# ---------------------------------------------------------------------------
# Helper: build the Gemini prompt for a quadrant
# ---------------------------------------------------------------------------


def _build_gemini_prompt(
    report_type_id: str,
    keyword: str,
    city: str,
    country: str,
    radius_km: float,
    quadrant_name: str = "",
    coord_batch: List[tuple] = None,
    place_name: Optional[str] = None,
) -> str:
    rt = _REPORT_TYPE_BY_ID.get(report_type_id)
    if not rt:
        raise ValueError(f"Unknown report_type_id: '{report_type_id}'")

    coord_str = (
        ", ".join(f"({lat:.5f}, {lon:.5f})" for lat, lon in (coord_batch or []))
        or "(no coordinates)"
    )


    if place_name:
        place_section = (
            f"USER'S ESTABLISHMENT\n"
            f"--------------------\n"
            f"The user owns or manages: '{place_name}'\n"
            f"This is their specific {keyword} in {city}.\n"
            f"Where relevant, compare the quadrant's general market landscape "
            f"to the specific position of '{place_name}' within it.\n\n"
        )
        comparison_section = (
            f"YOUR CAFE — {place_name.upper()}\n"
            f"How '{place_name}' specifically relates to this quadrant's SWOT:\n"
            f"1. [how this quadrant's strengths/weaknesses apply to '{place_name}']\n"
            f"2. [specific opportunity or threat for '{place_name}' in this area]\n\n"
        )
    else:
        place_section = ""
        comparison_section = ""

    # ── Fill the template ─────────────────────────────────────────────────────
    user_part = rt["prompt_template"].format(
        keyword=keyword,
        city=city,
        country=country,
        radius_km=radius_km,
        quadrant_name=quadrant_name,
        coord_str=coord_str,
        place_name=place_name or "your establishment",
        place_section=place_section,
        comparison_section=comparison_section,
    )


    json_instruction = (
        "\n\n"
        "JSON OUTPUT CONTRACT — THIS OVERRIDES ALL OTHER INSTRUCTIONS\n"
        "-------------------------------------------------------------\n"
        "Return ONLY a valid JSON object. No text before or after it.\n"
        "First character must be { and last must be }.\n"
        "\n"
        "{\n"
        '  "view_type": "report",\n'
        '  "results": [\n'
        "    {\n"
        '      "section": "string — as described in the prompt above",\n'
        '      "content": "string — full analysis following the content format above"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "\n"
        "CRITICAL RULES:\n"
        "1. results must contain EXACTLY ONE object.\n"
        "2. content must be a plain string — NEVER a nested object or array.\n"
        "3. All newlines inside content must be literal \\n characters in the JSON.\n"
        "4. Do not wrap the JSON in markdown code fences.\n"
        '5. view_type must always be "report".\n'
    )

    return user_part + json_instruction


# ---------------------------------------------------------------------------
# Helper: call Gemini and parse the response
# ---------------------------------------------------------------------------


def _call_gemini_and_parse(prompt_text: str, batch_number: int) -> dict:
    result: dict = {
        "batch_number": batch_number,
        "items": [],
        "view_type": "report",
        "char_count": 0,
        "status": "pending",
        "error": None,
    }

    # Mock mode — returns placeholder data when no Gemini key is configured
    if not GEMINI_AVAILABLE:
        logger.warning(
            f"Gemini unavailable — returning mock data for batch {batch_number}"
        )
        result["items"] = [
            {"name": f"Mock {batch_number}-{i}", "info": "No key"} for i in range(2)
        ]
        result["status"] = "mock"
        return result

    # Call Gemini via the key + model rotator
    try:
        raw = gemini_rotator.call(prompt_text, temperature=0.0)
        result["char_count"] = len(raw)
        logger.info(f"Gemini batch {batch_number}: received {len(raw)} chars")
    except RuntimeError as exc:
        logger.error(f"Gemini rotator failed for batch {batch_number}: {exc}")
        result["status"] = "error"
        result["error"] = str(exc)
        return result

    # Parse JSON from the response
    try:
        text = raw

        # Strip markdown code fences if Gemini added them
        if "```" in text:
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else parts[0]
            text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE).strip()

        # Extract outermost JSON object { … }
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:
            # Fallback: try plain array [ … ] for backward compatibility
            start = text.find("[")
            end = text.rfind("]")
            if start == -1 or end == -1:
                logger.warning(f"Batch {batch_number}: no JSON found in response")
                result["status"] = "parse_error"
                result["error"] = "No JSON found in Gemini response"
                return result
            parsed_array = json.loads(text[start : end + 1])
            result["items"] = parsed_array if isinstance(parsed_array, list) else []
            result["view_type"] = "table"
            result["status"] = "done"
            logger.info(
                f"Batch {batch_number}: parsed {len(result['items'])} items "
                "(plain array fallback)"
            )
            return result

        envelope = json.loads(text[start : end + 1])

        # Handle both {"view_type":…, "results":[…]} and plain list responses
        if isinstance(envelope, list):
            result["items"] = envelope
            result["view_type"] = "table"
        else:
            result["view_type"] = envelope.get("view_type", "report")
            items = envelope.get("results", envelope.get("data", []))
            result["items"] = items if isinstance(items, list) else []

        # Flatten any nested-object values to strings so React can render them
        flattened = []
        for item in result["items"]:
            flat_item = {}
            for k, v in item.items():
                if isinstance(v, (dict, list)):
                    try:
                        flat_item[k] = json.dumps(v, ensure_ascii=False)
                    except Exception:
                        flat_item[k] = str(v)
                else:
                    flat_item[k] = v
            flattened.append(flat_item)
        result["items"] = flattened

        result["status"] = "done"
        logger.info(
            f"Batch {batch_number}: parsed {len(result['items'])} items, "
            f"view_type={result['view_type']}"
        )

    except json.JSONDecodeError as exc:
        result["status"] = "parse_error"
        result["error"] = f"JSON parse error: {exc}"
        logger.error(f"Batch {batch_number}: JSON parse failed — {exc}")

    return result


# ---------------------------------------------------------------------------
# Background task: orchestrates the full search pipeline
# ---------------------------------------------------------------------------


def _build_cafe_swot_prompt(
    place_name: str,
    keyword: str,
    city: str,
    country: str,
    radius_km: float,
    quadrants: dict,
    center: tuple,
) -> str:
    quadrant_ranges = []
    for qname, pts in quadrants.items():
        if not pts:
            continue
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        quadrant_ranges.append(
            f"  {qname}: lat {min(lats):.4f}–{max(lats):.4f}, "
            f"lon {min(lons):.4f}–{max(lons):.4f}"
        )
    ranges_str = "\n".join(quadrant_ranges)

    prompt = (
        f"You are a senior business intelligence analyst specialising in "
        f"the food and beverage industry in {country}.\n\n"
        f"TASK\n"
        f"----\n"
        f"Produce a focused SWOT analysis specifically for '{place_name}', "
        f"a {keyword} in {city}, {country}.\n\n"
        f"STEP 1 — IDENTIFY THE QUADRANT\n"
        f"--------------------------------\n"
        f"The search area is divided into four quadrants based on these "
        f"coordinate ranges (centre: {center[0]:.4f}, {center[1]:.4f}):\n"
        f"{ranges_str}\n\n"
        f"Use your knowledge of where '{place_name}' is located in {city} "
        f"to determine which quadrant it falls in. State the quadrant clearly "
        f"in the section field.\n\n"
        f"STEP 2 — WRITE THE SWOT\n"
        f"------------------------\n"
        f"Write a SWOT analysis FOR '{place_name}' specifically:\n"
        f"- Strengths: what does '{place_name}' do well? "
        f"  Consider its location, reputation, format, and niche.\n"
        f"- Weaknesses: where is '{place_name}' vulnerable? "
        f"  Consider its specific location disadvantages, gaps, or constraints.\n"
        f"- Opportunities: what market opportunities exist for '{place_name}' "
        f"  given its location and the {keyword} landscape in {city}?\n"
        f"- Threats: what competitive or external threats face '{place_name}' "
        f"  specifically in its neighbourhood and the {radius_km} km radius?\n\n"
        f"RULES\n"
        f"-----\n"
        f"1. Every point must reference '{place_name}' or its specific location.\n"
        f"2. 3 numbered points per SWOT category.\n"
        f"3. Do NOT use 'based on Google Reviews'.\n"
        f"4. Return EXACTLY ONE result object.\n\n"
        f"CONTENT FORMAT:\n\n"
        f"YOUR CAFE: {place_name.upper()}\n\n"
        f"STRENGTHS\n1. ...\n2. ...\n3. ...\n\n"
        f"WEAKNESSES\n1. ...\n2. ...\n3. ...\n\n"
        f"OPPORTUNITIES\n1. ...\n2. ...\n3. ...\n\n"
        f"THREATS\n1. ...\n2. ...\n3. ...\n\n"
        f"section field must be: "
        f"'Your Cafe — {place_name} (<Quadrant> Quadrant, {city})'\n\n"
        "JSON OUTPUT CONTRACT\n"
        "--------------------\n"
        "Return ONLY a valid JSON object:\n"
        "{\n"
        '  "view_type": "report",\n'
        '  "results": [\n'
        '    { "section": "Your Cafe — <name> (<Quadrant> Quadrant, <city>)",\n'
        '      "content": "YOUR CAFE: ...\\nSTRENGTHS\\n1. ..." }\n'
        "  ]\n"
        "}\n"
        "content must be a plain string. First char must be {, last must be }.\n"
    )
    return prompt


def _run_search_task(
    task_id: str,
    keyword: str,
    report_type: str,
    city: str,
    country: str,
    radius_km: float,
    place_name: Optional[str] = None,
):
    task = search_tasks[task_id]

    try:
        if report_type == "competitive_swot":
            logger.info(f"[SEARCH {task_id}] Competitive SWOT — skipping inscriber")
            task["status_message"] = f"Analysing {place_name} vs competitors..."
            task["total_batches"] = 1
            task["current_batch"] = 1

            try:
                full_prompt = _build_gemini_prompt(
                    report_type_id=report_type,
                    keyword=keyword,
                    city=city,
                    country=country,
                    radius_km=radius_km,
                    place_name=place_name,
                )
            except ValueError as exc:
                task["error"] = str(exc)
                task["running"] = False
                return

            batch_result = _call_gemini_and_parse(full_prompt, 1)
            task["results"] = batch_result.get("items", [])
            task["view_type"] = batch_result.get("view_type", "report")
            task["progress"] = 100

            logger.info(
                f"[SEARCH {task_id}] Competitive SWOT done — "
                f"{len(task['results'])} items, status={batch_result['status']}"
            )
            return  

        # ── Step 1: city coordinates ──────────────────────────────────────────
        logger.info(f"[SEARCH {task_id}] Step 1: resolving city coordinates")
        task["status_message"] = "Resolving city coordinates..."

        center = _get_city_coordinates(country, city)
        if not center:
            task["error"] = f"Could not find coordinates for {city}, {country}"
            task["running"] = False
            task["status_message"] = "Error"
            logger.error(f"[SEARCH {task_id}] {task['error']}")
            return

        task["center"] = list(center)

        # ── Step 2: inscriber tiles ───────────────────────────────────────────
        logger.info(f"[SEARCH {task_id}] Step 2: fetching tiles from inscriber")
        task["status_message"] = "Fetching coordinate tiles..."

        bounds = _calculate_bounds(radius_km)
        tiles = _fetch_tiles(bounds)

        if not tiles:
            logger.warning(
                f"[SEARCH {task_id}] Inscriber returned no tiles — "
                "using city center only"
            )

        # ── Step 3: absolute coordinates ──────────────────────────────────────
        logger.info(f"[SEARCH {task_id}] Step 3: building target coordinates")
        task["status_message"] = "Building search coordinates..."

        all_coords = _build_target_coords(center, tiles)

        # Deduplicate to the nearest 6 decimal places
        seen = set()
        unique_coords = []
        for lat, lon in all_coords:
            key = (round(lat, 6), round(lon, 6))
            if key not in seen:
                seen.add(key)
                unique_coords.append((lat, lon))

        logger.info(f"[SEARCH {task_id}] Unique coordinates: {len(unique_coords)}")
        task["total_coordinates"] = len(unique_coords)

        # ── Step 4: split into quadrants ──────────────────────────────────────
        logger.info(f"[SEARCH {task_id}] Step 4: splitting into quadrants")
        task["status_message"] = "Splitting coordinates into quadrants..."

        quadrants = _split_into_quadrants(unique_coords, center)

        # Only process quadrants that have at least one coordinate
        active_quadrants = [
            (name, coords) for name, coords in quadrants.items() if coords
        ]

        total_quadrants = len(active_quadrants)
        task["total_batches"] = total_quadrants
        task["quadrant_summary"] = {
            name: len(coords) for name, coords in quadrants.items()
        }
        logger.info(
            f"[SEARCH {task_id}] Active quadrants: {total_quadrants} "
            f"({', '.join(f'{n}={len(c)}' for n, c in active_quadrants)})"
        )

        # ── Step 5: call Gemini per quadrant ──────────────────────────────────
        all_items: List[dict] = []

        for q_idx, (quadrant_name, coord_batch) in enumerate(active_quadrants):
            if not search_tasks.get(task_id, {}).get("running", False):
                logger.info(f"[SEARCH {task_id}] Cancelled at quadrant {quadrant_name}")
                break

            batch_num = q_idx + 1
            task["current_batch"] = batch_num
            task["status_message"] = (
                f"Generating {quadrant_name} report "
                f"({batch_num}/{total_quadrants})..."
            )
            logger.info(
                f"[SEARCH {task_id}] Quadrant {quadrant_name} "
                f"({batch_num}/{total_quadrants}) — {len(coord_batch)} coords"
            )

            # Build prompt — pass place_name so the comparison section is injected
            try:
                full_prompt = _build_gemini_prompt(
                    report_type_id=report_type,
                    keyword=keyword,
                    city=city,
                    country=country,
                    radius_km=radius_km,
                    quadrant_name=quadrant_name,
                    coord_batch=coord_batch,
                    place_name=place_name,
                )
            except ValueError as exc:
                task["error"] = str(exc)
                task["running"] = False
                return

            batch_result = _call_gemini_and_parse(full_prompt, batch_num)

            # Deduplicate by content fingerprint across quadrants
            existing_fps = {
                frozenset(str(v).lower().strip() for v in item.values() if v)
                for item in all_items
            }
            new_items = [
                item
                for item in batch_result.get("items", [])
                if (
                    frozenset(str(v).lower().strip() for v in item.values() if v)
                    not in existing_fps
                    and any(item.values())
                )
            ]
            all_items.extend(new_items)

            # Store view_type from the first successful quadrant
            if not task.get("view_type") and batch_result.get("view_type"):
                task["view_type"] = batch_result["view_type"]

            # Update task for live frontend polling
            task["results"] = all_items
            task["progress"] = round((batch_num / total_quadrants) * 100, 1)

            logger.info(
                f"[SEARCH {task_id}] Quadrant {quadrant_name} done — "
                f"new={len(new_items)}, total={len(all_items)}, "
                f"view_type={batch_result.get('view_type', '?')}, "
                f"status={batch_result['status']}"
            )

        logger.info(
            f"[SEARCH {task_id}] All quadrants complete. "
            f"Total items: {len(all_items)}"
        )

        # ── Step 6: dedicated cafe SWOT (if place_name provided) ─────────────
        place_name_log = (
            f'"{place_name}"' if place_name else "None (skipping cafe SWOT)"
        )
        logger.info(f"[SEARCH {task_id}] Step 6 check: place_name={place_name_log}")
        if place_name:
            logger.info(
                f"[SEARCH {task_id}] Step 6: generating cafe SWOT for '{place_name}'"
            )
            task["status_message"] = f"Analysing {place_name}..."
            task["current_batch"] = total_quadrants + 1
            task["total_batches"] = total_quadrants + 1

            cafe_prompt = _build_cafe_swot_prompt(
                place_name=place_name,
                keyword=keyword,
                city=city,
                country=country,
                radius_km=radius_km,
                quadrants=quadrants,
                center=center,
            )
            cafe_result = _call_gemini_and_parse(cafe_prompt, total_quadrants + 1)

            if cafe_result.get("items"):
                # Prepend cafe card so it appears first in the frontend
                all_items = cafe_result["items"] + all_items
                task["results"] = all_items
                logger.info(
                    f"[SEARCH {task_id}] Cafe SWOT added — "
                    f"total items now {len(all_items)}"
                )
            else:
                logger.warning(
                    f"[SEARCH {task_id}] Cafe SWOT returned no items: "
                    f"{cafe_result.get('error')}"
                )

    except Exception:
        logger.error(f"[SEARCH {task_id}] Unexpected error: {traceback.format_exc()}")
        task["error"] = "An unexpected error occurred. Check server logs."

    finally:
        task["running"] = False
        task["progress"] = 100
        task["status_message"] = "Complete"
        task["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        logger.info(f"[SEARCH {task_id}] Task finished")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@router.get("/search-config")
async def get_search_config():
    report_type_options = []
    for rt in REPORT_TYPES:
        # Generate a preview with placeholder values.
        # competitive_swot doesn't use quadrant_name/coord_str — use empty strings.
        try:
            preview = rt["prompt_template"].format(
                keyword="<keyword>",
                city="<city>",
                country="<country>",
                radius_km="<radius>",
                quadrant_name="North",
                coord_str="(lat1, lon1), (lat2, lon2), ...",
                place_name="<your establishment>",
                place_section="[establishment context injected here]\n\n",
                comparison_section="[comparison section injected here]\n\n",
            )
        except KeyError:
            preview = rt["prompt_template"]

        report_type_options.append(
            {
                "id": rt["id"],
                "label": rt["label"],
                "description": rt["description"],
                "requires_place": rt.get("requires_place", False),
                "prompt_preview": preview,
            }
        )

    return {
        "keywords": KEYWORDS,
        "report_types": report_type_options,
    }


@router.post("/search/")
async def start_search(request: SearchRequest, background_tasks: BackgroundTasks):
    if not request.keyword.strip():
        return JSONResponse(status_code=400, content={"error": "keyword is required"})
    if not request.city.strip() or not request.country.strip():
        return JSONResponse(
            status_code=400, content={"error": "city and country are required"}
        )
    if request.report_type not in _REPORT_TYPE_BY_ID:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Unknown report_type '{request.report_type}'. "
                f"Valid options: {list(_REPORT_TYPE_BY_ID.keys())}"
            },
        )

    # competitive_swot requires a place name
    if (
        request.report_type == "competitive_swot"
        and not (request.place_name or "").strip()
    ):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Establishment name is required for Competitive SWOT Analysis."
            },
        )

    # Use place_name directly — user typed it, no extraction needed
    place_name: Optional[str] = (request.place_name or "").strip() or None
    logger.info(
        f"[SEARCH] place_name='{place_name or '(none)'}' "
        f"report_type={request.report_type}"
    )

    task_id = str(uuid.uuid4())

    _save_search_input(
        task_id     = task_id,
        keyword     = request.keyword,
        report_type = request.report_type,
        city        = request.city,
        country     = request.country,
        radius_km   = request.radius_km,
        place_name  = place_name,
    )

    search_tasks[task_id] = {
        "running": True,
        "progress": 0,
        "results": [],
        "view_type": None,
        "error": None,
        "status_message": "Starting...",
        "current_batch": 0,
        "total_batches": 0,
        "total_coordinates": 0,
        "quadrant_summary": {},
        "center": None,
        "keyword": request.keyword,
        "report_type": request.report_type,
        "place_name": place_name,
        "city": request.city,
        "country": request.country,
        "radius_km": request.radius_km,
        "started_at": datetime.datetime.utcnow().isoformat() + "Z",
    }

    background_tasks.add_task(
        _run_search_task,
        task_id,
        request.keyword,
        request.report_type,
        request.city,
        request.country,
        request.radius_km,
        place_name,
    )

    logger.info(
        f"[SEARCH] Task {task_id} queued — "
        f"keyword={request.keyword} report_type={request.report_type} "
        f"city={request.city} country={request.country} "
        f"radius={request.radius_km} km "
        f"place_name={place_name or '(none)'}"
    )
    return {"task_id": task_id, "place_name": place_name}


@router.get("/search-progress/{task_id}")
async def get_search_progress(task_id: str):
    """
    Poll this endpoint while the search is running.
    Returns live results as they accumulate so the frontend can
    show progressive updates without waiting for all quadrants.
    """
    task = search_tasks.get(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"error": "Task not found"})

    return {
        "running": task.get("running", False),
        "progress": task.get("progress", 0),
        "status_message": task.get("status_message", ""),
        "results": task.get("results", []),
        "view_type": task.get("view_type", "report"),
        "error": task.get("error"),
        "current_batch": task.get("current_batch", 0),
        "total_batches": task.get("total_batches", 0),
        "total_coordinates": task.get("total_coordinates", 0),
        "quadrant_summary": task.get("quadrant_summary", {}),
        "keyword": task.get("keyword", ""),
        "report_type": task.get("report_type", ""),
        "city": task.get("city", ""),
        "country": task.get("country", ""),
    }


@router.post("/cancel-search/{task_id}")
async def cancel_search(task_id: str):
    """
    Cancel a running search task.
    Sets running=False; the background thread checks this flag and stops
    after completing the current quadrant.
    """
    task = search_tasks.get(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    task["running"] = False
    logger.info(f"[SEARCH] Task {task_id} cancelled by user")
    return {"message": f"Task {task_id} cancelled"}
