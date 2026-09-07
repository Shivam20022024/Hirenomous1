from fastapi import APIRouter, HTTPException, Request, Response
from twilio.twiml.voice_response import VoiceResponse

from app.core.database import get_db
from app.core.config import settings
from app.services.twilio_service import TwilioService
from app.services.demo_voice_service import DemoVoiceService
from app.services.twilio_service import QUESTION_TEXT

router = APIRouter()

STEP_MAPPING = {
    "v1": "interest",
    "v2": "skills",
    "v3": "availability",
    "interest": "interest",
    "skills": "skills",
    "availability": "availability",
}

QUESTION_TEXTS = {
    "interest": QUESTION_TEXT,
    "skills": "Do you have experience in Python or AI? Please answer yes or no.",
    "availability": "Are you available to join within 30 days? Please answer yes or no.",
}

CLOSING_MESSAGE = "Thank you for your time. Goodbye."


def resolve_step(stage: str) -> str:
    step = STEP_MAPPING.get(stage)
    if not step:
        raise HTTPException(status_code=404, detail="Invalid demo stage")
    return step


@router.post("/demo/call/{candidate_id}")
async def start_demo_call(candidate_id: str):
    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    phone_number = (candidate.get("phone") or "").strip()
    if not phone_number:
        raise HTTPException(status_code=400, detail="Candidate is missing a phone number")

    if not TwilioService.is_configured():
        raise HTTPException(
            status_code=500,
            detail=(
                "Twilio is not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                "TWILIO_FROM_NUMBER, and PUBLIC_BASE_URL."
            ),
        )

    call = await TwilioService.create_demo_outbound_call(candidate_id, phone_number)

    await db.candidates.update_one(
        {"id": candidate_id},
        {
            "$set": {
                "status": "called",
                "call_step": "interest",
                "twilio_call_sid": call.sid,
                "call_status": call.status,
            }
        },
    )

    return {
        "status": "success",
        "message": f"Demo screening call initiated for {candidate['name']}",
        "candidate": {"name": candidate["name"], "phone": phone_number},
        "call_sid": call.sid,
    }


@router.post("/demo/webhook/{candidate_id}/{stage}")
async def demo_webhook(candidate_id: str, stage: str):
    step = resolve_step(stage)
    response = VoiceResponse()

    if step == "interest":
        response.say(
            "Hello, this is an automated screening call for a job opportunity.",
            voice=settings.TWILIO_TTS_VOICE,
        )

    response.say(QUESTION_TEXTS[step], voice=settings.TWILIO_TTS_VOICE)
    response.record(
        max_length=12,
        timeout=3,
        play_beep=True,
        trim="trim-silence",
        action=TwilioService.build_url(f"/demo/twiml/callback/{candidate_id}/{step}"),
        method="POST",
    )

    return Response(content=str(response), media_type="application/xml")


@router.post("/demo/twiml/callback/{candidate_id}/{step}")
async def demo_twiml_callback(candidate_id: str, step: str, request: Request):
    step = resolve_step(step)
    form = await request.form()
    recording_status = str(form.get("RecordingStatus") or "").strip()
    recording_url = str(form.get("RecordingUrl") or "").strip()

    response = VoiceResponse()
    if recording_status != "completed" or not recording_url:
        response.say(
            "Sorry, I did not receive a recording. Goodbye.",
            voice=settings.TWILIO_TTS_VOICE,
        )
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    next_step = await DemoVoiceService.process_step(candidate_id, step, recording_url)

    if next_step == "closing":
        response.say(CLOSING_MESSAGE, voice=settings.TWILIO_TTS_VOICE)
        response.hangup()
    else:
        response.say(
            "Thank you. Moving to the next question.",
            voice=settings.TWILIO_TTS_VOICE,
        )
        response.redirect(TwilioService.build_url(f"/demo/webhook/{candidate_id}/{next_step}"))

    return Response(content=str(response), media_type="application/xml")


@router.post("/demo/call/status/{candidate_id}")
async def demo_call_status(candidate_id: str, request: Request):
    form = await request.form()
    call_status = str(form.get("CallStatus") or "").strip()
    call_sid = str(form.get("CallSid") or "").strip()

    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    await db.candidates.update_one(
        {"id": candidate_id},
        {
            "$set": {
                "call_status": call_status,
                "twilio_call_sid": call_sid,
            }
        },
    )

    return {"ok": True}
