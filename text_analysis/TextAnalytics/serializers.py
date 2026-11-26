from rest_framework import serializers

class TextSerializer(serializers.Serializer):
    text = serializers.CharField(required=True)
    target_language = serializers.CharField(required=False, allow_blank=True, default="English")

class MetaDataSerializer(serializers.Serializer):
    qrId = serializers.CharField(required=True)
    client = serializers.CharField(required=True)
    feedback_id = serializers.CharField(required=True)
    room_number = serializers.CharField(required=True)
    urgency_status = serializers.ChoiceField(choices=["high", "medium", "low"], required=True)
    is_resolved = serializers.BooleanField(required=True)
    last_updated = serializers.CharField(required=False, allow_blank=True, default="")

import json
from rest_framework import serializers

ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/aiff",
    "audio/x-aiff",
}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB upload guard


class AudioTranscriptionRequestSerializer(serializers.Serializer):
    audio = serializers.FileField()
    language_codes = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        allow_empty=True,
        default=list,
    )
    custom_vocabulary = serializers.ListField(
        child=serializers.CharField(max_length=120),
        required=False,
        allow_empty=True,
        default=list,
    )
    mode = serializers.ChoiceField(
        choices=["verbatim", "smart"],
        required=False,
        default="smart",
    )
    diarization = serializers.BooleanField(required=False, default=False)

    def to_internal_value(self, data):
        # Support multipart/form-data where list/boolean fields may arrive as JSON strings
        mutable = data.copy() if hasattr(data, "copy") else dict(data)
        for list_field in ("language_codes", "custom_vocabulary"):
            val = mutable.get(list_field)
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        mutable[list_field] = parsed
                except json.JSONDecodeError:
                    mutable[list_field] = [item.strip() for item in val.split(",") if item.strip()]

        if isinstance(mutable.get("diarization"), str):
            mutable["diarization"] = mutable["diarization"].lower() in ("true", "1", "yes")

        return super().to_internal_value(mutable)

    def validate_audio(self, file_obj):
        if file_obj.size > MAX_FILE_SIZE_BYTES:
            raise serializers.ValidationError("Audio file exceeds the 25 MB upload limit.")
        content_type = (file_obj.content_type or "").lower()
        if content_type and content_type not in ALLOWED_AUDIO_TYPES:
            raise serializers.ValidationError(
                f"Unsupported audio content type '{content_type}'. Use WAV, MP3, or AIFF."
            )
        return file_obj

    def validate(self, attrs):
        vocab = attrs.get("custom_vocabulary") or []
        diarization = attrs.get("diarization", False)
        mode = attrs.get("mode", "verbatim")

        if len(vocab) > 1000:
            raise serializers.ValidationError(
                {"custom_vocabulary": "At most 1,000 terms are supported."}
            )
        if vocab and diarization:
            raise serializers.ValidationError(
                "custom_vocabulary and diarization cannot be used in the same request."
            )
        if diarization and mode != "verbatim":
            raise serializers.ValidationError(
                {"mode": "Speaker diarization requires mode='verbatim'."}
            )
        return attrs