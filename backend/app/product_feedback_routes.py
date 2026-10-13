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

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
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
                "ffmpeg",
                "-y",
                "-i",
                in_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                out_path,
            ],
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"[PRODUCT_FEEDBACK] ffmpeg error: {result.stderr.decode()}")
            raise RuntimeError(
                f"ffmpeg conversion failed: {result.stderr.decode()[:200]}"
            )

        with open(out_path, "rb") as f:
            wav_bytes = f.read()

        return wav_bytes, file_id

    finally:
        for path in [in_path, out_path]:
            try:
                os.remove(path)
            except Exception:
                pass


def _upload_file_to_gridfs(wav_bytes: bytes, filename: str) -> str:
    """
    Uploads audio binary directly to DataCube GridFS storage via POST /api/v2/files/
    """
    if not CRUD_API_KEY:
        logger.warning("[PRODUCT_FEEDBACK] API Key missing, skipping GridFS upload")
        return ""

    files_url = f"{CRUD_BASE_URL.rstrip('/')}/files/"
    headers = {"Authorization": f"Api-Key {CRUD_API_KEY}"}

    try:
        resp = http_requests.post(
            files_url,
            headers=headers,
            files={"file": (f"{filename}.wav", wav_bytes, "audio/wav")},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            res_data = resp.json()
            if res_data.get("success"):
                gridfs_id = res_data.get("file_id", "")
                logger.info(f"[PRODUCT_FEEDBACK] Uploaded audio to GridFS: {gridfs_id}")
                return gridfs_id
        logger.warning(
            f"[PRODUCT_FEEDBACK] GridFS upload failed {resp.status_code}: {resp.text[:200]}"
        )
    except Exception as e:
        logger.error(f"[PRODUCT_FEEDBACK] GridFS upload error: {e}")

    return ""


def _save_to_datacube(
    id_param: str,
    batch_id: str,
    product_name: str,
    description: str,
    rating: int,
    file_id: str,
    gridfs_file_id: str = "",
    client_name: str = "",
    location: dict = None,
    emotion_metrics: dict = None,
    raw_emotion_distribution: dict = None,
    fused_metrics: dict = None,
    transcript: str = "",
    transcript_analysis: dict = None,
) -> str:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID:
        logger.warning("[PRODUCT_FEEDBACK] Datacube credentials missing, skipping save")
        return ""

    collection_name = _resolve_collection_by_qr_id(
        qr_id=id_param, default_client=client_name
    )

    try:
        doc_data = {
            "type": "product_feedback",
            "qr_id": id_param,
            "client_name": client_name,
            "product_name": product_name,
            "batch_id": batch_id,
            "rating": rating,
            "description": description,
            "location": location or {},
            "transcript": transcript,
            "transcript_analysis": transcript_analysis or {},
            "audio_file": f"{file_id}.wav",
            "gridfs_file_id": gridfs_file_id,
            "audio_analysis": emotion_metrics or {},
            "raw_emotion_distribution": raw_emotion_distribution or {},
            "dashboard_metrics": fused_metrics or {},
            "submitted_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            + "Z",
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
            logger.warning(
                f"[PRODUCT_FEEDBACK] Datacube save failed {resp.status_code}: {resp.text[:200]}"
            )
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
    fused_metrics: dict = None,
    emotion_metrics: dict = None,
    raw_emotion_distribution: dict = None,
) -> bool:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID or not doc_id:
        return False

    collection_name = _resolve_collection_by_qr_id(
        qr_id=id_param, default_client=client_name
    )

    try:
        target_url = f"{CRUD_BASE_URL.rstrip('/')}/crud/"

        update_fields = {
            "transcript": transcript,
            "transcript_analysis": transcript_analysis,
        }
        if fused_metrics:
            update_fields["dashboard_metrics"] = fused_metrics
        if emotion_metrics:
            update_fields["audio_analysis"] = emotion_metrics
        if raw_emotion_distribution:
            update_fields["raw_emotion_distribution"] = raw_emotion_distribution

        payload = {
            "database_id": MASTER_DATABASE_ID,
            "collection_name": collection_name,
            "filters": {"_id": doc_id},
            "update_data": update_fields,
            "update_all_fields": False,
            "update_many": False,
            "upsert": False,
        }

        resp = http_requests.put(
            target_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {CRUD_API_KEY}",
            },
            timeout=10,
        )

        return bool(resp.status_code in (200, 201) and resp.json().get("success"))

    except Exception as e:
        logger.error(f"[PRODUCT_FEEDBACK] Datacube update error: {e}")
        return False


