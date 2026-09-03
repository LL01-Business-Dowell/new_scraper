from pydantic import BaseModel, Field
import os
import requests

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

CRUD_BASE_URL = os.environ.get("CRUD_BASE_URL")
class DataCubeService:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def create_database(self, database_name: str, collections: list[dict]):
        url = f"{CRUD_BASE_URL}/create_databases/"
        headers = {"Authorization": f"Api-Key {self.api_key}"}
        
        payload = {
            "db_name": database_name,
            "collections": collections
        }
        try:
            response = requests.post(url, json=payload, headers=headers)
            
            return response.json()
        
        except Exception as e:
            raise Exception(f"Failed to create database: {e}")

    def insert_document(self, database_id: str, collection_name: str, data: list[dict]):
        url = f"{CRUD_BASE_URL}/crud/"

        print(f"url:{url}", "api_key:", self.api_key, "database_id:", database_id, "collection_name:", collection_name, "data:", data)
        headers = {"Authorization": f"Api-Key {self.api_key}"}
        payload = {
            "database_id": database_id,
            "collection_name": collection_name, 
            "documents": [data]
        }
        try:
            response = requests.post(url, json=payload, headers=headers)
            return response.json()
        
        except Exception as e:
            raise Exception(f"Failed to insert data: {e}")

    def fetch_document(self, database_id: str, collection_name: str, filters):
        print("Crud base url:", CRUD_BASE_URL, "database_id:", database_id, "collection_name:", collection_name, "filters:", filters)
        url = f"{CRUD_BASE_URL}/crud/?database_id={database_id}&collection_name={collection_name}&filters={filters}"

        headers = {"Authorization": f"Api-Key {self.api_key}"}

        try:
            response = requests.get(url, headers=headers)
            return response.json()
        
        except Exception as e:
            raise Exception(f"Failed to fetch data: {e}")

    def update_document(self, database_id: str, collection_name: str, filters: dict, update_data: dict):
        url = f"{CRUD_BASE_URL}/crud/"

        headers = {"Authorization": f"Api-Key {self.api_key}"}

        payload = {
            "database_id": database_id,
            "collection_name": collection_name,
            "filters": filters,
            "update_data": update_data,
            "update_all_fields": True,
            "update_many": True,
            "upsert": False
        }

        try:
            response = requests.put(url, json=payload, headers=headers)
            return response.json()
        
        except Exception as e:
            raise Exception(f"Failed to update data: {e}")

