import os
import json
import uuid
import datetime
import logging
import tempfile
import subprocess
import requests as http_requests
import torch
from .gemini_sentiment_analysis import analyze_sentiment, calculate_fused_metrics

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

CRUD_BASE_URL = os.getenv("CRUD_BASE_URL", "https://datacube.uxlivinglab.online/api/v2")
CRUD_API_KEY = os.getenv("FEEDBACK_CRUD_API_KEY", "")
MASTER_DATABASE_ID = "695ce92eff84eaf663c457c2"
S3_UPLOAD_API = "https://medsignqr.uxlivinglab.org/api/v1/transcription/upload-to-s3"
TRANSCRIPTION_API = "https://medsignqr.uxlivinglab.org/api/v1/transcription/transcribe"
AUDIO_ANALYSIS_API_URL = "http://audio-analysis:8003/api/analyze-audio/"


def _resolve_collection_by_qr_id(qr_id: str, default_client: str = "") -> str:
    """
    Extracts the first 4 characters/digits from the QR ID to serve as the collection name.
    Example: '100935c2f1ffd5d5' -> '1009'
    """
    if qr_id and len(qr_id.strip()) >= 4:
        return qr_id.strip()[:4]

    if qr_id and qr_id.strip():
        return qr_id.strip()

    if default_client and default_client.strip():
        return default_client.lower().strip().replace(" ", "_")

    return "0000"


def _convert_webm_to_wav(webm_bytes: bytes) -> tuple[bytes, str]:
    file_id = f"product-feedback-{uuid.uuid4().hex[:12]}"
    tmp_dir = tempfile.gettempdir()
    in_path = os.path.join(tmp_dir, f"{file_id}.webm")
    out_path = os.path.join(tmp_dir, f"{file_id}.wav")

    try:
        with open(in_path, "wb") as f:
            f.write(webm_bytes)

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", in_path,
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                out_path,
            ],
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"[PRODUCT_FEEDBACK] ffmpeg error: {result.stderr.decode()}")
            raise RuntimeError(f"ffmpeg conversion failed: {result.stderr.decode()[:200]}")

        with open(out_path, "rb") as f:
            wav_bytes = f.read()

        return wav_bytes, file_id

    finally:
        for path in [in_path, out_path]:
            try:
                os.remove(path)
            except Exception:
                pass


def _save_to_datacube(
    id_param: str,
    batch_id: str,
    product_name: str,
    description: str,
    file_id: str,
    client_name: str = "",
    location: dict = None,
    emotion_metrics: dict = None,
    raw_emotion_distribution: dict = None,
    fused_metrics: dict = None,
    transcript: str = "",
    transcript_analysis: dict = None
) -> str:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID:
        logger.warning("[PRODUCT_FEEDBACK] Datacube credentials missing, skipping save")
        return ""

    collection_name = _resolve_collection_by_qr_id(qr_id=id_param, default_client=client_name)

    try:
        doc_data = {
            "type": "product_feedback",
            "qr_id": id_param,
            "client_name": client_name,
            "product_name": product_name,
            "batch_id": batch_id,
            "description": description,
            "location": location or {},
            "transcript": transcript,
            "transcript_analysis": transcript_analysis or {},
            "audio_file": f"{file_id}.wav",
            "audio_analysis": emotion_metrics or {},
            "raw_emotion_distribution": raw_emotion_distribution or {},
            "dashboard_metrics": fused_metrics,
            "submitted_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
        }

        target_url = f"{CRUD_BASE_URL.rstrip('/')}/crud/"

        resp = http_requests.post(
            target_url,
            json={
                "database_id": MASTER_DATABASE_ID,
                "collection_name": collection_name,
                "documents": [doc_data],
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {CRUD_API_KEY}",
            },
            timeout=10,
        )
        
        res_data = resp.json() if resp.status_code in (200, 201) else {}
        if resp.status_code in (200, 201) and res_data.get("success", True):
            inserted_ids = res_data.get("inserted_ids", [])
            return inserted_ids[0] if inserted_ids else ""
        else:
            logger.warning(f"[PRODUCT_FEEDBACK] Datacube save failed {resp.status_code}: {resp.text[:200]}")
            return ""
    except Exception as e:
        logger.error(f"[PRODUCT_FEEDBACK] Datacube save error: {e}")
        return ""


def _update_datacube_transcription(
    id_param: str,
    doc_id: str,
    transcript: str,
    transcript_analysis: dict,
    client_name: str = "",
    fused_metrics: dict = None
) -> bool:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID or not doc_id:
        return False

    collection_name = _resolve_collection_by_qr_id(qr_id=id_param, default_client=client_name)

    try:
        target_url = f"{CRUD_BASE_URL.rstrip('/')}/crud/"

        payload = {
            "database_id": MASTER_DATABASE_ID,
            "collection_name": collection_name,
            "filters": {"_id": doc_id},
            "update_data": {
                "transcript": transcript,
                "transcript_analysis": transcript_analysis,
                "dashboard_metrics": fused_metrics
            },
            "update_all_fields": False,
            "update_many": False,
            "upsert": False
        }

        resp = http_requests.put(
            target_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {CRUD_API_KEY}",
            },
            timeout=10
        )

        return bool(resp.status_code in (200, 201) and resp.json().get("success"))

    except Exception as e:
        logger.error(f"[PRODUCT_FEEDBACK] Datacube update error: {e}")
        return False


