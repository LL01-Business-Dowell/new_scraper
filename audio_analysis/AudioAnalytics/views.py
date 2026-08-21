import io
import os
import logging
import traceback
import numpy as np
import torch
from pydub import AudioSegment

from django.apps import apps
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import AudioUploadSerializer

logger = logging.getLogger(__name__)

# Configure ffmpeg/ffprobe binary paths
AudioSegment.converter = "/usr/bin/ffmpeg"
AudioSegment.ffprobe = "/usr/bin/ffprobe"


class AudioSentimentAnalysisView(APIView):
    # Expanded Emotion Urgency Categories
    HIGH_URGENCY_AUDIO = {
        # Anger & Aggression
        "angry", "anger", "furious", "rage", "frustrated", "frustration", "annoyed", "irritated",
        # Panic & Distress
        "fearful", "fear", "panic", "panicked", "distressed", "terrified", "alarmed",
        # Active Sarcasm & Mocking
        "sarcastic", "sarcasm", "mocking", "cynical", "snarky", "scornful", "taunting", "derisive"
    }

    MEDIUM_URGENCY_AUDIO = {
        # Sadness & Disappointment
        "sad", "sadness", "disappointed", "disappointment", "grief", "despair",
        # Disgust & Aversion
        "disgust", "disgusted", "contempt",
        # Tension & Anxiety
        "anxious", "anxiety", "nervous", "hesitant", "surprised", "shocked",
        # Subtle Irony & Passive Aggression
        "ironic", "irony", "smug", "passive_aggressive", "dismissive", "condescending"
    }

    def post(self, request, *args, **kwargs):
        serializer = AudioUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['audio_file']

        try:
            # 1. Read raw submitted file bytes directly from memory
            audio_bytes = uploaded_file.read()

            # 2. Convert and resample audio via Pydub (Mono, 16000Hz)
            segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
            segment = segment.set_frame_rate(16000).set_channels(1)

            # 3. Extract and normalize raw PCM sample array
            raw_speech_array = np.array(segment.get_array_of_samples(), dtype=np.float32)

            if segment.sample_width == 2:
                raw_speech_array /= 32768.0
            elif segment.sample_width == 4:
                raw_speech_array /= 2147483648.0

            # 4. Access pre-loaded model/feature_extractor from AppConfig
            app_config = apps.get_app_config('AudioAnalytics')

            inputs = app_config.feature_extractor(
                raw_speech_array,
                sampling_rate=16000,
                return_tensors="pt"
            ).to(app_config.device)

            # 5. Execute neural inference
            with torch.no_grad():
                logits = app_config.predictor_model(inputs["input_values"]).logits

            # 6. Softmax probability transformation & dynamic label extraction
            scores = torch.nn.functional.softmax(logits, dim=-1).flatten().tolist()
            labels_dict = app_config.predictor_model.config.id2label

            # Normalize output dictionary key labels to lowercase strings
            analysis_distribution = {
                str(labels_dict[i]).lower(): round(scores[i], 4) 
                for i in range(len(scores))
            }
            print("Analysis Distribution:", analysis_distribution)
            # Identify dominant emotion label and top score
            primary_emotion = max(analysis_distribution, key=analysis_distribution.get)
            audio_score = analysis_distribution[primary_emotion]

            # 7. Expanded Hospitality Alert Routing Matrix
            dashboard_color = "green"
            severity_level = "low"
            action_required = "No immediate escalation. Review at shift change."

            if primary_emotion in self.HIGH_URGENCY_AUDIO:
                dashboard_color = "red"
                severity_level = "high"
                if primary_emotion in ["sarcastic", "sarcasm", "mocking", "snarky"]:
                    action_required = "HIGH RISK: Guest expressing severe dissatisfaction with a sarcastic tone."
                else:
                    action_required = "CRITICAL: Immediate manager dispatch to guest room/table."

            elif primary_emotion in self.MEDIUM_URGENCY_AUDIO:
                dashboard_color = "orange"
                severity_level = "medium"
                action_required = "URGENT: Front desk follow-up and resolution within 15 mins."

            # 8. Return response payload
            return Response({
                "status": "success",
                "dashboard_metrics": {
                    "assigned_color": dashboard_color,
                    "severity": severity_level,
                    "dominant_emotion": primary_emotion,
                    "recommended_action": action_required,
                    "audio_score": audio_score
                },
                "raw_emotion_distribution": analysis_distribution
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"[AUDIO ANALYTICS] Inference error: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "message": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )