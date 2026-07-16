import re
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── VADER ─────────────────────────────────────────────────────────────────
try:
    from nltk.sentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    logger.info("[SWOT] VADER loaded successfully")
except Exception as e:
    logger.warning(f"[SWOT] VADER not available: {e}. Will use rating-based fallback.")
    sia = None

# ── Theme definitions ──────────────────────────────────────────────────────
THEMES = {
    "food_quality": ("food quality",    ["food", "taste", "flavour", "flavor", "delicious", "fresh", "stale", "bland", "yummy", "awful", "amazing", "dish", "meal", "menu", "cuisine", "cook", "chef"]),
    "coffee":       ("coffee",          ["coffee", "espresso", "latte", "cappuccino", "brew", "barista"]),
    "service":      ("service",         ["service", "staff", "waiter", "waitress", "server", "friendly", "rude", "helpful", "attentive", "ignored", "prompt", "polite", "unprofessional"]),
    "ambiance":     ("ambiance",        ["ambiance", "atmosphere", "decor", "cozy", "cosy", "noisy", "quiet", "vibe", "aesthetic", "comfortable", "seating", "interior", "music"]),
    "price_value":  ("value for money", ["price", "expensive", "cheap", "affordable", "overpriced", "value", "worth", "cost", "pricey", "reasonable", "budget"]),
    "wait_time":    ("wait times",      ["wait", "queue", "slow", "fast", "quick", "long wait", "delay"]),
    "cleanliness":  ("cleanliness",     ["clean", "dirty", "hygiene", "hygienic", "mess", "spotless", "filthy"]),
    "portions":     ("portion size",    ["portion", "size", "quantity", "small", "large", "generous", "tiny"]),
    "location":     ("location",        ["location", "parking", "accessible", "nearby", "convenient", "far", "central"]),
    "consistency":  ("consistency",     ["consistent", "inconsistent", "always", "sometimes", "every time", "varies"]),
}


def _score_sentence(sentence: str) -> float:
    if not sia:
        return 0.0
    return sia.polarity_scores(sentence)["compound"]


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 8]


def _extract_theme_sentiments(reviews: List[Dict]) -> Dict[str, Dict]:
    theme_data = {
        k: {"label": v[0], "scores": [], "pos_quotes": [], "neg_quotes": []}
        for k, v in THEMES.items()
    }

    for review in reviews:
        text = review.get("text", "")
        if not text or text == "[Rating Only]":
            continue

        sentences = _split_sentences(text.lower())
        for sentence in sentences:
            for theme_key, (label, keywords) in THEMES.items():
                if any(kw in sentence for kw in keywords):
                    score = _score_sentence(sentence)
                    theme_data[theme_key]["scores"].append(score)
                    if len(sentence) <= 80:
                        if score >= 0.3 and len(theme_data[theme_key]["pos_quotes"]) < 2:
                            theme_data[theme_key]["pos_quotes"].append(sentence.strip())
                        elif score <= -0.3 and len(theme_data[theme_key]["neg_quotes"]) < 2:
                            theme_data[theme_key]["neg_quotes"].append(sentence.strip())

    result = {}
    for k, d in theme_data.items():
        if d["scores"]:
            avg = sum(d["scores"]) / len(d["scores"])
            result[k] = {
                "label":      d["label"],
                "score":      round(avg, 3),
                "count":      len(d["scores"]),
                "pos_quotes": d["pos_quotes"],
                "neg_quotes": d["neg_quotes"],
            }
    return result


