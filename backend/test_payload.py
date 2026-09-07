import asyncio
import os
import sys

# Add the backend directory to sys.path so we can import app modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.services.prompt_engine import PromptEngine
from app.models.job_ai_config import JobAIConfig

def test_prompt_generation():
    print("Testing Job A: Java Developer")
    job_a = {
        "title": "Java Developer",
        "description": "Backend Java development",
        "skills": ["Java", "Spring Boot"],
        "experience": "3-5 years",
        "location": "Remote",
        "jobType": "Full-time"
    }
    config_a = {
        "language": "English",
        "tone": "Professional",
        "voice": "Default",
        "screening_questions": [
            {"question": "How many years of Java development experience do you have?", "category": "Experience", "required": True, "order": 1}
        ]
    }
    
    prompt_a = PromptEngine.generate_prompt(job_a, config_a, "Test Candidate", "Test Company")
    
    assert "Java Developer" in prompt_a, "Job A title missing"
    assert "How many years of Java development experience do you have?" in prompt_a, "Job A question missing"
    print("Job A tests passed!")
    
    print("\nTesting Job B: Python Developer")
    job_b = {
        "title": "Python Developer",
        "description": "Backend Python development",
        "skills": ["Python", "FastAPI"],
        "experience": "2-4 years",
        "location": "Remote",
        "jobType": "Full-time"
    }
    config_b = {
        "language": "English",
        "tone": "Professional",
        "voice": "Default",
        "screening_questions": [
            {"question": "How many years of Python development experience do you have?", "category": "Experience", "required": True, "order": 1}
        ]
    }
    
    prompt_b = PromptEngine.generate_prompt(job_b, config_b, "Test Candidate", "Test Company")
    
    assert "Python Developer" in prompt_b, "Job B title missing"
    assert "How many years of Python development experience do you have?" in prompt_b, "Job B question missing"
    print("Job B tests passed!")
    
    print("\nPayload structure preview (Job A):")
    payload = {
        "agent_id": "mock_agent_id",
        "recipient_phone_number": "+1234567890",
        "user_data": {
            "candidate_id": "cand_123",
            "application_id": "app_456",
            "job_id": "job_a_id",
            "candidate_name": "Test Candidate",
            "job_title": "Java Developer",
            "company_name": "Test Company",
            "dynamic_prompt": prompt_a
        }
    }
    print("user_data.dynamic_prompt length:", len(payload["user_data"]["dynamic_prompt"]))
    print("user_data.dynamic_prompt present:", bool(payload["user_data"]["dynamic_prompt"]))

if __name__ == "__main__":
    test_prompt_generation()
