import os
import tempfile
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from fastapi.responses import FileResponse
from app.core.database import get_db
from app.api.deps import get_context_organization_id
from app.api.routes.resume_routes import format_candidate_response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Analytics"])

def get_date_ranges(date_range: str, custom_start: Optional[str] = None, custom_end: Optional[str] = None):
    now = datetime.utcnow()
    current_query = {}
    prev_query = {}
    
    if date_range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start}
        prev_start = start - timedelta(days=1)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start, "$lt": end}
        prev_start = start - timedelta(days=1)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "this_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start}
        prev_start = start - timedelta(days=7)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "last_7_days":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start}
        prev_start = start - timedelta(days=7)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "last_30_days":
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start}
        prev_start = start - timedelta(days=30)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start}
        last_day_prev_month = start - timedelta(days=1)
        prev_start = last_day_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "last_month":
        last_day_last_month = now.replace(day=1) - timedelta(days=1)
        start = last_day_last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start, "$lt": end}
        last_day_prev_prev_month = start - timedelta(days=1)
        prev_start = last_day_prev_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "this_quarter":
        quarter = (now.month - 1) // 3 + 1
        start_month = 3 * quarter - 2
        start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start}
        prev_quarter_month = start_month - 3
        prev_year = now.year
        if prev_quarter_month <= 0:
            prev_quarter_month += 12
            prev_year -= 1
        prev_start = now.replace(year=prev_year, month=prev_quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "this_year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        current_query = {"$gte": start}
        prev_start = start.replace(year=start.year - 1)
        prev_query = {"$gte": prev_start, "$lt": start}
    elif date_range == "custom" and custom_start and custom_end:
        try:
            start = datetime.strptime(custom_start, "%Y-%m-%d")
            end = datetime.strptime(custom_end, "%Y-%m-%d") + timedelta(days=1)
            current_query = {"$gte": start, "$lt": end}
            delta = end - start
            prev_start = start - delta
            prev_query = {"$gte": prev_start, "$lt": start}
        except ValueError:
            pass

    return current_query, prev_query

def get_base_pipeline(metric: str):
    # Returns the $cond for the specific metric.
    # NOTE: downstream funnel statuses are included in upstream metrics so the
    # hiring funnel stays monotonic (a "selected" candidate also counts as having
    # been "interested" and "interviewed").
    if metric == "candidates":
        return {"$literal": 1}
    if metric == "screened":
        return {"$cond": [{"$gt": ["$resume_score", 0]}, 1, 0]}
    if metric == "calls":
        return {"$cond": [{"$eq": ["$call_status", "completed"]}, 1, 0]}
    if metric == "interested":
        return {"$cond": [{"$in": ["$status", ["interested", "interview", "interview_completed", "interview_scheduled", "selected", "hired"]]}, 1, 0]}
    if metric == "interviews":
        # AI Interview stage: candidate has been invited to / has completed an AI interview,
        # or progressed past it. (Legacy "interview_scheduled" kept for backward compatibility.)
        return {"$cond": [{"$in": ["$status", ["interview", "interview_completed", "interview_scheduled", "selected", "hired"]]}, 1, 0]}
    if metric == "hired":
        return {"$cond": [{"$eq": ["$status", "hired"]}, 1, 0]}
    if metric == "callbacks":
        return {"$cond": [{"$eq": ["$status", "callback_required"]}, 1, 0]}
    if metric == "selected":
        return {"$cond": [{"$in": ["$status", ["selected", "hired"]]}, 1, 0]}
    if metric == "not_interested":
        return {"$cond": [{"$in": ["$status", ["not_interested", "rejected"]]}, 1, 0]}
    return 0

@router.get("/dashboard")
async def get_dashboard_metrics(
    job_id: Optional[str] = None, 
    date_range: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    db = get_db()
    
    current_date_query, prev_date_query = get_date_ranges(date_range, custom_start, custom_end)
    
    async def fetch_metrics(date_filter):
        match = {"organization_id": org_id}
        if job_id:
            match["job_id"] = job_id
        if date_filter:
            match["created_at"] = date_filter
            
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "total_candidates": {"$sum": 1},
                "screened": {"$sum": get_base_pipeline("screened")},
                "calls_completed": {"$sum": get_base_pipeline("calls")},
                "interested": {"$sum": get_base_pipeline("interested")},
                "callback_required": {"$sum": get_base_pipeline("callbacks")},
                "interviews": {"$sum": get_base_pipeline("interviews")},
                "selected": {"$sum": get_base_pipeline("selected")},
                "not_interested": {"$sum": get_base_pipeline("not_interested")},
                "hired": {"$sum": get_base_pipeline("hired")}
            }}
        ]
        res = await db.candidates.aggregate(pipeline).to_list(1)
        if res:
            res[0].pop("_id", None)
            return res[0]
        return {
            "total_candidates": 0, "screened": 0, "calls_completed": 0, 
            "interested": 0, "callback_required": 0, "interviews": 0, 
            "selected": 0, "not_interested": 0, "hired": 0
        }

    current = await fetch_metrics(current_date_query)
    previous = await fetch_metrics(prev_date_query)
    
    # Calculate percentage changes
    def calc_pct(curr, prev):
        if prev == 0:
            return 100 if curr > 0 else 0
        return round(((curr - prev) / prev) * 100, 1)

    return {
        "current": current,
        "previous": previous,
        "trends": {k: calc_pct(current[k], previous[k]) for k in current.keys()}
    }

