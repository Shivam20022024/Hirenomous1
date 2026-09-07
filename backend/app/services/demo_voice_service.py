from app.core.database import get_db
from app.services.voice_service import VoiceService
from app.services.classification_service import ClassificationService
from app.services.twilio_service import TwilioService
import json
import logging

logger = logging.getLogger(__name__)

class DemoVoiceService:
    @staticmethod
    async def process_step(candidate_id: str, step: str, recording_url: str):
        """Processes a single step of the screening call."""
        db = get_db()
        candidate = await db.candidates.find_one({"id": candidate_id})
        if not candidate:
            logger.error(f"Candidate {candidate_id} not found during step {step}")
            return None

        # 1. Download and Transcribe
        logger.info(f"Processing recording for {candidate_id}, step: {step}")
        audio_path = TwilioService.download_recording(recording_url, candidate_id, f"step_{step}")
        
        # Use OpenAI Whisper for low latency as requested
        transcript = await VoiceService.transcribe_with_openai(audio_path)
        logger.info(f"Transcript [{step}]: {transcript}")
        
        # 2. Classify response using Gemma
        classification_raw = await ClassificationService.classify_screening_response(transcript, step)
        classification = json.loads(classification_raw)
        result = classification.get("result", "unclear")
        logger.info(f"Classification [{step}]: {result}")
        
        # 3. Prepare DB Update
        update_doc = {
            f"screening_{step}": result,
            "transcription": (candidate.get("transcription") or "") + f"\n[{step.capitalize()}]: {transcript}"
        }
        
        # 4. Determine Logic Flow
        next_step = None
        if step == "interest":
            if result == "not_interested":
                next_step = "closing" # Jump to closing if not interested
                update_doc["final_status"] = "rejected"
                update_doc["status"] = "not_interested"
            else:
                next_step = "skills"
                update_doc["status"] = "interested"
        elif step == "skills":
            next_step = "availability"
        elif step == "availability":
            next_step = "closing"
            
            # Aggregate Final Status
            interest = candidate.get("screening_interest") or update_doc.get("screening_interest")
            skills = candidate.get("screening_skills") or update_doc.get("screening_skills")
            avail = result # current step
            
            if interest == "interested" and skills == "yes" and avail == "yes":
                update_doc["final_status"] = "qualified"
            elif interest == "not_interested" or (skills == "no" and interest != "unclear"):
                update_doc["final_status"] = "rejected"
            else:
                update_doc["final_status"] = "review"
        
        update_doc["call_step"] = next_step
        
        # update candidate in DB
        await db.candidates.update_one({"id": candidate_id}, {"$set": update_doc})
        
        return next_step
