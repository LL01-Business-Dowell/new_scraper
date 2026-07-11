"""
review_analysis_routes.py
-------------------------
FastAPI router for the single-establishment review analysis feature.
Route prefix: /api/review-analysis

Endpoints:
  POST /api/review-analysis/start      — start a scrape job
  GET  /api/review-analysis/progress/{task_id}  — poll progress
  GET  /api/review-analysis/report/pdf/{task_id} — download PDF report
"""

import uuid
import datetime
import io
import logging
import threading
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .single_review_scraper import scrape_single_establishment

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task store (same pattern as competitor_routes)
review_tasks = {}


# ── Request models ────────────────────────────────────────────────────────────


class StartReviewRequest(BaseModel):
    url: str
    days_back: int = 365


# ── Background worker ─────────────────────────────────────────────────────────


def _review_worker(task_id: str, url: str, days_back: int):
    def progress(current, total, message):
        review_tasks[task_id]["progress"] = current
        review_tasks[task_id]["status_message"] = message

    try:
        result = scrape_single_establishment(
            url=url,
            days_back=days_back,
            progress_callback=progress,
        )

        if result.get("error"):
            review_tasks[task_id]["status"] = "error"
            review_tasks[task_id]["error"] = result["error"]
            return

        review_tasks[task_id]["status"] = "complete"
        review_tasks[task_id]["progress"] = 100
        review_tasks[task_id][
            "status_message"
        ] = f"Complete — {len(result['reviews'])} reviews analysed"
        review_tasks[task_id]["business_details"] = result["business_details"]
        review_tasks[task_id]["reviews"] = result["reviews"]
        review_tasks[task_id]["sentiment"] = result["sentiment"]
        review_tasks[task_id]["scraped_at"] = result["scraped_at"]
        review_tasks[task_id]["days_back"] = days_back

        logger.info(
            f"[REVIEW ANALYSIS] task_id={task_id} complete. "
            f"{len(result['reviews'])} reviews for "
            f"{result['business_details'].get('name')}"
        )

    except Exception as e:
        review_tasks[task_id]["status"] = "error"
        review_tasks[task_id]["error"] = str(e)
        logger.error(f"[REVIEW ANALYSIS] task_id={task_id} failed: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/start")
async def start_review_analysis(request: StartReviewRequest):
    task_id = str(uuid.uuid4())

    review_tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "status_message": "Starting...",
        "business_details": {},
        "reviews": [],
        "sentiment": {},
        "error": None,
    }

    t = threading.Thread(
        target=_review_worker,
        args=(
            task_id,
            request.url,
            request.days_back,
        ),
        daemon=True,
    )
    t.start()

    return {
        "task_id": task_id,
    }


@router.get("/progress/{task_id}")
async def get_review_progress(task_id: str):
    task = review_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Don't return the full reviews list in progress poll — too large
    return {
        "status": task["status"],
        "progress": task["progress"],
        "status_message": task["status_message"],
        "business_details": task.get("business_details", {}),
        "sentiment": task.get("sentiment", {}),
        "review_count": len(task.get("reviews", [])),
        "error": task.get("error"),
        "scraped_at": task.get("scraped_at"),
        "days_back": task.get("days_back", 365),
    }


@router.get("/reviews/{task_id}")
async def get_reviews(task_id: str):
    """Return the full reviews list separately (can be large)."""
    task = review_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"reviews": task.get("reviews", [])}


@router.get("/report/pdf/{task_id}")
async def download_pdf_report(task_id: str):
    """Generate and stream a professional PDF report."""
    task = review_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "complete":
        raise HTTPException(status_code=400, detail="Analysis not complete yet")

    try:
        pdf_bytes = _generate_pdf_report(task)
        bd = task.get("business_details", {})
        filename = f"review-analysis-{bd.get('name', 'report').replace(' ', '-')}-{datetime.date.today()}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"[REVIEW ANALYSIS] PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


# ── PDF generation ────────────────────────────────────────────────────────────