@router.get("/candidates")
async def get_analytics_candidates(
    job_id: Optional[str] = None,
    date_range: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    db = get_db()
    current_date_query, _ = get_date_ranges(date_range, custom_start, custom_end)
    match = {"organization_id": org_id}
    if job_id:
        match["job_id"] = job_id
    if current_date_query:
        match["created_at"] = current_date_query

    cursor = db.candidates.find(match).sort("created_at", -1)
    candidates = await cursor.to_list(length=1000)
    return [format_candidate_response(c) for c in candidates]

@router.get("/funnel")
async def get_funnel_metrics(
    job_id: Optional[str] = None,
    date_range: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    db = get_db()
    current_date_query, _ = get_date_ranges(date_range, custom_start, custom_end)
    match = {"organization_id": org_id}
    if job_id:
        match["job_id"] = job_id
    if current_date_query:
        match["created_at"] = current_date_query

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "candidates": {"$sum": 1},
            "screened": {"$sum": get_base_pipeline("screened")},
            "interested": {"$sum": get_base_pipeline("interested")},
            "interview": {"$sum": get_base_pipeline("interviews")},
            "selected": {"$sum": {"$cond": [{"$in": ["$status", ["selected", "hired"]]}, 1, 0]}},
            "hired": {"$sum": get_base_pipeline("hired")}
        }}
    ]
    res = await db.candidates.aggregate(pipeline).to_list(1)
    if res:
        res[0].pop("_id", None)
        return res[0]
    return {"candidates": 0, "screened": 0, "interested": 0, "interview": 0, "selected": 0, "hired": 0}

@router.get("/roles")
async def get_role_metrics(
    date_range: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    db = get_db()
    current_date_query, _ = get_date_ranges(date_range, custom_start, custom_end)
    
    # 1. Fetch ALL jobs for this organization so we show 0-candidate jobs too
    all_jobs_cursor = db.jobs_board.find({"organization_id": org_id})
    all_jobs = await all_jobs_cursor.to_list(None)
    
    # Initialize dictionary with 0s for every active job
    stats_map = {}
    for job in all_jobs:
        job_id = job.get("id") or str(job.get("_id"))
        stats_map[job_id] = {
            "job_id": job_id,
            "role": job.get("title", "Unknown Role"),
            "candidates": 0,
            "screened": 0,
            "calls_completed": 0,
            "interested": 0,
            "callbacks": 0,
            "interviews": 0,
            "selected": 0,
            "not_interested": 0,
            "hired": 0
        }
        
    # Also initialize for unassigned candidates
    stats_map[None] = {
        "job_id": None,
        "role": "Unassigned Candidates",
        "candidates": 0,
        "screened": 0,
        "calls_completed": 0,
        "interested": 0,
        "callbacks": 0,
        "interviews": 0,
        "selected": 0,
        "not_interested": 0,
        "hired": 0
    }

    # 2. Run aggregation on candidates to get actual stats
    match = {"organization_id": org_id}
    if current_date_query:
        match["created_at"] = current_date_query

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$job_id",
            "candidates": {"$sum": 1},
            "screened": {"$sum": get_base_pipeline("screened")},
            "calls_completed": {"$sum": get_base_pipeline("calls")},
            "interested": {"$sum": get_base_pipeline("interested")},
            "callbacks": {"$sum": get_base_pipeline("callbacks")},
            "interviews": {"$sum": get_base_pipeline("interviews")},
            "selected": {"$sum": get_base_pipeline("selected")},
            "not_interested": {"$sum": get_base_pipeline("not_interested")},
            "hired": {"$sum": get_base_pipeline("hired")}
        }}
    ]
    
    results = await db.candidates.aggregate(pipeline).to_list(100)
    
    # 3. Update the stats_map with actual counts
    for r in results:
        job_id = r["_id"]
        if job_id not in stats_map:
            # Fallback for deleted jobs that still have candidates
            if job_id is None:
                role_name = "Unassigned Candidates"
            else:
                missing_job = await db.jobs_board.find_one({"id": job_id})
                role_name = missing_job["title"] if missing_job else "Deleted Role"
            stats_map[job_id] = {
                "job_id": job_id,
                "role": role_name,
                "candidates": 0,
                "screened": 0,
                "calls_completed": 0,
                "interested": 0,
                "callbacks": 0,
                "interviews": 0,
                "selected": 0,
                "not_interested": 0,
                "hired": 0
            }
            
        stats_map[job_id]["candidates"] += r.get("candidates", 0)
        stats_map[job_id]["screened"] += r.get("screened", 0)
        stats_map[job_id]["calls_completed"] += r.get("calls_completed", 0)
        stats_map[job_id]["interested"] += r.get("interested", 0)
        stats_map[job_id]["callbacks"] += r.get("callbacks", 0)
        stats_map[job_id]["interviews"] += r.get("interviews", 0)
        stats_map[job_id]["selected"] += r.get("selected", 0)
        stats_map[job_id]["not_interested"] += r.get("not_interested", 0)
        stats_map[job_id]["hired"] += r.get("hired", 0)

    # Remove unassigned candidates if there are none
    if stats_map[None]["candidates"] == 0:
        del stats_map[None]
        
    return list(stats_map.values())

@router.get("/trend")
async def get_trend_data(
    metric: str = "candidates", 
    period: str = "daily", # daily, weekly, monthly
    job_id: Optional[str] = None, 
    date_range: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    db = get_db()
    current_date_query, _ = get_date_ranges(date_range, custom_start, custom_end)
    match = {"organization_id": org_id}
    if job_id:
        match["job_id"] = job_id
    if current_date_query:
        match["created_at"] = current_date_query

    format_str = "%Y-%m-%d"
    if period == "weekly":
        format_str = "%Y-%U"
    elif period == "monthly":
        format_str = "%Y-%m"
        
    pipeline = [
        {"$match": match},
        {
            "$project": {
                "date": {"$dateToString": {"format": format_str, "date": "$created_at"}},
                "is_match": get_base_pipeline(metric)
            }
        },
        {"$group": {
            "_id": "$date",
            "count": {"$sum": "$is_match"}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    results = await db.candidates.aggregate(pipeline).to_list(100)
    return [{"date": r["_id"], "count": r["count"]} for r in results]

@router.get("/report")
async def get_report_data(
    period: str = "daily", # daily, weekly, monthly
    job_id: Optional[str] = None,
    date_range: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    db = get_db()
    current_date_query, _ = get_date_ranges(date_range, custom_start, custom_end)
    match = {"organization_id": org_id}
    if job_id:
        match["job_id"] = job_id
    if current_date_query:
        match["created_at"] = current_date_query

    format_str = "%Y-%m-%d"
    if period == "weekly":
        format_str = "%Y-%U"
    elif period == "monthly":
        format_str = "%Y-%m"

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"$dateToString": {"format": format_str, "date": "$created_at"}},
            "candidates": {"$sum": 1},
            "screened": {"$sum": get_base_pipeline("screened")},
            "calls": {"$sum": get_base_pipeline("calls")},
            "interested": {"$sum": get_base_pipeline("interested")},
            "callbacks": {"$sum": get_base_pipeline("callbacks")},
            "interviews": {"$sum": get_base_pipeline("interviews")},
            "selected": {"$sum": get_base_pipeline("selected")},
            "not_interested": {"$sum": get_base_pipeline("not_interested")},
            "hired": {"$sum": get_base_pipeline("hired")}
        }},
        {"$sort": {"_id": -1}} # newest first
    ]
    
    results = await db.candidates.aggregate(pipeline).to_list(100)
    return [{"date": r["_id"], **{k: v for k, v in r.items() if k != "_id"}} for r in results]

@router.get("/export")
async def export_analytics(
    report_type: str = Query(..., description="daily, weekly, monthly, roles"),
    format: str = Query("excel", description="excel or csv"),
    date_range: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    import pandas as pd
    
    db = get_db()
    current_date_query, _ = get_date_ranges(date_range, custom_start, custom_end)
    match = {"organization_id": org_id}
    if current_date_query:
        match["created_at"] = current_date_query

    data = []
    
    if report_type == "roles":
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": "$job_id",
                "Candidates": {"$sum": 1},
                "Screened": {"$sum": get_base_pipeline("screened")},
                "Interviews": {"$sum": get_base_pipeline("interviews")},
                "Hired": {"$sum": get_base_pipeline("hired")}
            }}
        ]
        results = await db.candidates.aggregate(pipeline).to_list(100)
        
        job_ids = [r["_id"] for r in results if r["_id"]]
        jobs_cursor = db.jobs_board.find({"id": {"$in": job_ids}})
        jobs_map = {job["id"]: job["title"] for job in await jobs_cursor.to_list(None)}
        
        for r in results:
            job_id = r["_id"]
            role_name = jobs_map.get(job_id, "Unassigned Candidates") if job_id else "Unassigned Candidates"
            data.append({
                "Role": role_name,
                "Candidates": r["Candidates"],
                "Screened": r["Screened"],
                "Interviews": r["Interviews"],
                "Hired": r["Hired"]
            })
    else:
        date_format = "%Y-%m-%d"
        if report_type == "monthly": date_format = "%Y-%m"
        elif report_type == "weekly": date_format = "%Y-%U"
            
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": {"$dateToString": {"format": date_format, "date": "$created_at"}},
                "Candidates": {"$sum": 1},
                "Screened": {"$sum": get_base_pipeline("screened")},
                "Interviews": {"$sum": get_base_pipeline("interviews")},
                "Hired": {"$sum": get_base_pipeline("hired")}
            }},
            {"$sort": {"_id": 1}}
        ]
        results = await db.candidates.aggregate(pipeline).to_list(1000)
        data = [{"Period": r["_id"], "Candidates": r["Candidates"], "Screened": r["Screened"], "Interviews": r["Interviews"], "Hired": r["Hired"]} for r in results]

    df = pd.DataFrame(data) if data else pd.DataFrame(columns=["Period" if report_type != "roles" else "Role", "Candidates", "Screened", "Interviews", "Hired"])
    
    file_ext = "xlsx" if format == "excel" else "csv"
    fd, temp_path = tempfile.mkstemp(suffix=f".{file_ext}")
    os.close(fd)
    
    if format == "csv":
        df.to_csv(temp_path, index=False)
        media_type = "text/csv"
    else:
        df.to_excel(temp_path, index=False)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        format = "xlsx"
        
    filename = f"hireonomous_report_{report_type}.{format}"
    return FileResponse(path=temp_path, filename=filename, media_type=media_type)

