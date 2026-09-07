from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from app.services.email_service import EmailService

from app.api.deps import get_context_organization_id
from fastapi import Depends

router = APIRouter(prefix="/email")

@router.post("/send-shortlisted")
async def send_shortlisted_emails(job_id: Optional[str] = None, org_id: str = Depends(get_context_organization_id)):
    if not EmailService.is_configured():
        raise HTTPException(
            status_code=500,
            detail=(
                "SMTP is not configured. Please set SMTP_HOST, SMTP_PORT, SMTP_USER, "
                "SMTP_PASSWORD, and SMTP_FROM_EMAIL in backend/.env.local."
            ),
        )

    db = get_db()

    # Candidate-facing emails always sign off with the product name, not the
    # tenant/org name — keeps every candidate touchpoint consistent.
    company_name = settings.APP_NAME

    # "Email Interested" should only reach candidates who actually expressed interest
    # (post-screening status), scoped to the job currently selected in the UI —
    # not every resume-score-qualifying candidate across the whole organization.
    # `email_sent != True` makes the action idempotent: clicking it again does NOT
    # re-send to candidates who already received this email.
    query = {
        "status": "interested",
        "organization_id": org_id,
        "email_sent": {"$ne": True},
    }
    if job_id:
        query["job_id"] = job_id

    cursor = db.candidates.find(query, {"_id": 0}).sort("created_at", -1)
    candidates = await cursor.to_list(length=500)

    if not candidates:
        already = await db.candidates.count_documents({
            "status": "interested", "organization_id": org_id, "email_sent": True,
            **({"job_id": job_id} if job_id else {}),
        })
        return {
            "status": "success",
            "message": (
                f"No new interested candidates to email — {already} already received this email."
                if already else "No interested candidates found for this selection."
            ),
            "sent": 0, "skipped": already, "failed": 0, "errors": [],
        }

    # Resolve each candidate's actual job title from jobs_board (via job_id) so the
    # email names the job they're really being progressed for, instead of the
    # candidate's resume-parsed `role` guess, which is stale/generic and can be
    # identical across a candidate's applications to different jobs.
    job_ids = list({c.get("job_id") for c in candidates if c.get("job_id")})
    if job_ids:
        jobs_cursor = db.jobs_board.find({"id": {"$in": job_ids}}, {"_id": 0, "id": 1, "title": 1, "skills": 1})
        jobs_map = {j["id"]: j async for j in jobs_cursor}
        for c in candidates:
            job = jobs_map.get(c.get("job_id"))
            if job:
                if job.get("title"):
                    c["job_title_for_email"] = job["title"]
                if job.get("skills"):
                    c["job_skills_for_email"] = job["skills"]

    # send_bulk_shortlist_emails does blocking network I/O (smtplib, requests) per
    # candidate. Run it in a worker thread so a slow/hung SMTP connection can't
    # freeze the single asyncio event loop for every other request on the server.
    result = await run_in_threadpool(EmailService.send_bulk_shortlist_emails, candidates, company_name)

    # Mark emailed candidates so a second click does not re-send to them.
    if result.get("sent_ids"):
        await db.candidates.update_many(
            {"id": {"$in": result["sent_ids"]}},
            {"$set": {"email_sent": True}}
        )

    return {
        "status": "success",
        "message": (
            f"Email sent to {result['sent']} candidate(s) who hadn't been emailed yet. "
            f"Skipped (no valid email): {result['skipped']}. Failed: {result['failed']}. "
            f"Candidates who already received this email are not re-sent to."
        ),
        **result,
    }
