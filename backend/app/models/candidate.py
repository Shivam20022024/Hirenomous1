from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import uuid

class CandidateBase(BaseModel):
    organization_id: Optional[str] = None
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = []
    resume_score: float = 0.0
    status: str = "uploaded"  # uploaded, shortlisted, calling, interested, not_interested, unclear
    shortlisted: bool = False
    email_sent: bool = False
    interest: Optional[str] = None # interested, not_interested, unclear
    
    # New AI Interaction Fields
    role: Optional[str] = None
    call_status: Optional[str] = None # Completed, No Response, Busy, Failed
    call_duration: Optional[str] = None
    call_start_time: Optional[datetime] = None
    call_end_time: Optional[datetime] = None
    transcript: Optional[str] = None
    candidate_responded: bool = False
    interest_status: Optional[str] = None # Interested, Not Interested, Follow-up Needed
    interview_status: Optional[str] = None
    interview_scheduled: bool = False
    interview_time: Optional[str] = None
    ai_summary: Optional[str] = None
    recruiter_verdict: Optional[str] = None
    conversation_summary: Optional[str] = None
    last_interaction: Optional[datetime] = None


    screening_interest: Optional[str] = None
    screening_skills: Optional[str] = None
    screening_availability: Optional[str] = None
    final_status: Optional[str] = None # qualified, rejected, review
    call_step: Optional[str] = "interest"
    transcription: Optional[str] = None
    summary: Optional[str] = None
    missing_skills: List[str] = []
    analysis_raw: Optional[str] = None
    call_timestamps: Dict[str, datetime] = {}
    
    # NEW FIELDS FOR REAL CALL DATA PIPELINE
    bolna_call_id: Optional[str] = None
    interview_date: Optional[str] = None
    communication_score: Optional[float] = None
    technical_score: Optional[float] = None
    confidence_score: Optional[float] = None
    final_recommendation: Optional[str] = None
    recording_url: Optional[str] = None
    job_role: Optional[str] = None




class CandidateCreate(CandidateBase):
    pass

class Candidate(CandidateBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

class ResumeAnalysisResponse(BaseModel):
    candidate_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    score: float
    skills: List[str]
    missing_skills: List[str] = []
    summary: Optional[str] = None
    status: str
