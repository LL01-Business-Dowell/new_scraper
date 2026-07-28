from django.shortcuts import render

import io
import numpy as np
import torch
from django.apps import apps
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import AudioUploadSerializer
import traceback
import os
import subprocess
from pydub import AudioSegment

AudioSegment.converter = "/usr/bin/ffmpeg"
AudioSegment.ffprobe = "/usr/bin/ffprobe"

class AudioSentimentAnalysisView(APIView):
    
    def post(self, request, *args, **kwargs):
        serializer = AudioUploadSerializer(data=request.data)
        print("Received request data:", request.data)  # Debugging line to check incoming data
        print("Serializer is valid:", serializer.is_valid())  # Debugging line to check serializer validity
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['audio_file']
        print("Uploaded file size:", uploaded_file.size)  # Debugging line to check the uploaded file size

        print("=" * 60)
        print("AudioSegment.converter:", AudioSegment.converter)
        print("Exists:", os.path.exists(AudioSegment.converter))

        print("AudioSegment.ffprobe:", AudioSegment.ffprobe)
        print("Exists:", os.path.exists(AudioSegment.ffprobe))

        try:
            subprocess.run(
                [AudioSegment.ffprobe, "-version"],
                check=True,
                capture_output=True,
                text=True,
            )
            print("ffprobe is executable")
        except Exception as e:
            print("ffprobe test failed:", repr(e))

        print("=" * 60)

        try:
            # 1. Read raw submitted file bytes directly from memory
            audio_bytes = uploaded_file.read()
            
            # 2. Pydub forces file format conversion to Mono + 16000Hz (Bypassing Torchaudio dependencies)
            segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
            # print("Segment sample width:", segment.sample_width)  # Debugging line to check sample width
            segment = segment.set_frame_rate(16000).set_channels(1)
            print("Audio resampled")

            # 3. Extract the underlying raw data as an array vector normalized between [-1.0, 1.0]
            raw_speech_array = np.array(segment.get_array_of_samples(), dtype=np.float32)
            print(raw_speech_array.shape)
            
            # Normalize integers down to floating point weights (handles 16-bit PCM scale)
            if segment.sample_width == 2:
                raw_speech_array /= 32768.0
            elif segment.sample_width == 4:
                raw_speech_array /= 2147483648.0

            # 4. Neural Inference Configuration Pipeline Access
            print("Loading AppConfig...")
            app_config = apps.get_app_config('AudioAnalytics')
            print("AppConfig loaded")

            print(type(raw_speech_array))
            print(raw_speech_array.shape)
            print(raw_speech_array.dtype)

            print("min:", raw_speech_array.min())
            print("max:", raw_speech_array.max())

            print(np.isnan(raw_speech_array).any())
            print(np.isinf(raw_speech_array).any())

            print("Extracting features...")
            inputs = app_config.feature_extractor(
                raw_speech_array, 
                sampling_rate=16000, 
                return_tensors="pt"
            ).to(app_config.device)

            print("Features extracted")
            print(inputs)
            print(inputs["input_values"].shape)
            print(inputs["input_values"].dtype)
            print(inputs["input_values"].device)

            print(torch.isnan(inputs["input_values"]).any())
            print(torch.isinf(inputs["input_values"]).any())
            print("Running inference...")

            with torch.no_grad():
                input_tensor = inputs["input_values"]
                logits = app_config.predictor_model(input_tensor).logits
            print("Inference finished")
            
            # Map structural raw logits into percentage/probabilities weights
            scores = torch.nn.functional.softmax(logits, dim=-1).flatten().tolist()
            audio_score = max(scores)
            labels = app_config.predictor_model.config.id2label

            # Match emotion labels directly with evaluated float values
            analysis_distribution = {labels[i]: round(scores[i], 4) for i in range(len(scores))}
            primary_emotion = max(analysis_distribution, key=analysis_distribution.get)

            # 5. Hospitality Logic Matrix: Maps mood directly to dashboard alerts
            dashboard_color = "green"
            severity_level = "low"
            
            if primary_emotion in ["angry", "fearful"]:
                dashboard_color = "red"
                severity_level = "high"
            elif primary_emotion in ["sad", "disgust"]:
                dashboard_color = "orange"
                severity_level = "medium"


            return Response({
                "status": "success",
                "dashboard_metrics": {
                    "assigned_color": dashboard_color,
                    "severity": severity_level,
                    "dominant_emotion": primary_emotion,
                    "audio_score": audio_score
                },
                "raw_emotion_distribution": analysis_distribution
            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()

            return Response(
                {
                    "status": "error",
                    "message": str(e),
                },
                status=500,
            )