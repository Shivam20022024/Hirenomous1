"""AI Interview orchestration.

All interview business logic lives here; route handlers stay thin. Reuses:
  - OpenAI STT           -> app.services.voice_service.VoiceService
  - OpenAI TTS           -> app.services.tts_service.TTSService
  - LLM prompt logic     -> app.services.interview_prompt_engine
  - Email infra          -> app.services.email_service.EmailService
  - Audit trail          -> app.services.audit_service.AuditService
  - DB / org scoping     -> app.core.database, existing `candidates` / `jobs_board` conventions
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import get_db
from app.core.interview_auth import (
    generate_interview_token,
    hash_interview_token,
    token_expiry,
    resolve_interview_by_token,
)
from app.models.interview import (
    Interview,
    InterviewQuestion,
    InterviewScores,
    TERMINAL_STATUSES,
    RECRUITER_DECISIONS,
)
from app.services.audit_service import AuditService
from app.services.email_service import EmailService
from app.services import interview_prompt_engine as ipe
from app.services import interview_integrity as integrity_engine
from app.services.interview_storage import InterviewStorage
from app.services.tts_service import TTSService
from app.services.voice_service import VoiceService

logger = logging.getLogger(__name__)

RUBRIC_VERSION = "interview-rubric-v1"
# Candidate statuses from which an AI interview may be created (business rule #1).
INVITABLE_CANDIDATE_STATUSES = {"interested", "interview", "interview_completed", "selected"}


# ======================================================================
# Serialization helpers
# ======================================================================

def _iso(v):
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    # `session_meta` (raw IP list) stays server-side; the recruiter sees only the
    # derived flags/signals under `integrity`.
    out = {k: v for k, v in doc.items() if k not in ("_id", "token_hash", "session_meta")}
    for key in ("token_expires_at", "invited_at", "started_at", "completed_at",
                "decided_at", "created_at", "updated_at"):
        if key in out:
            out[key] = _iso(out[key])
    # Redact raw storage paths from answers; expose only booleans + the answer index
    # so a recruiter can stream a recording through the authenticated endpoint.
    # has_video/has_audio reflect whether the file ACTUALLY exists on the media
    # store (a ref alone isn't enough — the file may have been purged).
    redacted = []
    for i, ans in enumerate(out.get("answers", []) or []):
        if not isinstance(ans, dict):
            redacted.append(ans)
            continue
        a = {k: v for k, v in ans.items() if k not in ("audio_ref", "video_ref")}
        a["answer_index"] = i
        a["has_video"] = InterviewStorage.exists(ans.get("video_ref"))
        a["has_audio"] = InterviewStorage.exists(ans.get("audio_ref"))
        if "answered_at" in a:
            a["answered_at"] = _iso(a["answered_at"])
        redacted.append(a)
    if "answers" in out:
        out["answers"] = redacted
    for t in out.get("transcript", []) or []:
        if isinstance(t, dict) and "ts" in t:
            t["ts"] = _iso(t["ts"])
    return out


async def _record_session_meta(db, interview_id: str, ip: Optional[str], ua: Optional[str], event: str) -> None:
    """Append a session-provenance entry (IP + user-agent) for integrity checks.
    Best-effort, de-duplicated on the most recent (ip, ua), list capped at 50."""
    if not ip and not ua:
        return
    try:
        doc = await db.interviews.find_one({"id": interview_id}, {"_id": 0, "session_meta": 1})
        meta = (doc or {}).get("session_meta") or []
        if meta and meta[-1].get("ip") == ip and meta[-1].get("ua") == ua:
            return
        await db.interviews.update_one(
            {"id": interview_id},
            {"$push": {"session_meta": {
                "$each": [{"ip": ip, "ua": (ua or "")[:400], "at": datetime.utcnow().isoformat(), "event": event}],
                "$slice": -50,
            }}},
        )
    except Exception as exc:
        logger.warning(f"_record_session_meta failed for {interview_id}: {exc}")


def _base_question_count(plan: List[dict]) -> int:
    return len([q for q in plan if not q.get("is_followup")])


_NO_AUDIBLE = "(no audible answer was captured)"


def _answered_count(interview: dict) -> int:
    return len([a for a in (interview.get("answers") or []) if a.get("answer_text")])


def _substantive_answer_chars(interview: dict) -> int:
    """Total characters the candidate actually contributed — placeholder / empty
    answers don't count. Used to decide whether there is anything to evaluate."""
    total = 0
    for a in (interview.get("answers") or []):
        t = (a.get("answer_text") or "").strip()
        if t and t != _NO_AUDIBLE:
            total += len(t)
    return total


# ======================================================================
# Service
# ======================================================================

