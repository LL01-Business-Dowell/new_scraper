from django.urls import path
from .views import AudioSentimentAnalysisView

urlpatterns = [
    path('analyze-audio/', AudioSentimentAnalysisView.as_view(), name='analyze_audio'),
]