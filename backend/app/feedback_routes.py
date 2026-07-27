"""
feedback_routes.py
------------------
Guest feedback route for hotel QR code form.
Route prefix: /api/feedback

Flow:
1. POST /api/feedback/transcribe
   - Receives WebM audio blob + room number + description
   - Converts WebM → WAV via ffmpeg (server-side)
   - Calls transcription API (Amazon Transcribe via medsignqr.uxlivinglab.org)
   - Returns transcript to frontend for guest confirmation

2. POST /api/feedback/submit
   - Reads the 'id' query parameter directly from URL (e.g. ?id=198239)
   - Analyzes transcript (sentiment, categorization, summary, urgency)
   - Forwards WAV file to Django Audio Analytics API
   - Saves all data (room number, description, raw transcript, text analysis, audio analysis, QR ID) to Datacube
   - Datacube Target Database: MASTER_DATABASE_ID = 695ce92eff84eaf663c457c2
   - Collection Name: Last 4 digits of QR ID parameter (e.g., ?id=198239 -> collection 8239)
   - Returns success response
"""

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

# ── Config ────────────────────────────────────────────────────────────────────
CRUD_BASE_URL       = os.getenv("CRUD_BASE_URL", "https://datacube.uxlivinglab.online/api/v2")
CRUD_API_KEY        = os.getenv("CRUD_API_KEY", "")
MASTER_DATABASE_ID         = "695ce92eff84eaf663c457c2"  # Master Database ID
S3_UPLOAD_API       = "https://medsignqr.uxlivinglab.org/api/v1/transcription/upload-to-s3"
TRANSCRIPTION_API  = "https://medsignqr.uxlivinglab.org/api/v1/transcription/transcribe"

# Audio Analytics Service URL
AUDIO_ANALYSIS_API_URL = "http://audio-analysis:8003/analyze-audio/"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_collection_name(id_param: str) -> str:
    """
    Extract last 4 digits of the ID parameter.
    Defaults to '0000' if missing or less than 4 digits.
    """
    clean_id = "".join(filter(str.isdigit, str(id_param or "")))
    if len(clean_id) >= 4:
        return clean_id[-4:]
    return "0000"


def _convert_webm_to_wav(webm_bytes: bytes) -> tuple[bytes, str]:
    """
    Convert WebM/Opus audio bytes to WAV using ffmpeg.
    Returns (wav_bytes, filename_without_extension).
    """
    file_id  = f"feedback-{uuid.uuid4().hex[:12]}"
    tmp_dir  = tempfile.gettempdir()
    in_path  = os.path.join(tmp_dir, f"{file_id}.webm")
    out_path = os.path.join(tmp_dir, f"{file_id}.wav")

    try:
        with open(in_path, "wb") as f:
            f.write(webm_bytes)

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", in_path,
                "-ar", "16000",      # 16kHz sample rate
                "-ac", "1",          # mono
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


def _analyze_transcript(transcript: str, description: str) -> dict:
    """
    Analyze the feedback transcript text (sentiment, issue categorization, summary, urgency).
    """
    combined_text = f"{description}. {transcript}".strip().lower()

    # 1. Sentiment analysis
    if any(word in combined_text for word in ["bad", "poor", "dirty", "loud", "broken", "terrible", "slow", "unacceptable"]):
        sentiment = "Negative"
    elif any(word in combined_text for word in ["great", "good", "excellent", "loved", "friendly", "clean", "wonderful"]):
        sentiment = "Positive"
    else:
        sentiment = "Neutral"

    # 2. Category tagging
    category = "General"
    if any(word in combined_text for word in ["ac", "air", "light", "tv", "shower", "bed", "room", "clean", "housekeeping"]):
        category = "Housekeeping / Room Amenities"
    elif any(word in combined_text for word in ["food", "breakfast", "dinner", "restaurant", "buffet"]):
        category = "Food & Beverage"
    elif any(word in combined_text for word in ["desk", "staff", "check-in", "reception", "service"]):
        category = "Front Desk / Service"

    # 3. Urgency score
    urgency_score = 1
    if sentiment == "Negative":
        urgency_score = 4 if any(word in combined_text for word in ["immediately", "now", "broken", "unacceptable"]) else 3

    return {
        "sentiment": sentiment,
        "category": category,
        "urgency_score": urgency_score,
        "summary": transcript[:150] + ("..." if len(transcript) > 150 else "")
    }


