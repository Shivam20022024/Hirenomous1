"""Pydantic models for the AI Interview feature.

An interview is stored as a single document in the `interviews` collection with
questions, answers and the ordered transcript embedded (matching the codebase's
schemaless / single-document conventions used for `candidates` and
`job_ai_config`). Audio blobs are never embedded — only a reference path.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


# --- Enummerable string values (kept as plain strings to match the rest of the codebase) ---

INTERVIEW_STATUSES = ["invited", "scheduled", "in_progress", "completed", "cancelled", "expired", "failed"]
EVALUATION_STATUSES = ["pending", "evaluated", "needs_review"]
RECOMMENDATIONS = ["strong_match", "match", "weak_match", "no_match"]
RECRUITER_DECISIONS = ["select", "reject", "needs_review"]
QUESTION_TYPES = ["introduction", "technical", "resume_specific", "problem_solving", "scenario", "behavioral", "follow_up", "closing"]

# Terminal interview states — a candidate session cannot progress from these.
TERMINAL_STATUSES = ["completed", "cancelled", "expired", "failed"]


class InterviewQuestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    question_type: str = "technical"
    sequence: int = 0
    target_skills: List[str] = []
    is_followup: bool = False
    parent_question_id: Optional[str] = None


class InterviewAnswer(BaseModel):
    question_id: str
    answer_text: Optional[str] = None
    audio_ref: Optional[str] = None          # storage ref for the audio clip used for STT — never the blob
    video_ref: Optional[str] = None          # storage ref for the video recording (recruiter review only)
    transcribed: bool = False
    score: Optional[float] = None            # per-answer 0-100, advisory
    feedback: Optional[str] = None
    duration_seconds: Optional[int] = None
    answered_at: datetime = Field(default_factory=datetime.utcnow)


class InterviewScores(BaseModel):
    overall: Optional[float] = None
    technical_knowledge: Optional[float] = None
    problem_solving: Optional[float] = None
    communication: Optional[float] = None
    role_specific: Optional[float] = None
    experience: Optional[float] = None
    answer_relevance: Optional[float] = None


class Interview(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    candidate_id: str
    job_id: Optional[str] = None
    interview_type: str = "ai_technical"

    status: str = "invited"
    evaluation_status: str = "pending"

    # Security — the raw token is never stored, only its hash.
    token_hash: Optional[str] = None
    token_expires_at: Optional[datetime] = None

    invited_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    question_plan: List[InterviewQuestion] = []
    answers: List[InterviewAnswer] = []
    transcript: List[Dict[str, Any]] = []      # [{role: "ai"|"candidate", text, ts}]

    scores: InterviewScores = Field(default_factory=InterviewScores)
    recommendation: Optional[str] = None       # AI, advisory only
    ai_report: Dict[str, Any] = {}             # {strengths[], areas_to_improve[], summary, llm_recommendation}

    # Recruiter decision is a SEPARATE field from the AI recommendation.
    recruiter_decision: Optional[str] = None
    recruiter_feedback: Optional[str] = None
    recruiter_id: Optional[str] = None
    decided_at: Optional[datetime] = None

    # Immutable snapshot of everything the evaluation depended on.
    snapshot: Dict[str, Any] = {}

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# --- Request bodies (recruiter) ---

class CreateInterviewRequest(BaseModel):
    candidate_id: str
    job_id: Optional[str] = None
    interview_type: str = "ai_technical"
    question_count: Optional[int] = None
    send_invite: bool = True


class RecruiterDecisionRequest(BaseModel):
    decision: str                              # select | reject | needs_review
    feedback: Optional[str] = None


class BulkInviteRequest(BaseModel):
    job_id: Optional[str] = None               # scope to one job posting; None = all
    question_count: Optional[int] = None


# --- Request bodies (candidate session) ---

class InterviewTurnRequest(BaseModel):
    """Used when the candidate submits a typed answer (audio uses multipart form)."""
    answer_text: str
    turn_seq: Optional[int] = None