@router.get("/callbacks")
async def get_callback_analytics(
    job_id: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    db = get_db()
    match = {"organization_id": org_id, "status": "callback_required"}
    if job_id:
        match["job_id"] = job_id
        
    cursor = db.candidates.find(match).sort("created_at", -1).limit(10)
    upcoming_callbacks = await cursor.to_list(length=10)
    
    return [format_candidate_response(c) for c in upcoming_callbacks]

@router.get("/ai-screening")
async def get_ai_screening_analytics(
    job_id: Optional[str] = None,
    date_range: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id)
):
    db = get_db()
    current_date_query, _ = get_date_ranges(date_range, custom_start, custom_end)
    match = {"organization_id": org_id}
    if job_id:
        match["job_id"] = job_id
    if current_date_query:
        match["created_at"] = current_date_query
        
    pipeline = [
        {"$match": match},
        {"$project": {
            "score": {"$ifNull": ["$screening_score", "$resume_score"]}
        }},
        {"$match": {"score": {"$gt": 0}}},
        {"$group": {
            "_id": None,
            "total_screened": {"$sum": 1},
            "avg_score": {"$avg": "$score"},
            "high_match": {"$sum": {"$cond": [{"$gte": ["$score", 80]}, 1, 0]}},
            "medium_match": {"$sum": {"$cond": [{"$and": [{"$gte": ["$score", 60]}, {"$lt": ["$score", 80]}]}, 1, 0]}},
            "low_match": {"$sum": {"$cond": [{"$lt": ["$score", 60]}, 1, 0]}}
        }}
    ]
    
    res = await db.candidates.aggregate(pipeline).to_list(1)
    if res:
        res[0].pop("_id", None)
        res[0]["avg_score"] = round(res[0]["avg_score"], 1)
        return res[0]
        
    return {
        "total_screened": 0,
        "avg_score": 0,
        "high_match": 0,
        "medium_match": 0,
        "low_match": 0
    }
