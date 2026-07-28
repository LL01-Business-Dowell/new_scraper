import os
import uuid
import datetime
import logging
import tempfile
import subprocess
import requests as http_requests

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

CRUD_BASE_URL = os.getenv("CRUD_BASE_URL", "https://datacube.uxlivinglab.online/api/v2")
CRUD_API_KEY = os.getenv("CRUD_API_KEY", "")
MASTER_DATABASE_ID = "695ce92eff84eaf663c457c2"
S3_UPLOAD_API = "https://medsignqr.uxlivinglab.org/api/v1/transcription/upload-to-s3"
TRANSCRIPTION_API = "https://medsignqr.uxlivinglab.org/api/v1/transcription/transcribe"
AUDIO_ANALYSIS_API_URL = "http://audio-analysis:8003/api/analyze-audio/"

# Hugging Face Configuration
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")
HF_MODEL_URL = os.getenv(
    "HF_MODEL_URL", 
    "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest"
)


def _get_collection_name(id_param: str) -> str:
    clean_id = "".join(filter(str.isdigit, str(id_param or "")))
    if len(clean_id) >= 4:
        return clean_id[-4:]
    return "0000"


def _convert_webm_to_wav(webm_bytes: bytes) -> tuple[bytes, str]:
    file_id = f"feedback-{uuid.uuid4().hex[:12]}"
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
            logger.error(f"[FEEDBACK] ffmpeg error: {result.stderr.decode()}")
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


def _analyze_transcript_fallback(transcript: str, description: str) -> dict:
    combined_text = f"{description}. {transcript}".strip().lower()

    if any(word in combined_text for word in ["bad", "poor", "dirty", "loud", "broken", "terrible", "slow", "unacceptable"]):
        sentiment = "Negative"
    elif any(word in combined_text for word in ["great", "good", "excellent", "loved", "friendly", "clean", "wonderful"]):
        sentiment = "Positive"
    else:
        sentiment = "Neutral"

    category = "General"
    if any(word in combined_text for word in ["ac", "air", "light", "tv", "shower", "bed", "room", "clean", "housekeeping"]):
        category = "Housekeeping / Room Amenities"
    elif any(word in combined_text for word in ["food", "breakfast", "dinner", "restaurant", "buffet"]):
        category = "Food & Beverage"
    elif any(word in combined_text for word in ["desk", "staff", "check-in", "reception", "service"]):
        category = "Front Desk / Service"

    urgency_score = 1
    if sentiment == "Negative":
        urgency_score = 4 if any(word in combined_text for word in ["immediately", "now", "broken", "unacceptable"]) else 3

    return {
        "sentiment": sentiment,
        "category": category,
        "urgency_score": urgency_score,
        "summary": transcript[:150] + ("..." if len(transcript) > 150 else "")
    }


