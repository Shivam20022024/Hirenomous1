import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, Iterable, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def sender_for(org: Optional[Dict[str, Any]], sender_name: Optional[str] = None) -> Dict[str, Optional[str]]:
        """Per-company sender identity for candidate-facing mail. The From address
        stays the one verified sending address, but the display name and Reply-To
        belong to the hiring company (multi-tenant branding). `sender_name`, when
        given, is the recruiter who actually took the action — shown alongside the
        company name so a candidate sees who at the company reached out."""
        org = org or {}
        name = org.get("name") or settings.APP_NAME
        display = f"{sender_name} - {name} Hiring Team" if sender_name else f"{name} Hiring Team"
        return {
            "from_name": display,
            "reply_to": org.get("reply_to") or org.get("contact_email"),
        }

    @staticmethod
    def is_configured() -> bool:
        return all([
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            settings.SMTP_USER,
            settings.SMTP_PASSWORD,
            settings.SMTP_FROM_EMAIL,
        ])

    @staticmethod
    def build_shortlist_email(candidate: dict, company_name: str, stage: str = "shortlisted") -> tuple[str, str]:
        """Progress-notification email.

        `stage="shortlisted"` -> "you've been shortlisted" (the "Email Interested" action).
        `stage="selected"`    -> "we'd like to move forward" (explicit recruiter Select).

        Contains NO meeting link and NO time slots — scheduling / next steps are
        handled by the hiring team (or, for the interview stage, by the dedicated
        AI Interview invitation email). The candidate's skills are their actual
        resume-parsed skills; the job requirements come from the real posting when
        the caller resolves them.
        """
        candidate_name = candidate.get("name") or "Candidate"

        # Real job title resolved by the caller from jobs_board via job_id
        # (falls back to the resume-parsed `role`).
        job_role = candidate.get("job_title_for_email") or candidate.get("role")
        if not job_role or job_role in ["Not Assessed", "Manual Entry", "Unassigned"]:
            job_role_display = "an open position"
        else:
            job_role_display = f"the {job_role} position"

        resume_skills = [str(s) for s in (candidate.get("skills") or []) if s][:6]
        job_skills = [str(s) for s in (candidate.get("job_skills_for_email") or []) if s][:8]

        # Factual profile line — only what is actually in the resume / posting.
        matched = [s for s in resume_skills if any(s.lower() in j.lower() or j.lower() in s.lower() for j in job_skills)]
        if matched:
            profile_line = f"Your experience with {', '.join(matched[:3])} is directly relevant to this role."
        elif resume_skills:
            profile_line = f"Your experience with {', '.join(resume_skills[:3])} stood out during our review."
        else:
            profile_line = "Your background was a good fit for what this role needs."

        if stage == "selected":
            subject = f"Update on your application - {job_role} at {company_name}" if job_role and job_role_display != "an open position" else f"Update on your application at {company_name}"
            opening = (
                f"We're pleased to let you know that we would like to move forward with your application for "
                f"{job_role_display} at {company_name}."
            )
            next_steps = "Our hiring team will contact you shortly to discuss the next steps."
        else:
            subject = f"You've been shortlisted - {job_role} at {company_name}" if job_role and job_role_display != "an open position" else f"You've been shortlisted at {company_name}"
            opening = (
                f"Thank you for your interest in {job_role_display} at {company_name}. "
                f"After reviewing your profile, we're pleased to tell you that you have been shortlisted."
            )
            next_steps = "Our hiring team will be in touch with the next steps in the process."

        prompt = f"""
        You are a recruitment assistant writing a short, professional email to a candidate.

        FACTS (use ONLY these — do not invent anything):
        - Candidate name: {candidate_name}
        - Company: {company_name}
        - Role: {job_role_display}
        - Stage: {"selected to move forward" if stage == "selected" else "shortlisted after profile review"}
        - Candidate's relevant skills (from their resume): {', '.join(resume_skills) or 'not specified'}
        - Note about their fit: {profile_line}
        - Next steps: {next_steps}

        Rules:
        - Greet the candidate by name.
        - State clearly that they have been {"selected to move forward" if stage == "selected" else "shortlisted"} for the role.
        - Include the one-line note about their fit.
        - State the next steps exactly as given.
        - DO NOT include any meeting link, video-call link, calendar link, or specific time slots.
        - DO NOT ask them to pick a time or confirm availability.
        - DO NOT invent any details, dates, or requirements.
        - Keep it under 120 words, plain text, warm and professional.
        - Sign off as "{company_name} Hiring Team".

        Return STRICT JSON: {{"subject": "...", "body": "..."}}
        """

        fallback_body = (
            f"Hi {candidate_name},\n\n"
            f"{opening}\n\n"
            f"{profile_line}\n\n"
            f"{next_steps}\n\n"
            "Best regards,\n"
            f"{company_name} Hiring Team"
        )

        try:
            import requests
            import json
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a recruitment assistant. Return only valid JSON. Never invent links, dates or time slots."},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
            }
            response = requests.post(settings.OPENROUTER_API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = json.loads(response.json()["choices"][0]["message"]["content"])
            body = str(result.get("body") or "").strip()
            # Guard: if the model still slipped in a link or a time slot, use the safe fallback.
            lowered = body.lower()
            import re as _re
            slot_like = bool(_re.search(r"\d{1,2}(:\d{2})?\s?(am|pm)\b", lowered)) or "time slot" in lowered
            if not body or "http" in lowered or "meet.google" in lowered or "calendly" in lowered or slot_like:
                logger.warning("Shortlist email model output contained a link/time slot; using safe fallback.")
                return subject, fallback_body
            return str(result.get("subject") or subject), body
        except Exception as exc:
            logger.warning(f"build_shortlist_email LLM failed, using fallback: {exc}")
            return subject, fallback_body

    @staticmethod
    def build_interview_invite_email(
        candidate: dict,
        job_title: str,
        interview_url: str,
        expected_minutes: str = "20-30",
        company_name: str = settings.APP_NAME,
        interview_type: str = "ai_technical",
    ) -> tuple[str, str]:
        """Dedicated AI Interview invitation email. Independent of the
        shortlist / selection email — creating an interview must never send that."""
        candidate_name = candidate.get("name", "Candidate")
        role_display = job_title or "the open position"
        
        is_l2 = interview_type == "ai_l2_technical"
        round_name = "Second Round (L2) AI Interview" if is_l2 else "AI Interview"
        
        subject = f"{round_name} Invitation - {role_display}"
        
        if is_l2:
            intro_text = (
                "Congratulations on passing the first round! We were impressed by your background "
                "and would like to invite you to a second-round (L2) AI-powered video interview.\n\n"
                "This round will be a deeper dive into system design, advanced technical problem-solving, "
                "and practical scenarios related to the role."
            )
        else:
            intro_text = (
                "You have been invited to complete an AI-powered video interview. It will assess your "
                "technical knowledge, problem solving, role-specific skills and communication."
            )

        body = (
            f"Hi {candidate_name},\n\n"
            f"Thank you for your interest in the {role_display} position.\n\n"
            f"{intro_text}\n\n"
            f"Interview duration:\nApproximately {expected_minutes} minutes.\n\n"
            f"Interview link:\n{interview_url}\n\n"
            "Before you begin:\n"
            "- Use a laptop or desktop with a working camera and microphone (Chrome or Edge recommended).\n"
            "- Allow camera and microphone access when prompted.\n"
            "- Sit in a quiet, well-lit place and keep your face visible.\n"
            "- Ensure a stable internet connection.\n"
            "- Complete the interview independently and in one sitting.\n\n"
            f"This link is personal to you and is valid for {settings.INTERVIEW_TOKEN_TTL_HOURS} hours only "
            "from the time this email was sent — after that it will expire, so please complete the "
            "interview well before then.\n\n"
            "Regards,\n"
            f"{company_name} Hiring Team"
        )
        return subject, body

    @staticmethod
    def send_selection_email(candidate: dict, company_name: str, org: Optional[dict] = None, sender_name: Optional[str] = None) -> dict:
        """Explicitly send the progress email to a SINGLE candidate at the
        'selected' stage. Reuses `build_shortlist_email`. Only ever called from an
        explicit recruiter 'Select' action — never from any interview lifecycle."""
        email = (candidate.get("email") or "").strip()
        name = candidate.get("name") or "Candidate"
        if not email or "@" not in email:
            return {"sent": 0, "skipped": 1, "failed": 0, "errors": [f"{name}: no valid email"]}
        try:
            subject, body = EmailService.build_shortlist_email(candidate, company_name, stage="selected")
            EmailService.send_email(email, subject, body, **EmailService.sender_for(org, sender_name))
            return {"sent": 1, "skipped": 0, "failed": 0, "errors": []}
        except Exception as exc:
            return {"sent": 0, "skipped": 0, "failed": 1, "errors": [f"{name} <{email}>: {exc}"]}

    @staticmethod
    def build_rejection_email(candidate: dict, company_name: str) -> tuple[str, str]:
        """Post-interview regret email. Fixed, professional template — no LLM,
        no specific reasons disclosed (standard hiring practice)."""
        candidate_name = candidate.get("name") or "Candidate"
        job_role = candidate.get("job_title_for_email") or candidate.get("role")
        if not job_role or job_role in ("Not Assessed", "Manual Entry", "Unassigned"):
            role_display = "the position"
            subject = f"Update on your application at {company_name}"
        else:
            role_display = f"the {job_role} position"
            subject = f"Update on your application - {job_role} at {company_name}"
        body = (
            f"Hi {candidate_name},\n\n"
            f"Thank you for taking the time to interview for {role_display} at {company_name}, "
            "and for your interest in joining our team.\n\n"
            "After careful consideration, we have decided not to move forward with your application "
            "at this stage. This was a competitive process and the decision was not an easy one; it "
            "does not take away from your skills and experience.\n\n"
            "We'd be glad to consider you for future roles that match your background, and we wish you "
            "the very best in your search.\n\n"
            "Best regards,\n"
            f"{company_name} Hiring Team"
        )
        return subject, body

    @staticmethod
    def send_rejection_email(candidate: dict, company_name: str, org: Optional[dict] = None, sender_name: Optional[str] = None) -> dict:
        """Send the post-interview rejection email to a SINGLE candidate. Only ever
        called from an explicit recruiter 'Reject' action on a completed interview."""
        email = (candidate.get("email") or "").strip()
        name = candidate.get("name") or "Candidate"
        if not email or "@" not in email:
            return {"sent": 0, "skipped": 1, "failed": 0, "errors": [f"{name}: no valid email"]}
        try:
            subject, body = EmailService.build_rejection_email(candidate, company_name)
            EmailService.send_email(email, subject, body, **EmailService.sender_for(org, sender_name))
            return {"sent": 1, "skipped": 0, "failed": 0, "errors": []}
        except Exception as exc:
            return {"sent": 0, "skipped": 0, "failed": 1, "errors": [f"{name} <{email}>: {exc}"]}

    @staticmethod
    def send_email(
        to_email: str, subject: str, body: str, *,
        from_name: Optional[str] = None, reply_to: Optional[str] = None,
    ) -> None:
        if not EmailService.is_configured():
            raise RuntimeError(
                "SMTP is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, and SMTP_FROM_EMAIL."
            )

        message = EmailMessage()
        message["From"] = formataddr((from_name, settings.SMTP_FROM_EMAIL)) if from_name else settings.SMTP_FROM_EMAIL
        message["To"] = to_email
        message["Subject"] = subject
        if reply_to and "@" in reply_to:
            message["Reply-To"] = reply_to
        message.set_content(body)

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)

    @staticmethod
    def send_bulk_shortlist_emails(candidates: Iterable[dict], company_name: str, org: Optional[dict] = None, sender_name: Optional[str] = None) -> dict:
        sent = 0
        skipped = 0
        failed = 0
        errors = []
        sent_ids = []
        sender = EmailService.sender_for(org, sender_name)

        for candidate in candidates:

            email = (candidate.get("email") or "").strip()
            name = candidate.get("name") or "Candidate"

            if not email or "@" not in email:
                skipped += 1
                continue

            try:
                subject, body = EmailService.build_shortlist_email(candidate, company_name)
                EmailService.send_email(email, subject, body, **sender)
                sent += 1
                if candidate.get("id"):
                    sent_ids.append(candidate["id"])

            except Exception as exc:
                failed += 1
                errors.append(f"{name} <{email}>: {str(exc)}")

        return {
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
            "errors": errors[:10],
            "sent_ids": sent_ids
        }

    @staticmethod
    async def send_password_reset_email(recipient_email: str, reset_link: str) -> bool:
        if not settings.SMTP_HOST:
            logger.warning(f"SMTP not configured. Skipping password reset email for {recipient_email}. Link: {reset_link}")
            return True
            
        try:
            subject = "Password Reset Request"
            body = f"""
Hello,

We received a request to reset your password. Click the link below to set a new password:

{reset_link}

If you did not request this, please ignore this email.

Best regards,
The {settings.APP_NAME} Team
            """
            
            EmailService.send_email(recipient_email, subject, body)
            logger.info(f"Successfully sent password reset email to {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send password reset email to {recipient_email}: {str(e)}")
            return False
