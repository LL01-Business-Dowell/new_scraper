from django.urls import path
from .views import TextTranslationView, SentimentAnalysisView

urlpatterns = [
    path('translate-to-english/', TextTranslationView.as_view(), name='translate_text'),
    path('analyze-sentiment/', SentimentAnalysisView.as_view(), name='analyze_sentiment')
]