def _build_swot_from_themes(
    theme_sentiments: Dict,
    name: str,
    rating: Optional[float],
    review_count: int,
    overall_sentiment: float,
) -> Tuple[List, List, List, List]:
    strengths     = []
    weaknesses    = []
    opportunities = []
    threats       = []

    # Rating anchor
    if rating:
        if rating >= 4.5:
            strengths.append(f"Excellent Google Maps rating of ★{rating} — strong trust signal for new customers")
        elif rating >= 4.0:
            strengths.append(f"Good Google Maps rating of ★{rating} — above-average market position")
        elif rating >= 3.5:
            weaknesses.append(f"Average rating of ★{rating} — room for improvement against higher-rated competitors")
        else:
            weaknesses.append(f"Below-average rating of ★{rating} — significant risk of losing customers to competitors")

    # Review volume
    if review_count >= 1000:
        strengths.append(f"Very high review volume ({review_count:,}) — strong market presence and discoverability")
    elif review_count >= 200:
        strengths.append(f"Established review base ({review_count:,} reviews) — good Google Maps visibility")
    elif review_count >= 50:
        opportunities.append(f"Growing review base ({review_count} reviews) — targeted campaigns could boost visibility")
    elif review_count > 0:
        weaknesses.append(f"Low review volume ({review_count} reviews) — limited social proof and discoverability")
        opportunities.append("Actively encourage satisfied customers to leave Google reviews")
    else:
        weaknesses.append("No review data available — Google Maps visibility unknown")

    # Theme-driven bullets — sorted by signal strength (count x |score|)
    scored_themes = sorted(
        [(k, v) for k, v in theme_sentiments.items() if v["count"] >= 2],
        key=lambda x: x[1]["count"] * abs(x[1]["score"]),
        reverse=True
    )

    for theme_key, data in scored_themes:
        label = data["label"]
        score = data["score"]
        count = data["count"]

        if score >= 0.4:
            strengths.append(
                f"Customers consistently praise {label} "
                f"(positive mentions in {count} review sentences)"
            )
        elif score >= 0.15:
            strengths.append(f"Generally positive mentions of {label} in customer reviews")
        elif score <= -0.4:
            weaknesses.append(
                f"Recurring complaints about {label} "
                f"(negative mentions in {count} review sentences)"
            )
        elif score <= -0.15:
            weaknesses.append(f"Mixed or negative feedback on {label} — worth monitoring")

        if score <= -0.2 and theme_key in ("service", "wait_time", "consistency", "cleanliness"):
            opportunities.append(
                f"Improving {label} could directly address the most common customer complaints"
            )

        if score < 0 and theme_key in ("food_quality", "price_value", "ambiance"):
            threats.append(
                f"Negative {label} feedback may push customers toward better-rated alternatives"
            )

    # Sentiment-level bullets
    if overall_sentiment > 0.5:
        opportunities.append("Strong positive word-of-mouth — leverage reviews in social media and marketing")
    elif overall_sentiment < -0.2:
        threats.append("Negative word-of-mouth risk — unaddressed complaints may spread and damage reputation")
        opportunities.append("Proactively respond to negative reviews to demonstrate customer care")

    # Market-level (always relevant)
    threats.append("Increasing local competition — new entrants and expanding chains in the area")
    threats.append("Changing consumer preferences and economic conditions affecting dining frequency")
    opportunities.append("Google Maps optimisation (photos, posts, responses) can improve discoverability for free")

    # Padding defaults — only added when review text gives insufficient signals
    padding = {
        "strengths":     ["Accessible local location", "Established presence in local market", "Diverse menu offerings"],
        "weaknesses":    ["Limited digital marketing compared to chain competitors", "Potential peak-hour inconsistency", "Dependency on Google Maps as primary discovery channel"],
        "opportunities": ["Partnership with local delivery platforms", "Loyalty programme or repeat-customer incentives", "Seasonal menu updates to drive repeat visits"],
        "threats":       ["New market entrants with stronger brand or funding", "Economic downturn reducing discretionary dining spend", "A single viral negative review can disproportionately impact ratings"],
    }
    for key, lst in [("strengths", strengths), ("weaknesses", weaknesses),
                     ("opportunities", opportunities), ("threats", threats)]:
        for pad in padding[key]:
            if len(lst) >= 3:
                break
            if pad not in lst:
                lst.append(pad)

    return strengths[:5], weaknesses[:5], opportunities[:5], threats[:5]