def _get_datacube_doc(id_param: str, doc_id: str, client_name: str = "") -> dict:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID or not doc_id:
        return {}
    collection_name = _resolve_collection_by_qr_id(qr_id=id_param, default_client=client_name)
    try:
        target_url = f"{CRUD_BASE_URL.rstrip('/')}/crud/"
        payload = {
            "database_id": MASTER_DATABASE_ID,
            "collection_name": collection_name,
            "filters": {"_id": doc_id}
        }
        resp = http_requests.post(
            target_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {CRUD_API_KEY}",
            },
            timeout=10
        )
        if resp.status_code in (200, 201):
            docs = resp.json().get("documents", [])
            return docs[0] if docs else {}
    except Exception as e:
        logger.error(f"[PRODUCT_FEEDBACK] Error fetching Datacube doc: {e}")
    return {}


@router.post("/submit")
async def submit_product_feedback(
    request: Request,
    audio: UploadFile = File(...),
    batch_id: str = Form(default=""),
    product_name: str = Form(default=""),
    description: str = Form(default=""),
    client_name: str = Form(default=""),
    file_id: str = Form(default=""),
    latitude: str = Form(default=None),
    longitude: str = Form(default=None),
):
    try:
        id_param = request.query_params.get("id", "")

        if not client_name:
            client_name = request.query_params.get("client", "") or request.query_params.get("client_name", "")

        webm_bytes = await audio.read()
        if not webm_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")

        wav_bytes, new_file_id = _convert_webm_to_wav(webm_bytes)
        final_file_id = file_id or new_file_id

        emotion_data = None
        raw_emotions = None

        user_location = None
        if latitude and longitude:
            try:
                user_location = {
                    "latitude": float(latitude),
                    "longitude": float(longitude)
                }
            except ValueError:
                logger.warning("[PRODUCT_FEEDBACK] Invalid location received")

        try:
            feedback_resp = http_requests.post(
                AUDIO_ANALYSIS_API_URL,
                files={"audio_file": (f"{final_file_id}.wav", wav_bytes, "audio/wav")},
                timeout=120,
            )
            if feedback_resp.status_code == 200:
                res_json = feedback_resp.json()
                if res_json.get("status") == "success":
                    emotion_data = res_json.get("dashboard_metrics")
                    raw_emotions = res_json.get("raw_emotion_distribution")
        except Exception as e:
            logger.warning(f"[PRODUCT_FEEDBACK] Audio analysis error: {e}")

        fused_metrics = None
        if emotion_data:
            fused_metrics = calculate_fused_metrics(
                text_sentiment="NEUTRAL",
                text_score=0.0,
                audio_emotion=emotion_data.get("dominant_emotion", "calm"),
                audio_score=emotion_data.get("audio_score", 0.0)
            )

        doc_id = _save_to_datacube(
            id_param=id_param,
            batch_id=batch_id,
            product_name=product_name,
            description=description,
            client_name=client_name,
            location=user_location,
            file_id=final_file_id,
            emotion_metrics=emotion_data,
            raw_emotion_distribution=raw_emotions,
            fused_metrics=fused_metrics,
            transcript="",
            transcript_analysis={}
        )

        return JSONResponse({
            "success": True,
            "message": "Product feedback received successfully.",
            "file_id": final_file_id,
            "doc_id": doc_id
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PRODUCT_FEEDBACK] Submit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe-lazy")
async def transcribe_on_demand(
    request: Request,
    audio: UploadFile = File(...),
    doc_id: str = Form(default=""),
    description: str = Form(default=""),
    file_id: str = Form(default=""),
    client_name: str = Form(default=""),
):
    try:
        id_param = request.query_params.get("id", "")
        if not client_name:
            client_name = request.query_params.get("client", "") or request.query_params.get("client_name", "")

        webm_bytes = await audio.read()
        if not webm_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")

        wav_bytes, new_file_id = _convert_webm_to_wav(webm_bytes)
        final_file_id = file_id or new_file_id

        try:
            upload_resp = http_requests.post(
                S3_UPLOAD_API,
                files={"file": (f"{final_file_id}.wav", wav_bytes, "audio/wav")},
                data={"fileName": final_file_id},
                timeout=60,
            )
            if not (upload_resp.status_code == 200 and upload_resp.json().get("success")):
                raise HTTPException(status_code=502, detail="Failed to upload audio to S3")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"S3 upload failed: {e}")

        transcript = ""
        try:
            trans_resp = http_requests.post(
                TRANSCRIPTION_API,
                json={"fileName": final_file_id, "format": "wav"},
                timeout=120,
            )
            if trans_resp.status_code == 200 and trans_resp.json().get("success"):
                transcript = trans_resp.json().get("data", {}).get("transcript", "")
        except Exception as e:
            logger.warning(f"[PRODUCT_FEEDBACK] Transcription error: {e}")

        gemini_api_key = os.getenv("GEMINI_KEY_2") or os.getenv("GEMINI_KEY_1")
        transcript_analysis = analyze_sentiment(gemini_api_key, transcript)

        doc_data = _get_datacube_doc(id_param, doc_id, client_name=client_name) if doc_id else {}
        audio_analysis = doc_data.get("audio_analysis", {})

        fused_metrics = calculate_fused_metrics(
            text_sentiment=transcript_analysis.get("label", "neutral"),
            text_score=transcript_analysis.get("confidence_score", 0.0),
            audio_emotion=audio_analysis.get("dominant_emotion", "calm"),
            audio_score=audio_analysis.get("audio_score", 0.0)
        )

        if doc_id:
            _update_datacube_transcription(
                id_param=id_param,
                doc_id=doc_id,
                transcript=transcript,
                transcript_analysis=transcript_analysis,
                client_name=client_name,
                fused_metrics=fused_metrics
            )

        return JSONResponse({
            "success": True,
            "transcript": transcript,
            "transcript_analysis": transcript_analysis,
            "dashboard_metrics": fused_metrics,
            "file_id": final_file_id,
            "doc_id": doc_id
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PRODUCT_FEEDBACK] Transcribe endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))