class InterviewService:

    # ------------------------------------------------------------------
    # Recruiter: create / invite
    # ------------------------------------------------------------------
    @staticmethod
    async def create_interview(
        *,
        org_id: str,
        recruiter_id: Optional[str],
        candidate_id: str,
        job_id: Optional[str] = None,
        interview_type: str = "ai_technical",
        question_count: Optional[int] = None,
        send_invite: bool = True,
    ) -> dict:
        db = get_db()

        candidate = await db.candidates.find_one({"id": candidate_id, "organization_id": org_id})
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        cand_status = (candidate.get("status") or "").lower()
        if cand_status not in INVITABLE_CANDIDATE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "AI Interviews can only be created for candidates who have reached the "
                    f"'interested' stage (current status: '{candidate.get('status')}')."
                ),
            )

        resolved_job_id = job_id or candidate.get("job_id")
        job = None
        if resolved_job_id:
            job = await db.jobs_board.find_one({"id": resolved_job_id, "organization_id": org_id})

        # Prevent duplicate active interviews for the same candidate + job.
        existing = await db.interviews.find_one({
            "organization_id": org_id,
            "candidate_id": candidate_id,
            "job_id": resolved_job_id,
            "status": {"$nin": TERMINAL_STATUSES},
        })
        if existing:
            logger.info(f"Returning existing active interview {existing['id']} for candidate {candidate_id}")
            return {"interview": _serialize(existing), "created": False}

        # Generate the reproducible question plan.
        count = question_count or settings.INTERVIEW_QUESTION_COUNT
        raw_plan = await ipe.generate_question_plan(job, candidate, count, interview_type)
        question_plan = [
            InterviewQuestion(
                text=q["text"],
                question_type=q.get("question_type", "technical"),
                sequence=idx + 1,
                target_skills=q.get("target_skills", []),
            ).model_dump()
            for idx, q in enumerate(raw_plan)
        ]

        token = generate_interview_token()
        expires_at = token_expiry()

        snapshot = {
            "job_context": ipe.job_context(job, fallback_jd=candidate.get("job_description", "")),
            "resume_context": ipe.safe_resume_context(candidate),
            "model": "gpt-4o-mini",
            "rubric_version": RUBRIC_VERSION,
            "job_title": (job or {}).get("title") or candidate.get("role") or "the role",
            "generated_at": datetime.utcnow().isoformat(),
        }

        interview = Interview(
            organization_id=org_id,
            candidate_id=candidate_id,
            job_id=resolved_job_id,
            interview_type=interview_type,
            status="invited",
            evaluation_status="pending",
            token_hash=hash_interview_token(token),
            token_expires_at=expires_at,
            question_plan=question_plan,
            snapshot=snapshot,
        )
        doc = interview.model_dump()
        doc["progress"] = {"plan_index": 0, "followups_used": 0, "pending_question": None}

        await db.interviews.insert_one(doc)

        update_fields = {
            "last_interaction": datetime.utcnow(),
        }
        if interview_type == "ai_l2_technical":
            update_fields["l2_interview_id"] = interview.id
            update_fields["l2_status"] = "interview"
        else:
            update_fields["status"] = "interview"
            update_fields["latest_interview_id"] = interview.id

        await db.candidates.update_one(
            {"id": candidate_id, "organization_id": org_id},
            {"$set": update_fields},
        )

        await AuditService.record(
            organization_id=org_id, event_type="interview_created", actor_type="recruiter",
            actor_id=recruiter_id, candidate_id=candidate_id, job_id=resolved_job_id,
            interview_id=interview.id, payload={"question_count": len(question_plan)},
        )

        invite_result = None
        interview_url = f"{settings.INTERVIEW_PUBLIC_BASE_URL.rstrip('/')}/interview/{token}"
        if send_invite:
            invite_result = await InterviewService._deliver_invite(
                org_id=org_id, recruiter_id=recruiter_id, interview_doc=doc,
                candidate=candidate, job=job, token=token,
            )

        fresh = await db.interviews.find_one({"id": interview.id})
        return {
            "interview": _serialize(fresh),
            "created": True,
            # The raw token / URL is returned ONCE, only to the creating recruiter.
            "interview_url": interview_url,
            "invite": invite_result,
        }

    @staticmethod
    async def _deliver_invite(*, org_id, recruiter_id, interview_doc, candidate, job, token) -> dict:
        db = get_db()
        job_title = (job or {}).get("title") or candidate.get("role") or "the position"
        interview_url = f"{settings.INTERVIEW_PUBLIC_BASE_URL.rstrip('/')}/interview/{token}"

        # Candidate-facing mail is branded with the hiring company (multi-tenant),
        # signed by the recruiter who actually sent the invite.
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1, "contact_email": 1, "reply_to": 1})
        company_name = (org or {}).get("name") or settings.APP_NAME
        recruiter = await db.users.find_one({"id": recruiter_id}, {"_id": 0, "name": 1}) if recruiter_id else None
        sender = EmailService.sender_for(org, (recruiter or {}).get("name"))

        email = (candidate.get("email") or "").strip()
        result = {"sent": False, "reason": None}
        if not email or "@" not in email:
            result["reason"] = "Candidate has no valid email address."
        elif not EmailService.is_configured():
            result["reason"] = "SMTP is not configured on the server."
        else:
            try:
                subject, body = EmailService.build_interview_invite_email(
                    candidate, job_title, interview_url, company_name=company_name, interview_type=interview_doc.get("interview_type", "ai_technical")
                )
                await run_in_threadpool(
                    lambda: EmailService.send_email(email, subject, body, **sender)
                )
                result["sent"] = True
            except Exception as exc:
                result["reason"] = f"Email send failed: {exc}"
                logger.error(f"Interview invite email failed for {interview_doc['id']}: {exc}")

        await db.interviews.update_one(
            {"id": interview_doc["id"]},
            {"$set": {"status": "invited", "invited_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
        )
        await AuditService.record(
            organization_id=org_id, event_type="interview_invited", actor_type="recruiter",
            actor_id=recruiter_id, candidate_id=candidate.get("id"), job_id=interview_doc.get("job_id"),
            interview_id=interview_doc["id"], payload={"email_sent": result["sent"]},
        )
        return result

    @staticmethod
    async def resend_invite(*, org_id: str, recruiter_id: Optional[str], interview_id: str) -> dict:
        """Rotate the token and re-send the invite email. If the interview had
        already reached a terminal state (e.g. the candidate submitted by
        mistake, or the link expired/failed), this is a full retake: prior
        answers, transcript, scores and recruiter decision are cleared so the
        candidate gets a genuinely fresh attempt rather than resuming stale data."""
        db = get_db()
        interview = await db.interviews.find_one({"id": interview_id, "organization_id": org_id})
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        if interview.get("status") == "cancelled":
            raise HTTPException(status_code=409, detail="Cannot resend — this interview was cancelled.")

        candidate = await db.candidates.find_one({"id": interview["candidate_id"], "organization_id": org_id})
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        job = None
        if interview.get("job_id"):
            job = await db.jobs_board.find_one({"id": interview["job_id"], "organization_id": org_id})

        # Rotate the token on every resend — invalidates any previously shared link.
        token = generate_interview_token()
        update_fields: Dict[str, Any] = {
            "token_hash": hash_interview_token(token),
            "token_expires_at": token_expiry(),
            "updated_at": datetime.utcnow(),
        }
        was_terminal = interview.get("status") in TERMINAL_STATUSES
        if was_terminal:
            update_fields.update({
                "status": "invited",
                "evaluation_status": "pending",
                "answers": [],
                "transcript": [],
                "scores": InterviewScores().model_dump(),
                "recommendation": None,
                "ai_report": {},
                "integrity": {},
                "session_meta": [],
                "started_at": None,
                "completed_at": None,
                "duration_seconds": None,
                "email_verified": False,
                "verification_attempts": 0,
                "progress": {"plan_index": 0, "followups_used": 0, "pending_question": None},
                "recruiter_decision": None,
                "recruiter_feedback": None,
                "recruiter_id": None,
                "decided_at": None,
            })
        await db.interviews.update_one({"id": interview_id}, {"$set": update_fields})

        if was_terminal:
            # A retake moves the candidate back into the interview stage, undoing
            # any decision that had already been made off the discarded attempt.
            await db.candidates.update_one(
                {"id": interview["candidate_id"], "organization_id": org_id},
                {"$set": {"status": "interview", "last_interaction": datetime.utcnow()}},
            )

        interview = await db.interviews.find_one({"id": interview_id})
        result = await InterviewService._deliver_invite(
            org_id=org_id, recruiter_id=recruiter_id, interview_doc=interview,
            candidate=candidate, job=job, token=token,
        )
        interview_url = f"{settings.INTERVIEW_PUBLIC_BASE_URL.rstrip('/')}/interview/{token}"
        await AuditService.record(
            organization_id=org_id, event_type="interview_resent", actor_type="recruiter",
            actor_id=recruiter_id, candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
            interview_id=interview_id, payload={"was_reset": was_terminal, "email_sent": result.get("sent")},
        )
        return {"invite": result, "interview_url": interview_url, "reset": was_terminal}

    @staticmethod
    async def bulk_invite(
        *, org_id: str, recruiter_id: Optional[str], job_id: Optional[str] = None, question_count: Optional[int] = None
    ) -> dict:
        """Create an AI interview + send the invite email for every 'interested'
        candidate (optionally scoped to one job). Each interview is candidate- and
        job-specific (one LLM call for the question plan), so calls are processed
        in small concurrent batches — same pattern as the resume Drive import."""
        db = get_db()
        query: Dict[str, Any] = {"organization_id": org_id, "status": "interested"}
        if job_id:
            query["job_id"] = job_id

        candidates = await db.candidates.find(query, {"_id": 0, "id": 1, "name": 1}).to_list(length=1000)
        if not candidates:
            return {"total": 0, "created": 0, "already_active": 0, "failed": 0,
                    "message": "No candidates at the 'interested' stage for this selection.", "results": []}

        sem = asyncio.Semaphore(4)   # cap concurrent LLM + email work
        results: List[Dict[str, Any]] = []

        async def _one(cand: dict) -> None:
            async with sem:
                name = cand.get("name") or "Candidate"
                try:
                    r = await InterviewService.create_interview(
                        org_id=org_id, recruiter_id=recruiter_id, candidate_id=cand["id"],
                        job_id=job_id, question_count=question_count, send_invite=True,
                    )
                    if not r.get("created"):
                        results.append({"candidate_id": cand["id"], "name": name, "status": "already_active"})
                    else:
                        sent = bool((r.get("invite") or {}).get("sent"))
                        results.append({
                            "candidate_id": cand["id"], "name": name,
                            "status": "created", "email_sent": sent,
                            "email_reason": (r.get("invite") or {}).get("reason"),
                        })
                except HTTPException as e:
                    results.append({"candidate_id": cand["id"], "name": name, "status": "failed", "error": str(e.detail)})
                except Exception as e:
                    logger.error(f"bulk_invite failed for {cand['id']}: {e}")
                    results.append({"candidate_id": cand["id"], "name": name, "status": "failed", "error": str(e)})

        await asyncio.gather(*[_one(c) for c in candidates])

        created = sum(1 for r in results if r["status"] == "created")
        already = sum(1 for r in results if r["status"] == "already_active")
        failed = sum(1 for r in results if r["status"] == "failed")
        emailed = sum(1 for r in results if r.get("email_sent"))

        await AuditService.record(
            organization_id=org_id, event_type="interview_bulk_invited", actor_type="recruiter",
            actor_id=recruiter_id, job_id=job_id,
            payload={"total": len(candidates), "created": created, "already_active": already, "failed": failed},
        )
        return {
            "total": len(candidates),
            "created": created,
            "already_active": already,
            "failed": failed,
            "emails_sent": emailed,
            "message": (
                f"Processed {len(candidates)} interested candidate(s): {created} invited"
                f"{f' ({emailed} email(s) sent)' if created else ''}, "
                f"{already} already had an active interview, {failed} failed."
            ),
            "results": results,
        }

    # ------------------------------------------------------------------
    # Recruiter: read
    # ------------------------------------------------------------------
    @staticmethod
    async def list_interviews(*, org_id: str, job_id=None, status=None, recommendation=None, interview_type=None) -> List[dict]:
        db = get_db()
        query: Dict[str, Any] = {"organization_id": org_id}
        if job_id:
            query["job_id"] = job_id
        if status:
            query["status"] = status
        if recommendation:
            query["recommendation"] = recommendation
        if interview_type:
            query["interview_type"] = interview_type

        projection = {
            "_id": 0, "token_hash": 0, "transcript": 0, "answers": 0,
            "question_plan": 0, "snapshot": 0, "progress": 0, "ai_report": 0,
            "session_meta": 0, "integrity": 0,
        }
        rows = await db.interviews.find(query, projection).sort("created_at", -1).to_list(length=500)

        cand_ids = list({r["candidate_id"] for r in rows if r.get("candidate_id")})
        job_ids = list({r["job_id"] for r in rows if r.get("job_id")})
        cand_map = {
            c["id"]: c async for c in db.candidates.find(
                {"id": {"$in": cand_ids}, "organization_id": org_id}, {"_id": 0, "id": 1, "name": 1, "role": 1}
            )
        } if cand_ids else {}
        job_map = {
            j["id"]: j.get("title") async for j in db.jobs_board.find(
                {"id": {"$in": job_ids}, "organization_id": org_id}, {"_id": 0, "id": 1, "title": 1}
            )
        } if job_ids else {}

        out = []
        for r in rows:
            s = _serialize(r)
            cand = cand_map.get(r.get("candidate_id"), {})
            s["candidate_name"] = cand.get("name") or "Unknown"
            s["position"] = job_map.get(r.get("job_id")) or cand.get("role") or "Unassigned"
            s["overall_score"] = (r.get("scores") or {}).get("overall")
            out.append(s)
        return out

    @staticmethod
    async def get_interview(*, org_id: str, interview_id: str) -> dict:
        db = get_db()
        interview = await db.interviews.find_one({"id": interview_id, "organization_id": org_id})
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        s = _serialize(interview)
        s.pop("progress", None)
        candidate = await db.candidates.find_one(
            {"id": interview["candidate_id"], "organization_id": org_id}, {"_id": 0, "name": 1, "email": 1, "role": 1}
        )
        s["candidate_name"] = (candidate or {}).get("name") or "Unknown"
        s["candidate_email"] = (candidate or {}).get("email")
        if interview.get("job_id"):
            job = await db.jobs_board.find_one(
                {"id": interview["job_id"], "organization_id": org_id}, {"_id": 0, "title": 1}
            )
            s["position"] = (job or {}).get("title") or (candidate or {}).get("role") or "Unassigned"
        else:
            s["position"] = (candidate or {}).get("role") or "Unassigned"
        return s

    @staticmethod
    async def get_report(*, org_id: str, interview_id: str, allow_retry: bool = True) -> dict:
        db = get_db()
        interview = await db.interviews.find_one({"id": interview_id, "organization_id": org_id})
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")

        # Lazily (re)run evaluation if the interview finished but evaluation never succeeded.
        if allow_retry and interview.get("status") == "completed" and interview.get("evaluation_status") == "pending":
            await InterviewService.evaluate(interview_id)
            interview = await db.interviews.find_one({"id": interview_id, "organization_id": org_id})

        candidate = await db.candidates.find_one(
            {"id": interview["candidate_id"], "organization_id": org_id}, {"_id": 0, "name": 1, "role": 1}
        )
        position = (candidate or {}).get("role") or "Unassigned"
        if interview.get("job_id"):
            job = await db.jobs_board.find_one({"id": interview["job_id"], "organization_id": org_id}, {"_id": 0, "title": 1})
            if job and job.get("title"):
                position = job["title"]

        plan = interview.get("question_plan") or []
        return {
            "interview_id": interview["id"],
            "candidate_id": interview["candidate_id"],
            "job_id": interview.get("job_id"),
            "candidate_name": (candidate or {}).get("name") or "Unknown",
            "position": position,
            "status": interview.get("status"),
            "evaluation_status": interview.get("evaluation_status"),
            "scores": interview.get("scores") or {},
            "recommendation": interview.get("recommendation"),
            "ai_report": interview.get("ai_report") or {},
            "integrity": interview.get("integrity") or {},
            "recruiter_decision": interview.get("recruiter_decision"),
            "recruiter_feedback": interview.get("recruiter_feedback"),
            # Total = everything actually asked (planned questions + any follow-ups).
            "questions_total": len(plan),
            "questions_planned": _base_question_count(plan),
            "questions_answered": _answered_count(interview),
            "duration_seconds": interview.get("duration_seconds"),
            "duration_minutes": round((interview["duration_seconds"] or 0) / 60) if interview.get("duration_seconds") else None,
            "started_at": _iso(interview.get("started_at")),
            "completed_at": _iso(interview.get("completed_at")),
        }

    @staticmethod
    async def get_transcript(*, org_id: str, interview_id: str) -> dict:
        db = get_db()
        interview = await db.interviews.find_one(
            {"id": interview_id, "organization_id": org_id},
            {"_id": 0, "transcript": 1, "candidate_id": 1, "job_id": 1, "answers": 1, "question_plan": 1},
        )
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        transcript = interview.get("transcript") or []
        for t in transcript:
            if isinstance(t, dict) and "ts" in t:
                t["ts"] = _iso(t["ts"])
        return {"interview_id": interview_id, "transcript": transcript}

    # ------------------------------------------------------------------
    # Recruiter: mutate
    # ------------------------------------------------------------------
    @staticmethod
    async def cancel_interview(*, org_id: str, recruiter_id: Optional[str], interview_id: str) -> dict:
        db = get_db()
        interview = await db.interviews.find_one({"id": interview_id, "organization_id": org_id})
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        if interview.get("status") in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail=f"Interview is already {interview['status']}.")

        await db.interviews.update_one(
            {"id": interview_id, "organization_id": org_id},
            {"$set": {"status": "cancelled", "updated_at": datetime.utcnow()}},
        )
        await AuditService.record(
            organization_id=org_id, event_type="interview_cancelled", actor_type="recruiter",
            actor_id=recruiter_id, candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
            interview_id=interview_id,
        )
        return {"status": "cancelled"}

    @staticmethod
    async def recruiter_decision(
        *, org_id: str, recruiter_id: Optional[str], interview_id: str, decision: str, feedback: Optional[str] = None
    ) -> dict:
        if decision not in RECRUITER_DECISIONS:
            raise HTTPException(status_code=400, detail=f"decision must be one of {RECRUITER_DECISIONS}")

        db = get_db()
        interview = await db.interviews.find_one({"id": interview_id, "organization_id": org_id})
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")

        now = datetime.utcnow()
        await db.interviews.update_one(
            {"id": interview_id, "organization_id": org_id},
            {"$set": {
                "recruiter_decision": decision,        # SEPARATE from the AI recommendation
                "recruiter_feedback": feedback,
                "recruiter_id": recruiter_id,
                "decided_at": now,
                "updated_at": now,
            }},
        )

        candidate = await db.candidates.find_one({"id": interview["candidate_id"], "organization_id": org_id})
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1, "contact_email": 1, "reply_to": 1})
        company_name = (org or {}).get("name") or settings.APP_NAME
        recruiter = await db.users.find_one({"id": recruiter_id}, {"_id": 0, "name": 1}) if recruiter_id else None
        sender_name = (recruiter or {}).get("name")
        email_result = None

        if decision == "select":
            await db.candidates.update_one(
                {"id": interview["candidate_id"], "organization_id": org_id},
                {"$set": {"status": "selected", "recruiter_verdict": feedback or "Selected by recruiter",
                          "last_interaction": now}},
            )
            # ONLY an explicit recruiter Select triggers the existing selection email.
            cand_for_email = dict(candidate or {})
            if interview.get("job_id"):
                job = await db.jobs_board.find_one({"id": interview["job_id"]}, {"_id": 0, "title": 1, "skills": 1})
                if job and job.get("title"):
                    cand_for_email["job_title_for_email"] = job["title"]
                if job and job.get("skills"):
                    cand_for_email["job_skills_for_email"] = job["skills"]
            email_result = await run_in_threadpool(
                EmailService.send_selection_email, cand_for_email, company_name, org, sender_name
            )
            await AuditService.record(
                organization_id=org_id, event_type="recruiter_selected", actor_type="recruiter",
                actor_id=recruiter_id, candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
                interview_id=interview_id, payload={"feedback": feedback, "selection_email": email_result},
            )
        elif decision == "reject":
            await db.candidates.update_one(
                {"id": interview["candidate_id"], "organization_id": org_id},
                {"$set": {"status": "rejected", "recruiter_verdict": feedback or "Rejected by recruiter",
                          "last_interaction": now}},
            )
            # An explicit recruiter Reject sends the post-interview regret email.
            cand_for_email = dict(candidate or {})
            if interview.get("job_id"):
                job = await db.jobs_board.find_one({"id": interview["job_id"]}, {"_id": 0, "title": 1})
                if job and job.get("title"):
                    cand_for_email["job_title_for_email"] = job["title"]
            email_result = await run_in_threadpool(
                EmailService.send_rejection_email, cand_for_email, company_name, org, sender_name
            )
            await AuditService.record(
                organization_id=org_id, event_type="recruiter_rejected", actor_type="recruiter",
                actor_id=recruiter_id, candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
                interview_id=interview_id, payload={"feedback": feedback, "rejection_email": email_result},
            )
        else:  # needs_review — no candidate status change
            await AuditService.record(
                organization_id=org_id, event_type="recruiter_needs_review", actor_type="recruiter",
                actor_id=recruiter_id, candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
                interview_id=interview_id, payload={"feedback": feedback},
            )

        # `decision_email` is the canonical key; `selection_email` kept for older clients.
        return {
            "status": "success",
            "decision": decision,
            "decision_email": email_result,
            "selection_email": email_result if decision == "select" else None,
        }

    # ------------------------------------------------------------------
    # Candidate session
    # ------------------------------------------------------------------
    @staticmethod
    async def session_info(token: str) -> dict:
        interview = await resolve_interview_by_token(token)
        db = get_db()
        candidate = await db.candidates.find_one({"id": interview["candidate_id"]}, {"_id": 0, "name": 1, "email": 1})
        first_name = ((candidate or {}).get("name") or "there").split(" ")[0]
        job_title = (interview.get("snapshot") or {}).get("job_title") or "the role"
        plan = interview.get("question_plan") or []
        answered = _answered_count(interview)
        needs_verify = InterviewService._needs_email_verify(interview, candidate)
        return {
            "candidate_first_name": first_name,
            "job_title": job_title,
            "status": interview.get("status"),
            "mode": "video",
            "total_questions": _base_question_count(plan),
            "answered_questions": answered,
            "in_progress": interview.get("status") == "in_progress",
            "already_completed": interview.get("status") == "completed",
            "requires_email_verification": needs_verify,
            "email_verified": bool(interview.get("email_verified")),
            "assesses": ["Technical knowledge", "Problem solving", "Role-specific skills", "Communication"],
        }

    @staticmethod
    def _needs_email_verify(interview: dict, candidate: Optional[dict]) -> bool:
        """Verification applies only when enabled, the interview hasn't started yet,
        and we actually have an email on file to check against."""
        if not settings.INTERVIEW_REQUIRE_EMAIL_VERIFY:
            return False
        if interview.get("email_verified"):
            return False
        if interview.get("status") == "in_progress" or interview.get("started_at"):
            return False
        return bool((candidate or {}).get("email"))

    @staticmethod
    async def verify_email(token: str, email: str, *, client_ip: Optional[str] = None) -> dict:
        """Candidate confirms the email address they were shortlisted with, before the
        interview can start. Token still does the real auth — this is a light identity
        check that also makes a shared link a little less useful."""
        interview = await resolve_interview_by_token(token)
        if interview.get("status") in ("completed", "cancelled", "expired", "failed"):
            raise HTTPException(status_code=410, detail=f"This interview is {interview['status']}.")
        db = get_db()

        if interview.get("email_verified"):
            return {"verified": True, "attempts_left": None}

        candidate = await db.candidates.find_one({"id": interview["candidate_id"]}, {"_id": 0, "email": 1})
        on_file = (candidate or {}).get("email")
        if not on_file:
            # Nothing to check against — let them through.
            await db.interviews.update_one({"id": interview["id"]}, {"$set": {"email_verified": True}})
            return {"verified": True, "attempts_left": None}

        attempts = int(interview.get("verification_attempts") or 0)
        if attempts >= settings.INTERVIEW_MAX_VERIFY_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many incorrect attempts. Contact the recruiter who sent your link.")

        supplied = (email or "").strip().lower()
        if supplied and supplied == str(on_file).strip().lower():
            await db.interviews.update_one(
                {"id": interview["id"]},
                {"$set": {"email_verified": True, "updated_at": datetime.utcnow()}},
            )
            await AuditService.record(
                organization_id=interview["organization_id"], event_type="interview_email_verified",
                actor_type="candidate", candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
                interview_id=interview["id"], payload={"ip": client_ip},
            )
            return {"verified": True, "attempts_left": None}

        attempts += 1
        await db.interviews.update_one(
            {"id": interview["id"]},
            {"$set": {"verification_attempts": attempts, "updated_at": datetime.utcnow()}},
        )
        await AuditService.record(
            organization_id=interview["organization_id"], event_type="interview_email_verify_failed",
            actor_type="candidate", candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
            interview_id=interview["id"], payload={"attempt": attempts, "ip": client_ip},
        )
        left = max(0, settings.INTERVIEW_MAX_VERIFY_ATTEMPTS - attempts)
        raise HTTPException(
            status_code=403,
            detail=f"That email doesn't match our records. {left} attempt(s) left." if left
            else "That email doesn't match our records. Contact the recruiter who sent your link.",
        )

    @staticmethod
    async def start_session(token: str, *, client_ip: Optional[str] = None, client_ua: Optional[str] = None) -> dict:
        interview = await resolve_interview_by_token(token, require_active=True)
        db = get_db()
        await _record_session_meta(db, interview["id"], client_ip, client_ua, "start")

        # Email confirmation gates only the FIRST start (see _needs_email_verify) —
        # a candidate already mid-interview is never stranded by it.
        if settings.INTERVIEW_REQUIRE_EMAIL_VERIFY and not interview.get("email_verified"):
            candidate = await db.candidates.find_one({"id": interview["candidate_id"]}, {"_id": 0, "email": 1})
            if InterviewService._needs_email_verify(interview, candidate):
                raise HTTPException(status_code=403, detail="Please confirm your email address before starting.")

        if interview.get("status") == "in_progress" and (interview.get("progress") or {}).get("pending_question"):
            # Idempotent resume: re-serve the current question.
            return await InterviewService._question_payload(interview, resume=True)

        plan = interview.get("question_plan") or []
        if not plan:
            raise HTTPException(status_code=500, detail="Interview has no question plan.")

        first_q = plan[0]
        now = datetime.utcnow()
        progress = {"plan_index": 1, "followups_used": 0, "pending_question": first_q}
        transcript_entry = {"role": "ai", "text": first_q["text"], "ts": now}

        await db.interviews.update_one(
            {"id": interview["id"], "status": {"$nin": TERMINAL_STATUSES}},
            {"$set": {"status": "in_progress", "started_at": now, "progress": progress, "updated_at": now},
             "$push": {"transcript": transcript_entry}},
        )
        await AuditService.record(
            organization_id=interview["organization_id"], event_type="interview_started",
            actor_type="candidate", candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
            interview_id=interview["id"],
        )
        interview = await db.interviews.find_one({"id": interview["id"]})
        return await InterviewService._question_payload(interview)

    @staticmethod
    async def process_turn(
        token: str,
        *,
        audio: Optional[UploadFile] = None,
        video: Optional[UploadFile] = None,
        answer_text: Optional[str] = None,
        turn_seq: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        client_ip: Optional[str] = None,
        client_ua: Optional[str] = None,
        client_signals: Optional[Dict[str, Any]] = None,
    ) -> dict:
        interview = await resolve_interview_by_token(token, require_active=True)
        db = get_db()
        await _record_session_meta(db, interview["id"], client_ip, client_ua, "turn")

        if interview.get("status") != "in_progress":
            raise HTTPException(status_code=409, detail="Interview is not in progress.")
        progress = interview.get("progress") or {}
        pending = progress.get("pending_question")
        if not pending:
            raise HTTPException(status_code=409, detail="No question is awaiting an answer. Call /start first.")

        plan = interview.get("question_plan") or []
        # Navigation walks ONLY the fixed base plan; follow-ups are appended to
        # `question_plan` for the record but are never selected by `plan_index`.
        base_questions = [q for q in plan if not q.get("is_followup")]
        base_count = len(base_questions)
        plan_index = min(int(progress.get("plan_index", base_count)), base_count)
        followups_used = int(progress.get("followups_used", 0))
        now = datetime.utcnow()

        # Has the current pending question already been answered? This is either a
        # duplicate submission (network retry) or a recovered stuck state — in both
        # cases do NOT re-record; just advance to the next base question.
        already_answered = any(
            a.get("question_id") == pending["id"] and a.get("answer_text")
            for a in (interview.get("answers") or [])
        )

        analysis = {"ask_followup": False, "followup_text": None}
        if not already_answered:
            # 1. Persist media (video for review, audio for STT), then transcribe.
            #    The full video is NEVER read into the DB or sent to the LLM.
            audio_ref = None
            video_ref = None
            transcript_text = ""
            transcribed = False

            if video is not None:
                video_ref = await InterviewStorage.save_upload(
                    interview_id=interview["id"], category="interview_video",
                    upload=video, question_id=pending["id"],
                )
            if audio is not None:
                audio_ref = await InterviewStorage.save_upload(
                    interview_id=interview["id"], category="interview_audio",
                    upload=audio, question_id=pending["id"],
                )

            # STT: prefer the small dedicated audio clip; else fall back to the
            # video file (OpenAI Whisper extracts audio from webm/mp4).
            stt_source = audio_ref or video_ref
            if stt_source:
                transcript_text = await InterviewService._transcribe(InterviewStorage.abs_path(stt_source))
                transcribed = bool(transcript_text)
            elif answer_text:
                transcript_text = answer_text.strip()
                transcribed = True
            if not transcript_text:
                transcript_text = "(no audible answer was captured)"

            sig = client_signals or {}
            answer_entry = {
                "question_id": pending["id"],
                "answer_text": transcript_text,
                "audio_ref": audio_ref,
                "video_ref": video_ref,
                "transcribed": transcribed,
                "score": None,
                "feedback": None,
                "duration_seconds": duration_seconds,
                "answered_at": now,
                # Integrity telemetry (best-effort, from the browser).
                "typed_only": bool(answer_text) and audio_ref is None and video_ref is None,
                "focus_lost_count": sig.get("focus_lost_count"),
                "focus_lost_ms": sig.get("focus_lost_ms"),
                "paste_count": sig.get("paste_count"),
                "fullscreen_exits": sig.get("fullscreen_exits"),
                "time_to_first_answer_ms": sig.get("time_to_first_answer_ms"),
            }
            await db.interviews.update_one(
                {"id": interview["id"]},
                {"$push": {"answers": answer_entry, "transcript": {"role": "candidate", "text": transcript_text, "ts": now}},
                 "$set": {"updated_at": now}},
            )
            if video_ref:
                await AuditService.record(
                    organization_id=interview["organization_id"], event_type="interview_video_uploaded",
                    actor_type="candidate", candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
                    interview_id=interview["id"], payload={"question_id": pending["id"]},
                )

            # 2. Analyse the answer + decide whether ONE follow-up would help.
            followups_remaining = max(0, settings.INTERVIEW_MAX_FOLLOWUPS - followups_used)
            job = None
            if interview.get("job_id"):
                job = await db.jobs_board.find_one({"id": interview["job_id"]})
            analysis = await ipe.analyze_answer(
                job=job,
                question_text=pending["text"],
                question_target_skills=pending.get("target_skills", []),
                answer_text=transcript_text,
                followups_remaining=followups_remaining,
            )
            await db.interviews.update_one(
                {"id": interview["id"], "answers.question_id": pending["id"]},
                {"$set": {"answers.$.score": analysis.get("score"), "answers.$.feedback": analysis.get("feedback")}},
            )
        else:
            logger.info(f"Interview {interview['id']}: pending q {pending['id']} already answered — advancing")

        # 3. Determine the next question.
        #    - At most ONE follow-up per base question (never a follow-up on a follow-up),
        #      and never more than INTERVIEW_MAX_FOLLOWUPS overall.
        can_followup = (
            not already_answered
            and not pending.get("is_followup")
            and followups_used < settings.INTERVIEW_MAX_FOLLOWUPS
            and analysis.get("ask_followup")
            and analysis.get("followup_text")
        )

        next_q = None
        if can_followup:
            next_q = InterviewQuestion(
                text=analysis["followup_text"],
                question_type="follow_up",
                sequence=pending.get("sequence", 0),
                target_skills=pending.get("target_skills", []),
                is_followup=True,
                parent_question_id=pending["id"],
            ).model_dump()
            followups_used += 1
            await db.interviews.update_one({"id": interview["id"]}, {"$push": {"question_plan": next_q}})
        elif plan_index < base_count:
            next_q = base_questions[plan_index]
            plan_index += 1

        if not next_q:
            # No more questions -> interview body is done (candidate then calls /complete).
            await db.interviews.update_one(
                {"id": interview["id"]},
                {"$set": {"progress.pending_question": None,
                          "progress.plan_index": plan_index,
                          "progress.followups_used": followups_used,
                          "updated_at": datetime.utcnow()}},
            )
            return {"done": True, "message": "That was the final question. Thank you."}

        await db.interviews.update_one(
            {"id": interview["id"]},
            {"$set": {"progress.pending_question": next_q,
                      "progress.plan_index": plan_index,
                      "progress.followups_used": followups_used,
                      "updated_at": datetime.utcnow()},
             "$push": {"transcript": {"role": "ai", "text": next_q["text"], "ts": datetime.utcnow()}}},
        )
        interview = await db.interviews.find_one({"id": interview["id"]})
        return await InterviewService._question_payload(interview)

    @staticmethod
    async def complete_session(token: str) -> dict:
        interview = await resolve_interview_by_token(token)
        db = get_db()

        if interview.get("status") == "completed":
            return {"status": "completed", "message": "Interview already completed."}
        if interview.get("status") in ("cancelled", "expired", "failed"):
            raise HTTPException(status_code=410, detail=f"Interview is {interview['status']}.")

        now = datetime.utcnow()
        started = interview.get("started_at")
        duration = int((now - started).total_seconds()) if isinstance(started, datetime) else None

        res = await db.interviews.update_one(
            {"id": interview["id"], "status": "in_progress"},
            {"$set": {"status": "completed", "completed_at": now, "duration_seconds": duration,
                      "progress.pending_question": None, "updated_at": now}},
        )
        if res.matched_count == 0:
            # Not in progress (e.g. never started) — mark completed anyway so it's terminal.
            await db.interviews.update_one(
                {"id": interview["id"], "status": {"$nin": TERMINAL_STATUSES}},
                {"$set": {"status": "completed", "completed_at": now, "duration_seconds": duration, "updated_at": now}},
            )

        await AuditService.record(
            organization_id=interview["organization_id"], event_type="interview_completed",
            actor_type="candidate", candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
            interview_id=interview["id"], payload={"duration_seconds": duration},
        )
        if interview.get("interview_type") == "ai_l2_technical":
            await db.candidates.update_one(
                {"id": interview["candidate_id"], "organization_id": interview["organization_id"]},
                {"$set": {"l2_status": "interview_completed", "last_interaction": now}},
            )
        else:
            await db.candidates.update_one(
                {"id": interview["candidate_id"], "organization_id": interview["organization_id"], "status": "interview"},
                {"$set": {"status": "interview_completed", "last_interaction": now}},
            )

        # Evaluate in the background — never block the candidate's completion response.
        asyncio.create_task(InterviewService.evaluate(interview["id"]))

        return {"status": "completed", "message": "Your interview is complete. Thank you for your time."}

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    @staticmethod
    async def evaluate(interview_id: str) -> dict:
        db = get_db()
        interview = await db.interviews.find_one({"id": interview_id})
        if not interview:
            return {"status": "error", "reason": "not found"}
        if interview.get("status") != "completed":
            return {"status": "skipped", "reason": f"status is {interview.get('status')}"}
        if interview.get("evaluation_status") == "evaluated":
            return {"status": "already_evaluated"}

        # Nothing to evaluate: the candidate answered nothing (or only inaudible
        # blanks). Do NOT run the LLM — it would score the résumé and invent a
        # match. Store an honest empty result and flag for human review.
        if _answered_count(interview) == 0 or _substantive_answer_chars(interview) < 25:
            now = datetime.utcnow()
            await db.interviews.update_one(
                {"id": interview_id},
                {"$set": {
                    "scores": {k: None for k in
                               ("overall", "technical_knowledge", "problem_solving", "communication",
                                "role_specific", "experience", "answer_relevance")},
                    "recommendation": None,
                    "ai_report": {
                        "strengths": [], "areas_to_improve": [],
                        "summary": ("The candidate ended the interview without giving any answers, "
                                    "so there is nothing to evaluate. The interview was likely abandoned."),
                        "llm_recommendation": None,
                        "not_evaluable": True,
                    },
                    "evaluation_status": "needs_review",
                    "updated_at": now,
                }},
            )
            await AuditService.record(
                organization_id=interview["organization_id"], event_type="interview_not_evaluable",
                actor_type="ai", candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
                interview_id=interview_id, payload={"reason": "no_answers"},
            )
            await InterviewService._run_integrity(interview_id)
            return {"status": "needs_review", "reason": "no_answers"}

        try:
            result = await ipe.evaluate_interview(
                interview.get("snapshot") or {},
                interview.get("transcript") or [],
                interview.get("answers") or [],
            )
        except Exception as exc:
            logger.error(f"Interview evaluation failed for {interview_id}: {exc}")
            # Keep the interview completed; leave evaluation retryable.
            await db.interviews.update_one(
                {"id": interview_id},
                {"$set": {"evaluation_status": "pending", "updated_at": datetime.utcnow(),
                          "ai_report.error": str(exc)}},
            )
            return {"status": "failed", "reason": str(exc)}

        plan = interview.get("question_plan") or []
        answered = _answered_count(interview)
        base_q = _base_question_count(plan)
        overall = (result.get("scores") or {}).get("overall")

        needs_review = (
            overall is None
            or (base_q and answered < max(1, base_q // 2))
            or len(interview.get("transcript") or []) < 4
        )
        eval_status = "needs_review" if needs_review else "evaluated"

        now = datetime.utcnow()
        await db.interviews.update_one(
            {"id": interview_id},
            {"$set": {
                "scores": result["scores"],
                "recommendation": result["recommendation"],
                "ai_report": result["ai_report"],
                "evaluation_status": eval_status,
                "updated_at": now,
            }},
        )
        await AuditService.record(
            organization_id=interview["organization_id"], event_type="interview_evaluated",
            actor_type="ai", candidate_id=interview["candidate_id"], job_id=interview.get("job_id"),
            interview_id=interview_id,
            payload={"overall": overall, "recommendation": result["recommendation"], "evaluation_status": eval_status},
        )

        # Integrity analysis runs alongside evaluation — advisory flags only, never
        # blocks the report and never changes the score. Best-effort.
        await InterviewService._run_integrity(interview_id)

        return {"status": eval_status, "scores": result["scores"], "recommendation": result["recommendation"]}

    @staticmethod
    async def _run_integrity(interview_id: str) -> Optional[dict]:
        if not settings.INTERVIEW_INTEGRITY_ENABLED:
            return None
        db = get_db()
        try:
            interview = await db.interviews.find_one(
                {"id": interview_id},
                {"_id": 0, "id": 1, "answers": 1, "transcript": 1, "session_meta": 1,
                 "verification_attempts": 1, "organization_id": 1, "candidate_id": 1, "job_id": 1},
            )
            if not interview:
                return None
            result = await integrity_engine.analyze(interview)
            await db.interviews.update_one(
                {"id": interview_id}, {"$set": {"integrity": result, "updated_at": datetime.utcnow()}}
            )
            await AuditService.record(
                organization_id=interview.get("organization_id"), event_type="interview_integrity_analyzed",
                actor_type="ai", candidate_id=interview.get("candidate_id"), job_id=interview.get("job_id"),
                interview_id=interview_id,
                payload={"level": result.get("level"), "score": result.get("score"),
                         "flags": [f.get("code") for f in result.get("flags", [])]},
            )
            return result
        except Exception as exc:
            logger.warning(f"integrity analysis failed for {interview_id}: {exc}")
            return None

    @staticmethod
    async def retry_integrity(*, org_id: str, interview_id: str) -> dict:
        db = get_db()
        interview = await db.interviews.find_one(
            {"id": interview_id, "organization_id": org_id}, {"_id": 0, "status": 1}
        )
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        result = await InterviewService._run_integrity(interview_id)
        if result is None:
            raise HTTPException(status_code=503, detail="Integrity analysis is unavailable or disabled.")
        return result

    @staticmethod
    async def retry_evaluation(*, org_id: str, interview_id: str) -> dict:
        db = get_db()
        interview = await db.interviews.find_one({"id": interview_id, "organization_id": org_id})
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        if interview.get("status") != "completed":
            raise HTTPException(status_code=409, detail="Interview is not completed.")
        await db.interviews.update_one({"id": interview_id}, {"$set": {"evaluation_status": "pending"}})
        return await InterviewService.evaluate(interview_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _question_payload(interview: dict, resume: bool = False) -> dict:
        progress = interview.get("progress") or {}
        pending = progress.get("pending_question")
        if not pending:
            return {"done": True, "message": "No further questions."}
        plan = interview.get("question_plan") or []
        base_total = _base_question_count(plan)
        # `plan_index` points at the NEXT base question; the current base question is
        # therefore `plan_index` (1-based). Follow-ups keep the same number.
        current_number = min(base_total, max(1, int(progress.get("plan_index", 1))))

        audio_url = None
        try:
            path = await TTSService.generate_speech(pending["text"], voice=settings.INTERVIEW_TTS_VOICE)
            audio_url = os.path.basename(path)
        except Exception as exc:
            logger.warning(f"TTS failed for interview {interview['id']}: {exc}")  # text-only fallback

        return {
            "done": False,
            "resumed": resume,
            "question_text": pending["text"],
            "question_type": pending.get("question_type"),
            "is_followup": pending.get("is_followup", False),
            "question_number": current_number,
            "total_questions": base_total,
            "audio_file": audio_url,   # served via /interview-session/{token}/audio/{audio_file}
        }

    @staticmethod
    async def get_recording(*, org_id: str, interview_id: str, answer_index: int) -> Dict[str, Any]:
        """Recruiter-only: resolve the stored video (or audio) recording for one
        answer. Returns {path, media_type, filename}. Org-scoped."""
        db = get_db()
        interview = await db.interviews.find_one(
            {"id": interview_id, "organization_id": org_id}, {"_id": 0, "answers": 1}
        )
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        answers = interview.get("answers") or []
        if answer_index < 0 or answer_index >= len(answers):
            raise HTTPException(status_code=404, detail="Answer not found")
        ans = answers[answer_index]
        ref = ans.get("video_ref") or ans.get("audio_ref")
        if not ref or not InterviewStorage.exists(ref):
            raise HTTPException(status_code=404, detail="No recording available for this answer")
        path = InterviewStorage.abs_path(ref)
        ext = os.path.splitext(path)[1].lower()
        media_type = {
            ".webm": "video/webm", ".mp4": "video/mp4",
            ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".wav": "audio/wav", ".mp3": "audio/mpeg",
        }.get(ext, "application/octet-stream")
        return {"path": path, "media_type": media_type, "filename": os.path.basename(path)}

    @staticmethod
    async def _transcribe(audio_path: str) -> str:
        """Reuse the existing OpenAI STT. Retry once on failure; never raise
        (a failed transcription must not lose the interview)."""
        for attempt in (1, 2):
            try:
                text = await VoiceService.transcribe_with_openai(audio_path)
                if text:
                    return text.strip()
            except Exception as exc:
                logger.warning(f"STT attempt {attempt} failed for {audio_path}: {exc}")
        return ""


# ======================================================================
# Index bootstrap (called from app startup)
# ======================================================================

async def ensure_interview_indexes():
    try:
        db = get_db()
        await db.interviews.create_index([("organization_id", 1), ("status", 1)])
        await db.interviews.create_index([("candidate_id", 1)])
        await db.interviews.create_index([("job_id", 1)])
        await db.interviews.create_index([("token_hash", 1)], unique=True, sparse=True)
        await db.interviews.create_index([("id", 1)], unique=True)
        await db.hiring_events.create_index([("organization_id", 1), ("created_at", -1)])
        await db.hiring_events.create_index([("interview_id", 1)])
        logger.info("Interview indexes ensured.")
    except Exception as exc:
        logger.error(f"ensure_interview_indexes failed: {exc}")
