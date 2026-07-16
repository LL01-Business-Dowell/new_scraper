from rest_framework import serializers

class AudioUploadSerializer(serializers.Serializer):
    audio_file = serializers.FileField(required=True)