"""AI Interview API.

Two clearly separated authentication boundaries:
  * /interviews/*          -> recruiter, existing JWT + organization scoping
  * /interview-session/*    -> candidate, opaque interview token only (no recruiter JWT)
"""
import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Path
from fastapi.responses import FileResponse

from app.api.deps import get_context_organization_id, get_current_active_user
from app.core.interview_auth import resolve_interview_by_token
from app.models.interview import CreateInterviewRequest, RecruiterDecisionRequest, BulkInviteRequest
from app.models.user import UserInDB
from app.services.interview_service import InterviewService

logger = logging.getLogger(__name__)

# ======================================================================
# Recruiter API
# ======================================================================
recruiter_router = APIRouter(prefix="/interviews", tags=["AI Interview"])


@recruiter_router.post("")
async def create_interview(
    payload: CreateInterviewRequest,
    org_id: str = Depends(get_context_organization_id),
    user: UserInDB = Depends(get_current_active_user),
):
    return await InterviewService.create_interview(
        org_id=org_id,
        recruiter_id=user.id,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        interview_type=payload.interview_type,
        question_count=payload.question_count,
        send_invite=payload.send_invite,
    )


@recruiter_router.post("/bulk-invite")
async def bulk_invite(
    payload: BulkInviteRequest,
    org_id: str = Depends(get_context_organization_id),
    user: UserInDB = Depends(get_current_active_user),
):
    return await InterviewService.bulk_invite(
        org_id=org_id, recruiter_id=user.id,
        job_id=payload.job_id, question_count=payload.question_count,
    )


@recruiter_router.get("")
async def list_interviews(
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    recommendation: Optional[str] = None,
    org_id: str = Depends(get_context_organization_id),
):
    return await InterviewService.list_interviews(
        org_id=org_id, job_id=job_id, status=status, recommendation=recommendation
    )


@recruiter_router.get("/{interview_id}")
async def get_interview(interview_id: str, org_id: str = Depends(get_context_organization_id)):
    return await InterviewService.get_interview(org_id=org_id, interview_id=interview_id)


@recruiter_router.post("/{interview_id}/send-invite")
async def send_invite(
    interview_id: str,
    org_id: str = Depends(get_context_organization_id),
    user: UserInDB = Depends(get_current_active_user),
):
    return await InterviewService.resend_invite(org_id=org_id, recruiter_id=user.id, interview_id=interview_id)


@recruiter_router.post("/{interview_id}/cancel")
async def cancel_interview(
    interview_id: str,
    org_id: str = Depends(get_context_organization_id),
    user: UserInDB = Depends(get_current_active_user),
):
    return await InterviewService.cancel_interview(org_id=org_id, recruiter_id=user.id, interview_id=interview_id)


@recruiter_router.get("/{interview_id}/report")
async def get_report(interview_id: str, org_id: str = Depends(get_context_organization_id)):
    return await InterviewService.get_report(org_id=org_id, interview_id=interview_id)


@recruiter_router.post("/{interview_id}/reevaluate")
async def reevaluate(interview_id: str, org_id: str = Depends(get_context_organization_id)):
    return await InterviewService.retry_evaluation(org_id=org_id, interview_id=interview_id)


@recruiter_router.get("/{interview_id}/transcript")
async def get_transcript(interview_id: str, org_id: str = Depends(get_context_organization_id)):
    return await InterviewService.get_transcript(org_id=org_id, interview_id=interview_id)


@recruiter_router.get("/{interview_id}/recording/{answer_index}")
async def get_recording(
    interview_id: str,
    answer_index: int,
    org_id: str = Depends(get_context_organization_id),
    user: UserInDB = Depends(get_current_active_user),
):
    """Stream one answer's recording. Recruiter JWT + org-scoped; never exposed
    through the candidate token endpoints. Supports HTTP Range for seeking."""
    rec = await InterviewService.get_recording(
        org_id=org_id, interview_id=interview_id, answer_index=answer_index
    )
    return FileResponse(rec["path"], media_type=rec["media_type"], filename=rec["filename"])


@recruiter_router.post("/{interview_id}/decision")
async def recruiter_decision(
    interview_id: str,
    payload: RecruiterDecisionRequest,
    org_id: str = Depends(get_context_organization_id),
    user: UserInDB = Depends(get_current_active_user),
):
    return await InterviewService.recruiter_decision(
        org_id=org_id, recruiter_id=user.id, interview_id=interview_id,
        decision=payload.decision, feedback=payload.feedback,
    )


# ======================================================================
# Candidate session API  (token auth only — no recruiter JWT)
# ======================================================================
candidate_router = APIRouter(prefix="/interview-session", tags=["AI Interview (Candidate)"])


@candidate_router.get("/{token}")
async def session_info(token: str = Path(..., min_length=20)):
    return await InterviewService.session_info(token)


@candidate_router.post("/{token}/start")
async def start_session(token: str = Path(..., min_length=20)):
    return await InterviewService.start_session(token)


@candidate_router.post("/{token}/turn")
async def process_turn(
    token: str = Path(..., min_length=20),
    video: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    answer_text: Optional[str] = Form(None),
    turn_seq: Optional[int] = Form(None),
    duration_seconds: Optional[int] = Form(None),
):
    if video is None and audio is None and not answer_text:
        raise HTTPException(status_code=400, detail="Provide a video/audio recording or answer_text.")
    return await InterviewService.process_turn(
        token, video=video, audio=audio, answer_text=answer_text,
        turn_seq=turn_seq, duration_seconds=duration_seconds,
    )


@candidate_router.post("/{token}/complete")
async def complete_session(token: str = Path(..., min_length=20)):
    return await InterviewService.complete_session(token)


@candidate_router.get("/{token}/audio/{filename}")
async def get_session_audio(token: str = Path(..., min_length=20), filename: str = Path(...)):
    # Validate the token first so audio is not world-readable.
    await resolve_interview_by_token(token)
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Invalid audio reference")
    path = os.path.join("temp_audio", safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg")
