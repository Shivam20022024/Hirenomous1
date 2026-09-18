"""LLM prompt logic for the AI Interview.

Reuses the existing AI infrastructure:
  - `ResumeService.get_client()`  -> shared pooled httpx.AsyncClient
  - `clean_json_response()`       -> tolerant JSON extraction / repair
  - OpenAI chat completions endpoint + settings (same as resume_service.py)

Three responsibilities:
  1. generate_question_plan  -> a structured, reproducible interview plan
  2. analyze_answer          -> score the last answer + decide the next question / follow-up
  3. evaluate_interview      -> final job-anchored rubric evaluation
"""
import json
import logging
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.services.resume_service import ResumeService, clean_json_response

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"

# Every interview opens with the same warm-up question, for every candidate.
# The resume/job-specific questions follow it.
INTRO_QUESTION = {
    "text": "To begin, tell me a bit about yourself — your background and the experience most relevant to this role.",
    "question_type": "introduction",
    "target_skills": [],
}

L2_INTRO_QUESTION = {
    "text": "Welcome back. In this second round, we will dive deeper into advanced technical topics and system design.",
    "question_type": "introduction",
    "target_skills": [],
}

# Applied to every interview / evaluation prompt.
FAIRNESS_RULES = (
    "Evaluate ONLY job-relevant professional competencies (technical knowledge, problem solving, "
    "role-specific skills, relevant experience, communication of ideas, answer relevance). "
    "NEVER consider or infer age, gender, race, ethnicity, nationality, religion, disability, "
    "marital or family status, accent, native language, name, photo, university prestige, or "
    "employment gaps as negatives. Judge the substance of answers, not fluency of English."
)

SCORE_DIMENSIONS = [
    "technical_knowledge",
    "problem_solving",
    "communication",
    "role_specific",
    "experience",
    "answer_relevance",
]

# Deterministic weights for the overall score (must sum to 1.0).
OVERALL_WEIGHTS = {
    "technical_knowledge": 0.28,
    "problem_solving": 0.22,
    "role_specific": 0.20,
    "experience": 0.12,
    "communication": 0.10,
    "answer_relevance": 0.08,
}


def safe_resume_context(candidate: dict) -> str:
    """Strip PII; keep only what is fair and relevant for interview questions/scoring."""
    skills = candidate.get("skills") or []
    parts = []
    if skills:
        parts.append("Skills: " + ", ".join(str(s) for s in skills[:25]))
    if candidate.get("total_experience"):
        parts.append(f"Total experience: {candidate.get('total_experience')}")
    if candidate.get("relevant_experience"):
        parts.append(f"Relevant experience: {candidate.get('relevant_experience')}")
    summary = candidate.get("summary") or candidate.get("experience_summary") or ""
    if summary:
        parts.append(f"Experience summary: {str(summary)[:1200]}")
    return "\n".join(parts) if parts else "No structured resume data available."


def job_context(job: Optional[dict], fallback_jd: str = "") -> str:
    if not job:
        return fallback_jd or "General software / technical role."
    parts = [f"Job title: {job.get('title', 'the role')}"]
    if job.get("description"):
        parts.append(f"Job description: {str(job.get('description'))[:2000]}")
    if job.get("skills"):
        parts.append("Required skills: " + ", ".join(str(s) for s in job.get("skills", [])))
    if job.get("experience"):
        parts.append(f"Experience expected: {job.get('experience')}")
    return "\n".join(parts)