def _generate_pdf_report(task: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        HRFlowable,
        PageBreak,
        KeepTogether,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    bd = task.get("business_details", {})
    sentiment = task.get("sentiment", {})
    reviews = task.get("reviews", [])
    days_back = task.get("days_back", 365)
    scraped_at = task.get("scraped_at", "")

    # Colours
    PURPLE = colors.HexColor("#7C3AED")
    PURPLE_DARK = colors.HexColor("#4C1D95")
    PURPLE_LITE = colors.HexColor("#EDE9FE")
    SLATE = colors.HexColor("#1E293B")
    SLATE_MID = colors.HexColor("#475569")
    SLATE_LITE = colors.HexColor("#F8FAFC")
    GREEN = colors.HexColor("#059669")
    RED = colors.HexColor("#DC2626")
    AMBER = colors.HexColor("#D97706")
    WHITE = colors.white

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2 * cm,
        title=f"Review Analysis — {bd.get('name', 'Report')}",
        author="DoWell Samanta Scraper",
    )

    styles = getSampleStyleSheet()

    def S(name, **kwargs):
        return ParagraphStyle(name, **kwargs)

    style_cover_title = S(
        "CoverTitle",
        fontSize=28,
        leading=34,
        textColor=WHITE,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    )
    style_cover_sub = S(
        "CoverSub",
        fontSize=12,
        leading=18,
        textColor=PURPLE_LITE,
        fontName="Helvetica",
        alignment=TA_LEFT,
    )
    style_cover_meta = S(
        "CoverMeta",
        fontSize=9,
        leading=14,
        textColor=PURPLE_LITE,
        fontName="Helvetica",
        alignment=TA_LEFT,
    )
    style_section = S(
        "Section",
        fontSize=13,
        leading=18,
        textColor=PURPLE_DARK,
        fontName="Helvetica-Bold",
        spaceBefore=18,
        spaceAfter=6,
    )
    style_subsection = S(
        "SubSection",
        fontSize=10,
        leading=14,
        textColor=SLATE,
        fontName="Helvetica-Bold",
        spaceBefore=10,
        spaceAfter=4,
    )
    style_body = S(
        "Body",
        fontSize=9,
        leading=14,
        textColor=SLATE_MID,
        fontName="Helvetica",
        spaceAfter=4,
    )
    style_body_bold = S(
        "BodyBold", fontSize=9, leading=14, textColor=SLATE, fontName="Helvetica-Bold"
    )
    style_small = S(
        "Small", fontSize=8, leading=12, textColor=SLATE_MID, fontName="Helvetica"
    )
    style_review_text = S(
        "ReviewText",
        fontSize=8,
        leading=13,
        textColor=SLATE_MID,
        fontName="Helvetica-Oblique",
        spaceAfter=2,
    )
    style_caption = S(
        "Caption",
        fontSize=8,
        leading=12,
        textColor=SLATE_MID,
        fontName="Helvetica",
        alignment=TA_CENTER,
    )
    style_number_big = S(
        "NumBig",
        fontSize=32,
        leading=36,
        textColor=PURPLE,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    style_number_label = S(
        "NumLabel",
        fontSize=8,
        leading=10,
        textColor=SLATE_MID,
        fontName="Helvetica",
        alignment=TA_CENTER,
    )

    W = A4[0] - 4 * cm  # usable width

    story = []

    # ── Cover page ────────────────────────────────────────────────────────────
    # Dark header block
    cover_table = Table(
        [
            [Paragraph(bd.get("name", "Business Review Analysis"), style_cover_title)],
            [Paragraph("Customer Review Analysis Report", style_cover_sub)],
            [Spacer(1, 0.3 * cm)],
            [
                Paragraph(
                    f"{bd.get('address', '')}  |  Rating: {'★' * int(round(bd.get('rating') or 0))} {bd.get('rating', 'N/A')}/5.0  |  {bd.get('total_reviews', 0):,} total reviews on Google Maps",
                    style_cover_meta,
                )
            ],
            [
                Paragraph(
                    f"Analysis period: last {days_back} days  |  Reviews scraped: {len(reviews):,}  |  Generated: {datetime.date.today().strftime('%d %B %Y')}",
                    style_cover_meta,
                )
            ],
        ],
        colWidths=[W],
    )
    cover_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PURPLE_DARK),
                ("TOPPADDING", (0, 0), (-1, 0), 24),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 24),
                ("LEFTPADDING", (0, 0), (-1, -1), 20),
                ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [PURPLE_DARK]),
            ]
        )
    )
    story.append(cover_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── KPI tiles row ──────────────────────────────────────────────────────────
    s = sentiment
    score = s.get("overall_score", 0)
    score_color = GREEN if score > 0.2 else (RED if score < -0.2 else AMBER)

    kpi_data = [
        [
            Paragraph(f"{len(reviews):,}", style_number_big),
            Paragraph(f"{s.get('avg_rating', 'N/A')}", style_number_big),
            Paragraph(
                f"{score:+.2f}",
                ParagraphStyle(
                    "ScoreNum",
                    fontSize=32,
                    leading=36,
                    textColor=score_color,
                    fontName="Helvetica-Bold",
                    alignment=TA_CENTER,
                ),
            ),
            Paragraph(
                f"{s.get('positive_count', 0):,}",
                ParagraphStyle(
                    "PosNum",
                    fontSize=32,
                    leading=36,
                    textColor=GREEN,
                    fontName="Helvetica-Bold",
                    alignment=TA_CENTER,
                ),
            ),
        ],
        [
            Paragraph("Reviews Scraped", style_number_label),
            Paragraph("Avg Review Rating", style_number_label),
            Paragraph(s.get("overall_label", ""), style_number_label),
            Paragraph("Positive Reviews", style_number_label),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[W / 4] * 4)
    kpi_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), SLATE_LITE),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(kpi_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Sentiment overview ─────────────────────────────────────────────────────
    story.append(Paragraph("Sentiment Overview", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.2 * cm))

    total_with_text = s.get("total_with_text", 1) or 1
    pos = s.get("positive_count", 0)
    neu = s.get("neutral_count", 0)
    neg = s.get("negative_count", 0)
    total_sent = pos + neu + neg or 1

    sent_data = [
        ["Sentiment", "Count", "Percentage", ""],
        [
            Paragraph('<font color="#059669">Positive</font>', style_body_bold),
            str(pos),
            f"{pos/total_sent*100:.1f}%",
            _bar_cell(pos / total_sent, GREEN, W * 0.3),
        ],
        [
            Paragraph('<font color="#B45309">Neutral</font>', style_body_bold),
            str(neu),
            f"{neu/total_sent*100:.1f}%",
            _bar_cell(neu / total_sent, AMBER, W * 0.3),
        ],
        [
            Paragraph('<font color="#DC2626">Negative</font>', style_body_bold),
            str(neg),
            f"{neg/total_sent*100:.1f}%",
            _bar_cell(neg / total_sent, RED, W * 0.3),
        ],
    ]
    sent_table = Table(sent_data, colWidths=[W * 0.25, W * 0.12, W * 0.13, W * 0.5])
    sent_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PURPLE_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (2, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE_LITE]),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(sent_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Rating distribution ────────────────────────────────────────────────────
    story.append(Paragraph("Rating Distribution", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.2 * cm))

    rd = s.get("rating_distribution", {})
    total_rated = sum(rd.values()) or 1
    rating_rows = [["Stars", "Count", "Distribution", ""]]
    for star in ["5", "4", "3", "2", "1"]:
        cnt = rd.get(star, 0)
        star_str = "★" * int(star) + "☆" * (5 - int(star))
        rating_rows.append(
            [
                Paragraph(f"{star_str}", style_body),
                str(cnt),
                f"{cnt/total_rated*100:.1f}%",
                _bar_cell(
                    cnt / total_rated,
                    (
                        AMBER
                        if int(star) >= 4
                        else (RED if int(star) <= 2 else colors.HexColor("#F59E0B"))
                    ),
                    W * 0.3,
                ),
            ]
        )
    rd_table = Table(rating_rows, colWidths=[W * 0.25, W * 0.12, W * 0.13, W * 0.5])
    rd_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PURPLE_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (2, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE_LITE]),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(rd_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Keyword themes ─────────────────────────────────────────────────────────
    story.append(Paragraph("Topic Frequency in Reviews", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.2 * cm))

    themes = s.get("keyword_themes", {})
    max_theme = max(themes.values(), default=1) or 1
    theme_rows = [["Topic", "Mentions", "Relative Frequency"]]
    for topic, count in sorted(themes.items(), key=lambda x: x[1], reverse=True):
        theme_rows.append(
            [
                topic,
                str(count),
                _bar_cell(count / max_theme, PURPLE, W * 0.45),
            ]
        )
    theme_table = Table(theme_rows, colWidths=[W * 0.30, W * 0.15, W * 0.55])
    theme_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PURPLE_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE_LITE]),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(theme_table)

    # ── Monthly breakdown ──────────────────────────────────────────────────────
    monthly = s.get("monthly_breakdown", {})
    if monthly:
        story.append(PageBreak())
        story.append(Paragraph("Monthly Review Breakdown", style_section))
        story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
        story.append(Spacer(1, 0.2 * cm))

        month_rows = [["Month", "Reviews", "Avg Sentiment", "Avg Rating"]]
        for month, data in sorted(monthly.items(), reverse=True):
            sc = data.get("avg_sentiment", 0)
            sc_color = (
                "#059669" if sc > 0.2 else ("#DC2626" if sc < -0.2 else "#B45309")
            )
            month_rows.append(
                [
                    datetime.datetime.strptime(month, "%Y-%m").strftime("%B %Y"),
                    str(data["count"]),
                    Paragraph(f'<font color="{sc_color}">{sc:+.3f}</font>', style_body),
                    f"{'★' * int(round(data['avg_rating'])) if data.get('avg_rating') else '—'} {data['avg_rating'] or '—'}",
                ]
            )
        month_table = Table(
            month_rows, colWidths=[W * 0.35, W * 0.15, W * 0.25, W * 0.25]
        )
        month_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PURPLE_DARK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE_LITE]),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(month_table)

    # ── Top reviews ────────────────────────────────────────────────────────────
    story.append(PageBreak())

    for section_label, phrases, border_color in [
        ("Most Positive Reviews", s.get("top_positive_phrases", []), GREEN),
        ("Most Critical Reviews", s.get("top_negative_phrases", []), RED),
    ]:
        if not phrases:
            continue
        story.append(Paragraph(section_label, style_section))
        story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
        story.append(Spacer(1, 0.2 * cm))

        for item in phrases:
            block = KeepTogether(
                [
                    Table(
                        [
                            [
                                Paragraph(
                                    f'{item.get("author", "Reviewer")}', style_body_bold
                                ),
                                Paragraph(
                                    f'{item.get("date", "")}',
                                    ParagraphStyle(
                                        "RightSmall",
                                        fontSize=8,
                                        textColor=SLATE_MID,
                                        fontName="Helvetica",
                                        alignment=TA_RIGHT,
                                    ),
                                ),
                            ]
                        ],
                        colWidths=[W * 0.7, W * 0.3],
                        style=TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, -1), SLATE_LITE),
                                ("TOPPADDING", (0, 0), (-1, -1), 6),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                ("LINEBELOW", (0, 0), (-1, -1), 2, border_color),
                            ]
                        ),
                    ),
                    Table(
                        [[Paragraph(f'"{item.get("text", "")}"', style_review_text)]],
                        colWidths=[W],
                        style=TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                                ("TOPPADDING", (0, 0), (-1, -1), 8),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                (
                                    "BOX",
                                    (0, 0),
                                    (-1, -1),
                                    0.5,
                                    colors.HexColor("#E2E8F0"),
                                ),
                            ]
                        ),
                    ),
                    Spacer(1, 0.25 * cm),
                ]
            )
            story.append(block)

    # ── Footer note ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor("#E2E8F0")))
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        Paragraph(
            f"Generated by DoWell Samanta Scraper  ·  {datetime.date.today().strftime('%d %B %Y')}  ·  "
            f"Data source: Google Maps  ·  Analysis period: last {days_back} days",
            style_caption,
        )
    )

    doc.build(story)
    return buf.getvalue()


def _bar_cell(ratio: float, color, max_width: float):
    """Create a simple filled-bar table cell for charts."""
    from reportlab.platypus import Table, Spacer
    from reportlab.platypus.tables import TableStyle

    bar_w = max(1, ratio * max_width)
    bar_table = Table([[""]], colWidths=[bar_w], rowHeights=[10])
    bar_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return bar_table
