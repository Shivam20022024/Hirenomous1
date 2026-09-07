from app.core.database import get_db
from app.services.voice_service import VoiceService
from app.services.classification_service import ClassificationService
from app.services.twilio_service import TwilioService
from app.services.question_service import QuestionService
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class HiringVoiceService:
    @staticmethod
    async def process_screening_step(candidate_id: str, step_index: int, recording_url: str):
        """
        Processes a single step of the screening call based on Excel questions.
        1. Downloads recording from Twilio.
        2. Transcribes locally using Faster-Whisper.
        3. Classifies response using Gemma.
        4. Updates candidate record and determines next step.
        """
        db = get_db()
        candidate = await db.candidates.find_one({"id": candidate_id})
        if not candidate:
            logger.error(f"Candidate {candidate_id} not found during screening step {step_index}")
            return None

        # Get current question info
        question = QuestionService.get_question(step_index)
        if not question:
            logger.error(f"Question not found for index {step_index}")
            return "closing"

        # 1. Download and Transcribe
        logger.info(f"Processing screening recording for {candidate_id}, step: {step_index}")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        audio_path = TwilioService.download_recording(recording_url, candidate_id, f"step_{step_index}_{timestamp}")
        
        # Transcribe locally
        transcript = await VoiceService.transcribe_audio(audio_path)
        logger.info(f"Transcript for {candidate_id} [Step {step_index}]: {transcript}")
        
        # 2. Classify response
        # We pass the full question dictionary to use intent mapping
        classification_raw = await ClassificationService.classify_screening_response(transcript, question)
        classification = json.loads(classification_raw)
        result = classification.get("result", "unclear")
        callback_date = classification.get("callback_date")
        callback_time = classification.get("callback_time")
        logger.info(f"Classification for {candidate_id} [Step {step_index}]: {result} (Date: {callback_date}, Time: {callback_time})")
        
        # 3. Prepare DB Update
        now = datetime.utcnow()
        response_obj = {
            "question_id": question.get("question_id"),
            "question": question["question_text"],
            "answer": result,
            "transcript": transcript,
            "timestamp": now.isoformat()
        }
        
        # Append to screening_responses
        await db.candidates.update_one(
            {"id": candidate_id},
            {"$push": {"screening_responses": response_obj}}
        )
        
        # Check how many attempts for this question
        existing_responses = candidate.get("screening_responses", [])
        attempts = len([r for r in existing_responses if r.get("question_id") == question.get("question_id")]) + 1
        
        # 4. Determine next step
        total_questions = QuestionService.get_total_questions()
        next_step_index = step_index + 1
        
        # Handle unclear / multiple attempts
        if result == "unclear":
            max_attempts = question.get("max_attempts")
            
            try:
                max_attempts = int(max_attempts)
            except (ValueError, TypeError):
                max_attempts = 1
            
            if attempts < max_attempts:
                logger.info(f"Candidate {candidate_id} response unclear. Attempt {attempts} of {max_attempts}. Repeating step {step_index}.")
                # Do NOT increment call_step. Return the same step so it repeats.
                return str(step_index)
            else:
                logger.info(f"Candidate {candidate_id} response unclear after {attempts} attempts. Moving to next step.")
                # We exceeded max attempts, we will move to next step.

        # Special logic: Availability check (Step 0)
        if step_index == 0:
            if result == "REJECTED" or result == "not_interested":
                logger.info(f"Candidate {candidate_id} marked as not interested. Stopping.")
                await db.candidates.update_one(
                    {"id": candidate_id},
                    {"$set": {
                        "status": "not_interested",
                        "interest": "not_interested",
                        "final_status": "rejected",
                        "call_step": "closing"
                    }}
                )
                return "closing"
            elif result in ["NOT_AVAILABLE", "CALLBACK_REQUESTED"]:
                logger.info(f"Candidate {candidate_id} requested callback. Stopping.")
                await db.candidates.update_one(
                    {"id": candidate_id},
                    {"$set": {
                        "status": "CALLBACK_REQUIRED",
                        "callback_requested": True,
                        "callback_date": callback_date,
                        "callback_time": callback_time,
                        "call_step": "closing"
                    }}
                )
                return "closing"
            elif result == "AVAILABLE":
                pass # Proceed normally


        # Check if we finished all questions
        if next_step_index >= total_questions:
            logger.info(f"Candidate {candidate_id} finished all questions.")
            await db.candidates.update_one(
                {"id": candidate_id},
                {"$set": {
                    "call_step": "closing",
                    "final_status": "review" # Default to review until all checked
                }}
            )
            return "closing"
        
        # Update current step and proceed
        await db.candidates.update_one(
            {"id": candidate_id},
            {"$set": {"call_step": str(next_step_index)}}
        )
        
        return str(next_step_index)
