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
        ratings = [r["rating"] for r in scraped if r.get("rating") is not None and isinstance(r.get("rating"), (int, float))]
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
    """Generate a comprehensive competitive landscape report from individual SWOTs."""
    if not analyses:
        return {}

    rated     = [a for a in analyses if a.get("rating")]
    reviewed  = [a for a in analyses if a.get("review_count", 0) > 0]
    sentd     = [a for a in analyses if a.get("sentiment_score") is not None]

    avg_rating    = round(sum(a["rating"] for a in rated) / len(rated), 2) if rated else 0
    avg_sentiment = round(sum(a.get("sentiment_score", 0) for a in sentd) / len(sentd), 2) if sentd else 0
    avg_reviews   = round(sum(a.get("review_count", 0) for a in analyses) / len(analyses)) if analyses else 0

    top     = max(analyses, key=lambda x: x.get("rating") or 0)
    lowest  = min(analyses, key=lambda x: x.get("rating") or 5)
    most_reviewed = max(analyses, key=lambda x: x.get("review_count") or 0)
    best_sentiment = max(analyses, key=lambda x: x.get("sentiment_score") or -1)

    # Rating distribution
    rating_dist = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    for a in rated:
        r = a["rating"]
        if r >= 4.5:   rating_dist["5"] += 1
        elif r >= 3.5: rating_dist["4"] += 1
        elif r >= 2.5: rating_dist["3"] += 1
        elif r >= 1.5: rating_dist["2"] += 1
        else:          rating_dist["1"] += 1

    # Sentiment distribution
    positive = sum(1 for a in sentd if a.get("sentiment_score", 0) > 0.2)
    neutral  = sum(1 for a in sentd if -0.2 <= a.get("sentiment_score", 0) <= 0.2)
    negative = sum(1 for a in sentd if a.get("sentiment_score", 0) < -0.2)

    # Common themes across all SWOTs
    common_strengths  = {}
    common_weaknesses = {}
    for a in analyses:
        for s in a["swot"]["strengths"]:
            common_strengths[s] = common_strengths.get(s, 0) + 1
        for w in a["swot"]["weaknesses"]:
            common_weaknesses[w] = common_weaknesses.get(w, 0) + 1

    top_strengths  = sorted(common_strengths.items(),  key=lambda x: x[1], reverse=True)[:5]
    top_weaknesses = sorted(common_weaknesses.items(), key=lambda x: x[1], reverse=True)[:5]

    # ── Market characterisation ────────────────────────────────────────────
    if avg_rating >= 4.5:
        market_quality = "highly competitive, with most players delivering excellent customer experiences"
        quality_label  = "Highly Competitive"
    elif avg_rating >= 4.0:
        market_quality = "competitive with generally strong performance across players"
        quality_label  = "Strong"
    elif avg_rating >= 3.5:
        market_quality = "moderately competitive with room for differentiation through service quality"
        quality_label  = "Moderate"
    else:
        market_quality = "underperforming overall, presenting a clear opportunity for a standout player"
        quality_label  = "Weak"

    if avg_sentiment > 0.4:
        sentiment_label = "Very Positive"
        sentiment_desc  = "Customers are broadly enthusiastic — word-of-mouth is a key growth driver in this market."
    elif avg_sentiment > 0.1:
        sentiment_label = "Positive"
        sentiment_desc  = "Customer sentiment leans positive, though there is clear room to stand out with consistently excellent experiences."
    elif avg_sentiment > -0.1:
        sentiment_label = "Mixed"
        sentiment_desc  = "Sentiment is mixed across the market — reliability and consistency are the main differentiators here."
    else:
        sentiment_label = "Negative"
        sentiment_desc  = "Negative sentiment dominates — a significant market-wide pain point that a quality-focused player can exploit."

    # ── Insights ───────────────────────────────────────────────────────────
    insights = []

    # Rating insight
    if avg_rating >= 4.5:
        insights.append("Excellence is the baseline in this market. With most competitors averaging above 4.5 stars, merely being good is not enough — you need a distinctive edge in either experience, value, or niche specialisation.")
    elif avg_rating >= 4.0:
        insights.append(f"The market average of {avg_rating}★ indicates strong competition. Achieving a 4.5+ rating would position a business in the top tier and significantly improve Google Maps visibility.")
    elif avg_rating >= 3.5:
        insights.append(f"With a market average of {avg_rating}★, there is a real opportunity for a well-run business to dominate by consistently hitting 4.5+. The bar is achievable.")
    else:
        insights.append(f"The low market average ({avg_rating}★) signals widespread dissatisfaction. A business that delivers reliable quality and service has an exceptional opportunity to become the clear market leader quickly.")

    # Sentiment insight
    insights.append(sentiment_desc)

    # Review volume insight
    if avg_reviews >= 500:
        insights.append(f"Review volumes are high (average {avg_reviews:,} per place), meaning Google Maps SEO is intensely competitive. A sustained review-generation strategy is essential to maintain visibility.")
    elif avg_reviews >= 100:
        insights.append(f"With an average of {avg_reviews:,} reviews per competitor, growing review volume is a medium-term priority — especially for newer entrants who need social proof to compete.")
    else:
        insights.append(f"Review volumes are low across the market (average {avg_reviews:,}). Early movers who actively collect reviews will gain a lasting Google Maps ranking advantage.")

    # Top vs lowest
    if top.get("rating") and lowest.get("rating"):
        gap = round(top["rating"] - lowest["rating"], 1)
        if gap >= 1.5:
            insights.append(f"There is a {gap}-star gap between the market leader ({top['name']}, ★{top['rating']}) and the lowest rated player ({lowest['name']}, ★{lowest['rating']}). This spread indicates significant quality variance — customers are actively choosing between very different experiences.")
        elif gap >= 0.5:
            insights.append(f"The gap between the top ({top['name']}, ★{top['rating']}) and bottom ({lowest['name']}, ★{lowest['rating']}) is {gap} stars — a moderately tight field where small improvements in service quality translate directly to competitive advantage.")

    # Common weakness as opportunity
    if top_weaknesses:
        most_common_weakness = top_weaknesses[0][0]
        insights.append(f"The most common weakness across competitors is: \"{most_common_weakness}\". Addressing this systematically represents the single biggest differentiator available in this market.")

    # Google Maps as discovery channel
    insights.append("Google Maps is the primary discovery and trust channel for local businesses in this category. Rating, review recency, photo quality, and response rate all directly affect search ranking and click-through rates.")

    # ── Strategic recommendations ──────────────────────────────────────────
    recommendations = []

    if avg_rating < 4.3:
        recommendations.append("Prioritise reaching a 4.5+ Google Maps rating — this is the single most impactful lever for organic discovery and customer trust in this market.")

    if avg_reviews < 200:
        recommendations.append("Launch an active review generation campaign. A simple post-visit message with a direct Maps review link can 3-5x review velocity within months.")

    if positive < len(analyses) * 0.6:
        recommendations.append("Address the root causes of negative sentiment identified in competitor reviews — these are the pain points customers are most vocal about and most willing to switch providers over.")

    recommendations.append("Respond to all Google reviews (positive and negative) within 48 hours. Review response rate is a Maps ranking signal and demonstrates active management to prospective customers.")
    recommendations.append("Ensure your Google Business Profile is fully completed: photos updated monthly, menu/services current, Q&A populated, and business hours accurate.")

    if top.get("name"):
        recommendations.append(f"Study {top['name']} (★{top.get('rating')}) closely — they are setting the quality benchmark this market is being judged against.")

    # ── Build narrative text report ────────────────────────────────────────
    sorted_by_rating = sorted(rated, key=lambda x: x.get("rating") or 0, reverse=True)
    top5 = sorted_by_rating[:5]

    narrative = f"""COMPETITIVE INTELLIGENCE REPORT
{'=' * 60}

EXECUTIVE SUMMARY
-----------------
This report covers {len(analyses)} businesses operating in the same competitive
space. The market is {market_quality}.

  Market Quality:     {quality_label}
  Average Rating:     ★{avg_rating} / 5.0
  Customer Sentiment: {sentiment_label} (score: {avg_sentiment:+.2f})
  Total Competitors:  {len(analyses)} analysed
  Avg Review Volume:  {avg_reviews:,} reviews per business

MARKET LEADER: {top.get('name', 'N/A')} — ★{top.get('rating', 'N/A')}
MOST REVIEWED: {most_reviewed.get('name', 'N/A')} — {most_reviewed.get('review_count', 0):,} reviews
BEST SENTIMENT: {best_sentiment.get('name', 'N/A')} — score {best_sentiment.get('sentiment_score', 0):+.2f}


RATING DISTRIBUTION
-------------------
  ★★★★★ (4.5–5.0): {rating_dist['5']} businesses  {'█' * rating_dist['5']}
  ★★★★  (3.5–4.4): {rating_dist['4']} businesses  {'█' * rating_dist['4']}
  ★★★   (2.5–3.4): {rating_dist['3']} businesses  {'█' * rating_dist['3']}
  ★★    (1.5–2.4): {rating_dist['2']} businesses  {'█' * rating_dist['2']}
  ★     (1.0–1.4): {rating_dist['1']} businesses  {'█' * rating_dist['1']}


SENTIMENT BREAKDOWN
-------------------
  Positive (>0.2):  {positive} businesses ({round(positive/len(analyses)*100) if analyses else 0}%)
  Neutral  (±0.2):  {neutral} businesses ({round(neutral/len(analyses)*100) if analyses else 0}%)
  Negative (<-0.2): {negative} businesses ({round(negative/len(analyses)*100) if analyses else 0}%)


TOP 5 COMPETITORS BY RATING
----------------------------"""

    for i, a in enumerate(top5, 1):
        narrative += f"\n  {i}. {a['name']}"
        narrative += f"\n     Rating: ★{a.get('rating', 'N/A')}  |  Reviews: {a.get('review_count', 0):,}  |  Sentiment: {a.get('sentiment_score', 0):+.2f}"
        if a['swot']['strengths']:
            narrative += f"\n     Key Strength: {a['swot']['strengths'][0]}"
        if a['swot']['weaknesses']:
            narrative += f"\n     Key Weakness: {a['swot']['weaknesses'][0]}"
        narrative += "\n"

    narrative += f"""

COMMON MARKET STRENGTHS
-----------------------
(Themes appearing across multiple competitors — the table stakes in this market)
"""
    for theme, count in top_strengths:
        pct = round(count / len(analyses) * 100)
        narrative += f"  • {theme} ({count}/{len(analyses)} businesses, {pct}%)\n"

    narrative += f"""

COMMON MARKET WEAKNESSES
------------------------
(Shared pain points — opportunities for differentiation)
"""
    for theme, count in top_weaknesses:
        pct = round(count / len(analyses) * 100)
        narrative += f"  • {theme} ({count}/{len(analyses)} businesses, {pct}%)\n"

    narrative += f"""

MARKET INSIGHTS
---------------
"""
    for i, insight in enumerate(insights, 1):
        # Word-wrap at ~70 chars
        words = insight.split()
        lines = []
        current = f"  {i}. "
        indent = "     "
        for word in words:
            if len(current) + len(word) + 1 > 75:
                lines.append(current)
                current = indent + word
            else:
                current += (" " if current.strip() else "") + word
        lines.append(current)
        narrative += "\n".join(lines) + "\n\n"

    narrative += f"""STRATEGIC RECOMMENDATIONS
--------------------------
"""
    for i, rec in enumerate(recommendations, 1):
        words = rec.split()
        lines = []
        current = f"  {i}. "
        indent  = "     "
        for word in words:
            if len(current) + len(word) + 1 > 75:
                lines.append(current)
                current = indent + word
            else:
                current += (" " if current.strip() else "") + word
        lines.append(current)
        narrative += "\n".join(lines) + "\n\n"

    narrative += f"""
{'=' * 60}
Report generated by DoWell Samanta Scraper
Businesses analysed: {len(analyses)}  |  Average rating: ★{avg_rating}
{'=' * 60}
"""

    return {
        "total_analyzed":           len(analyses),
        "average_rating":           avg_rating,
        "average_sentiment":        avg_sentiment,
        "average_reviews":          avg_reviews,
        "market_leader":            top.get("name"),
        "market_leader_rating":     top.get("rating"),
        "most_reviewed":            most_reviewed.get("name"),
        "most_reviewed_count":      most_reviewed.get("review_count", 0),
        "best_sentiment":           best_sentiment.get("name"),
        "lowest_rated":             lowest.get("name"),
        "lowest_rated_rating":      lowest.get("rating"),
        "rating_distribution":      rating_dist,
        "sentiment_breakdown":      {"positive": positive, "neutral": neutral, "negative": negative},
        "quality_label":            quality_label,
        "sentiment_label":          sentiment_label,
        "common_strengths":         top_strengths,
        "common_weaknesses":        top_weaknesses,
        "market_insights":          insights,
        "recommendations":          recommendations,
        "narrative_report":         narrative,
    }

def analyze_batch_swot(places: List[Dict], progress_callback=None) -> List[Dict]:
    """Analyze a batch of places. Backward-compatible wrapper over analyze_place_swot."""
    results = []
    for i, p in enumerate(places):
        results.append(analyze_place_swot(p))
        if progress_callback:
            progress_callback(i + 1, len(places), f"Analysed {p.get('name', '')}")
    return results