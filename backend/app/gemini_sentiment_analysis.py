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