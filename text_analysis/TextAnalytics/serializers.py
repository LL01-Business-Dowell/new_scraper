from rest_framework import serializers

class TextSerializer(serializers.Serializer):
    text = serializers.CharField(required=True)
    target_language = serializers.CharField(required=False, allow_blank=True, default="English")

class MetaDataSerializer(serializers.Serializer):
    qrId = serializers.CharField(required=True)
    feedback_id = serializers.CharField(required=True)
    room = serializers.CharField(required=True)
    urgency_status = serializers.ChoiceField(choices=["high", "medium", "low"], required=True)
    is_resolved = serializers.BooleanField(required=True)
    last_updated = serializers.CharField(required=True)