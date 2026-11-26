import os
from google import genai
from google.genai import types
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
import json
from .schema import TranslationSchema, SentimentAnalysisSchema, DataCubeService
from .serializers import TextSerializer, MetaDataSerializer, AudioTranscriptionRequestSerializer
import datetime
import tempfile
from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser


class TextTranslationView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = TextSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "message": "Invalid input data."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        text = serializer.validated_data.get("text")
        target = serializer.validated_data.get("target_language", "en")

        if not text or not target:
            return Response(
                {"success": False, "message": "No text or target language provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = genai.Client(api_key=os.environ.get("DOWELL_GEMINI_KEY"))

        prompt = f"""
            You are a language detection and translation assistant.
            Analyze the input text and provide:
            1. The detected language of the original text.
            2. The ISO 639-1 language code (or ISO 639-3 if unavailable).
            3. An accurate, natural {target} translation of the text.

            Input text: "{text}"
            """

        try:
            response = client.models.generate_content(
                model="gemini-3.7-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TranslationSchema,
                    temperature=0.0,
                ),
            )

            translation_data = json.loads(response.text)

            return Response(
                {
                    "success": True, 
                    "message": "Translation successful", 
                    "data": translation_data
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"success": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class SentimentAnalysisView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = TextSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "message": "Invalid input data."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        text = serializer.validated_data.get("text")

        try:
            client=genai.Client(api_key=os.environ.get("DOWELL_GEMINI_KEY"))
            prompt = f'Analyze the sentiment of this text: "{text}"'
            
            response = client.models.generate_content(
                model="gemini-3.7-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SentimentAnalysisSchema,
                    temperature=0.0,
                ),
            )
            result = json.loads(response.text)
            return Response({"success": True, "message": "Sentiment analysis successful", "data": result}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

datacube = DataCubeService(api_key=os.environ.get("FEEDBACK_CRUD_API_KEY"))
feedback_metadata_db = os.environ.get("FEEDBACK_METADATA_DB")
feedback_metadata_coll = os.environ.get("FEEDBACK_METADATA_COLL")

class FeedbackMetaDataView(APIView):
    def post(self, request):
        serializer = MetaDataSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False, "message": "Invalid input data."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        qrId = serializer.validated_data.get("qrId")
        client = serializer.validated_data.get("client")
        feedback_id = serializer.validated_data.get("feedback_id")
        room_number = serializer.validated_data.get("room_number")
        urgency_status = serializer.validated_data.get("urgency_status")
        is_resolved = serializer.validated_data.get("is_resolved")
        last_updated = serializer.validated_data.get("last_updated")
        created_at = datetime.datetime.now().isoformat()

        metadata = {
            "qrId": qrId,
            "client": client,
            "feedback_id": feedback_id,
            "room_number": room_number,
            "urgency_status": urgency_status,
            "is_resolved": is_resolved,
            "last_updated": last_updated,
            "created_at": created_at
        }
        
        try:
            datacube.insert_document(
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
        # client = request.GET.get("client")
        feedback_id = request.GET.get("feedback_id")

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
                "qrId": qrId,
                # "client": client,
                "feedback_id": feedback_id
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
        feedback_id = request.data.get("feedback_id")
        # client = request.data.get("client")
        is_resolved = request.data.get("is_resolved")
        urgency_status = request.data.get("urgency_status")
        last_updated = request.data.get("last_updated")
        print("Received data for update:", request.data)
        if not feedback_id:
            return Response(
                {
                    "success": False,
                    "error": "Required feedback ID"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            filters = { "_id": feedback_id }
            update_data = {
                "is_resolved": is_resolved,
                "urgency_status": urgency_status,
                "last_updated": last_updated
            }

            response = datacube.update_document(database_id=feedback_metadata_db, collection_name=feedback_metadata_coll, filters=filters, update_data=update_data)
            print("Update response:", response)
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
        

def _extract_speaker_turns(interaction_response) -> list[dict]:
    words = []
    for step in getattr(interaction_response, "steps", []) or []:
        for content in getattr(step, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                if getattr(annotation, "type", None) == "word_info":
                    words.append(annotation)

    turns = []
    current_speaker = None
    current_words = []

    for word in words:
        speaker = getattr(word, "speaker", "unknown")
        text = getattr(word, "text", "")
        if speaker != current_speaker:
            if current_words:
                turns.append({"speaker": current_speaker, "text": " ".join(current_words)})
            current_speaker = speaker
            current_words = [text]
        else:
            current_words.append(text)

    if current_words:
        turns.append({"speaker": current_speaker, "text": " ".join(current_words)})

    return turns


class AudioTranscribeAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = AudioTranscriptionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        uploaded_file = data["audio"]
        suffix = os.path.splitext(uploaded_file.name or "")[1] or ".wav"

        transcription_config = {}
        if data["language_codes"]:
            transcription_config["language_codes"] = data["language_codes"]
        if data["custom_vocabulary"]:
            transcription_config["custom_vocabulary"] = data["custom_vocabulary"]

        if data["diarization"]:
            transcription_config["mode"] = {
                "type": "verbatim",
                "diarization_mode": "speaker",
            }
        elif data["mode"] == "smart":
            transcription_config["mode"] = {"type": "smart"}

        client = genai.Client(
            api_key=getattr(settings, "GEMINI_API_KEY", None),
            http_options={"api_version": "v1beta"},
        )

        tmp_path = None
        remote_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in uploaded_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            remote_file = client.files.upload(file=tmp_path)

            request_kwargs = {
                "model": "gemini-3.5-transcribe",
                "input": [
                    {
                        "type": "audio",
                        "uri": remote_file.uri,
                        "mime_type": remote_file.mime_type,
                    }
                ],
            }
            if transcription_config:
                request_kwargs["generation_config"] = {
                    "transcription_config": transcription_config
                }

            interaction = client.interactions.create(**request_kwargs)

            payload = {
                "transcript": interaction.output_text,
                "mode": data["mode"],
                "language_codes": data["language_codes"],
            }
            if data["diarization"]:
                payload["turns"] = _extract_speaker_turns(interaction)

            return Response(payload, status=status.HTTP_200_OK)

        except Exception as exc:
            return Response(
                {"detail": f"Transcription failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        finally:
            if remote_file is not None:
                try:
                    client.files.delete(name=remote_file.name)
                except Exception:
                    pass
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass