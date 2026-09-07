import httpx
from app.core.config import settings
import os
import uuid
import logging

logger = logging.getLogger(__name__)

class TTSService:
    @staticmethod
    async def generate_speech(text: str, voice: str = "alloy") -> str:
        """
        Converts text to speech using OpenAI TTS API and returns the path to the saved file.
        """
        temp_dir = "temp_audio"
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"ai_speech_{uuid.uuid4()}.mp3"
        file_path = os.path.join(temp_dir, filename)

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "tts-1",
            "input": text,
            "voice": voice or "alloy"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{settings.OPENAI_API_BASE}/audio/speech",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
                
                return file_path
            except Exception as e:
                logger.error(f"TTS Generation failed: {str(e)}")
                raise Exception(f"Failed to generate speech: {str(e)}")
