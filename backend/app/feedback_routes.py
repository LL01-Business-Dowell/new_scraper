import os
import uuid
import datetime
import logging
import tempfile
import subprocess
import requests as http_requests
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
import torch
import json

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

# Hugging Face Configuration
MODEL_ID = "joeddav/distilbert-base-uncased-go-emotions-student"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# 28 GoEmotions Labels Mapping
GO_EMOTIONS_LABELS = [
    "admiration", "amusement", "anger", "annoyance", "approval", "caring",
    "confusion", "curiosity", "desire", "disappointment", "disapproval",
    "disgust", "embarrassment", "excitement", "fear", "gratitude", "grief",
    "joy", "love", "nervousness", "optimism", "pride", "realization",
    "relief", "remorse", "sadness", "surprise", "neutral"
]

POSITIVE_EMOTIONS = {"admiration", "amusement", "approval", "caring", "excitement", "gratitude", "joy", "love", "optimism", "pride", "relief"}
NEGATIVE_EMOTIONS = {"anger", "annoyance", "disappointment", "disapproval", "disgust", "embarrassment", "fear", "grief", "nervousness", "remorse", "sadness"}


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


def _load_huggingface_model(model_id: str):
    try:
        tokenizer = DistilBertTokenizer.from_pretrained(model_id)
        model = DistilBertForSequenceClassification.from_pretrained(model_id)
        model.to(DEVICE)
        model.eval()
        logger.info(f"[FEEDBACK] HuggingFace model '{model_id}' successfully pre-loaded on {DEVICE}.")
        return tokenizer, model
    except Exception as e:
        logger.error(f"[FEEDBACK] Error loading HuggingFace model {model_id}: {e}")
        return None, None

TOKENIZER, MODEL = _load_huggingface_model(MODEL_ID)


def _distilbert_sentiment_analysis(transcript: str) -> dict:
    if MODEL is None or TOKENIZER is None or not transcript.strip():
        logger.warning("[FEEDBACK] Model uninitialized or empty transcript received.")
        return {"label": "neutral", "confidence_score": 0.0, "predicted_class": -1, "detected_emotion": "neutral", "text": transcript}

    try:
        tokenize = TOKENIZER(
            transcript,
            return_tensors="pt",
            truncation=True,
            max_length=TOKENIZER.model_max_length,
            padding=True
        )

        inputs = {key: value.to(DEVICE) for key, value in tokenize.items()}

        with torch.no_grad():
            output = MODEL(**inputs)

        logits = output.logits
        probabilities = torch.softmax(logits, dim=-1)

        predicted_class = torch.argmax(probabilities, dim=-1).item()
        confidence_score = probabilities[0][predicted_class].item()

        emotion_name = GO_EMOTIONS_LABELS[predicted_class] if predicted_class < len(GO_EMOTIONS_LABELS) else "neutral"

        if emotion_name in POSITIVE_EMOTIONS:
            sentiment_label = "positive"
        elif emotion_name in NEGATIVE_EMOTIONS:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"

        return {
            "predicted_class": predicted_class,
            "detected_emotion": emotion_name,
            "label": sentiment_label,
            "confidence_score": confidence_score,
            "text": transcript
        }
    except Exception as e:
        logger.warning(f"[FEEDBACK] Inference error: {e}")
        return {"label": "neutral", "confidence_score": 0.0, "predicted_class": -1, "detected_emotion": "neutral", "text": transcript}


