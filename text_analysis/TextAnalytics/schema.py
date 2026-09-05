from pydantic import BaseModel, Field

# Define response structure schema
class TranslationSchema(BaseModel):
    detected_language: str = Field(
        description="Name of the detected language"
    )
    language_code: str = Field(
        description="ISO 639-1 code (or ISO 639-3 if unavailable)"
    )
    english_translation: str = Field(
        description="Accurate and natural English translation of the text"
    )

class SentimentAnalysisSchema(BaseModel):
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