def analyze_place_swot(place_data: Dict) -> Dict:
    name         = place_data.get("name", "Unknown")
    rating       = place_data.get("rating")
    review_count = place_data.get("reviews", 0) or 0
    scraped      = place_data.get("scraped_reviews", []) or []

    overall_sentiment = 0.0
    theme_sentiments  = {}

    if scraped and sia:
        texts = [r["text"] for r in scraped if r.get("text") and r["text"] != "[Rating Only]"]
        if texts:
            scores = [sia.polarity_scores(t)["compound"] for t in texts[:50]]
            overall_sentiment = round(sum(scores) / len(scores), 3)
            theme_sentiments  = _extract_theme_sentiments(scraped)
    elif rating:
        overall_sentiment = round((rating - 3.0) / 2.0, 3)

    avg_review_rating = None
    if scraped:
        ratings = [r["rating"] for r in scraped if isinstance(r.get("rating"), (int, float))]
        if ratings:
            avg_review_rating = round(sum(ratings) / len(ratings), 1)

    effective_rating = avg_review_rating or rating

    strengths, weaknesses, opportunities, threats = _build_swot_from_themes(
        theme_sentiments  = theme_sentiments,
        name              = name,
        rating            = effective_rating,
        review_count      = review_count,
        overall_sentiment = overall_sentiment,
    )

    logger.debug(
        f"[SWOT] {name}: rating={effective_rating}, sentiment={overall_sentiment}, "
        f"scraped={len(scraped)}, themes={list(theme_sentiments.keys())}"
    )

    return {
        "name":            name,
        "rating":          effective_rating,
        "review_count":    review_count,
        "scraped_count":   len(scraped),
        "sentiment_score": overall_sentiment,
        "swot": {
            "strengths":     strengths,
            "weaknesses":    weaknesses,
            "opportunities": opportunities,
            "threats":       threats,
        }
    }


def analyze_batch_swot(places: List[Dict], progress_callback=None) -> Dict:
    individual_analyses = []
    selected = [p for p in places if p.get("selected", True)]
    total = len(selected)

    for i, place in enumerate(selected):
        individual_analyses.append(analyze_place_swot(place))
        if progress_callback:
            progress_callback(
                i + 1, total,
                f"Analysing {place.get('name', 'place')} ({i+1}/{total})..."
            )

    return {
        "individual_analyses":  individual_analyses,
        "competitive_analysis": generate_competitive_analysis(individual_analyses),
    }


def generate_competitive_analysis(analyses: List[Dict]) -> Dict:
    if not analyses:
        return {}

    rated         = [a for a in analyses if a.get("rating")]
    avg_rating    = round(sum(a["rating"] for a in rated) / len(rated), 2) if rated else 0
    avg_sentiment = round(sum(a.get("sentiment_score", 0) for a in analyses) / len(analyses), 2)
    top           = max(analyses, key=lambda x: x.get("rating") or 0)
    lowest        = min(analyses, key=lambda x: x.get("rating") or 5)

    common_strengths  = defaultdict(int)
    common_weaknesses = defaultdict(int)

    for a in analyses:
        for s in a["swot"]["strengths"]:
            common_strengths[s[:60]] += 1
        for w in a["swot"]["weaknesses"]:
            common_weaknesses[w[:60]] += 1

    insights = []
    if avg_rating < 3.5:
        insights.append("Market shows low overall satisfaction — strong opportunity for differentiation through superior service")
    elif avg_rating >= 4.5:
        insights.append("Highly competitive market — excellence is the baseline, not the differentiator")
    else:
        insights.append("Mixed market satisfaction — consistency and reliability are key competitive advantages")

    if avg_sentiment > 0.4:
        insights.append("Strongly positive sentiment market-wide — word-of-mouth is the primary trust signal")
    elif avg_sentiment > 0.1:
        insights.append("Moderately positive sentiment — businesses that actively collect reviews gain a visibility advantage")
    elif avg_sentiment < -0.1:
        insights.append("Widespread negative sentiment — a standout player with great service could capture significant share")

    insights.append("Google Maps rating and review volume are the primary discovery and trust signals in this market")

    return {
        "total_analyzed":       len(analyses),
        "average_rating":       avg_rating,
        "average_sentiment":    avg_sentiment,
        "market_leader":        top.get("name"),
        "market_leader_rating": top.get("rating"),
        "lowest_rated":         lowest.get("name"),
        "lowest_rated_rating":  lowest.get("rating"),
        "common_strengths":     sorted(common_strengths.items(),  key=lambda x: x[1], reverse=True)[:5],
        "common_weaknesses":    sorted(common_weaknesses.items(), key=lambda x: x[1], reverse=True)[:5],
        "market_insights":      insights,
    }