def _analyze_transcript_huggingface(transcript: str, description: str) -> dict:
    combined_text = f"{description}. {transcript}".strip()
    if not combined_text or not HUGGINGFACE_API_KEY:
        return _analyze_transcript_fallback(transcript, description)

    try:
        headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
        payload = {"inputs": combined_text[:512]}

        resp = http_requests.post(HF_MODEL_URL, headers=headers, json=payload, timeout=10)
        
        if resp.status_code == 200:
            predictions = resp.json()
            if isinstance(predictions, list) and len(predictions) > 0:
                top_pred = predictions[0][0] if isinstance(predictions[0], list) else predictions[0]
                raw_label = top_pred.get("label", "Neutral").lower()

                if "pos" in raw_label:
                    sentiment = "Positive"
                elif "neg" in raw_label:
                    sentiment = "Negative"
                else:
                    sentiment = "Neutral"

                fallback_data = _analyze_transcript_fallback(transcript, description)

                return {
                    "sentiment": sentiment,
                    "category": fallback_data["category"],
                    "urgency_score": 4 if sentiment == "Negative" else 1,
                    "summary": transcript[:150] + ("..." if len(transcript) > 150 else ""),
                    "confidence_score": round(top_pred.get("score", 0.0), 4)
                }
        else:
            logger.warning(f"[FEEDBACK] HuggingFace inference status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"[FEEDBACK] HuggingFace inference error, using fallback: {e}")

    return _analyze_transcript_fallback(transcript, description)


def _save_to_datacube(
    id_param: str,
    room_number: str,
    description: str,
    file_id: str,
    emotion_metrics: dict = None,
    transcript: str = "",
    transcript_analysis: dict = None
) -> str:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID:
        logger.warning("[FEEDBACK] Datacube credentials missing, skipping save")
        return ""

    collection_name = _get_collection_name(id_param)

    try:
        doc_data = {
            "qr_id": id_param,
            "room_number": room_number,
            "description": description,
            "transcript": transcript,
            "transcript_analysis": transcript_analysis or {},
            "audio_file": f"{file_id}.wav",
            "audio_analysis": emotion_metrics or {},
            "submitted_at": datetime.datetime.utcnow().isoformat() + "Z",
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
            doc_id = inserted_ids[0] if inserted_ids else ""
            logger.info(f"[FEEDBACK] Datacube document created: db={MASTER_DATABASE_ID}, collection={collection_name}, doc_id={doc_id}")
            return doc_id
        else:
            logger.warning(f"[FEEDBACK] Datacube save failed {resp.status_code}: {resp.text[:200]}")
            return ""
    except Exception as e:
        logger.error(f"[FEEDBACK] Datacube save error: {e}")
        return ""


def _update_datacube_transcription(
    id_param: str,
    doc_id: str,
    transcript: str,
    transcript_analysis: dict
) -> bool:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID or not doc_id:
        logger.warning("[FEEDBACK] Missing parameters for Datacube update")
        return False

    collection_name = _get_collection_name(id_param)

    try:
        target_url = f"{CRUD_BASE_URL.rstrip('/')}/crud/"

        payload = {
            "database_id": MASTER_DATABASE_ID,
            "collection_name": collection_name,
            "filters": {
                "_id": doc_id
            },
            "update_data": {
                "transcript": transcript,
                "transcript_analysis": transcript_analysis
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

        if resp.status_code in (200, 201) and resp.json().get("success"):
            logger.info(f"[FEEDBACK] Datacube document updated: doc_id={doc_id}")
            return True
        else:
            logger.warning(f"[FEEDBACK] Datacube update failed {resp.status_code}: {resp.text[:200]}")
            return False

    except Exception as e:
        logger.error(f"[FEEDBACK] Datacube update error: {e}")
        return False


@router.post("/submit")
async def submit_feedback(
    request: Request,
    audio: UploadFile = File(...),
    room_number: str = Form(default=""),
    description: str = Form(default=""),
    file_id: str = Form(default=""),
):
    try:
        id_param = request.query_params.get("id", "")

        webm_bytes = await audio.read()
        if not webm_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")

        wav_bytes, new_file_id = _convert_webm_to_wav(webm_bytes)
        final_file_id = file_id or new_file_id

        emotion_data = None
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
            logger.info(f"[FEEDBACK] Audio analysis response status: {feedback_resp.status_code}")
        except Exception as e:
            logger.warning(f"[FEEDBACK] Audio analysis error (non-fatal): {e}")

        doc_id = _save_to_datacube(
            id_param=id_param,
            room_number=room_number,
            description=description,
            file_id=final_file_id,
            emotion_metrics=emotion_data,
            transcript="",
            transcript_analysis={}
        )

        return JSONResponse({
            "success": True,
            "message": "Thank you for your feedback.",
            "file_id": final_file_id,
            "doc_id": doc_id
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FEEDBACK] Submit endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe-lazy")
async def transcribe_on_demand(
    request: Request,
    audio: UploadFile = File(...),
    doc_id: str = Form(default=""),
    description: str = Form(default=""),
    file_id: str = Form(default=""),
):
    try:
        id_param = request.query_params.get("id", "")

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
            if upload_resp.status_code == 200 and upload_resp.json().get("success"):
                logger.info(f"[FEEDBACK] S3 upload successful: file_id={final_file_id}")
            else:
                logger.error(f"[FEEDBACK] S3 upload failed: {upload_resp.text[:200]}")
                raise HTTPException(status_code=502, detail="Failed to upload audio to S3")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[FEEDBACK] S3 upload error: {e}")
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
            else:
                logger.warning(f"[FEEDBACK] Transcription failed: {trans_resp.text[:200]}")
        except Exception as e:
            logger.warning(f"[FEEDBACK] Transcription error (non-fatal): {e}")

        transcript_analysis = _analyze_transcript_huggingface(transcript, description)

        if doc_id:
            _update_datacube_transcription(
                id_param=id_param,
                doc_id=doc_id,
                transcript=transcript,
                transcript_analysis=transcript_analysis
            )

        return JSONResponse({
            "success": True,
            "transcript": transcript,
            "transcript_analysis": transcript_analysis,
            "file_id": final_file_id,
            "doc_id": doc_id
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FEEDBACK] Transcribe-lazy endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))