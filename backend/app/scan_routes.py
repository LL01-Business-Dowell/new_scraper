import os
import json
import logging
import httpx
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

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
async def get_recent_scans(
    type: Optional[str] = Query(None),
    hours: Optional[int] = Query(None),
    time: Optional[str] = Query(None)
):
    print(">>> REQUEST HIT FASTAPI BACKEND! <<<", flush=True)
    # Determine the time window in hours based on `hours` or `time` parameter
    selected_hours = 24  # Default to 24 hours

    if hours is not None:
        selected_hours = hours
    elif time is not None:
        clean_time = time.lower().strip()
        if clean_time in ["7", "7d"]:
            selected_hours = 168  # 7 days * 24 hours
        elif clean_time in ["30", "30d"]:
            selected_hours = 720  # 30 days * 24 hours
        elif clean_time in ["24", "24h", "1", "1d"]:
            selected_hours = 24
        else:
            try:
                selected_hours = int(clean_time)
            except ValueError:
                selected_hours = 24

    logger.info(f"=== [START] Processing scan request | type filter: {type} | window: {selected_hours} hours ===")

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

    # Log outbound request payload details
    logger.info(f"Outbound Request URL: {DATACUBE_URL}")
    logger.info(f"Outbound Query Params: {json.dumps(params, indent=2)}")
    logger.info(f"Outbound Headers: {{'Authorization': 'Api-Key [REDACTED]'}}")

    docs = []
    try:
        # Configured explicit 30.0s timeout to account for DataCube response latency
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            res = await client.get(DATACUBE_URL, params=params, headers=headers)
            
            logger.info(f"DataCube Response Status Code: {res.status_code}")
            
            if res.status_code != 200:
                logger.error(f"DataCube request failed with status code {res.status_code}. Response body: {res.text}")
                raise HTTPException(status_code=res.status_code, detail="Failed to fetch data from DataCube")

            json_data = res.json()
            
            # Log DataCube response structure and raw item count
            if isinstance(json_data, dict):
                docs = json_data.get("data", [])
                logger.info(f"DataCube Response JSON (dict keys): {list(json_data.keys())}")
                logger.info(f"DataCube returned {len(docs)} documents in 'data' field.")
            elif isinstance(json_data, list):
                docs = json_data
                logger.info(f"DataCube returned {len(docs)} documents as a direct list.")
            else:
                logger.warning(f"Unexpected DataCube response structure: {type(json_data)}")

            # Log sample raw document if available
            if docs:
                logger.info(f"Sample raw document from DataCube: {json.dumps(docs[0], indent=2)}")

    except httpx.ReadTimeout:
        logger.error("DataCube request timed out after 30 seconds.")
        raise HTTPException(status_code=504, detail="DataCube service timeout")
    except httpx.RequestError as exc:
        logger.error(f"HTTP network error while communicating with DataCube: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"DataCube connection error: {str(exc)}")
    except Exception as exc:
        logger.error(f"Unexpected error during DataCube request: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(exc)}")

    now = datetime.now(timezone.utc)
    time_cutoff = now - timedelta(hours=selected_hours)

    recent_scans = []
    filtered_out_type = 0
    filtered_out_coords = 0
    filtered_out_time = 0

    for doc in docs:
        # Fallback check: Filter in memory if DataCube doesn't strictly enforce filter queries
        if type and doc.get("type") != type:
            filtered_out_type += 1
            continue

        scanned_at_str = doc.get("scanned_at") or doc.get("submitted_at") or doc.get("created_at")
        lat = doc.get("latitude")
        lng = doc.get("longitude")

        if not scanned_at_str or lat is None or lng is None:
            filtered_out_coords += 1
            continue

        try:
            lat_val = float(lat)
            lng_val = float(lng)

            if lat_val == 0.0 and lng_val == 0.0:
                filtered_out_coords += 1
                continue

            scan_time = datetime.fromisoformat(scanned_at_str.replace("Z", "+00:00"))
            
            if scan_time >= time_cutoff:
                recent_scans.append({
                    "qr_id": doc.get("qr_id", "N/A"),
                    "latitude": lat_val,
                    "longitude": lng_val,
                    "scanned_at": scanned_at_str,
                    "type": doc.get("type", "N/A")
                })
            else:
                filtered_out_time += 1

        except (ValueError, TypeError):
            filtered_out_coords += 1
            continue

    logger.info(
        f"=== [END] Filtering summary: Total fetched={len(docs)} | Valid scans={len(recent_scans)} | "
        f"Filtered by type={filtered_out_type} | Filtered by coords={filtered_out_coords} | Filtered by time={filtered_out_time} ==="
    )

    return {"success": True, "count": len(recent_scans), "data": recent_scans}