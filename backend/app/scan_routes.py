import os
import json
import logging
import httpx
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

# Configure logger
logger = logging.getLogger("scan_routes")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/scans", tags=["Scans"])

# Correct DataCube Base and Endpoint per official docs
DATACUBE_URL = "https://datacube.uxlivinglab.online/api/v2/crud/"
CRUD_API_KEY = os.getenv("CRUD_API_KEY")
MASTER_DATABASE_ID = "69985c0844ca8a1af7fd639e"
COLLECTION_NAME = "medsign_qr_scan"  

@router.get("/last24hours")
async def get_recent_scans(type: Optional[str] = Query(None)):
    logger.info(f"Processing last 24 hours scan request (type filter: {type})")

    if not CRUD_API_KEY:
        logger.error("Missing required server configuration: CRUD_API_KEY is not set")
        raise HTTPException(status_code=500, detail="Server configuration missing CRUD_API_KEY.")

    headers = {
        "Authorization": f"Api-Key {CRUD_API_KEY}"
    }

    # Pass the type filter to DataCube if provided
    db_filters = {}
    if type:
        db_filters["type"] = type

    params = {
        "database_id": MASTER_DATABASE_ID,
        "collection_name": COLLECTION_NAME,
        "filters": json.dumps(db_filters),
        "page": 1,
        "page_size": 500
    }

    docs = []
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Executing GET request to DataCube endpoint: {DATACUBE_URL}")
            res = await client.get(DATACUBE_URL, params=params, headers=headers)
            
            if res.status_code != 200:
                logger.error(f"DataCube request failed with status code {res.status_code}. Response body: {res.text}")
                raise HTTPException(status_code=res.status_code, detail="Failed to fetch data from DataCube")

            json_data = res.json()
            
            if isinstance(json_data, dict):
                docs = json_data.get("data", [])
            elif isinstance(json_data, list):
                docs = json_data

    except httpx.RequestError as exc:
        logger.error(f"HTTP network error while communicating with DataCube: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"DataCube connection error: {str(exc)}")
    except Exception as exc:
        logger.error(f"Unexpected error during DataCube request: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(exc)}")

    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)

    recent_scans = []

    for doc in docs:
        # Fallback check: Filter in memory if DataCube doesn't strictly enforce filter queries
        if type and doc.get("type") != type:
            continue

        scanned_at_str = doc.get("scanned_at") or doc.get("submitted_at") or doc.get("created_at")
        lat = doc.get("latitude")
        lng = doc.get("longitude")

        if not scanned_at_str or lat is None or lng is None:
            continue

        try:
            lat_val = float(lat)
            lng_val = float(lng)

            if lat_val == 0.0 and lng_val == 0.0:
                continue

            scan_time = datetime.fromisoformat(scanned_at_str.replace("Z", "+00:00"))
            
            if scan_time >= twenty_four_hours_ago:
                recent_scans.append({
                    "qr_id": doc.get("qr_id", "N/A"),
                    "latitude": lat_val,
                    "longitude": lng_val,
                    "scanned_at": scanned_at_str,
                    "type": doc.get("type", "N/A")
                })

        except (ValueError, TypeError):
            continue

    return {"success": True, "count": len(recent_scans), "data": recent_scans}