from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid

class ScreeningQuestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    category: str = "General"
    required: bool = True
    order: int = 0

class JobAIConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    organization_id: str
    language: str = "English"
    tone: str = "Professional & Conversational"
    voice: str = "Configured Voice"
    screening_mode: str = "Standard Screening"
    is_active: bool = False
    status: str = "Draft"
    screening_questions: List[ScreeningQuestion] = []
    prompt_template_version: str = "1.0"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
