from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Response
from app.services.voice_service import VoiceService
from app.services.classification_service import ClassificationService
from app.services.twilio_service import TwilioService
from app.services.hiring_voice_service import HiringVoiceService
from app.services.question_service import QuestionService
import pandas as pd
from app.core.database import get_db
from app.core.config import settings
import os
import shutil
import uuid
import json
import logging
from twilio.twiml.voice_response import VoiceResponse
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/call-shortlisted")
async def call_shortlisted():
    """Initiates screening calls for all shortlisted candidates who haven't been contacted."""
    db = get_db()
    
    threshold = getattr(settings, "SHORTLIST_THRESHOLD", 70)
    cursor = db.candidates.find({
        "resume_score": {"$gte": threshold},
        "$or": [
            {"interest": {"$exists": False}},
            {"interest": "pending"},
            {"interest": None}
        ]
    })
    candidates = await cursor.to_list(length=100)
    
    if not candidates:
        logger.info("No fresh shortlisted candidates found for calling.")
        return {"status": "success", "message": "No candidates to call", "called_ids": []}

    if not TwilioService.is_configured():
        raise HTTPException(status_code=500, detail="Twilio is not configured properly.")

    called_ids = []
    logger.info(f"Starting bulk call process for {len(candidates)} candidates.")
    
    for candidate in candidates:
        candidate_id = candidate["id"]
        phone_number = (candidate.get("phone") or "").strip()
        
        if not phone_number:
            logger.warning(f"Skipping call for {candidate['name']} - No phone number found.")
            continue
            
        try:
            call = await TwilioService.create_outbound_call(candidate_id, phone_number)
            
            await db.candidates.update_one(
                {"id": candidate_id},
                {"$set": {
                    "call_step": "0", # Start at index 0
                    "status": "calling", 
                    "twilio_call_sid": call.sid,
                    "final_status": "pending",
                    "calling_started_at": datetime.utcnow()
                }}
            )
            called_ids.append(candidate_id)
            logger.info(f"Call initiated: {candidate['name']} -> {phone_number} (SID: {call.sid})")
            
        except Exception as e:
            logger.error(f"Failed to trigger call for {candidate['name']} ({phone_number}): {str(e)}")

    return {
        "status": "success", 
        "called_count": len(called_ids), 
        "called_ids": called_ids,
        "source": "api"
    }

@router.post("/call-candidate/{candidate_id}")
async def call_candidate(candidate_id: str):
    """Initiates the screening call for a specific candidate."""
    db = get_db()
    candidate = None

    # 1. DB Lookup
    try:
        # Try ID first
        candidate = await db.candidates.find_one({"id": candidate_id})
        
        # Try name fallback in DB
        if not candidate:
            logger.info(f"ID lookup failed for {candidate_id}. Trying name search in DB.")
            candidate = await db.candidates.find_one({"name": {"$regex": candidate_id.replace("-", " "), "$options": "i"}})
    except Exception as e:
        logger.error(f"Database lookup failed during call initiation: {str(e)}")
        candidate = None

    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")

    phone_number = (candidate.get("phone") or "").strip()
    if not phone_number:
        raise HTTPException(status_code=400, detail="Candidate is missing a phone number")

    if not TwilioService.is_configured():
        raise HTTPException(status_code=500, detail="Twilio is not configured properly.")

    try:
        call = await TwilioService.create_outbound_call(candidate_id, phone_number)
        
        # Always update DB to show 'calling' status
        await db.candidates.update_one(
            {"id": candidate_id},
            {"$set": {
                "call_step": "0", # Start at index 0
                "status": "calling", 
                "twilio_call_sid": call.sid,
                "final_status": "pending",
                "calling_started_at": datetime.utcnow()
            }}
        )
        
        logger.info(f"Individual call initiated: {candidate['name']} (SID: {call.sid})")
        return {"status": "success", "call_sid": call.sid, "candidate": candidate["name"]}
    except Exception as e:
        logger.error(f"Error initiating call for {candidate_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Twilio call failed: {str(e)}")

