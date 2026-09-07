from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import FileResponse
from app.services.simulation_service import SimulationService
from app.services.tts_service import TTSService
from app.core.database import get_db
from app.core.config import settings
import os
import logging
from typing import List, Dict

router = APIRouter(prefix="/simulation")
logger = logging.getLogger(__name__)

@router.post("/next-question")
async def next_question(
    candidate_id: str = Body(...),
    history: List[Dict] = Body(...),
    jd: str = Body(None),
    custom_prompt: str = Body(None),
    intro_greeting: str = Body(None)
):
    """
    Returns the next AI question text and a URL to its speech audio.
    """
    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    
    # If JD not provided in body, use the one from candidate record if available
    target_jd = jd or (candidate.get("job_description") if candidate else "Software Engineer role")
    
    try:
        if candidate and not history:
            await db.candidates.update_one(
                {"id": candidate_id},
                {"$set": {"status": "calling", "interest": candidate.get("interest") or "pending"}}
            )

        # 1. Generate text
        question_result = await SimulationService.get_next_question(target_jd, history, custom_prompt, intro_greeting)
        question_text = question_result["text"]
        
        # 2. Generate audio
        audio_path = await TTSService.generate_speech(question_text)
        audio_filename = os.path.basename(audio_path)
        
        return {
            "text": question_text,
            "audio_url": f"/simulation/audio/{audio_filename}",
            "done": question_result.get("done", False),
        }
    except Exception as e:
        logger.error(f"Error in next-question: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/audio/{filename}")
async def get_audio(filename: str):
    """
    Serves the generated AI speech audio files.
    """
    file_path = os.path.join("temp_audio", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    
    return FileResponse(file_path, media_type="audio/mpeg")

@router.post("/evaluate")
async def evaluate(
    candidate_id: str = Body(...),
    history: List[Dict] = Body(...),
    jd: str = Body(None),
    custom_prompt: str = Body(None)
):
    """
    Final evaluation of the interview session.
    """
    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    target_jd = jd or (candidate.get("job_description") if candidate else "Software Engineer role")
    
    try:
        evaluation = await SimulationService.evaluate_interview(target_jd, history, custom_prompt)
        
        # Save evaluation to candidate record
        if candidate:
            await db.candidates.update_one(
                {"id": candidate_id},
                {"$set": {
                    "interview_evaluation": evaluation,
                    "interview_transcript": history,
                    "interest": "interviewed",
                    "status": "interviewed"
                }}
            )
            
        return evaluation
    except Exception as e:
        logger.error(f"Error in evaluation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
