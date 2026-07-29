"""
qr_datacube_routes.py
---------------------
Backend routes matching official DataCube API v2 documentation:
Base URL: https://datacube.uxlivinglab.online
Auth: Authorization: Api-Key <CRUD_API_KEY>
"""

import os
import re
import datetime
import requests
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/feedback-qr", tags=["Feedback QR DataCube"])

DATACUBE_BASE_URL = "https://datacube.uxlivinglab.online"

# Reads CRUD_API_KEY directly from environment/.env
CRUD_API_KEY = os.getenv("CRUD_API_KEY", "")
# DATABASE_ID = os.getenv("DATACUBE_DATABASE_ID", "6a69cbefff5146ff3f2b568a") 
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
    client_name: str       # Collection name (e.g., hyatt, hilton)
    name: str              # e.g., "Main Lobby Desk"
    room_number: str       # e.g., "404"
    user_id: str           # Alphanumeric ID input (e.g. "hyatt-suite")

class CreateClientRequest(BaseModel):
    client_name: str       # New collection name (e.g., marriott)

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _get_next_sequence_id(client_name: str) -> int:
    """
    Fetches existing QR records using GET /api/v2/crud/ 
    and calculates the next 4-digit sequence integer (starting at 1000).
    """
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
    except Exception as e:
        print(f"Error fetching existing QRs for sequence count: {e}")

    return highest_seq + 1

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/clients")
async def list_clients():
    """
    GET /api/v2/list_collections/?database_id=...
    Retrieves the list of client collections inside the database.
    """
    url = f"{DATACUBE_BASE_URL}/api/v2/list_collections/"
    params = {"database_id": DATABASE_ID}
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code == 200:
            res_data = response.json()
            raw_collections = res_data.get("data", [])
            client_names = [col.get("name") for col in raw_collections if col.get("name")]
            return {"status": "success", "clients": client_names}
        else:
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"DataCube Error: {response.text}"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-client")
async def add_client(req: CreateClientRequest):
    """
    POST /api/v2/add_collection/
    Creates a new client collection inside DataCube database.
    """
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
                    {"name": "name", "type": "string"},
                    {"name": "room_number", "type": "string"},
                    {"name": "user_id", "type": "string"},
                    {"name": "sequence_number", "type": "number"},
                    {"name": "full_id", "type": "string"},
                    {"name": "target_url", "type": "string"},
                    {"name": "created_at", "type": "string"}
                ]
            }
        ]
    }

    try:
        response = requests.post(url, headers=get_headers(), json=payload)
        if response.status_code in (200, 201):
            return {
                "status": "success",
                "message": f"Client collection '{client_name}' created successfully.",
                "client_name": client_name
            }
        else:
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"DataCube Error ({response.status_code}): {response.text}"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/qrs/{client_name}")
async def get_client_qrs(client_name: str):
    """
    GET /api/v2/crud/?database_id=...&collection_name=...
    Retrieves all QR documents for the selected client collection.
    """
    url = f"{DATACUBE_BASE_URL}/api/v2/crud/"
    params = {
        "database_id": DATABASE_ID,
        "collection_name": client_name.lower().strip(),
        "filters": "{}",
        "page": 1,
        "page_size": 100
    }
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code == 200:
            res_data = response.json()
            return {
                "status": "success",
                "client": client_name,
                "qr_codes": res_data.get("data", [])
            }
        else:
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"DataCube Error: {response.text}"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_qr_code(req: CreateQrRequest):
    """
    POST /api/v2/crud/
    Inserts a new QR document into the client's DataCube collection.
    """
    client_col = req.client_name.lower().strip()
    
    # 1. Compute next sequential 4-digit ID
    next_seq = _get_next_sequence_id(client_col)
    
    # 2. Combine user alphanumeric ID with sequence ID
    full_id = f"{req.user_id.strip()}-{next_seq}"
    target_url = f"https://your-domain.com/feedback?id={full_id}"
    
    doc = {
        "name": req.name,
        "room_number": req.room_number,
        "user_id": req.user_id,
        "sequence_number": next_seq,
        "full_id": full_id,
        "target_url": target_url,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    
    # 3. Format per DataCube v2 API specification
    payload = {
        "database_id": DATABASE_ID,
        "collection_name": client_col,
        "documents": [doc]
    }
    
    url = f"{DATACUBE_BASE_URL}/api/v2/crud/"
    response = requests.post(url, headers=get_headers(), json=payload)
    
    if response.status_code in (200, 201):
        return {
            "status": "success",
            "message": f"QR code {full_id} stored in DataCube.",
            "record": doc,
            "datacube_response": response.json()
        }
    else:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to save to DataCube ({response.status_code}): {response.text}"
        )