import httpx
import json
import logging
import re
from app.core.config import settings

logger = logging.getLogger(__name__)

class SimulationService:
    @staticmethod
    def _last_candidate_reply(history: list) -> str:
        for entry in reversed(history):
            if entry.get("role") != "ai":
                return str(entry.get("text", "")).strip()
        return ""

    @staticmethod
    def _looks_negative(text: str) -> bool:
        lowered = text.lower()
        return bool(re.search(r"\b(no|not now|busy|later|not interested|don't|do not|can't|cannot)\b", lowered))

    @staticmethod
    def _looks_positive(text: str) -> bool:
        lowered = text.lower()
        return bool(re.search(r"\b(yes|yeah|yep|sure|okay|ok|interested|available|good time)\b", lowered))

    @staticmethod
    async def get_next_question(jd: str, history: list, custom_prompt: str = None, intro_greeting: str = None) -> dict:
        """
        Generates the next interview question based on the job description, history, and custom instructions.
        """
        ai_turns = [entry for entry in history if entry.get("role") == "ai"]
        last_reply = SimulationService._last_candidate_reply(history)

        if len(ai_turns) == 0:
            return {
                "text": intro_greeting or "Hi, this is an AI recruiter calling from Novlantis regarding your job application. Is now a good time for a quick 2-3 minute screening call?",
                "done": False,
            }

        if len(ai_turns) == 1:
            if SimulationService._looks_negative(last_reply):
                return {
                    "text": "Got it, thanks for letting me know. Please share a better time, and our team will contact you shortly. Have a great day!",
                    "done": True,
                }
            return {
                "text": "Great, thank you! I'll ask you a few quick questions to understand your profile better. Are you currently interested in exploring this opportunity?",
                "done": False,
            }

        if len(ai_turns) == 2:
            if SimulationService._looks_negative(last_reply):
                return {
                    "text": "Got it, thanks for letting me know. We'll keep your profile on file, and our team may contact you for a future opportunity. Have a great day!",
                    "done": True,
                }
            return {
                "text": "Thanks for sharing. Could you briefly tell me about your relevant experience?",
                "done": False,
            }

        if len(ai_turns) == 3:
            return {
                "text": "That sounds good. Can you tell me what kind of projects or technologies you've worked with?",
                "done": False,
            }

        if len(ai_turns) == 4:
            return {
                "text": "Got it. How soon would you be available to join if selected?",
                "done": False,
            }

        if len(ai_turns) == 5:
            return {
                "text": "Thanks for sharing. Could you share your current and expected salary?",
                "done": False,
            }

        if len(ai_turns) >= 6:
            return {
                "text": "Thanks for sharing. Based on this quick screening, our team will review your profile and contact you shortly for the next steps. It was nice speaking with you. Have a great day!",
                "done": True,
            }

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        # Format history for the prompt
        transcript = ""
        for entry in history:
            role = "AI" if entry["role"] == "ai" else "Candidate"
            transcript += f"{role}: {entry['text']}\n"

        system_instruction = (
            "You are a friendly, professional voice recruiter conducting a short phone screening for Novlantis. "
            "Ask one question at a time, keep each response under 2 sentences, acknowledge candidate replies, "
            "and do not repeat the company introduction after the opening."
        )
        if custom_prompt:
            system_instruction += f" Specific instructions for this interview: {custom_prompt}"

        # If it's the very first message and we have a custom intro, use it.
        if not transcript and intro_greeting:
            return {"text": intro_greeting, "done": False}

        prompt = f"""
        Handle the next turn in an AI Recruiter interview for Novlantis.
        
        Job Description:
        {jd}
        
        Conversation History:
        {transcript if transcript else "(No history yet)"}
        
        RECRUITER GUIDELINES:
        {custom_prompt if custom_prompt else "Follow this exact phone screening sequence:"}
        1. Greeting and availability check.
        2. Short transition: say you will ask a few quick questions.
        3. Interest check for the opportunity.
        4. Relevant experience.
        5. Projects or technologies worked on.
        6. Availability / notice period.
        7. Current and expected salary.
        8. Short fit decision and polite closing.

        Rules:
        1. Ask exactly ONE question at a time.
        2. Wait for the candidate's response before moving to the next phase.
        3. Keep the tone natural, professional, and helpful.
        4. Do not repeat the company introduction after the first turn.
        5. Acknowledge responses briefly with phrases like "Got it", "Thanks for sharing", or "That sounds good".
        6. If the candidate says now is not a good time, ask for a better time and end politely.
        7. If the candidate is not interested, end politely.
        8. If the input is unclear, say "Sorry, could you repeat that?"
        9. If the user is silent, say "Are you still there?"
        10. Return ONLY the AI's spoken response text.
        """

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{settings.OPENAI_API_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=settings.AI_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()
                return {"text": data["choices"][0]["message"]["content"].strip(), "done": False}
            except Exception as e:
                logger.error(f"Failed to generate next question: {str(e)}")
                return {"text": "Could you tell me a bit more about your background?", "done": False}

    @staticmethod
    async def evaluate_interview(jd: str, history: list, custom_prompt: str = None) -> dict:
        """
        Evaluates the interview at the end of the session, considering custom instructions.
        """
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        transcript = ""
        for entry in history:
            role = "AI" if entry["role"] == "ai" else "Candidate"
            transcript += f"{role}: {entry['text']}\n"

        prompt = f"""
        Analyze this interview transcript based on the following Job Description.
        
        Job Description:
        {jd}
        
        {f"Special Evaluation Focus: {custom_prompt}" if custom_prompt else ""}

        Transcript:
        {transcript}
        
        Provide an evaluation as a JSON object with:
        {{
            "skill_match_score": 0-100,
            "communication_quality_score": 0-100,
            "technical_score": 0-100,
            "confidence_score": 0-100,
            "sentiment": "positive" | "neutral" | "negative",
            "emotion": "confident" | "nervous" | "enthusiastic" | "hesitant",
            "summary": "Short paragraph summary of the interview.",
            "pros": ["Pro 1", "..."],
            "cons": ["Con 1", "..."]
        }}
        """

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a recruitment analyst. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{settings.OPENAI_API_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=settings.AI_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()
                return json.loads(data["choices"][0]["message"]["content"])
            except Exception as e:
                logger.error(f"Interview evaluation failed: {str(e)}")
                return {
                    "skill_match_score": 0,
                    "communication_quality_score": 0,
                    "technical_score": 0,
                    "confidence_score": 0,
                    "summary": "Evaluation failed due to system error.",
                    "pros": [],
                    "cons": []
                }
