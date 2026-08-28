import json
import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

class SentimentResult(BaseModel):
    tone: str = Field(
        description="Tone of the text, e.g., Accusatory, Impatient, Polite"
    )
    key_signals: list[str] = Field(
        description="Key phrases or indicators driving the analysis"
    )
    predicted_class: int = Field(
        description="Numeric class mapping (e.g., 0 for Negative, 1 for Neutral, 2 for Positive)"
    )
    detected_emotion: str = Field(
        description="Main emotion detected (e.g., Frustration, Joy, Anger)"
    )
    label: str = Field(
        description="Sentiment label: 'Positive', 'Negative', or 'Neutral'"
    )
    confidence_score: float = Field(
        description="Confidence score between 0.0 and 1.0"
    )
    text: str = Field(
        description="The original input transcript text being analyzed"
    )


def analyze_sentiment(API_KEY: str, transcript: str) -> dict:
    client = genai.Client(api_key=API_KEY)

    prompt = f'Analyze the sentiment of this text: "{transcript}"'

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SentimentResult,
            temperature=0.0,
        ),
    )

    return json.loads(response.text)

import logging
logger = logging.getLogger(__name__)

HIGH_URGENCY_AUDIO = [
        # Anger & Aggression
        "angry", "anger", "furious", "rage", "frustrated", "frustration", "annoyed", "irritated",
        # Panic & Distress
        "fearful", "fear", "panic", "panicked", "distressed", "terrified", "alarmed",
        # Active Sarcasm & Mocking
        "sarcastic", "sarcasm", "mocking", "cynical", "snarky", "scornful", "taunting", "derisive"
    ]
        
MEDIUM_URGENCY_AUDIO = [
        # Sadness & Disappointment
        "sad", "sadness", "disappointed", "disappointment", "grief", "despair",
        # Disgust & Aversion
        "disgust", "disgusted", "contempt",
        # Tension & Anxiety
        "anxious", "anxiety", "nervous", "hesitant", "surprised", "shocked",
        # Subtle Irony & Passive Aggression
        "ironic", "irony", "smug", "passive_aggressive", "dismissive", "condescending"
    ]
        

def generate_ai_assessment(text_sentiment: str, text_score: float, audio_emotion: str, audio_score: float) -> str:
    """
    Compares semantic and acoustic confidence scores to infer context 
    and generate an actionable AI Assessment remark.
    """
    text_sentiment = text_sentiment.upper()
    audio_emotion = audio_emotion.lower()
    
    text_pct = int(text_score * 100)
    audio_pct = int(audio_score * 100)
    score_delta = text_score - audio_score  # Positive if text is more confident

    # 1. POSITIVE TEXT EDGE CASE: High positive text vs weak/moderate sad tone
    if text_sentiment == "POSITIVE":
        if audio_emotion in MEDIUM_URGENCY_AUDIO and score_delta > 0.20:
            return (
                f"Genuinely Satisfied ({text_pct}% text confidence). "
                f"Acoustic '{audio_emotion}' rating ({audio_pct}%) is low-confidence and likely triggered by "
                f"vocal pauses, slow speech rate, or fatigue rather than actual dissatisfaction."
            )
        elif audio_emotion in HIGH_URGENCY_AUDIO:
            return (
                f"Mixed Signals: Highly positive words ({text_pct}%), but acoustic model detected "
                f"underlying vocal friction/agitation ({audio_pct}% {audio_emotion}). Brief courtesy check recommended."
            )
        else:
            return f"Strong Positive Alignment: Wording ({text_pct}%) and vocal tone confirm guest satisfaction."

    # 2. NEGATIVE TEXT EDGE CASE: High negative text vs calm voice (Sarcasm / Controlled anger)
    elif text_sentiment == "NEGATIVE":
        if audio_emotion in ["calm", "neutral", "happy"]:
            return (
                f"Controlled Dissatisfaction ({text_pct}% text confidence). "
                f"Guest expresses negative feedback in a controlled/calm tone ({audio_pct}%). "
                f"High risk for delayed negative review."
            )
        elif audio_emotion in HIGH_URGENCY_AUDIO:
            return f"Active Escalation: Severe negative wording ({text_pct}%) paired with aggressive vocal tone ({audio_pct}%)."
        else:
            return f"High-Risk Feedback: Words confirm dissatisfaction ({text_pct}%) paired with distressed vocal tone ({audio_pct}%)."

    # 3. NEUTRAL TEXT CASES
    else:
        if audio_emotion in HIGH_URGENCY_AUDIO and audio_score >= 0.65:
            return f"Vocal Distress Alert: Neutral words ({text_pct}%), but voice tone indicates high tension/frustration ({audio_pct}%)."
        
    return f"Balanced Evaluation: Text evaluated as {text_sentiment} ({text_pct}%) alongside {audio_emotion} vocal tone ({audio_pct}%)."

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
            
       
        dashboard_color = "green"
        severity_level = "low"
        action_required = "No immediate action. Review at shift change."
       
        if text_sentiment == "NEGATIVE":
            if audio_emotion in HIGH_URGENCY_AUDIO:
                dashboard_color = "red"
                severity_level = "high"
                action_required = "CRITICAL: Immediate manager dispatch to guest room/table."
            elif audio_emotion in MEDIUM_URGENCY_AUDIO:
                dashboard_color = "orange"
                severity_level = "medium"
                action_required = "URGENT: Front desk to call guest with an alternative/resolution within 15 mins."
            else:
                dashboard_color = "red"
                severity_level = "high"
                action_required = "HIGH RISK: Guest is expressing severe dissatisfaction with a controlled tone."

        elif text_sentiment in ["POSITIVE", "NEUTRAL"] and audio_emotion in HIGH_URGENCY_AUDIO:
            dashboard_color = "orange"
            severity_level = "medium"
            action_required = "POTENTIAL FRICTION: Staff to follow up and verify guest comfort."

        assessment_remark = generate_ai_assessment(text_sentiment, text_score, audio_emotion, audio_score)

        return {
            "assigned_color": dashboard_color,
            "severity": severity_level,
            "recommended_action": action_required,
            "ai_assessment_remark": assessment_remark,
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
            "ai_assessment_remark": "Error calculating metrics. Defaulting to baseline.",
            "confidence_scores": {
                "semantic_confidence": 0.0,
                "acoustic_confidence": 0.0
            }
        }