async def _chat_json(system: str, user: str, *, temperature: float = 0.3, timeout: float = 60.0) -> dict:
    """One JSON chat-completion call using the shared client + tolerant parsing."""
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    client = await ResumeService.get_client()
    resp = await client.post(
        f"{settings.OPENAI_API_BASE}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return clean_json_response(content)


# --------------------------------------------------------------------------
# 1. Question plan
# --------------------------------------------------------------------------

def _fallback_question_plan(job: Optional[dict], count: int) -> List[Dict[str, Any]]:
    title = (job or {}).get("title") or "this role"
    skills = ((job or {}).get("skills") or [])[:4]
    base = [
        dict(INTRO_QUESTION),
        {"text": "Walk me through a recent project you are proud of and your specific contribution.",
         "question_type": "resume_specific", "target_skills": []},
        {"text": f"What are the key technical skills required for {title}, and how do you rate yourself on them?",
         "question_type": "technical", "target_skills": skills},
        {"text": "Describe a difficult technical problem you solved and how you approached it.",
         "question_type": "problem_solving", "target_skills": []},
        {"text": "How would you design a scalable, reliable service for a high-traffic workload?",
         "question_type": "scenario", "target_skills": skills},
        {"text": "Tell me about a time you disagreed with a teammate on a technical decision. How was it resolved?",
         "question_type": "behavioral", "target_skills": []},
        {"text": "What do you do to keep your skills current, and what are you learning right now?",
         "question_type": "behavioral", "target_skills": []},
        {"text": "Is there anything about your experience you would like to add that we have not covered?",
         "question_type": "closing", "target_skills": []},
    ]
    return base[:max(3, count)]


def _l2_fallback_question_plan(job: Optional[dict], count: int) -> List[Dict[str, Any]]:
    title = (job or {}).get("title") or "this role"
    skills = ((job or {}).get("skills") or [])[:4]
    base = [
        dict(L2_INTRO_QUESTION),
        {"text": "Walk me through the architecture of the most complex system you've designed or scaled.",
         "question_type": "scenario", "target_skills": []},
        {"text": f"How would you approach designing a fault-tolerant system using {', '.join(skills) if skills else 'standard patterns'}?",
         "question_type": "technical", "target_skills": skills},
        {"text": "Describe a scenario where you had to debug a critical production failure under pressure.",
         "question_type": "problem_solving", "target_skills": []},
        {"text": "What strategies do you use for optimizing performance in a high-traffic environment?",
         "question_type": "technical", "target_skills": skills},
        {"text": "How do you ensure data consistency and handle race conditions in distributed systems?",
         "question_type": "technical", "target_skills": []},
        {"text": "Do you have any final questions or thoughts regarding the deeper technical aspects of this role?",
         "question_type": "closing", "target_skills": []},
    ]
    return base[:max(3, count)]


async def generate_question_plan(job: Optional[dict], candidate: dict, count: int, interview_type: str = "ai_technical") -> List[Dict[str, Any]]:
    count = max(3, min(count, 15))
    remaining = count - 1
    
    is_l2 = interview_type == "ai_l2_technical"
    intro_q = L2_INTRO_QUESTION if is_l2 else INTRO_QUESTION
    
    system = (
        "You are an experienced technical interviewer designing a structured, job-specific interview. "
        + FAIRNESS_RULES
        + " Questions must be answerable verbally in 1-3 minutes each. Do NOT ask for code to be written."
    )
    
    if is_l2:
        user = f"""
Design {remaining} advanced interview questions for this candidate and job for a second-round (L2) interview.

JOB
{job_context(job)}

CANDIDATE (resume, PII removed)
{safe_resume_context(candidate)}

Requirements:
- This is a deep-dive L2 round. Do NOT ask basic introductory questions or "tell me about yourself".
- Focus heavily on system design, architecture, advanced problem solving, and complex scenarios.
- Ground the questions in the REQUIRED SKILLS above and the candidate's actual resume experience.
- Vary question_type across: technical, scenario, problem_solving, closing.
- Last question: a natural closing question.

Return STRICT JSON:
{{
  "questions": [
    {{"text": "...", "question_type": "technical", "target_skills": ["skill", ...]}}
  ]
}}
"""
    else:
        user = f"""
Design {remaining} interview questions for this candidate and job.

JOB
{job_context(job)}

CANDIDATE (resume, PII removed)
{safe_resume_context(candidate)}

Requirements:
- Do NOT include a generic "tell me about yourself" / introduction question — that is
  asked separately as question 1. Your first question should already be substantive.
- Include role-specific technical questions grounded in the REQUIRED SKILLS above.
- Include at least one question that references the candidate's actual resume skills/experience.
- Include a problem-solving question and a practical scenario question.
- Include one communication / behavioural question if appropriate.
- Last question: a natural closing question.
- Vary question_type across: technical, resume_specific, problem_solving, scenario, behavioral, closing.

Return STRICT JSON:
{{
  "questions": [
    {{"text": "...", "question_type": "technical", "target_skills": ["skill", ...]}}
  ]
}}
"""
    try:
        data = await _chat_json(system, user, temperature=0.4)
        raw = data.get("questions") or []
        plan: List[Dict[str, Any]] = [dict(intro_q)]
        for q in raw[:remaining]:
            text = str(q.get("text", "")).strip()
            if not text:
                continue
            plan.append({
                "text": text,
                "question_type": str(q.get("question_type") or "technical"),
                "target_skills": [str(s) for s in (q.get("target_skills") or [])][:6],
            })
        if len(plan) >= 3:
            return plan
        logger.warning("Question plan too short from LLM; using fallback.")
    except Exception as exc:
        logger.error(f"generate_question_plan failed: {exc}")
    
    return _l2_fallback_question_plan(job, count) if is_l2 else _fallback_question_plan(job, count)


# --------------------------------------------------------------------------
# 2. Per-turn answer analysis + follow-up decision
# --------------------------------------------------------------------------

async def analyze_answer(
    *,
    job: Optional[dict],
    question_text: str,
    question_target_skills: List[str],
    answer_text: str,
    followups_remaining: int,
) -> Dict[str, Any]:
    """Returns {score, feedback, ask_followup, followup_text}."""
    if not answer_text or not answer_text.strip():
        return {"score": 0.0, "feedback": "No answer was provided.", "ask_followup": False, "followup_text": None}

    system = (
        "You are a technical interviewer scoring a single spoken answer and deciding whether one "
        "concise follow-up would meaningfully probe deeper. " + FAIRNESS_RULES
    )
    user = f"""
JOB CONTEXT
{job_context(job)}

QUESTION ASKED
{question_text}
Target skills for this question: {', '.join(question_target_skills) or 'general'}

CANDIDATE ANSWER (speech-to-text, may contain transcription noise)
{answer_text[:2500]}

Follow-up questions still allowed in this interview: {followups_remaining}

Decide `ask_followup` = true ONLY when ALL of these hold:
- follow-ups remain (the number above is > 0);
- the answer contained a real, on-topic attempt worth probing further;
- a specific, DIFFERENT follow-up question would surface new signal.
Set `ask_followup` = false when the answer is empty, off-topic, unintelligible,
a refusal, or already thorough — in those cases just move on. The follow-up, if
any, must be a NEW question, not a rephrasing of the question asked.

Return STRICT JSON:
{{
  "score": 0-100,                         // quality of THIS answer only
  "feedback": "one sentence, factual",
  "ask_followup": true|false,
  "followup_text": "a new, specific follow-up question, or null"
}}
"""
    try:
        data = await _chat_json(system, user, temperature=0.3, timeout=45.0)
        score = data.get("score")
        try:
            score = float(str(score).replace("%", "").strip())
        except Exception:
            score = None
        ask = bool(data.get("ask_followup")) and followups_remaining > 0
        followup = str(data.get("followup_text")).strip() if data.get("followup_text") else None
        if ask and not followup:
            ask = False
        return {
            "score": score,
            "feedback": str(data.get("feedback") or "").strip() or None,
            "ask_followup": ask,
            "followup_text": followup if ask else None,
        }
    except Exception as exc:
        logger.error(f"analyze_answer failed: {exc}")
        return {"score": None, "feedback": None, "ask_followup": False, "followup_text": None}


# --------------------------------------------------------------------------
# 3. Final evaluation
# --------------------------------------------------------------------------

def _bucket(overall: float) -> str:
    if overall >= 82:
        return "strong_match"
    if overall >= 65:
        return "match"
    if overall >= 45:
        return "weak_match"
    return "no_match"


def compute_overall(scores: Dict[str, Any]) -> Optional[float]:
    """Deterministic weighted mean over whichever dimensions the LLM returned."""
    num = 0.0
    denom = 0.0
    for dim, weight in OVERALL_WEIGHTS.items():
        v = scores.get(dim)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        v = max(0.0, min(100.0, v))
        num += v * weight
        denom += weight
    if denom == 0:
        return None
    return round(num / denom, 1)


def _empty_eval() -> Dict[str, Any]:
    return {
        "scores": {k: None for k in SCORE_DIMENSIONS + ["overall"]},
        "recommendation": None,
        "ai_report": {
            "strengths": [], "areas_to_improve": [],
            "summary": "The candidate did not answer any interview questions, so there is nothing to evaluate.",
            "llm_recommendation": None, "not_evaluable": True,
        },
    }


async def evaluate_interview(snapshot: dict, transcript: List[dict], answers: List[dict]) -> Dict[str, Any]:
    """Returns a dict with `scores` (incl. deterministic overall), `recommendation`
    (deterministic bucket) and `ai_report` (qualitative + the LLM's own suggestion)."""
    lines = []
    candidate_turns = 0
    candidate_chars = 0
    for t in transcript:
        is_candidate = t.get("role") != "ai"
        role = "Candidate" if is_candidate else "Interviewer"
        text = str(t.get("text", "") or "")
        lines.append(f"{role}: {text}")
        if is_candidate and text.strip() and text.strip() != "(no audible answer was captured)":
            candidate_turns += 1
            candidate_chars += len(text.strip())
    transcript_text = "\n".join(lines)[:12000]

    # Defense in depth: never let the LLM score a transcript with no real answers
    # (it would grade the résumé and invent a match).
    if candidate_turns == 0 or candidate_chars < 25:
        logger.info("evaluate_interview: no substantive candidate answers — returning empty evaluation")
        return _empty_eval()

    system = (
        "You are a hiring analyst producing an objective, job-anchored evaluation of an AI interview "
        "transcript. " + FAIRNESS_RULES + " Output ONLY the requested JSON."
    )
    user = f"""
ROLE REQUIREMENTS (what the job needs — this is context, NOT the candidate's answers)
{snapshot.get('job_context', 'N/A')}

WHAT THE ROLE TYPICALLY EXPECTS FROM A RESUME (context only — the candidate has NOT verified any of this in the interview)
{snapshot.get('resume_context', 'N/A')}

INTERVIEW TRANSCRIPT (the ONLY evidence you may score from)
{transcript_text}

SCORING RULES — read carefully:
- Score every dimension 0-100 using ONLY what the candidate actually SAID in the transcript above.
- NEVER infer knowledge, skill or experience from the résumé context. The résumé tells you what
  the role wants; it is not evidence the candidate can do it. A strong résumé with weak answers is
  a low score.
- A question the candidate did not answer, answered off-topic, or answered "I don't know" contributes
  NOTHING to any dimension — score that portion 0.
- `strengths` and `areas_to_improve` must quote or paraphrase something the candidate SAID. Do not
  list résumé skills as strengths.
- If the candidate barely spoke, most dimensions should be well below 40.

Return STRICT JSON:
{{
  "technical_knowledge": 0-100,
  "problem_solving": 0-100,
  "communication": 0-100,
  "role_specific": 0-100,
  "experience": 0-100,
  "answer_relevance": 0-100,
  "strengths": ["short bullet grounded in what the candidate said", ...],
  "areas_to_improve": ["short bullet", ...],
  "summary": "2-4 sentence factual summary of how the candidate performed IN THE INTERVIEW",
  "recommendation": "strong_match | match | weak_match | no_match"
}}
"""
    llm: Dict[str, Any] = {}
    try:
        llm = await _chat_json(system, user, temperature=0.0, timeout=90.0)
    except Exception as exc:
        logger.error(f"evaluate_interview LLM call failed: {exc}")
        raise

    scores: Dict[str, Any] = {}
    for dim in SCORE_DIMENSIONS:
        v = llm.get(dim)
        try:
            scores[dim] = round(max(0.0, min(100.0, float(v))), 1)
        except (TypeError, ValueError):
            scores[dim] = None

    overall = compute_overall(scores)
    scores["overall"] = overall
    recommendation = _bucket(overall) if overall is not None else None

    ai_report = {
        "strengths": [str(s) for s in (llm.get("strengths") or [])][:8],
        "areas_to_improve": [str(s) for s in (llm.get("areas_to_improve") or [])][:8],
        "summary": str(llm.get("summary") or "").strip(),
        "llm_recommendation": str(llm.get("recommendation") or "").strip() or None,
    }

    return {"scores": scores, "recommendation": recommendation, "ai_report": ai_report}
