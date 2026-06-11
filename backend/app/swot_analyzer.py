"""
swot_analyzer.py
----------------
SWOT analysis using NLTK VADER sentiment on real scraped reviews.
No API calls — runs locally and fast.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Initialize VADER once at module level
try:
    from nltk.sentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    logger.info("[SWOT] VADER loaded successfully")
except Exception as e:
    logger.warning(f"[SWOT] VADER not available: {e}. Will use rating-based fallback.")
    sia = None

def analyze_batch_swot(places, progress_callback=None):
    individual_analyses = []

    selected_places = [p for p in places if p.get("selected", True)]
    total = len(selected_places)

    for i, place in enumerate(selected_places):
        individual_analyses.append(
            analyze_place_swot(place)
        )

        if progress_callback:
            progress_callback(
                i + 1,
                total,
                f"Analyzing {place.get('name', 'place')} ({i+1}/{total})..."
            )

    return {
        "individual_analyses": individual_analyses,
        "competitive_analysis": generate_competitive_analysis(
            individual_analyses
        )
    }

def analyze_place_swot(place_data: Dict) -> Dict:
    """
    Generate SWOT for a single place using real scraped reviews + VADER.

    Input place_data:
    {
        "name": str,
        "rating": float | None,
        "reviews": int,          # review count from Maps listing
        "url": str,
        "scraped_reviews": [     # from review_scraper.py (optional)
            {"author": str, "rating": int, "date": str, "text": str},
            ...
        ]
    }
    """
    name         = place_data.get("name", "Unknown")
    rating       = place_data.get("rating")
    review_count = place_data.get("reviews", 0)
    scraped      = place_data.get("scraped_reviews", [])

    # ── Sentiment from real reviews ────────────────────────────────────────
    sentiment_score = 0.0
    keyword_themes  = {"service": 0, "quality": 0, "price": 0, "ambiance": 0, "wait": 0}

    if scraped and sia:
        texts = [r["text"] for r in scraped if r.get("text") and r["text"] != "[Rating Only]"]
        if texts:
            scores = [sia.polarity_scores(t)["compound"] for t in texts[:50]]
            sentiment_score = sum(scores) / len(scores)

            # Keyword frequency for richer SWOT
            combined = " ".join(texts).lower()
            keyword_themes["service"]  = sum(combined.count(w) for w in ["service", "staff", "friendly", "rude", "slow"])
            keyword_themes["quality"]  = sum(combined.count(w) for w in ["quality", "fresh", "taste", "flavour", "stale"])
            keyword_themes["price"]    = sum(combined.count(w) for w in ["price", "expensive", "cheap", "value", "worth"])
            keyword_themes["ambiance"] = sum(combined.count(w) for w in ["ambiance", "atmosphere", "decor", "noisy", "cozy"])
            keyword_themes["wait"]     = sum(combined.count(w) for w in ["wait", "queue", "slow", "fast", "quick"])

    elif rating:
        sentiment_score = (rating - 2.5) / 2.5  # scale 1-5 → -1 to 1

    # ── Aggregate review ratings ───────────────────────────────────────────
    avg_review_rating = None
    if scraped:
        ratings = [r["rating"] for r in scraped if isinstance(r.get("rating"), (int, float))]
        avg_review_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

    effective_rating = avg_review_rating or rating

    # ── Build SWOT ─────────────────────────────────────────────────────────
    strengths     = []
    weaknesses    = []
    opportunities = []
    threats       = []

    # Strengths
    if effective_rating and effective_rating >= 4.5:
        strengths.append(f"Excellent customer rating (★{effective_rating})")
    elif effective_rating and effective_rating >= 4.0:
        strengths.append(f"Strong customer rating (★{effective_rating})")
    if review_count >= 500:
        strengths.append(f"Very high review volume ({review_count:,} reviews) — strong market presence")
    elif review_count >= 100:
        strengths.append(f"Established customer base ({review_count:,} reviews)")
    if sentiment_score > 0.5:
        strengths.append("Strongly positive customer sentiment in reviews")
    elif sentiment_score > 0.2:
        strengths.append("Generally positive customer sentiment")
    if keyword_themes["service"] > 5 and sentiment_score > 0:
        strengths.append("Customers highlight good service quality")
    if keyword_themes["ambiance"] > 3 and sentiment_score > 0:
        strengths.append("Positive mentions of ambiance and atmosphere")

    # Weaknesses
    if effective_rating and effective_rating < 3.5:
        weaknesses.append(f"Low customer rating (★{effective_rating}) — needs improvement")
    if review_count < 20:
        weaknesses.append("Limited customer feedback — low visibility")
    if sentiment_score < -0.2:
        weaknesses.append("Negative customer sentiment detected in reviews")
    if keyword_themes["wait"] > 5 and sentiment_score < 0.3:
        weaknesses.append("Multiple reviews mention long wait times")
    if keyword_themes["price"] > 5 and sentiment_score < 0.3:
        weaknesses.append("Pricing concerns raised in customer reviews")

    # Opportunities
    if effective_rating and 3.5 <= effective_rating < 4.5:
        opportunities.append("Potential to reach 4.5+ rating with targeted service improvements")
    if review_count < 100:
        opportunities.append("Grow customer base and increase review volume")
    if keyword_themes["quality"] > 3:
        opportunities.append("Quality is a talking point — leverage in marketing")
    opportunities.append("Expand digital presence and Google Maps engagement")
    if sentiment_score > 0.3:
        opportunities.append("Leverage positive reviews in social media marketing")

    # Threats
    if sentiment_score < 0:
        threats.append("Negative word-of-mouth risk from dissatisfied customers")
    threats.append("Increasing competition in local market")
    if effective_rating and effective_rating < 4.0:
        threats.append("Risk of losing customers to higher-rated competitors")
    if keyword_themes["service"] > 5 and sentiment_score < 0:
        threats.append("Service complaints could damage long-term reputation")
    threats.append("Changing consumer preferences and economic conditions")

    # Pad to minimum 3 items
    defaults = {
        "strengths":     ["Accessible location", "Established local presence", "Diverse offerings"],
        "weaknesses":    ["Limited marketing presence", "Potential pricing concerns", "Inconsistent customer experience"],
        "opportunities": ["Partner with local businesses", "Host events or promotions", "Loyalty program implementation"],
        "threats":       ["New market entrants", "Economic downturn impact", "Platform algorithm changes"],
    }
    for key, items in [("strengths", strengths), ("weaknesses", weaknesses),
                       ("opportunities", opportunities), ("threats", threats)]:
        if len(items) < 3:
            needed = 3 - len(items)
            for d in defaults[key]:
                if d not in items and needed > 0:
                    items.append(d)
                    needed -= 1

    return {
        "name":            name,
        "rating":          effective_rating,
        "review_count":    review_count,
        "scraped_count":   len(scraped),
        "sentiment_score": round(sentiment_score, 2),
        "swot": {
            "strengths":     strengths[:4],
            "weaknesses":    weaknesses[:4],
            "opportunities": opportunities[:4],
            "threats":       threats[:4],
        }
    }


def generate_competitive_analysis(analyses: List[Dict]) -> Dict:
    """Generate overall competitive landscape from individual SWOTs."""
    if not analyses:
        return {}

    rated = [a for a in analyses if a.get("rating")]
    avg_rating    = round(sum(a["rating"] for a in rated) / len(rated), 2) if rated else 0
    avg_sentiment = round(sum(a.get("sentiment_score", 0) for a in analyses) / len(analyses), 2)
    top           = max(analyses, key=lambda x: x.get("rating") or 0)
    lowest        = min(analyses, key=lambda x: x.get("rating") or 5)

    common_strengths  = {}
    common_weaknesses = {}
    for a in analyses:
        for s in a["swot"]["strengths"]:
            common_strengths[s] = common_strengths.get(s, 0) + 1
        for w in a["swot"]["weaknesses"]:
            common_weaknesses[w] = common_weaknesses.get(w, 0) + 1

    insights = []
    if avg_rating < 3.5:
        insights.append("Market shows low overall satisfaction — strong opportunity for differentiation through superior service quality")
    elif avg_rating >= 4.5:
        insights.append("Highly competitive market with strong satisfaction — excellence is the baseline, not the differentiator")
    else:
        insights.append("Mixed market satisfaction — consistency and reliability are key competitive advantages")

    if avg_sentiment > 0.3:
        insights.append("Positive sentiment dominates — word-of-mouth is a major competitive factor in this market")
    elif avg_sentiment < -0.1:
        insights.append("Widespread negative sentiment suggests a market-wide service quality issue — an opportunity for a standout player")

    insights.append("Google Maps rating and review volume are the primary discovery and trust signals in this market")

    return {
        "total_analyzed":           len(analyses),
        "average_rating":           avg_rating,
        "average_sentiment":        avg_sentiment,
        "market_leader":            top.get("name"),
        "market_leader_rating":     top.get("rating"),
        "lowest_rated":             lowest.get("name"),
        "lowest_rated_rating":      lowest.get("rating"),
        "common_strengths":         sorted(common_strengths.items(), key=lambda x: x[1], reverse=True)[:5],
        "common_weaknesses":        sorted(common_weaknesses.items(), key=lambda x: x[1], reverse=True)[:5],
        "market_insights":          insights,
    }