@router.post("/twilio-webhook/{candidate_id}/{step}")
async def twilio_webhook(candidate_id: str, step: str):
    """Generates TwiML for a specific screening step index."""
    logger.info(f"TWILIO WEBHOOK HIT: candidate={candidate_id}, step={step}")
    response = VoiceResponse()
    
    # 1. Check if we are at the closing stage
    if step == "closing":
        logger.info("Executing call hangup (closing step).")
        response.say("Thank you for your time. Our team will contact you soon. Goodbye.", voice=settings.TWILIO_TTS_VOICE)
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # 2. Parse step index
    try:
        step_index = int(step)
    except ValueError:
        logger.error(f"Invalid step index: {step}")
        response.say("I'm sorry, an error occurred. Goodbye.", voice=settings.TWILIO_TTS_VOICE)
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # 3. Audible Greeting for step 0
    if step_index == 0:
        response.say(
            "Hello, this is an automated screening call for your recent job application.", 
            voice=settings.TWILIO_TTS_VOICE
        )
    
    # 4. Get the specific question from Excel
    question = QuestionService.get_question(step_index)
    if not question:
        logger.warning(f"No question found for step {step_index}. Moving to closing.")
        response.redirect(TwilioService.build_url(f"/voice/twilio-webhook/{candidate_id}/closing"))
        return Response(content=str(response), media_type="application/xml")

    # Determine if this is a repeat attempt
    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    existing_responses = candidate.get("screening_responses", []) if candidate else []
    attempts = len([r for r in existing_responses if r.get("question_id") == question.get("question_id")])
    
    if attempts > 0 and pd.notna(question.get("clarification")) and str(question.get("clarification")).strip():
        prompt = str(question["clarification"])
        logger.info(f"Speaking CLARIFICATION for step {step_index} (Attempt {attempts + 1}): '{prompt}'")
    else:
        prompt = str(question["question_text"])
        logger.info(f"Speaking question {step_index} (Attempt {attempts + 1}): '{prompt}'")
    response.say(prompt, voice=settings.TWILIO_TTS_VOICE)
    
    # 5. Handle Recording
    logger.info(f"Starting recording for step: {step_index}")
    response.record(
        max_length=20,
        timeout=4,
        play_beep=True,
        action=TwilioService.build_url(f"/voice/process-recording/{candidate_id}/{step_index}"),
        method="POST"
    )
        
    return Response(content=str(response), media_type="application/xml")

@router.post("/process-recording/{candidate_id}/{step}")
async def process_recording(candidate_id: str, step: str, request: Request):
    """Processes the recording and redirects to the next step index."""
    logger.info(f"PROCESSING RECORDING: Candidate={candidate_id}, Step={step}")
    form = await request.form()
    recording_url = str(form.get("RecordingUrl") or "").strip()
    
    if not recording_url:
        logger.warning(f"No RecordingUrl received from Twilio for candidate {candidate_id} at step {step}")
    
    try:
        step_index = int(step)
    except ValueError:
        logger.error(f"Invalid step index in recording handler: {step}")
        next_step = "closing"
    else:
        # Process the step logic
        next_step = await HiringVoiceService.process_screening_step(candidate_id, step_index, recording_url)
    
    logger.info(f"Next step index determined: {next_step or 'closing'}")
    
    # Redirect to the next step's TwiML
    response = VoiceResponse()
    redirect_url = TwilioService.build_url(f"/voice/twilio-webhook/{candidate_id}/{next_step or 'closing'}")
    logger.info(f"Redirecting Twilio to: {redirect_url}")
    response.redirect(redirect_url)
    
    return Response(content=str(response), media_type="application/xml")

@router.get("/results")
async def get_screening_results():
    """Returns all candidates with their screening status."""
    db = get_db()
    cursor = db.candidates.find(
        {"final_status": {"$exists": True, "$ne": None}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "screening_interest": 1, "screening_skills": 1, "screening_availability": 1, "final_status": 1, "status": 1}
    ).sort("created_at", -1)
    
    return await cursor.to_list(length=100)


