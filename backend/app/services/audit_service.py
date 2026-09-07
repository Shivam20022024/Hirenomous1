"""Lightweight, organization-scoped audit trail for hiring actions.

The modular Hireonomous backend has no existing audit mechanism (the legacy
`activity_logs` collection is written by other products sharing the cluster and
is not tenant-scoped), so this introduces a dedicated `hiring_events` collection.
Writes are best-effort and never block or fail the caller's operation.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, Any, Dict

from app.core.database import get_db

logger = logging.getLogger(__name__)


class AuditService:
    @staticmethod
    async def record(
        *,
        organization_id: str,
        event_type: str,
        actor_type: str = "system",          # recruiter | ai | system | candidate
        actor_id: Optional[str] = None,
        candidate_id: Optional[str] = None,
        job_id: Optional[str] = None,
        interview_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            db = get_db()
            await db.hiring_events.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": organization_id,
                "event_type": event_type,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "candidate_id": candidate_id,
                "job_id": job_id,
                "interview_id": interview_id,
                "payload": payload or {},
                "created_at": datetime.utcnow(),
            })
        except Exception as exc:  # audit must never break the primary action
            logger.warning(f"AuditService.record failed for {event_type}: {exc}")