def calculate_fused_metrics(text_sentiment, text_score, audio_emotion, audio_score):
    logger.info(f"[FUSED METRICS] Input raw values -> sentiment: {text_sentiment}, text_score: {text_score}, audio_emotion: {audio_emotion}, audio_score: {audio_score}")

    try:
        text_sentiment = str(text_sentiment or "NEUTRAL").upper()
        audio_emotion = str(audio_emotion or "calm").lower()

        try:
            text_score = float(text_score) if text_score is not None else 0.0
        except (ValueError, TypeError):
            text_score = 0.0

        try:
            audio_score = float(audio_score) if audio_score is not None else 0.0
        except (ValueError, TypeError):
            audio_score = 0.0
            
        high_urgency_audio = ["angry", "fearful"]
        medium_urgency_audio = ["sad", "disgust"]
        
        dashboard_color = "green"
        severity_level = "low"
        action_required = "No immediate action. Review at shift change."
       
        if text_sentiment == "NEGATIVE":
            if audio_emotion in high_urgency_audio:
                dashboard_color = "red"
                severity_level = "high"
                action_required = "CRITICAL: Immediate manager dispatch to guest room/table."
            elif audio_emotion in medium_urgency_audio:
                dashboard_color = "orange"
                severity_level = "medium"
                action_required = "URGENT: Front desk to call guest with an alternative/resolution within 15 mins."
            else:
                dashboard_color = "red"
                severity_level = "high"
                action_required = "HIGH RISK: Guest is expressing severe dissatisfaction with a controlled tone."

        elif text_sentiment in ["POSITIVE", "NEUTRAL"] and audio_emotion in high_urgency_audio:
            dashboard_color = "orange"
            severity_level = "medium"
            action_required = "POTENTIAL FRICTION: Staff to follow up and verify guest comfort."

        return {
            "assigned_color": dashboard_color,
            "severity": severity_level,
            "recommended_action": action_required,
            "confidence_scores": {
                "semantic_confidence": round(text_score, 2),
                "acoustic_confidence": round(audio_score, 2)
            }
        }

    except Exception as e:
        logger.error(f"[FUSED METRICS] Calculation error: {e}", exc_info=True)
        return {
            "assigned_color": "green",
            "severity": "low",
            "recommended_action": "Error calculating metrics. Defaulting to baseline.",
            "confidence_scores": {
                "semantic_confidence": 0.0,
                "acoustic_confidence": 0.0
            }
        }


def _save_to_datacube(
    id_param: str,
    room_number: str,
    description: str,
    file_id: str,
    client_name: str = "",
    emotion_metrics: dict = None,
    raw_emotion_distribution: dict = None,
    fused_metrics: dict = None,
    transcript: str = "",
    transcript_analysis: dict = None
) -> str:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID:
        logger.warning("[FEEDBACK] Datacube credentials missing, skipping save")
        return ""

    collection_name = _get_collection_name(id_param)

    try:
        doc_data = {
            "type": "feedback",
            "qr_id": id_param,
            "client_name": client_name,
            "room_number": room_number,
            "description": description,
            "transcript": transcript,
            "transcript_analysis": transcript_analysis or {},
            "audio_file": f"{file_id}.wav",
            "audio_analysis": emotion_metrics or {},
            "raw_emotion_distribution": raw_emotion_distribution or {},
            "dashboard_metrics": fused_metrics,
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
            return inserted_ids[0] if inserted_ids else ""
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
    transcript_analysis: dict,
    fused_metrics: dict = None
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
        logger.error(f"[FEEDBACK] Datacube update error: {e}")
        return False


def _get_datacube_doc(id_param: str, doc_id: str) -> dict:
    if not CRUD_API_KEY or not MASTER_DATABASE_ID or not doc_id:
        return {}
    collection_name = _get_collection_name(id_param)
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
        logger.error(f"[FEEDBACK] Error fetching Datacube doc: {e}")
    return {}


@router.post("/submit")
async def submit_feedback(
    request: Request,
    audio: UploadFile = File(...),
    room_number: str = Form(default=""),
    description: str = Form(default=""),
    client_name: str = Form(default=""),
    file_id: str = Form(default=""),
):
    try:
        id_param = request.query_params.get("id", "")

        if not client_name:
            client_name = request.query_params.get("client_name", "") or request.query_params.get("client", "")
            if not client_name and "-" in id_param:
                client_name = id_param.split("-")[0]

        webm_bytes = await audio.read()
        if not webm_bytes:
            raise HTTPException(status_code=400, detail="No audio data received")

        wav_bytes, new_file_id = _convert_webm_to_wav(webm_bytes)
        final_file_id = file_id or new_file_id

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
            logger.warning(f"[FEEDBACK] Audio analysis error: {e}")

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
            room_number=room_number,
            description=description,
            client_name=client_name,
            file_id=final_file_id,
            emotion_metrics=emotion_data,
            raw_emotion_distribution=raw_emotions,
            fused_metrics=fused_metrics,
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
            if not (upload_resp.status_code == 200 and upload_resp.json().get("success")):
                raise HTTPException(status_code=502, detail="Failed to upload audio to S3")
        except HTTPException:
            raise
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
            logger.warning(f"[FEEDBACK] Transcription error: {e}")

        transcript_analysis = _distilbert_sentiment_analysis(transcript)

        doc_data = _get_datacube_doc(id_param, doc_id) if doc_id else {}
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
        logger.error(f"[FEEDBACK] Transcribe-lazy endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))