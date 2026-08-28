import os
from google import genai
from google.genai import types
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
import json
from .schema import TranslationSchema, SentimentAnalysisSchema
from .serializers import TextSerializer

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