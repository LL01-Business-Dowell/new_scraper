import os
import json
import time
import logging
import datetime
import requests as http_requests
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/integrations/zoho", tags=["Zoho Integration"])

# Zoho OAuth Configuration (.in Data Center)
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN", "")
ZOHO_ORGANIZATION_ID = os.getenv("ZOHO_ORGANIZATION_ID", "")

# DataCube / PureTrace Configuration (aligned with server.js)
DATACUBE_BASE = os.getenv("CRUD_BASE_URL", "https://datacube.uxlivinglab.online/api/v2").rstrip("/")
DATACUBE_API_KEY = os.getenv("PURETRACE_API_KEY", "")
PURETRACE_DB_ID = "69985c0844ca8a1af7fd639e"
COLLECTION_NAME = "medsign_links"

_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0}
# Track SKUs pushed from PureTrace to prevent infinite webhook echo loops
_recently_pushed_skus: Dict[str, float] = {}


def _datacube_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if DATACUBE_API_KEY:
        headers["Authorization"] = f"Api-Key {DATACUBE_API_KEY}"
    return headers


def get_zoho_access_token() -> str:
    """Retrieves and caches a Zoho OAuth2 access token using your permanent refresh token."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    if not all([ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN]):
        raise RuntimeError("Missing Zoho OAuth credentials in environment variables.")

    response = http_requests.post(
        "https://accounts.zoho.in/oauth/v2/token",
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
    if "access_token" not in data:
        raise RuntimeError(f"Zoho Token Error: {data}")

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3600) - 300
    return _token_cache["token"]


def fetch_full_zoho_item(item_id: str) -> Optional[Dict[str, Any]]:
    """Fetches full item details (including SKU and batches array) from Zoho Inventory/Books (.in)."""
    if not item_id or not ZOHO_ORGANIZATION_ID:
        return None

    try:
        token = get_zoho_access_token()
        headers = {"Authorization": f"Zoho-oauthtoken {token}"}
        params = {"organization_id": ZOHO_ORGANIZATION_ID}

        for base_url in (
            f"https://www.zohoapis.in/inventory/v1/items/{item_id}",
            f"https://www.zohoapis.in/books/v3/items/{item_id}",
        ):
            res = http_requests.get(base_url, headers=headers, params=params, timeout=10)
            if res.ok:
                item_data = res.json().get("item")
                if item_data:
                    return item_data
    except Exception as e:
        logger.warning(f"[ZOHO-SYNC] Full item fetch skipped ({e}); falling back to webhook payload.")

    return None


def _build_puretrace_batch_entries(item: Dict[str, Any], webhook_batch: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Maps Zoho SKU item + batches into PureTrace product_details array entries."""
    custom_fields = item.get("custom_field_hash") or {}
    batches = item.get("batches") or []

    if not batches and webhook_batch:
        batches = [webhook_batch]
    if not batches:
        batches = [{}]

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
    default_mfg = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    entries: List[Dict[str, Any]] = []

    for b in batches:
        batch_number = str(
            b.get("batch_number")
            or custom_fields.get("cf_batch_number")
            or item.get("batch_number")
            or item.get("item_id")
            or "DEFAULT_BATCH"
        )

        raw_mfg = (
            b.get("manufactured_date")
            or custom_fields.get("cf_mfg_date")
            or item.get("mfg_date")
            or default_mfg
        )
        raw_exp = (
            b.get("expiry_date")
            or custom_fields.get("cf_expiry_date")
            or item.get("expiry_date")
            or ""
        )

        qty = (
            b.get("in_quantity")
            or b.get("available_quantity")
            or item.get("stock_on_hand")
            or item.get("initial_stock")
            or item.get("quantity")
            or 0
        )

        entries.append({
            "status": "active",
            "product_name": item.get("name", item.get("product_name", "")),
            "batch_id": batch_number,
            "description": item.get("description") or item.get("sales_description") or item.get("name", ""),
            "quantity": str(qty),
            "quantity_unit": item.get("unit") or item.get("quantity_unit") or "pcs",
            "mrp": str(item.get("rate") or item.get("sales_rate") or item.get("mrp") or 0.0),
            "mrp_currency": custom_fields.get("cf_currency") or item.get("currency_code") or "INR",
            "manufactured_by": item.get("manufacturer") or custom_fields.get("cf_manufactured_by") or "DoWell",
            "marketed_by": item.get("brand") or custom_fields.get("cf_marketed_by") or "DoWell",
            "mfg_date": str(raw_mfg)[:10],
            "mfg_time": custom_fields.get("cf_mfg_time") or item.get("mfg_time") or "",
            "country_of_origin": custom_fields.get("cf_country_of_origin") or "India",
            "customer_care_contact": custom_fields.get("cf_customer_care_contact") or "Customer Support",
            "customer_care_phone": custom_fields.get("cf_customer_care_phone") or "",
            "customer_care_email": custom_fields.get("cf_customer_care_email") or "",
            "serial_number": str(item.get("sku") or ""),
            "product_size": custom_fields.get("cf_product_size") or "",
            "unit_sales_price": str(item.get("rate") or item.get("sales_rate") or 0.0),
            "gst_number": custom_fields.get("cf_gst_number") or "",
            "expiry_date": str(raw_exp)[:10],
            "expiry_details": custom_fields.get("cf_expiry_details") or "",
            "website": custom_fields.get("cf_website") or "",
            "whatsapp_link": custom_fields.get("cf_whatsapp_link") or "",
            "storage_location_manufacturer": custom_fields.get("cf_storage_location") or "",
            "storage_instructions_consumer": custom_fields.get("cf_storage_instructions") or "",
            "package_recycling": custom_fields.get("cf_package_recycling") or "",
            "location_coordinates": custom_fields.get("cf_location_coordinates") or "",
            "splash_screen_video": custom_fields.get("cf_splash_screen_video") or "",
            "splash_screen_logo": custom_fields.get("cf_splash_screen_logo") or "",
            "notes": custom_fields.get("cf_notes") or "",
            "zoho_item_id": str(item.get("item_id", "")),
            "zoho_batch_id": str(b.get("batch_in_id") or b.get("batch_id") or ""),
            "synced_from": "zoho_inventory",
            "updated_at": now_iso,
        })

    return entries


def _upsert_medsign_link_batches(link_id: str, new_entries: List[Dict[str, Any]]) -> None:
    """Queries medsign_links by link_id (SKU) and upserts batches into product_details array."""
    headers = _datacube_headers()
    filters = json.dumps({"link_id": str(link_id)})

    get_resp = http_requests.get(
        f"{DATACUBE_BASE}/crud/",
        params={
            "database_id": PURETRACE_DB_ID,
            "collection_name": COLLECTION_NAME,
            "filters": filters,
            "page": 1,
            "page_size": 1,
        },
        headers=headers,
        timeout=15,
    )

    if not get_resp.ok:
        logger.error(f"[ZOHO-SYNC] DataCube GET failed ({get_resp.status_code}): {get_resp.text[:200]}")
        return

    existing_docs = get_resp.json().get("data", [])

    if not existing_docs:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        new_doc = {
            "link_id": str(link_id),
            "email": "zoho-sync@uxlivinglab.org",
            "link_url": f"https://location-map-1.onrender.com/puretrace.html?id={link_id}",
            "batch_id": new_entries[0]["batch_id"] if new_entries else "",
            "client_name": new_entries[0].get("marketed_by", "") if new_entries else "",
            "client_no": [],
            "product_details": new_entries,
            "created_at": now_iso,
            "status": "active",
        }
        post_resp = http_requests.post(
            f"{DATACUBE_BASE}/crud",
            json={
                "database_id": PURETRACE_DB_ID,
                "collection_name": COLLECTION_NAME,
                "documents": [new_doc],
            },
            headers=headers,
            timeout=15,
        )
        if post_resp.ok:
            logger.info(f"[ZOHO-SYNC] Created new medsign_link '{link_id}' with {len(new_entries)} batch(es).")
        else:
            logger.error(f"[ZOHO-SYNC] DataCube POST failed ({post_resp.status_code}): {post_resp.text[:200]}")
        return

    raw_details = existing_docs[0].get("product_details") or []
    if isinstance(raw_details, str):
        try:
            raw_details = json.loads(raw_details)
        except Exception:
            raw_details = []
    if isinstance(raw_details, dict):
        raw_details = [raw_details] if raw_details else []

    media_keys = (
        "splash_screen_logo",
        "splash_screen_video",
        "product_images",
        "certificates",
        "product_videos",
    )

    for entry in new_entries:
        idx = next(
            (
                i
                for i, existing in enumerate(raw_details)
                if existing.get("status") == "draft" or existing.get("batch_id") == entry["batch_id"]
            ),
            -1,
        )
        if idx != -1:
            preserved_media = {
                k: v for k, v in raw_details[idx].items() if k in media_keys and v
            }
            raw_details[idx] = {**entry, **preserved_media}
        else:
            raw_details.append(entry)

    put_resp = http_requests.put(
        f"{DATACUBE_BASE}/crud",
        json={
            "database_id": PURETRACE_DB_ID,
            "collection_name": COLLECTION_NAME,
            "filters": {"link_id": str(link_id)},
            "update_data": {
                "product_details": raw_details,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
            },
            "update_all_fields": False,
            "update_many": True,
            "upsert": False,
        },
        headers=headers,
        timeout=15,
    )

    if put_resp.ok:
        logger.info(
            f"[ZOHO-SYNC] Synced {len(new_entries)} batch(es) into medsign_links link_id='{link_id}' "
            f"(total batches: {len(raw_details)})."
        )
    else:
        logger.error(f"[ZOHO-SYNC] DataCube PUT failed ({put_resp.status_code}): {put_resp.text[:200]}")


def _process_zoho_batch_sync(payload: Dict[str, Any]) -> None:
    """Background Task 1: Zoho -> PureTrace DataCube sync."""
    try:
        webhook_item = payload.get("item", payload)
        webhook_batch = payload.get("batch", {})
        item_id = str(webhook_item.get("item_id", ""))

        full_item = fetch_full_zoho_item(item_id) or webhook_item
        link_id = str(full_item.get("sku") or "").strip()

        if not link_id:
            logger.info(
                f"[ZOHO-SYNC] Item '{full_item.get('name')}' (item_id={item_id}) has no SKU set. Skipping sync."
            )
            return

        if time.time() < _recently_pushed_skus.get(link_id, 0):
            logger.info(f"[ZOHO-SYNC] Skipping echo webhook for recently pushed SKU '{link_id}'.")
            return

        batch_entries = _build_puretrace_batch_entries(full_item, webhook_batch)
        _upsert_medsign_link_batches(link_id, batch_entries)
    except Exception as e:
        logger.error(f"[ZOHO-SYNC] Exception syncing Zoho item/batches: {e}")


def _push_puretrace_batch_to_zoho(link_id: str, product_details: Dict[str, Any]) -> None:
    """Background Task 2: PureTrace -> Zoho Books (.in) sync using link_id as SKU."""
    try:
        token = get_zoho_access_token()
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json",
        }
        params = {"organization_id": ZOHO_ORGANIZATION_ID}
        base_api = "https://www.zohoapis.in/books/v3"

        _recently_pushed_skus[str(link_id)] = time.time() + 15

        search_res = http_requests.get(
            f"{base_api}/items",
            headers=headers,
            params={**params, "sku": str(link_id)},
            timeout=15,
        )
        items = search_res.json().get("items", []) if search_res.ok else []
        existing_item = next((i for i in items if str(i.get("sku", "")).strip() == str(link_id)), None)

        try:
            rate = float(product_details.get("unit_sales_price") or product_details.get("mrp") or 0)
        except ValueError:
            rate = 0.0

        try:
            qty = float(product_details.get("quantity") or 0)
        except ValueError:
            qty = 0.0

        batch_number = str(product_details.get("batch_id") or f"BATCH-{link_id}")
        qty_unit = product_details.get("quantity_unit") or "pcs"

        mfg_date = str(product_details.get("mfg_date") or "")
        if len(mfg_date) == 7:
            mfg_date = f"{mfg_date}-01"

        expiry_date = str(product_details.get("expiry_date") or "")

        batch_summary = f"Batch: {batch_number} | Qty: {qty} {qty_unit}"
        if mfg_date:
            batch_summary += f" | Mfg: {mfg_date}"
        if expiry_date:
            batch_summary += f" | Exp: {expiry_date}"

        base_desc = (product_details.get("description") or "").strip()
        full_description = f"{base_desc}\n{batch_summary}".strip()

        item_payload: Dict[str, Any] = {
            "name": product_details.get("product_name") or f"PureTrace Product {link_id}",
            "sku": str(link_id),
            "description": full_description,
            "rate": rate,
            "unit": qty_unit,
        }

        if existing_item:
            item_id = existing_item["item_id"]
            resp = http_requests.put(
                f"{base_api}/items/{item_id}",
                headers=headers,
                params=params,
                json=item_payload,
                timeout=15,
            )
            action = "Updated"
        else:
            resp = http_requests.post(
                f"{base_api}/items",
                headers=headers,
                params=params,
                json=item_payload,
                timeout=15,
            )
            action = "Created"

        if resp.ok:
            logger.info(f"[PURETRACE->ZOHO] {action} Zoho SKU='{link_id}' with batch='{batch_number}'.")
        else:
            logger.error(f"[PURETRACE->ZOHO] Zoho API error ({resp.status_code}): {resp.text[:300]}")
    except Exception as e:
        logger.error(f"[PURETRACE->ZOHO] Exception pushing to Zoho: {e}")


@router.post("/webhook")
async def handle_zoho_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receives Zoho Inventory/Books webhooks and queues background sync (<200ms response)."""
    try:
        payload = await request.json()
    except Exception:
        try:
            form = await request.form()
            payload = dict(form)
            if "JSONString" in payload:
                payload = json.loads(payload["JSONString"])
        except Exception as e:
            logger.error(f"[ZOHO-WEBHOOK] Invalid payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid webhook payload")

    background_tasks.add_task(_process_zoho_batch_sync, payload)
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Zoho webhook queued for background sync."},
    )


@router.post("/sync-from-puretrace")
async def sync_from_puretrace(request: Request, background_tasks: BackgroundTasks):
    """Receives submitted form data from puretrace.html and syncs it to Zoho Books."""
    body = await request.json()
    link_id = str(body.get("link_id") or "").strip()
    product_details = body.get("product_details") or {}

    if not link_id or not product_details:
        raise HTTPException(status_code=400, detail="Missing link_id or product_details")

    background_tasks.add_task(_push_puretrace_batch_to_zoho, link_id, product_details)
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": f"Queued PureTrace SKU '{link_id}' for Zoho sync."},
    )


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