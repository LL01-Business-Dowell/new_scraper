"""
swot_analyzer.py
----------------
Generate SWOT analysis for a place using NLTK VADER sentiment analysis.
No Gemini API calls — runs locally and fast.
"""

import logging
from typing import Dict, List
from nltk.sentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

# Initialize VADER once
try:
    sia = SentimentIntensityAnalyzer()
except:
    logger.warning("VADER not available, will use fallback")
    sia = None


def analyze_place_swot(place_data: Dict) -> Dict:
    """
    Generate SWOT analysis for a single place.
    
    Input place_data:
    {
        "name": "Cafe Name",
        "address": "Address",
        "rating": 4.5,
        "reviews": 123,
        "url": "...",
        "review_texts": ["review 1", "review 2", ...] (optional)
    }
    
    Output:
    {
        "name": "Cafe Name",
        "rating": 4.5,
        "sentiment_score": 0.7,  # -1 to 1
        "swot": {
            "strengths": ["strength 1", ...],
            "weaknesses": ["weakness 1", ...],
            "opportunities": ["opportunity 1", ...],
            "threats": ["threat 1", ...]
        }
    }
    """
    
    name = place_data.get("name", "Unknown")
    rating = place_data.get("rating")
    review_count = place_data.get("reviews", 0)
    review_texts = place_data.get("review_texts", [])
    
    # Calculate sentiment from reviews if available
    sentiment_score = 0.0
    if review_texts and sia:
        scores = [sia.polarity_scores(text)["compound"] for text in review_texts[:50]]
        sentiment_score = sum(scores) / len(scores) if scores else 0.0
    elif rating:
        # Fallback: use rating as proxy for sentiment
        sentiment_score = (rating - 2.5) / 2.5  # Scale 1-5 to -1 to 1
    
    # Rule-based SWOT generation
    strengths = []
    weaknesses = []
    opportunities = []
    threats = []
    
    # Strengths
    if rating and rating >= 4.5:
        strengths.append(f"High customer satisfaction (★{rating})")
    if review_count >= 100:
        strengths.append(f"Established reputation ({review_count}+ reviews)")
    if sentiment_score > 0.5:
        strengths.append("Strong positive customer sentiment")
    if rating and rating >= 4.0:
        strengths.append("Reliable service quality")
    
    # Weaknesses
    if rating and rating < 3.5:
        weaknesses.append(f"Below-average rating (★{rating})")
    if review_count < 20:
        weaknesses.append("Limited customer feedback")
    if sentiment_score < -0.3:
        weaknesses.append("Notable customer dissatisfaction")
    if rating and rating < 4.0:
        weaknesses.append("Inconsistent service quality")
    
    # Opportunities
    if rating and 3.5 <= rating < 4.5:
        opportunities.append("Potential to improve and reach 4.5+ rating")
    if review_count < 100:
        opportunities.append("Room to build larger customer base")
    opportunities.append("Expand digital presence and online ordering")
    opportunities.append("Implement customer feedback improvements")
    if sentiment_score > 0.3:
        opportunities.append("Leverage positive reviews in marketing")
    
    # Threats
    if sentiment_score < 0:
        threats.append("Negative word-of-mouth from dissatisfied customers")
    threats.append("Increasing competition in local market")
    threats.append("Changing consumer preferences")
    if rating and rating < 4.0:
        threats.append("Risk of losing customers to higher-rated competitors")
    
    # Ensure at least 3 items per category
    if len(strengths) < 3:
        strengths.extend([
            "Accessible location",
            "Diverse product/service offerings"
        ][:3 - len(strengths)])
    
    if len(weaknesses) < 3:
        weaknesses.extend([
            "Limited marketing presence",
            "Potential pricing concerns"
        ][:3 - len(weaknesses)])
    
    if len(opportunities) < 3:
        opportunities.extend([
            "Partner with local businesses",
            "Host special events or promotions"
        ][:3 - len(opportunities)])
    
    if len(threats) < 3:
        threats.extend([
            "Economic downturn affecting discretionary spending",
            "New market entrants"
        ][:3 - len(threats)])
    
    return {
        "name": name,
        "rating": rating,
        "review_count": review_count,
        "sentiment_score": round(sentiment_score, 2),
        "swot": {
            "strengths": strengths[:3],
            "weaknesses": weaknesses[:3],
            "opportunities": opportunities[:3],
            "threats": threats[:3]
        }
    }


def analyze_batch_swot(places: List[Dict], progress_callback=None) -> List[Dict]:
    """
    Analyze SWOT for multiple places and generate overall competitive analysis.
    
    progress_callback: function(current, total, status_text)
    """
    results = []
    
    for i, place in enumerate(places):
        if not place.get("selected", True):
            continue  # Skip deselected places
        
        swot_result = analyze_place_swot(place)
        results.append(swot_result)
        
        if progress_callback:
            progress_callback(i + 1, len(places), f"Analyzed {i + 1} places...")
    
    # Generate overall competitive analysis
    overall_analysis = _generate_competitive_analysis(results)
    
    return {
        "individual_analyses": results,
        "competitive_analysis": overall_analysis
    }


def _generate_competitive_analysis(analyses: List[Dict]) -> Dict:
    """
    Generate overall competitive landscape summary from individual SWOT analyses.
    """
    if not analyses:
        return {"summary": "No data available"}
    
    # Calculate averages
    avg_rating = sum([a.get("rating") or 0 for a in analyses]) / len(analyses)
    avg_sentiment = sum([a.get("sentiment_score", 0) for a in analyses]) / len(analyses)
    
    # Find top and bottom performers
    top_rated = max(analyses, key=lambda x: x.get("rating", 0))
    lowest_rated = min(analyses, key=lambda x: x.get("rating", 5))
    
    # Aggregate common themes
    common_strengths = {}
    common_weaknesses = {}
    
    for analysis in analyses:
        for strength in analysis["swot"]["strengths"]:
            common_strengths[strength] = common_strengths.get(strength, 0) + 1
        for weakness in analysis["swot"]["weaknesses"]:
            common_weaknesses[weakness] = common_weaknesses.get(weakness, 0) + 1
    
    return {
        "total_competitors_analyzed": len(analyses),
        "average_rating": round(avg_rating, 2),
        "average_sentiment": round(avg_sentiment, 2),
        "market_leader": top_rated.get("name"),
        "market_leader_rating": top_rated.get("rating"),
        "lowest_rated": lowest_rated.get("name"),
        "lowest_rated_rating": lowest_rated.get("rating"),
        "common_strengths_across_market": sorted(
            common_strengths.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5],
        "common_weaknesses_across_market": sorted(
            common_weaknesses.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5],
        "market_insights": _generate_market_insights(analyses, avg_rating, avg_sentiment)
    }


def _generate_market_insights(analyses: List[Dict], avg_rating: float, avg_sentiment: float) -> List[str]:
    """Generate text insights about the competitive market."""
    insights = []
    
    if avg_rating < 3.5:
        insights.append("Market shows low overall satisfaction — opportunity for differentiation through superior service")
    elif avg_rating >= 4.5:
        insights.append("Market is highly competitive with strong customer satisfaction across providers")
    else:
        insights.append("Market shows mixed customer satisfaction — focus on consistency and quality to stand out")
    
    if avg_sentiment < -0.2:
        insights.append("Negative sentiment dominates — poor reviews are a competitive disadvantage")
    elif avg_sentiment > 0.3:
        insights.append("Positive sentiment across market — strong word-of-mouth is a competitive factor")
    
    insights.append("Digital presence and online reviews are critical competitive factors")
    insights.append("Customer retention through quality and service is key to market success")
    
    return insights