from urllib.parse import quote
import os
import re
import logging
import datetime
import requests
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger("qr_datacube")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/feedback-qr", tags=["Feedback QR DataCube"])

DATACUBE_BASE_URL = "https://datacube.uxlivinglab.online"

CRUD_API_KEY = os.getenv("FEEDBACK_QR_API_KEY", "")
DATABASE_ID = "6a69cbefff5146ff3f2b568a"

def get_headers():
    return {
        "Authorization": f"Api-Key {CRUD_API_KEY}",
        "Content-Type": "application/json"
    }

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class CreateQrRequest(BaseModel):
    client_name: str       
    name: str             
    room_number: str       
    user_id: str           

class CreateClientRequest(BaseModel):
    client_name: str       

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _get_next_sequence_id(client_name: str) -> int:
    url = f"{DATACUBE_BASE_URL}/api/v2/crud/"
    params = {
        "database_id": DATABASE_ID,
        "collection_name": client_name.lower().strip(),
        "filters": "{}",
        "page": 1,
        "page_size": 500
    }
    
    highest_seq = 999  # First generated code starts at 1000

    try:
        logger.info(f"Fetching sequence count for collection '{client_name}' from DataCube")
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code == 200:
            res_data = response.json()
            documents = res_data.get("data", [])
            for doc in documents:
                seq = doc.get("sequence_number")
                if seq and isinstance(seq, int) and seq > highest_seq:
                    highest_seq = seq
                else:
                    full_id = str(doc.get("full_id", ""))
                    match = re.search(r'(\d{4})$', full_id)
                    if match:
                        num = int(match.group(1))
                        if num > highest_seq:
                            highest_seq = num
        else:
            logger.warning(f"Failed sequence check from DataCube. Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        logger.exception(f"Exception encountered while calculating sequence ID: {e}")

    return highest_seq + 1

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/clients")
async def list_clients():
    url = f"{DATACUBE_BASE_URL}/api/v2/list_collections/"
    params = {"database_id": DATABASE_ID}
    
    if not CRUD_API_KEY:
        logger.error("CRUD_API_KEY is missing or empty in environment variables!")

    logger.info(f"Fetching clients list from DataCube: {url} | DATABASE_ID: {DATABASE_ID}")
    
    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=10)
        logger.info(f"DataCube /list_collections/ status code: {response.status_code}")

        if response.status_code == 200:
            res_data = response.json()
            
            # DataCube API v2 returns "collections", fallback to "data" if missing
            raw_collections = res_data.get("collections") or res_data.get("data", [])
            
            if isinstance(raw_collections, list):
                client_names = [
                    col.get("name") for col in raw_collections 
                    if isinstance(col, dict) and col.get("name")
                ]
            else:
                client_names = []

            logger.info(f"Successfully retrieved {len(client_names)} clients: {client_names}")
            return {"status": "success", "clients": client_names}
        else:
            logger.error(f"DataCube error response ({response.status_code}): {response.text}")
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"DataCube Error ({response.status_code}): {response.text}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unhandled error in /clients endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.post("/add-client")
async def add_client(req: CreateClientRequest):
    client_name = req.client_name.lower().strip().replace(" ", "_")
    if not client_name:
        raise HTTPException(status_code=400, detail="Client name cannot be empty.")

    url = f"{DATACUBE_BASE_URL}/api/v2/add_collection/"
    payload = {
        "database_id": DATABASE_ID,
        "collections": [
            {
                "name": client_name,
                "fields": [
                    {"name": "id", "type": "string"},
                    {"name": "unique_id", "type": "string"},
                    {"name": "name", "type": "string"},
                    {"name": "room_number", "type": "string"},
                    {"name": "user_id", "type": "string"},
                    {"name": "sequence_number", "type": "number"},
                    {"name": "collection_name", "type": "string"},
                    {"name": "full_id", "type": "string"},
                    {"name": "target_url", "type": "string"},
                    {"name": "created_at", "type": "string"}
                ]
            }
        ]
    }

    logger.info(f"Adding collection '{client_name}' to DataCube via {url}")

    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        logger.info(f"DataCube /add_collection/ status code: {response.status_code}")

        if response.status_code in (200, 201):
            logger.info(f"Successfully created collection '{client_name}'")
            return {
                "status": "success",
                "message": f"Client collection '{client_name}' created successfully.",
                "client_name": client_name
            }
        else:
            logger.error(f"Failed to add collection '{client_name}'. DataCube Error: {response.text}")
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"DataCube Error ({response.status_code}): {response.text}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unhandled exception in /add-client endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/qrs/{client_name}")
async def get_client_qrs(client_name: str):
    url = f"{DATACUBE_BASE_URL}/api/v2/crud/"
    clean_client = client_name.lower().strip()
    params = {
        "database_id": DATABASE_ID,
        "collection_name": clean_client,
        "filters": "{}",
        "page": 1,
        "page_size": 100
    }
    
    logger.info(f"Fetching QR codes for collection '{clean_client}' from DataCube")

    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=10)
        logger.info(f"DataCube /crud/ fetch status code: {response.status_code}")

        if response.status_code == 200:
            res_data = response.json()
            return {
                "status": "success",
                "client": clean_client,
                "qr_codes": res_data.get("data", [])
            }
        else:
            logger.error(f"DataCube CRUD fetch failed ({response.status_code}): {response.text}")
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"DataCube Error ({response.status_code}): {response.text}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unhandled exception in /qrs/{client_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_qr_code(req: CreateQrRequest):
    client_col = req.client_name.lower().strip()
    client_name = req.client_name.strip()
    qr_name = req.name.strip()
    
    logger.info(f"Creating new QR code record for client '{client_col}'")

    try:
        # 1. Get the next 4-digit sequence number (e.g. 1000, 1001, 1002)
        next_seq = _get_next_sequence_id(client_col)

        # 2. Format as a 4-digit string
        seq_prefix = f"{next_seq:04d}"

        # 3. Combine sequence prefix with random UUID string
        unique_qr_id = f"{seq_prefix}{uuid.uuid4().hex[:12]}" 

        safe_client = quote(client_name)
        safe_id = quote(unique_qr_id)
        safe_name = quote(qr_name)

        # 4. Target URL now contains the sequence number as the first 4 digits of the ID
        target_url = f"https://reviewanalysis.uxlivinglab.org/feedback?client={safe_client}&id={safe_id}&name={safe_name}"
        
        doc = {
            "id": unique_qr_id,                 
            "unique_id": unique_qr_id,           
            "name": req.name,
            "room_number": req.room_number,
            "user_id": req.user_id.strip(),       
            "sequence_number": next_seq,         
            "collection_name": client_col,       
            "target_url": target_url,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        
        payload = {
            "database_id": DATABASE_ID,
            "collection_name": client_col,
            "documents": [doc]
        }
        
        url = f"{DATACUBE_BASE_URL}/api/v2/crud/"
        logger.info(f"Posting new QR code doc to DataCube: {payload}")

        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        logger.info(f"DataCube /crud/ create status code: {response.status_code}")

        if response.status_code in (200, 201):
            return {
                "status": "success",
                "message": f"QR code {unique_qr_id} stored in DataCube.",
                "record": doc,
                "datacube_response": response.json()
            }
        else:
            logger.error(f"Failed to save QR to DataCube ({response.status_code}): {response.text}")
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to save to DataCube ({response.status_code}): {response.text}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unhandled exception in /create QR code: {e}")
        raise HTTPException(status_code=500, detail=str(e))