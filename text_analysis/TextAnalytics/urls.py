from django.urls import path
from .views import TextTranslationView, SentimentAnalysisView, FeedbackMetaDataView

urlpatterns = [
    path('translate-to-english/', TextTranslationView.as_view(), name='translate_text'),
    path('analyze-sentiment/', SentimentAnalysisView.as_view(), name='analyze_sentiment'),
    path('feedback-metadata/', FeedbackMetaDataView.as_view(), name='feedback_metadata'),
]