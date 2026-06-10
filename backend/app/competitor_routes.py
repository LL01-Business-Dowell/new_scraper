"""
competitor_routes.py
---------------------
FastAPI routes for competitor search, approval, and SWOT analysis.
Integrates google_maps_scraper.py and swot_analyzer.py
"""

import uuid
import logging
from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import requests

from .google_maps_scraper import search_google_maps_competitors
from .swot_analyzer import analyze_batch_swot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/competitors", tags=["competitors"])

# In-memory task store for competitor analysis
competitor_tasks = {}


class SearchRequest(BaseModel):
    """Request to search for competitors on Google Maps."""
    keyword: str
    city: str
    country: str
    establishment_name: str
    radius_km: float = 5.0
    limit: int = 100


class ApproveListRequest(BaseModel):
    """Request to approve/edit the competitor list and start analysis."""
    task_id: str
    approved_places: List[dict]  # List of place dicts with "selected": True/False


@router.post("/search")
async def search_competitors(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Search Google Maps for competitors matching keyword in city + radius.
    
    Returns immediately with task_id.
    Frontend polls GET /competitors/progress/{task_id} to get results.
    """
    task_id = str(uuid.uuid4())
    
    logger.info(
        f"[COMPETITOR SEARCH] task_id={task_id} "
        f"keyword={request.keyword} city={request.city} radius={request.radius_km}km"
    )
    
    # Store task
    competitor_tasks[task_id] = {
        "status": "searching",
        "progress": 0,
        "status_message": "Initializing Google Maps search...",
        "places": [],
        "error": None,
    }
    
    # Run search in background
    background_tasks.add_task(
        _search_worker,
        task_id=task_id,
        keyword=request.keyword,
        city=request.city,
        radius_km=request.radius_km,
        limit=request.limit,
        establishment_name=request.establishment_name,
    )
    
    return {"task_id": task_id}


def _search_worker(task_id: str, keyword: str, city: str, radius_km: float, limit: int, establishment_name: str):
    """Background worker to search for competitors."""
    try:
        def progress_callback(current, total, status_text):
            competitor_tasks[task_id]["progress"] = int((current / total) * 90)
            competitor_tasks[task_id]["status_message"] = status_text
        
        places = search_google_maps_competitors(
            keyword=keyword,
            city=city,
            radius_km=radius_km,
            limit=limit,
            progress_callback=progress_callback,
        )
        
        # Add the establishment itself as the first entry
        establishment = {
            "name": establishment_name,
            "address": f"{city}, {keyword} area",
            "rating": None,
            "reviews": 0,
            "url": "",
            "selected": True,
            "is_user_establishment": True,
        }
        places.insert(0, establishment)
        
        competitor_tasks[task_id]["places"] = places
        competitor_tasks[task_id]["status"] = "ready_for_approval"
        competitor_tasks[task_id]["progress"] = 100
        competitor_tasks[task_id]["status_message"] = f"Found {len(places)} places. Please review and approve."
        
        logger.info(f"[COMPETITOR SEARCH] task_id={task_id} completed. Found {len(places)} places.")
        
    except Exception as e:
        logger.error(f"[COMPETITOR SEARCH] task_id={task_id} failed: {str(e)}")
        competitor_tasks[task_id]["status"] = "error"
        competitor_tasks[task_id]["error"] = str(e)
        competitor_tasks[task_id]["progress"] = 100


@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """
    Poll the progress of a competitor search or analysis task.
    """
    if task_id not in competitor_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = competitor_tasks[task_id]
    
    return {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "status_message": task.get("status_message", ""),
        "places": task.get("places", []),
        "error": task.get("error"),
        "swot_results": task.get("swot_results"),
        "competitive_analysis": task.get("competitive_analysis"),
    }


@router.post("/approve-and-analyze")
async def approve_and_analyze(request: ApproveListRequest, background_tasks: BackgroundTasks):
    """
    User approves/edits the competitor list and kicks off SWOT analysis.
    
    Returns immediately with task_id.
    Frontend polls GET /competitors/progress/{task_id} for results.
    """
    if request.task_id not in competitor_tasks:
        raise HTTPException(status_code=404, detail="Original search task not found")
    
    task = competitor_tasks[request.task_id]
    task["status"] = "analyzing"
    task["progress"] = 0
    task["status_message"] = "Starting SWOT analysis..."
    task["approved_places"] = request.approved_places
    
    logger.info(
        f"[COMPETITOR ANALYSIS] task_id={request.task_id} "
        f"analyzing {len([p for p in request.approved_places if p.get('selected')])} places"
    )
    
    # Run analysis in background
    background_tasks.add_task(
        _analysis_worker,
        task_id=request.task_id,
        places=request.approved_places,
    )
    
    return {"task_id": request.task_id, "status": "analyzing"}


def _analysis_worker(task_id: str, places: List[dict]):
    """Background worker to run SWOT analysis on approved places."""
    try:
        def progress_callback(current, total, status_text):
            competitor_tasks[task_id]["progress"] = int((current / total) * 100)
            competitor_tasks[task_id]["status_message"] = status_text
        
        # Run batch SWOT analysis
        analysis_results = analyze_batch_swot(places, progress_callback=progress_callback)
        
        competitor_tasks[task_id]["swot_results"] = analysis_results["individual_analyses"]
        competitor_tasks[task_id]["competitive_analysis"] = analysis_results["competitive_analysis"]
        competitor_tasks[task_id]["status"] = "complete"
        competitor_tasks[task_id]["progress"] = 100
        competitor_tasks[task_id]["status_message"] = "Analysis complete!"
        
        logger.info(
            f"[COMPETITOR ANALYSIS] task_id={task_id} completed. "
            f"Analyzed {len(analysis_results['individual_analyses'])} places."
        )
        
    except Exception as e:
        logger.error(f"[COMPETITOR ANALYSIS] task_id={task_id} failed: {str(e)}")
        competitor_tasks[task_id]["status"] = "error"
        competitor_tasks[task_id]["error"] = str(e)
        competitor_tasks[task_id]["progress"] = 100


@router.get("/download-results/{task_id}")
async def download_results(task_id: str, format: str = "json"):
    """
    Download the analysis results as JSON or CSV.
    """
    if task_id not in competitor_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = competitor_tasks[task_id]
    
    if task["status"] != "complete":
        raise HTTPException(status_code=400, detail="Analysis not yet complete")
    
    if format == "json":
        return {
            "individual_analyses": task.get("swot_results", []),
            "competitive_analysis": task.get("competitive_analysis", {}),
        }
    
    elif format == "csv":
        import csv
        from io import StringIO
        from fastapi.responses import StreamingResponse
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Place Name",
            "Rating",
            "Review Count",
            "Sentiment Score",
            "Strength 1",
            "Strength 2",
            "Strength 3",
            "Weakness 1",
            "Weakness 2",
            "Weakness 3",
            "Opportunity 1",
            "Opportunity 2",
            "Opportunity 3",
            "Threat 1",
            "Threat 2",
            "Threat 3",
        ])
        
        # Write data rows
        for analysis in task.get("swot_results", []):
            swot = analysis.get("swot", {})
            writer.writerow([
                analysis.get("name", ""),
                analysis.get("rating", ""),
                analysis.get("review_count", ""),
                analysis.get("sentiment_score", ""),
                swot.get("strengths", [""])[0],
                swot.get("strengths", ["", ""])[1],
                swot.get("strengths", ["", "", ""])[2],
                swot.get("weaknesses", [""])[0],
                swot.get("weaknesses", ["", ""])[1],
                swot.get("weaknesses", ["", "", ""])[2],
                swot.get("opportunities", [""])[0],
                swot.get("opportunities", ["", ""])[1],
                swot.get("opportunities", ["", "", ""])[2],
                swot.get("threats", [""])[0],
                swot.get("threats", ["", ""])[1],
                swot.get("threats", ["", "", ""])[2],
            ])
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=competitor_analysis.csv"}
        )
    
    else:
        raise HTTPException(status_code=400, detail="Unsupported format")