def _save_to_datacube(
    id_param: str,
    room_number: str,
    description: str,
    transcript: str,
    file_id: str,
    emotion_metrics: dict = None,
    transcript_analysis: dict = None
):
    """
    Saves guest feedback, transcripts, transcript analysis, and audio analysis response 
    all together in Datacube once processing completes.
    """
    if not CRUD_API_KEY or not MASTER_DATABASE_ID:
        logger.warning(f"[FEEDBACK] Datacube credentials not set (key_set={bool(CRUD_API_KEY)}, db_set={bool(MASTER_DATABASE_ID)}) — skipping save")
        return

    collection_name = _get_collection_name(id_param)

    try:
        doc_data = {
            "qr_id":               id_param,
            "room_number":         room_number,
            "description":         description,
            "transcript":          transcript,
            "transcript_analysis": transcript_analysis or {},
            "audio_file":          f"{file_id}.wav",
            "audio_analysis":      emotion_metrics or {},
            "submitted_at":        datetime.datetime.utcnow().isoformat() + "Z",
        }

        # Fix 1: Target the specific /add/ action endpoint
        target_url = f"{CRUD_BASE_URL.rstrip('/')}/crud/add/"

        resp = http_requests.post(
            target_url,
            json={
                "database_id":     MASTER_DATABASE_ID,
                "collection_name": collection_name,
                "documents":       [doc_data],
            },
            headers={
                "Content-Type":  "application/json",
                # Fix 2: Provide both x-api-key and Bearer header formats for maximum API compatibility
                "x-api-key":     CRUD_API_KEY,
                "Authorization": f"Bearer {CRUD_API_KEY}",
            },
            timeout=10,
        )
        
        # Check HTTP status code as well as application-level response status
        res_data = resp.json() if resp.status_code in (200, 201) else {}
        if resp.status_code in (200, 201) and res_data.get("success", True):
            logger.info(f"[FEEDBACK] Saved all data to Datacube — db={MASTER_DATABASE_ID}, collection={collection_name}, room={room_number}")
        else:
            logger.warning(f"[FEEDBACK] Datacube save failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"[FEEDBACK] Datacube save error: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    room_number: str  = Form(default=""),
    description: str  = Form(default=""),
):
    """
    Step 1: Receive audio blob, convert to WAV, call transcription API.
    Returns transcript for guest to confirm before final submission.
    """
    try:
        webm_bytes = await audio.read()
        if not webm_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")

        logger.info(f"[FEEDBACK] Received audio — {len(webm_bytes)} bytes, room={room_number}")

        # Convert WebM → WAV
        wav_bytes, file_id = _convert_webm_to_wav(webm_bytes)

        # Step 1 — Upload WAV to S3
        try:
            upload_resp = http_requests.post(
                S3_UPLOAD_API,
                files={"file": (f"{file_id}.wav", wav_bytes, "audio/wav")},
                data={"fileName": file_id},
                timeout=60,
            )
            if upload_resp.status_code == 200 and upload_resp.json().get("success"):
                logger.info(f"[FEEDBACK] Uploaded to S3 — file_id={file_id}")
            else:
                logger.error(f"[FEEDBACK] S3 upload failed: {upload_resp.text[:200]}")
                raise HTTPException(status_code=502, detail="Failed to upload audio to S3")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[FEEDBACK] S3 upload error: {e}")
            raise HTTPException(status_code=502, detail=f"S3 upload failed: {e}")

        # Step 2 — Transcribe from S3
        try:
            trans_resp = http_requests.post(
                TRANSCRIPTION_API,
                json={"fileName": file_id, "format": "wav"},
                timeout=120,
            )
            if trans_resp.status_code == 200 and trans_resp.json().get("success"):
                transcript = trans_resp.json().get("data", {}).get("transcript", "")
            else:
                logger.warning(f"[FEEDBACK] Transcription failed: {trans_resp.text[:200]}")
                transcript = ""
        except Exception as e:
            logger.warning(f"[FEEDBACK] Transcription error (non-fatal): {e}")
            transcript = ""

        return JSONResponse({
            "success":    True,
            "transcript": transcript,
            "file_id":    file_id,
            "wav_size":   len(wav_bytes),
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FEEDBACK] Transcribe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit")
async def submit_feedback(
    request: Request,
    audio: UploadFile = File(...),
    room_number: str  = Form(default=""),
    description: str  = Form(default=""),
    transcript:  str  = Form(default=""),
    file_id:     str  = Form(default=""),
):
    """
    Step 2: Guest has confirmed transcript. Submit feedback.
    - Extracts 'id' parameter from query params (URL)
    - Performs text analysis on transcript
    - Sends WAV file to Audio Analytics Service
    - Once analysis succeeds, saves ALL data together in Datacube
    """
    try:
        # Extract query parameter 'id' directly from URL (e.g., ?id=198239)
        id_param = request.query_params.get("id", "")

        webm_bytes = await audio.read()
        if not webm_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")

        # Convert to WAV
        wav_bytes, new_file_id = _convert_webm_to_wav(webm_bytes)
        final_file_id = file_id or new_file_id

        # 1. Perform Transcript Text Analysis
        transcript_analysis = _analyze_transcript(transcript, description)

        # 2. Call Audio Analytics API
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
            logger.info(f"[FEEDBACK] Audio Analytics API response: {feedback_resp.status_code}")
        except Exception as e:
            logger.warning(f"[FEEDBACK] Audio Analytics API error (non-fatal): {e}")

        # 3. Save Everything Together into Datacube
        _save_to_datacube(
            id_param=id_param,
            room_number=room_number,
            description=description,
            transcript=transcript,
            file_id=final_file_id,
            emotion_metrics=emotion_data,
            transcript_analysis=transcript_analysis
        )

        return JSONResponse({
            "success": True,
            "message": "Thank you for your feedback.",
            "file_id": final_file_id,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FEEDBACK] Submit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))