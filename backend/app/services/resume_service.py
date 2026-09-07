import httpx
import json
from app.core.config import settings
from app.models.candidate import Candidate
import uuid
import re
import logging
import traceback
from typing import List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
PHONE_REGEX = re.compile(r'(\+?\d[\d\-\s\(\)]{7,}\d)')

def _clean_candidate_name(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z\s]', ' ', value)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def _extract_skills_from_text(text: str) -> List[str]:
    known_skills = [
        "python", "java", "javascript", "typescript", "react", "node", "django",
        "flask", "fastapi", "sql", "mongodb", "ai", "machine learning", "aws",
        "docker", "kubernetes", "html", "css", "git"
    ]
    lowered = text.lower()
    found = []
    for skill in known_skills:
        if skill in lowered:
            found.append(skill.title())
    return found[:12]

def fallback_parse_resume_text(text: str) -> dict:
    """Best-effort local parsing when external AI parsing fails."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    email_match = EMAIL_REGEX.search(text)
    phone_match = PHONE_REGEX.search(text)

    candidate_name = "Candidate"
    for line in lines[:8]:
        cleaned = _clean_candidate_name(line)
        words = cleaned.split()
        if 2 <= len(words) <= 4 and all(word[:1].isalpha() for word in words):
            candidate_name = " ".join(word.capitalize() for word in words)
            break

    summary_lines = []
    for line in lines[1:6]:
        if len(line) > 30:
            summary_lines.append(line)
        if len(summary_lines) == 2:
            break

    return {
        "name": candidate_name,
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0).strip() if phone_match else None,
        "skills": _extract_skills_from_text(text),
        "experience_summary": " ".join(summary_lines)[:300] if summary_lines else "Resume parsed with local fallback.",
        "total_experience": "Not Assessed"
    }

def clean_json_response(text: str) -> dict:
    """
    Cleans the AI response to extract a valid JSON object.
    Supports markdown code blocks and stripping extra text.
    Modified for higher robustness.
    """
    if not text:
        raise ValueError("AI returned empty response")
        
    # Remove markdown code blocks if present (more robust regex)
    text = re.sub(r"```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", "", text)
    
    # Sometimes AI adds prefixes like "JSON:" or "Here is the result:"
    # Extract only the content between the first { and last }
    start = text.find('{')
    end = text.rfind('}')
    
    if start == -1 or end == -1:
        logger.error(f"Failed to find JSON boundaries in raw text. Raw snippet: {text[:500]}")
        raise ValueError("Could not find valid JSON object in AI response")
        
    json_str = text[start:end+1]
    
    # Remove single line comments that might be added by some models
    json_str = re.sub(r'//.*?\n', '\n', json_str)
    
    try:
        return json.loads(json_str.strip())
    except json.JSONDecodeError as e:
        logger.warning(f"Initial JSON Decode Error: {str(e)}. Attempting advanced cleanup...")
        try:
            # Basic attempt to fix minor issues like trailing commas
            # Remove trailing commas before closing braces/brackets
            fixed_str = re.sub(r',\s*([\]}])', r'\1', json_str)
            # Remove control characters that might break JSON
            fixed_str = re.sub(r'[\x00-\x1F\x7F]', '', fixed_str)
            return json.loads(fixed_str)
        except Exception as inner_e:
            logger.error(f"Advanced cleanup failed: {str(inner_e)}")
            logger.error(f"Problematic JSON string: {json_str[:500]}")
            raise ValueError(f"Failed to parse AI response as JSON: {str(e)}")

class ResumeService:
    _client = None

    @classmethod
    async def get_client(cls):
        """Returns a shared AsyncClient instance."""
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=15, max_connections=25)
            )
        return cls._client

    @classmethod
    async def close_client(cls):
        """Closes the shared AsyncClient instance."""
        if cls._client and not cls._client.is_closed:
            await cls._client.aclose()
            cls._client = None

    @classmethod
    async def parse_and_score_resume_with_gpt(cls, text: str, job_description: str):
        """Extracts candidate info AND scores it against the job description in a
        single OpenAI call. Combining what used to be two sequential round-trips
        (parse, then score) into one roughly halves per-resume latency and API cost."""
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        prompt = f"""
        You are an expert HR recruiter. Extract the candidate's information from the resume text below,
        AND compare it against the job description to score their fit.
        Return it strictly as a single JSON object with:
        {{
            "name": "Full Name",
            "email": "Email Address",
            "phone": "Phone Number",
            "skills": ["Skill 1", "Skill 2", ...],
            "experience_summary": "Short summary of experience",
            "total_experience": "X years",
            "score": 85,
            "missing_skills": ["Skill X", "Skill Y"],
            "reason": "Explain why this candidate is or isn't a good fit for the job description.",
            "role": "Short Job Title (e.g. AI Engineer Intern)"
        }}

        Job Description:
        {job_description}

        Resume text:
        {text[:4000]}
        """
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }

        client = await cls.get_client()
        try:
            logger.info("Calling OpenAI API for combined resume parsing + scoring...")
            response = await client.post(
                f"{settings.OPENAI_API_BASE}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except httpx.HTTPStatusError as e:
            error_data = e.response.text
            logger.error(f"OpenAI API status error ({e.response.status_code}): {error_data}")
            raise Exception(f"OpenAI API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"OpenAI API call failed: {str(e)}")
            raise Exception(f"Failed to communicate with OpenAI: {str(e)}")

    @classmethod
    async def process_resume(cls, text: str, job_description: str):
        request_id = str(uuid.uuid4())[:8]
        parsing_failed = False
        try:
            logger.info(f"[{request_id}] AI processing started (combined parse + score call)...")
            try:
                raw = await cls.parse_and_score_resume_with_gpt(text, job_description)
                combined_data = clean_json_response(raw)
            except Exception as e:
                logger.error(f"[{request_id}] Combined parse+score call failed: {str(e)}")
                parsing_failed = True
                combined_data = {
                    **fallback_parse_resume_text(text),
                    "score": 50.0,
                    "missing_skills": [],
                    "reason": "Candidate requires manual review (AI parsing/scoring could not be completed).",
                    "role": "AI Engineer Intern"
                }

            # Validation: Ensure basic fields exist
            if not combined_data.get("name") or combined_data.get("name") == "Unknown":
                combined_data["name"] = "Candidate"

            logger.info(f"[{request_id}] AI processing complete. Parsing Failed: {parsing_failed}")

            # Normalize Keys
            normalized_score = 50.0 # Default fallback
            for k, v in combined_data.items():
                if "score" in k.lower():
                    try:
                        # Handle strings like "85%"
                        raw_val = str(v).replace('%', '').strip()
                        normalized_score = float(raw_val)
                        break
                    except:
                        continue

            # Safety check: if normalization somehow resulted in 0 but it was a fallback situation
            if parsing_failed and normalized_score == 0:
                normalized_score = 50.0

            final_result = {
                **combined_data,
                "score": normalized_score,
                "missing_skills": combined_data.get("missing_skills", []),
                "reason": combined_data.get("reason", "No reason provided."),
                "role": combined_data.get("role", "AI Engineer Intern"),
                "summary": combined_data.get("experience_summary", "No summary available.")
            }

            return final_result

        except Exception as e:
            logger.error(f"[{request_id}] Critical error in process_resume: {str(e)}")
            logger.error(traceback.format_exc())
            # Return a minimal safe object to avoid UI crashes
            return {
                "name": "Candidate",
                "email": None,
                "phone": None,
                "skills": [],
                "missing_skills": [],
                "score": 50.0,
                "reason": "Internal system error during processing.",
                "summary": "N/A"
            }
