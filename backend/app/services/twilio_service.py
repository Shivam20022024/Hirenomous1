import os
from typing import Optional

import requests
from twilio.rest import Client

from app.core.config import settings


QUESTION_TEXT = (
    "Hello, this is an automated call regarding a job opportunity. "
    "Are you interested in this role?"
)


class TwilioService:
    @staticmethod
    def is_configured() -> bool:
        return all(
            [
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
                settings.TWILIO_FROM_NUMBER,
                settings.PUBLIC_BASE_URL,
            ]
        )

    @staticmethod
    def get_client() -> Client:
        if not TwilioService.is_configured():
            raise RuntimeError(
                "Twilio is not configured. Set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, and PUBLIC_BASE_URL."
            )

        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    @staticmethod
    def build_url(path: str) -> str:
        base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    @staticmethod
    async def create_outbound_call(candidate_id: str, phone_number: str):
        """Initiates an outbound call for a candidate via Twilio."""
        client = TwilioService.get_client()

        return client.calls.create(
            to=phone_number,
            from_=settings.TWILIO_FROM_NUMBER,
            # Directing to the multi-step screening interest webhook
            url=TwilioService.build_url(f"/voice/twilio-webhook/{candidate_id}/0"),
            method="POST",
            status_callback=TwilioService.build_url(f"/voice/call/status/{candidate_id}"),
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"]
        )

    @staticmethod
    async def create_demo_outbound_call(candidate_id: str, phone_number: str):
        client = TwilioService.get_client()

        return client.calls.create(
            to=phone_number,
            from_=settings.TWILIO_FROM_NUMBER,
            url=TwilioService.build_url(f"/demo/webhook/{candidate_id}/v1"),
            method="POST",
            status_callback=TwilioService.build_url(f"/demo/call/status/{candidate_id}"),
            status_callback_method="POST",
            status_callback_event="initiated ringing answered completed",
        )



    @staticmethod
    def download_recording(recording_url: str, candidate_id: str, recording_sid: str) -> str:
        if not recording_url:
            raise ValueError("Missing recording URL.")

        os.makedirs(settings.TWILIO_RECORDING_DIR, exist_ok=True)
        file_path = os.path.join(
            settings.TWILIO_RECORDING_DIR,
            f"{candidate_id}_{recording_sid}.mp3",
        )

        download_url = recording_url if recording_url.endswith(".mp3") else f"{recording_url}.mp3"
        response = requests.get(
            download_url,
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            timeout=120,
        )
        response.raise_for_status()

        with open(file_path, "wb") as output:
            output.write(response.content)

        return file_path
