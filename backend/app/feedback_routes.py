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
   - Receives confirmed transcript + room number + description + audio
   - Calls dummy feedback API with WAV file
   - Saves room number + description + transcript to Datacube
   - Returns success/error

Env vars used:
  CRUD_BASE_URL       — Datacube base URL
  CRUD_API_KEY        — Datacube API key
  SAMANTA_DATABASE_ID — Database ID
  FEEDBACK_API_URL    — Dummy feedback API endpoint (placeholder)
"""

import os
import uuid
import datetime
import logging
import tempfile
import subprocess
import requests as http_requests

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────
CRUD_BASE_URL       = os.getenv("CRUD_BASE_URL", "https://datacube.uxlivinglab.online/api/v2")
CRUD_API_KEY        = os.getenv("CRUD_API_KEY", "")
DATABASE_ID         = os.getenv("SAMANTA_DATABASE_ID", "")
FEEDBACK_COLLECTION = "guest_feedback"
S3_UPLOAD_API    = "https://medsignqr.uxlivinglab.org/api/v1/transcription/upload-to-s3"
TRANSCRIPTION_API = "https://medsignqr.uxlivinglab.org/api/v1/transcription/transcribe"
FEEDBACK_API_URL    = os.getenv("FEEDBACK_API_URL", "https://placeholder.example.com/api/feedback")


# ── Helpers ───────────────────────────────────────────────────────────────────

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
                "-ar", "16000",      # 16kHz sample rate — optimal for speech recognition
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


def _save_to_datacube(room_number: str, description: str, transcript: str, file_id: str):
    """Save guest feedback metadata to Datacube. Non-fatal — never raises."""
    if not CRUD_API_KEY or not DATABASE_ID:
        logger.warning("[FEEDBACK] Datacube credentials not set — skipping save")
        return
    try:
        resp = http_requests.post(
            f"{CRUD_BASE_URL.rstrip('/')}/crud/",
            json={
                "database_id":     DATABASE_ID,
                "collection_name": FEEDBACK_COLLECTION,
                "documents": [{
                    "room_number":  room_number,
                    "description":  description,
                    "transcript":   transcript,
                    "audio_file":   f"{file_id}.wav",
                    "submitted_at": datetime.datetime.utcnow().isoformat() + "Z",
                }],
            },
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Api-Key {CRUD_API_KEY}",
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info(f"[FEEDBACK] Saved to Datacube — room={room_number}")
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
        logger.info(f"[FEEDBACK] Converted to WAV — {len(wav_bytes)} bytes, file_id={file_id}")

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
                logger.info(f"[FEEDBACK] Transcription: {transcript[:100]}")
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
    audio: UploadFile = File(...),
    room_number: str  = Form(default=""),
    description: str  = Form(default=""),
    transcript:  str  = Form(default=""),
    file_id:     str  = Form(default=""),
):
    """
    Step 2: Guest has confirmed transcript. Submit feedback.
    - Calls dummy feedback API with WAV
    - Saves metadata to Datacube
    """
    try:
        webm_bytes = await audio.read()
        if not webm_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")

        # Convert to WAV
        wav_bytes, new_file_id = _convert_webm_to_wav(webm_bytes)
        final_file_id = file_id or new_file_id

        # Call dummy feedback API
        try:
            feedback_resp = http_requests.post(
                FEEDBACK_API_URL,
                files={"audio": (f"{final_file_id}.wav", wav_bytes, "audio/wav")},
                timeout=30,
            )
            api_success = feedback_resp.status_code in (200, 201)
            logger.info(f"[FEEDBACK] Feedback API response: {feedback_resp.status_code}")
        except Exception as e:
            logger.warning(f"[FEEDBACK] Feedback API error (non-fatal): {e}")
            api_success = False

        # Save to Datacube (non-fatal)
        _save_to_datacube(
            room_number=room_number,
            description=description,
            transcript=transcript,
            file_id=final_file_id,
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