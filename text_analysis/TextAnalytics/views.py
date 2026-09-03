import os
from google import genai
from google.genai import types
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
import json
from .schema import TranslationSchema, SentimentAnalysisSchema, DataCubeService
from .serializers import TextSerializer, MetaDataSerializer
import datetime

class TextTranslationView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = TextSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "message": "Invalid input data."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        text = serializer.validated_data.get("text")
        if not text:
            return Response(
                {"status": "error", "message": "No text provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = genai.Client(api_key=os.environ.get("GEMINI_KEY_3"))

        prompt = f"""
            You are a language detection and translation assistant.
            Analyze the input text and provide:
            1. The detected language of the original text.
            2. The ISO 639-1 language code (or ISO 639-3 if unavailable).
            3. An accurate, natural English translation of the text.

            Input text: "{text}"
            """

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TranslationSchema,
                    temperature=0.0,
                ),
            )

            translation_data = json.loads(response.text)

            return Response(
                {"status": "success", "data": translation_data},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class SentimentAnalysisView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = TextSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "message": "Invalid input data."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        text = serializer.validated_data.get("text")

        try:
            client=genai.Client(api_key=os.environ.get("GEMINI_KEY_3"))
            prompt = f'Analyze the sentiment of this text: "{text}"'
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SentimentAnalysisSchema,
                    temperature=0.0,
                ),
            )
            result = json.loads(response.text)
            return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

datacube = DataCubeService(api_key=os.environ.get("FEEDBACK_CRUD_API_KEY"))
feedback_metadata_db = os.environ.get("FEEDBACK_METADATA_DB")
feedback_metadata_coll = os.environ.get("FEEDBACK_METADATA_COLL")

class FeedbackMetaDataView(APIView):
    def post(self, request):
        serializer = MetaDataSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error", "message": "Invalid input data."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        qrId = serializer.validated_data.get("qrId")
        feedback_id = serializer.validated_data.get("feedback_id")
        room = serializer.validated_data.get("room")        
        urgency_status = serializer.validated_data.get("urgency_status")        
        is_resolved = serializer.validated_data.get("is_resolved")        
        last_updated = serializer.validated_data.get("last_updated")        
        created_at = datetime.datetime.now().isoformat()

        metadata = {
            "qrId": qrId,
            "feedback_id": feedback_id,
            "room": room,
            "urgency_status": urgency_status,
            "is_resolved": is_resolved,
            "last_updated": last_updated,
            "created_at": created_at
        }
        
        try:
            response = datacube.insert_document(
                database_id=feedback_metadata_db,
                collection_name=feedback_metadata_coll,
                data=metadata
            )
            
            return Response(
                {
                    "success": True, 
                    "message": "Metadata inserted successfully"
                }, 
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": "Error inserting metadata", 
                    "error":str(e)
                }, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request):
        qrId = request.GET.get("qrId")

        if not qrId:
            return Response(
                {
                    "success": False,
                    "error": "Required qr code ID"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            filters = {
                "qrId": qrId
            }

            response = datacube.fetch_document(
                database_id=feedback_metadata_db,
                collection_name=feedback_metadata_coll,
                filters=json.dumps(filters)
            )

            return Response(
                {
                    "success": True,
                    "message": "Fetched metadata successfully",
                    "data": response["data"]
                }, 
                status=status.HTTP_200_OK
            )
        
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": "Failed to fetch data",
                    "error": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request):
        qrId = request.data.get("qrId")
        is_resolved = request.data.get("is_resolved")
        urgency_status = request.data.get("urgency_status")
        last_updated = request.data.get("last_updated")

        if not qrId:
            return Response(
                {
                    "success": False,
                    "error": "Required qr code ID"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            filters = { "qrId": qrId }
            update_data = {
                "is_resolved": is_resolved,
                "urgency_status": urgency_status,
                "last_updated": last_updated
            }

            response = datacube.update_document(database_id=feedback_metadata_db, collection_name=feedback_metadata_coll, filters=filters, update_data=update_data)

            return Response(
                response,
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": "Failed to update data",
                    "error": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