def _process_audio_pipeline_async(
    doc_id: str,
    id_param: str,
    client_name: str,
    final_file_id: str,
    wav_bytes: bytes,
):
    """
    Background worker that runs emotion analysis, S3 upload, transcription,
    and Gemini sentiment analysis, then updates the Datacube document.
    """
    logger.info(f"[PRODUCT_FEEDBACK] Background task started for doc_id: {doc_id}")

    # 1. Audio Emotion Analysis
    emotion_data = None
    raw_emotions = None
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
        logger.warning(f"[PRODUCT_FEEDBACK] Async Audio analysis error: {e}")

    # 2. Upload Audio to S3
    try:
        upload_resp = http_requests.post(
            S3_UPLOAD_API,
            files={"file": (f"{final_file_id}.wav", wav_bytes, "audio/wav")},
            data={"fileName": final_file_id},
            timeout=60,
        )
        if not (upload_resp.status_code == 200 and upload_resp.json().get("success")):
            logger.warning("[PRODUCT_FEEDBACK] Async S3 upload failed")
    except Exception as e:
        logger.warning(f"[PRODUCT_FEEDBACK] Async S3 upload error: {e}")

    # 3. Audio Transcription
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
        logger.warning(f"[PRODUCT_FEEDBACK] Async Transcription error: {e}")

    # 4. Gemini Sentiment Analysis
    transcript_analysis = {}
    if transcript:
        gemini_api_key = os.getenv("GEMINI_KEY_2") or os.getenv("GEMINI_KEY_1")
        transcript_analysis = analyze_sentiment(gemini_api_key, transcript)

    # 5. Metric Fusion
    fused_metrics = calculate_fused_metrics(
        text_sentiment=transcript_analysis.get("label", "NEUTRAL"),
        text_score=transcript_analysis.get("confidence_score", 0.0),
        audio_emotion=(
            emotion_data.get("dominant_emotion", "calm") if emotion_data else "calm"
        ),
        audio_score=emotion_data.get("audio_score", 0.0) if emotion_data else 0.0,
    )

    # 6. Update Datacube record with analysis results
    if doc_id:
        _update_datacube_transcription(
            id_param=id_param,
            doc_id=doc_id,
            transcript=transcript,
            transcript_analysis=transcript_analysis,
            client_name=client_name,
            fused_metrics=fused_metrics,
            emotion_metrics=emotion_data,
            raw_emotion_distribution=raw_emotions,
        )
        logger.info(f"[PRODUCT_FEEDBACK] Async processing complete for doc_id: {doc_id}")


@router.post("/submit")
async def submit_product_feedback(
    request: Request,
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    batch_id: str = Form(default=""),
    product_name: str = Form(default=""),
    description: str = Form(default=""),
    rating: int = Form(default=0),
    client_name: str = Form(default=""),
    file_id: str = Form(default=""),
    latitude: str = Form(default=None),
    longitude: str = Form(default=None),
):
    try:
        id_param = request.query_params.get("id", "")

        if not client_name:
            client_name = request.query_params.get(
                "client", ""
            ) or request.query_params.get("client_name", "")

        webm_bytes = await audio.read()
        if not webm_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")

        wav_bytes, new_file_id = _convert_webm_to_wav(webm_bytes)
        final_file_id = file_id or new_file_id

        user_location = None
        if latitude and longitude:
            try:
                user_location = {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                }
            except ValueError:
                logger.warning("[PRODUCT_FEEDBACK] Invalid location received")

        # 1. Store Audio Binary directly to DataCube GridFS
        gridfs_file_id = _upload_file_to_gridfs(wav_bytes, final_file_id)

        # 2. Save Initial Record into DataCube (Immediate)
        doc_id = _save_to_datacube(
            id_param=id_param,
            batch_id=batch_id,
            product_name=product_name,
            description=description,
            rating=rating,
            client_name=client_name,
            location=user_location,
            file_id=final_file_id,
            gridfs_file_id=gridfs_file_id,
        )

        # 3. Queue Background Processing (Audio Analysis, S3 Upload, Transcription, Gemini Sentiment)
        background_tasks.add_task(
            _process_audio_pipeline_async,
            doc_id=doc_id,
            id_param=id_param,
            client_name=client_name,
            final_file_id=final_file_id,
            wav_bytes=wav_bytes,
        )

        # 4. Immediate response to user
        return JSONResponse(
            {
                "success": True,
                "message": "Product feedback received successfully.",
                "file_id": final_file_id,
                "gridfs_file_id": gridfs_file_id,
                "doc_id": doc_id,
                "rating": rating,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PRODUCT_FEEDBACK] Submit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))