"""Media storage abstraction for interview recordings.

There is no object storage in the project today (resumes/TTS use local `temp/`
dirs), so this is a thin local-filesystem implementation behind a small
interface. To move to S3/GCS later, implement `save` / `abs_path` / `exists` /
`delete` against the bucket and keep the `ref` string format
(`<category>/<interview_id>/<filename>`).

Large video is NEVER read into MongoDB and NEVER returned in normal API
responses — only the `ref` string is stored on the answer, and recruiters
stream the file through an authenticated endpoint.
"""
import os
import uuid
import logging
from typing import Optional

from fastapi import UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024  # 1 MiB streamed writes — never load a whole video into memory


def _root() -> str:
    return settings.INTERVIEW_MEDIA_DIR


class InterviewStorage:
    """Local-filesystem media store. `ref` = "<category>/<interview_id>/<file>"."""

    @staticmethod
    def _safe(part: str) -> str:
        return os.path.basename(str(part)).replace("..", "_")

    @classmethod
    def abs_path(cls, ref: str) -> str:
        parts = [cls._safe(p) for p in ref.split("/") if p]
        return os.path.join(_root(), *parts)

    @classmethod
    def exists(cls, ref: Optional[str]) -> bool:
        return bool(ref) and os.path.isfile(cls.abs_path(ref))

    @classmethod
    async def save_upload(
        cls, *, interview_id: str, category: str, upload: UploadFile, question_id: str = "q"
    ) -> Optional[str]:
        """Stream an UploadFile to disk in chunks. Returns the storage ref, or
        None if the upload was empty. Never raises for an empty/oversized file
        beyond the configured cap."""
        ext = os.path.splitext(upload.filename or "")[1].lower() or ".webm"
        if ext not in (".webm", ".mp4", ".m4a", ".ogg", ".wav", ".mp3"):
            ext = ".webm"
        folder = os.path.join(_root(), cls._safe(category), cls._safe(interview_id))
        os.makedirs(folder, exist_ok=True)
        fname = f"{cls._safe(question_id)}_{uuid.uuid4().hex}{ext}"
        dest = os.path.join(folder, fname)

        written = 0
        cap = settings.INTERVIEW_MEDIA_MAX_MB * 1024 * 1024
        try:
            await upload.seek(0)
            with open(dest, "wb") as f:
                while True:
                    chunk = await upload.read(_CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > cap:
                        logger.warning(f"Interview media exceeded {settings.INTERVIEW_MEDIA_MAX_MB}MB cap; truncating")
                        break
                    f.write(chunk)
        except Exception as exc:
            logger.error(f"InterviewStorage.save_upload failed: {exc}")
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except Exception:
                    pass
            return None

        if written == 0:
            try:
                os.remove(dest)
            except Exception:
                pass
            return None

        return f"{cls._safe(category)}/{cls._safe(interview_id)}/{fname}"

    @classmethod
    def delete_interview(cls, interview_id: str) -> None:
        import shutil
        for category in ("interview_video", "interview_audio"):
            folder = os.path.join(_root(), category, cls._safe(interview_id))
            shutil.rmtree(folder, ignore_errors=True)