@router.post("/call/twiml/{candidate_id}")
async def twilio_call_twiml(candidate_id: str):
    response = VoiceResponse()
    response.say(QUESTION_TEXT, voice=settings.TWILIO_TTS_VOICE)
    response.record(
        max_length=10,
        timeout=3,
        play_beep=True,
        trim="trim-silence",
        action=TwilioService.build_url(f"/call/twiml/{candidate_id}/complete"),
        method="POST",
        recording_status_callback=TwilioService.build_url(f"/call/recording/{candidate_id}"),
        recording_status_callback_method="POST",
        recording_status_callback_event="completed absent",
    )
    return Response(content=str(response), media_type="application/xml")


@router.post("/call/twiml/{candidate_id}/complete")
async def twilio_call_complete(candidate_id: str):
    response = VoiceResponse()
    response.say("Thank you. Goodbye.", voice=settings.TWILIO_TTS_VOICE)
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


@router.post("/call/status/{candidate_id}")
async def twilio_call_status(candidate_id: str, request: Request):
    form = await request.form()
    call_status = str(form.get("CallStatus") or "").strip()
    call_sid = str(form.get("CallSid") or "").strip()

    db = get_db()
    await db.candidates.update_one(
        {"id": candidate_id},
        {
            "$set": {
                "status": "called",
                "call_status": call_status,
                "twilio_call_sid": call_sid,
            }
        },
    )

    return {"ok": True}


@router.post("/call/recording/{candidate_id}")
async def twilio_recording_callback(candidate_id: str, request: Request):
    form = await request.form()
    recording_status = str(form.get("RecordingStatus") or "").strip()
    recording_url = str(form.get("RecordingUrl") or "").strip()
    recording_sid = str(form.get("RecordingSid") or "").strip()
    call_sid = str(form.get("CallSid") or "").strip()

    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if recording_status != "completed" or not recording_url:
        await db.candidates.update_one(
            {"id": candidate_id},
            {
                "$set": {
                    "status": "unclear",
                    "interest": "unclear",
                    "analysis_raw": json.dumps(
                        {
                            "interest": "unclear",
                            "reason": "No completed recording was received from Twilio.",
                        }
                    ),
                    "recording_status": recording_status or "absent",
                    "twilio_call_sid": call_sid,
                    "twilio_recording_sid": recording_sid,
                }
            },
        )
        return {"status": "ignored", "reason": "Recording not completed"}

    audio_path = TwilioService.download_recording(recording_url, candidate_id, recording_sid)
    transcript = await VoiceService.transcribe_audio(audio_path)
    classification_raw = await ClassificationService.classify_interest(transcript)
    classification = json.loads(classification_raw)

    await db.candidates.update_one(
        {"id": candidate_id},
        {
            "$set": {
                "interest": classification.get("interest"),
                "status": classification.get("interest"),
                "transcription": transcript,
                "analysis_raw": classification_raw,
                "recording_status": recording_status,
                "recording_url": recording_url,
                "recording_path": audio_path,
                "twilio_call_sid": call_sid,
                "twilio_recording_sid": recording_sid,
            }
        },
    )

    return {
        "name": candidate["name"],
        "phone": candidate.get("phone"),
        "interest": classification.get("interest"),
        "transcript": transcript,
    }

@router.post("/process-response")
async def process_voice_response(candidate_id: str, file: UploadFile = File(...)):
    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # 1. Save temp audio
    temp_dir = "temp_audio"
    os.makedirs(temp_dir, exist_ok=True)
    audio_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{file.filename}")
    
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # 2. Transcribe locally with Faster-Whisper
        transcript = await VoiceService.transcribe_audio(audio_path)
        
        # 3. Classify interest with Gemma
        classification_raw = await ClassificationService.classify_interest(transcript)
        classification = json.loads(classification_raw)
        
        # 4. Update Candidate in DB
        await db.candidates.update_one(
            {"id": candidate_id},
            {
                "$set": {
                    "interest": classification.get("interest"),
                    "status": classification.get("interest"), # Update status to the interest result
                    "transcription": transcript,
                    "analysis_raw": classification_raw
                }
            }
        )
        
        return {
            "candidate_id": candidate_id,
            "transcript": transcript,
            "classification": classification
        }
        
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
