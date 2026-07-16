from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import StreamingResponse
import pandas as pd
import time
import threading
import re
from selenium_stealth import stealth
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
import os
import requests
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback
import logging
import datetime
import random
import requests
from .utils import calculate_boundary_points
import csv
import uuid
import logging
from threading import Thread
from fastapi import Form
from fastapi.responses import FileResponse
import io

from .gemini_routes import router as gemini_router
from .raw_gemini_routes import router as raw_gemini_router
from .search_routes import router as search_router
from .csv_routes import router as csv_router

from .gemini_rotator import gemini_rotator
from .session_routes import router as session_router

# from .google_maps_scraper import search_google_maps_competitors
# from .swot_analyzer import analyze_batch_swot
from .competitor_routes import router as competitor_router


# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def log_message(message: str) -> None:
    """Timestamped log — writes to both stdout and the module logger."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    logger.info(entry)


# ─── App setup ───────────────────────────────────────────────────────────────

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://reviewanalysis.uxlivinglab.org",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(gemini_router)
app.include_router(raw_gemini_router)
app.include_router(search_router)
app.include_router(csv_router)

app.include_router(session_router)
app.include_router(competitor_router)

tasks = {}

csv_tasks: dict[str, dict] = {}

# ─── Configuration / external services ───────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FOLDER = os.path.join(BASE_DIR, "data", "countries")

INSCRIBER_URL = os.getenv("INSCRIBER_URL", "http://inscriber:8002/api/geo-query-cube/")
CRUD_BASE_URL = os.getenv("CRUD_BASE_URL", "")
CRUD_COORDS_PATH = os.getenv("CRUD_COORDS_PATH", "/crud")
CRUD_RESULTS_PATH = os.getenv("CRUD_RESULTS_PATH", "/crud")
CRUD_API_KEY = os.getenv("CRUD_API_KEY", "")
DATABASE_ID = os.getenv("DATABASE_ID", "")
CRUD_COLLECTION_NAME = os.getenv("CRUD_COLLECTION_NAME", "map_scraper_data")


def _post_to_crud(path: str, document: dict) -> bool:
    if not CRUD_BASE_URL or not DATABASE_ID:
        log_message("CRUD config missing; skipping save")
        return False
    url = f"{CRUD_BASE_URL.rstrip('/')}{path}"
    headers = {"Content-Type": "application/json"}
    if CRUD_API_KEY:
        headers["Authorization"] = f"Api-Key {CRUD_API_KEY}"
    payload = {
        "database_id": DATABASE_ID,
        "collection_name": CRUD_COLLECTION_NAME,
        "documents": [document],
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if 200 <= resp.status_code < 300:
            return True
        log_message(f"CRUD POST failed {resp.status_code}: {resp.text}")
        return False
    except Exception as exc:
        log_message(f"CRUD POST exception: {exc}")
        return False


def save_coordinates_to_crud(
    task_id, keyword, mode, centers, bounds, tiles, target_coords, email, radius_km
):
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    document = {
        "sessionId": task_id,
        "createdAt": now_iso,
        "updatedAt": now_iso,
        "status": "initialized",
        "urls": [],
        "results": {},
        "metadata": {
            "mode": mode,
            "keyword": keyword,
            "email": email,
            "radiusKm": radius_km,
            "centers": centers,
            "bounds": {
                "top_left": list(bounds[0]) if bounds else None,
                "top_right": list(bounds[1]) if bounds else None,
                "bottom_left": list(bounds[2]) if bounds else None,
                "bottom_right": list(bounds[3]) if bounds else None,
            },
            "tiles": tiles,
            "target_coords": target_coords,
        },
        "email": email,
    }
    _post_to_crud(CRUD_COORDS_PATH, document)


def save_results_to_crud(task_id, keyword, results, task_snapshot):
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    urls = [r.get("URL") for r in results if r.get("URL")]
    metadata = {
        "mode": "location" if task_snapshot.get("center") else "csv",
        "keyword": keyword,
        "email": task_snapshot.get("email", ""),
        "radiusKm": task_snapshot.get("radius_km"),
        "centers": task_snapshot.get("centers")
        or ([list(task_snapshot.get("center"))] if task_snapshot.get("center") else []),
        "bounds": (
            {
                "top_left": list(task_snapshot["bounds"][0]),
                "top_right": list(task_snapshot["bounds"][1]),
                "bottom_left": list(task_snapshot["bounds"][2]),
                "bottom_right": list(task_snapshot["bounds"][3]),
            }
            if task_snapshot.get("bounds")
            else None
        ),
        "tiles": task_snapshot.get("tiles"),
        "target_coords": task_snapshot.get("target_coords"),
        "country": task_snapshot.get("country", ""),
        "city": task_snapshot.get("city", ""),
    }
    document = {
        "sessionId": task_id,
        "createdAt": now_iso,
        "updatedAt": now_iso,
        "status": "completed" if not task_snapshot.get("error") else "error",
        "urls": urls,
        "results": {"items": results},
        "metadata": metadata,
        "email": task_snapshot.get("email", ""),
    }
    _post_to_crud(CRUD_RESULTS_PATH, document)


def get_city_coordinates(country: str, city: str):
    try:
        country_files = {
            f.lower(): f for f in os.listdir(JSON_FOLDER) if f.endswith(".json")
        }
        country_filename = country.lower() + ".json"
        if country_filename not in country_files:
            return None
        file_path = os.path.join(JSON_FOLDER, country_files[country_filename])
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            if entry.get("ASCII Name", "").lower() == city.lower():
                try:
                    coords = (
                        float(entry.get("latitude")),
                        float(entry.get("longitude")),
                    )
                    log_message(f"Found coordinates for {city}, {country}: {coords}")
                    return coords
                except Exception:
                    return None
        log_message(f"City {city} not found in {country_filename}")
        return None
    except Exception:
        log_message(f"Error reading city data for {country}: {traceback.format_exc()}")
        return None


def fetch_inscriber_tiles(bounds: list) -> list:
    """
    Call the inscriber service and return a flat list of (lat, lon) offsets.
    """
    log_message("Requesting tiles from inscriber")
    try:
        payload = {
            "top_left": list(bounds[0]),
            "top_right": list(bounds[1]),
            "bottom_left": list(bounds[2]),
            "bottom_right": list(bounds[3]),
        }
        log_message(f"Inscriber payload: {payload}")
        resp = requests.post(INSCRIBER_URL, json=payload, timeout=300)
        log_message(f"Inscriber response status: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        log_message(f"Inscriber raw response (first 500): {str(data)[:500]}")

        if isinstance(data, dict) and "result" in data:
            data = data["result"]

        if isinstance(data, list):
            tiles = [(float(p[0]), float(p[1])) for p in data]
            log_message(f"Received {len(tiles)} tiles (list) from inscriber")
            return tiles

        if isinstance(data, dict) and "raw_coordinates" in data:
            flat = []
            for block in data["raw_coordinates"]:
                if isinstance(block, list):
                    for item in block:
                        if isinstance(item, dict):
                            lat = item.get("latitude")
                            lon = item.get("longitude")
                        elif isinstance(item, (list, tuple)) and len(item) >= 2:
                            lat, lon = item[0], item[1]
                        else:
                            continue
                        if lat is not None and lon is not None:
                            flat.append((float(lat), float(lon)))
                elif isinstance(block, dict):
                    lat = block.get("latitude")
                    lon = block.get("longitude")
                    if lat is not None and lon is not None:
                        flat.append((float(lat), float(lon)))
            log_message(f"Received {len(flat)} tiles (raw_coordinates) from inscriber")
            return flat

        log_message(f"Unrecognised inscriber response shape: {str(data)[:200]}")
        return []

    except Exception as exc:
        log_message(f"Inscriber fetch failed: {exc}\n{traceback.format_exc()}")
        return []


def build_target_coordinates(centers: list, relative_tiles: list) -> list:
    log_message(
        f"Building target coordinates: centers={len(centers)}, "
        f"tiles={len(relative_tiles)}"
    )
    if not relative_tiles:
        return centers
    return [
        (c_lat + d_lat, c_lon + d_lon)
        for c_lat, c_lon in centers
        for d_lat, d_lon in relative_tiles
    ]


# ─── HTTP endpoints (non-CSV-processing) ─────────────────────────────────────


@app.get("/countries")
def get_countries():
    try:
        countries = sorted(
            [f[:-5] for f in os.listdir(JSON_FOLDER) if f.endswith(".json")]
        )
        return {"countries": countries}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/cities/{country}")
def get_cities(country: str):
    try:
        country_files = {
            f.lower(): f for f in os.listdir(JSON_FOLDER) if f.endswith(".json")
        }
        country_filename = country.lower() + ".json"
        if country_filename not in country_files:
            return JSONResponse(
                status_code=404,
                content={"error": f"Country '{country}' not found"},
            )
        file_path = os.path.join(JSON_FOLDER, country_files[country_filename])
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cities = [
            city["ASCII Name"]
            for city in data
            if int(city.get("Population", 0)) > 100000
        ]
        if not cities:
            return JSONResponse(
                status_code=200,
                content={"message": "No cities with population greater than 100000"},
            )
        return {"cities": cities}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/cancel/{task_id}")
def cancel_task(task_id: str):
    if task_id in tasks:
        tasks[task_id]["running"] = False
        time.sleep(1)
        return {"message": f"Task {task_id} has been canceled"}
    return JSONResponse(status_code=404, content={"error": "Task not found"})


@app.get("/download-search/{task_id}")
def download_search_results(task_id: str):
    if task_id not in tasks or not tasks[task_id]["results"]:
        return {"error": "No results found"}

    def iter_csv():
        yield "Name,Address,Phone,Website,URL,City,Country\n"
        for row in tasks[task_id]["results"]:
            yield (
                f'"{row["Name"]}","{row["Address"]}","{row["Phone"]}",'
                f'"{row["Website"]}","{row["URL"]}","{row["City"]}",'
                f'"{row["Country"]}"\n'
            )

    return StreamingResponse(
        iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=results_{task_id}.csv"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
