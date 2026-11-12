import os
import time
import logging
import datetime
import requests as http_requests
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/integrations/zoho", tags=["Zoho Integration"])

# Zoho OAuth Configuration
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN", "")
ZOHO_ORGANIZATION_ID = os.getenv("ZOHO_ORGANIZATION_ID", "")

# DataCube / PureTrace Configuration (aligned with your existing env vars)
CRUD_BASE_URL = os.getenv("CRUD_BASE_URL", "https://datacube.uxlivinglab.online/api/v2")
CRUD_API_KEY = os.getenv("FEEDBACK_CRUD_API_KEY") or os.getenv("CRUD_API_KEY", "")
MASTER_DATABASE_ID = "695ce92eff84eaf663c457c2"

_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0}


def get_zoho_access_token() -> str:
    """Retrieves and caches a Zoho OAuth2 access token using your permanent refresh token."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    if not all([ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN]):
        raise RuntimeError("Missing Zoho OAuth credentials in environment variables.")

    response = http_requests.post(
        "https://accounts.zoho.com/oauth/v2/token",
        params={
            "refresh_token": ZOHO_REFRESH_TOKEN,
            "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Zoho Auth Error: {response.text}")

    data = response.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3600) - 300
    return _token_cache["token"]


def _process_zoho_batch_sync(payload: Dict[str, Any]) -> None:
    """Background Task: Maps Zoho item/batch payload to puretrace.html schema and saves to DataCube."""
    item = payload.get("item", payload)
    batch = payload.get("batch", {})

    batch_number = (
        batch.get("batch_number")
        or item.get("cf_batch_number")
        or item.get("batch_number")
        or "DEFAULT_BATCH"
    )

    link_id = (
        item.get("cf_puretrace_qr_id")
        or item.get("cf_puretrace_qr_prefix")
        or batch.get("cf_puretrace_qr_prefix")
        or "1009"
    )

    # Extract 4-char collection prefix (e.g., '100935c2f1ffd5d5' -> '1009')
    collection_name = link_id[:4] if len(link_id) >= 4 else "1009"

    product_details = {
        "status": "active",
        "product_name": item.get("name", item.get("product_name", "")),
        "batch_id": batch_number,
        "description": item.get("description", ""),
        "quantity": str(item.get("initial_stock", item.get("quantity", 0))),
        "quantity_unit": item.get("unit", item.get("quantity_unit", "pcs")),
        "mrp": str(item.get("rate", item.get("mrp", 0.0))),
        "mrp_currency": item.get("cf_currency", item.get("mrp_currency", "INR")),
        "manufactured_by": item.get("cf_manufactured_by", item.get("manufactured_by", "")),
        "marketed_by": item.get("cf_marketed_by", item.get("marketed_by", "")),
        "mfg_date": item.get("cf_mfg_date", item.get("mfg_date", "")),
        "mfg_time": item.get("cf_mfg_time", item.get("mfg_time", "")),
        "country_of_origin": item.get("cf_country_of_origin", item.get("country_of_origin", "")),
        "customer_care_contact": item.get("cf_customer_care_contact", item.get("customer_care_contact", "")),
        "customer_care_phone": item.get("cf_customer_care_phone", item.get("customer_care_phone", "")),
        "customer_care_email": item.get("cf_customer_care_email", item.get("customer_care_email", "")),
        "serial_number": item.get("sku", item.get("serial_number", "")),
        "product_size": item.get("cf_product_size", item.get("product_size", "")),
        "unit_sales_price": str(item.get("rate", item.get("unit_sales_price", 0.0))),
        "gst_number": item.get("cf_gst_number", item.get("gst_number", "")),
        "expiry_date": item.get("cf_expiry_date", batch.get("expiry_date", "")),
        "expiry_details": item.get("cf_expiry_details", item.get("expiry_details", "")),
        "website": item.get("cf_website", item.get("website", "")),
        "whatsapp_link": item.get("cf_whatsapp_link", item.get("whatsapp_link", "")),
        "storage_location_manufacturer": item.get("cf_storage_location", ""),
        "storage_instructions_consumer": item.get("cf_storage_instructions", ""),
        "package_recycling": item.get("cf_package_recycling", ""),
        "location_coordinates": item.get("cf_location_coordinates", ""),
        "splash_screen_video": item.get("cf_splash_screen_video", ""),
        "splash_screen_logo": item.get("cf_splash_screen_logo", ""),
        "notes": item.get("cf_notes", ""),
        "synced_from": "zoho_inventory",
        "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
    }

    document = {
        "type": "zoho_batch_mapping",
        "link_id": link_id,
        "batch_id": batch_number,
        "product_details": product_details,
    }

    try:
        headers = {"Content-Type": "application/json"}
        if CRUD_API_KEY:
            headers["Authorization"] = f"Api-Key {CRUD_API_KEY}"

        resp = http_requests.post(
            f"{CRUD_BASE_URL.rstrip('/')}/crud/",
            json={
                "database_id": MASTER_DATABASE_ID,
                "collection_name": collection_name,
                "documents": [document],
            },
            headers=headers,
            timeout=15,
        )
        if 200 <= resp.status_code < 300:
            logger.info(f"[ZOHO-SYNC] Batch '{batch_number}' synced to collection '{collection_name}' (link_id={link_id}).")
        else:
            logger.warning(f"[ZOHO-SYNC] DataCube insert failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        logger.error(f"[ZOHO-SYNC] Exception syncing batch: {e}")


@router.post("/webhook")
async def handle_zoho_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receives Zoho Inventory/Books webhooks and queues background sync (<200ms response)."""
    try:
        payload = await request.json()
        background_tasks.add_task(_process_zoho_batch_sync, payload)
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Zoho webhook queued for background sync."},
        )
    except Exception as e:
        logger.error(f"[ZOHO-WEBHOOK] Invalid JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")


@router.get("/status")
async def check_zoho_integration_status():
    """Health check endpoint to verify Zoho OAuth credentials."""
    try:
        token = get_zoho_access_token()
        return {
            "status": "connected",
            "zoho_organization_id": ZOHO_ORGANIZATION_ID,
            "access_token_active": bool(token),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}