"""Interview integrity ("proctoring") analysis.

Advisory only — like the AI recommendation, this produces flags for a recruiter
to review, never a verdict. v1 uses signals available WITHOUT extra ML infra:

  * session provenance  -> link opened from multiple IPs / devices
  * client telemetry    -> tab-focus loss, paste, fullscreen exits, answer latency
  * answer shape        -> typed-not-spoken answers
  * transcript LLM pass -> "read-aloud vs spoken", AI-assistance likelihood,
                           follow-up handling, consistency

Deferred to v2 (needs models the current host can't run):
  face match to a reference photo, gaze estimation, voice fingerprinting, lip-sync.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.services.interview_prompt_engine import _chat_json, FAIRNESS_RULES

logger = logging.getLogger(__name__)

# Concern points added per flag severity; the total is capped at 100.
_SEV_WEIGHT = {"low": 8, "medium": 22, "high": 45}

_FOCUS_LOSS_MS = 4000     # per interview, "meaningfully away from the tab"
_LATENCY_MS = 12000       # a pause this long before answering is notable


def _level(score: int, flags: List[dict], is_l2: bool = False) -> str:
    highs = sum(1 for f in flags if f["severity"] == "high")
    serious = sum(1 for f in flags if f["severity"] in ("high", "medium"))
    
    if is_l2:
        # Zero tolerance in L2: any single high flag or multiple serious flags = high risk
        if score >= 40 or highs >= 1 or serious >= 2:
            return "high_risk"
        if serious >= 1 or score >= 10:
            return "review"
        return "clean"
        
    if score >= 55 or (highs >= 1 and serious >= 2):
        return "high_risk"
    if serious >= 1 or score >= 20:
        return "review"
    return "clean"


def _flag(code: str, severity: str, title: str, detail: str) -> dict:
    return {"code": code, "severity": severity, "title": title, "detail": detail}


async def analyze(interview: dict, *, run_llm: bool = True) -> Dict[str, Any]:
    is_l2 = interview.get("interview_type") == "ai_l2_technical"
    answers = interview.get("answers") or []
    meta = interview.get("session_meta") or []
    flags: List[dict] = []

    # Interview never actually taken — say so plainly instead of a misleading "Clean".
    real_answers = [
        a for a in answers
        if (a.get("answer_text") or "").strip()
        and (a.get("answer_text") or "").strip() != "(no audible answer was captured)"
    ]
    if not real_answers:
        return {
            "score": 0,
            "level": "review",
            "flags": [_flag(
                "not_attempted", "medium", "Interview not attempted",
                "The candidate ended the interview without answering any questions. There is nothing to "
                "check for integrity, and nothing to evaluate.",
            )],
            "signals": {"answered": 0},
            "analyzed_at": datetime.utcnow().isoformat(),
            "version": "integrity-v1",
        }

    # ------------------------------------------------------------------
    # 1. Session provenance
    # ------------------------------------------------------------------
    ips = sorted({str(m.get("ip")) for m in meta if m.get("ip")})
    uas = sorted({str(m.get("ua")) for m in meta if m.get("ua")})
    if len(ips) >= 3:
        flags.append(_flag(
            "multi_ip", "high", "Link opened from several networks",
            f"{len(ips)} different IP addresses were seen during this interview: {', '.join(ips[:6])}.",
        ))
    elif len(ips) == 2:
        flags.append(_flag(
            "multi_ip", "medium", "Link opened from two networks",
            f"IP addresses: {', '.join(ips)}. Could be a network switch mid-interview, or the link was shared.",
        ))
    if len(uas) >= 2:
        flags.append(_flag(
            "multi_device", "medium", "More than one device or browser",
            f"{len(uas)} distinct browser signatures were used on this interview link.",
        ))

    verify_fails = int(interview.get("verification_attempts") or 0)
    if verify_fails >= 2:
        flags.append(_flag(
            "email_verify_failed", "medium" if verify_fails < 4 else "high",
            "Failed the email check before starting",
            f"The email confirmation was entered incorrectly {verify_fails} time(s) before the interview started "
            "— the person taking it may not be the shortlisted candidate.",
        ))

    # ------------------------------------------------------------------
    # 2. Client telemetry (browser, best-effort)
    # ------------------------------------------------------------------
    focus_events = sum(a.get("focus_lost_count") or 0 for a in answers)
    focus_ms = sum(a.get("focus_lost_ms") or 0 for a in answers)
    pastes = sum(a.get("paste_count") or 0 for a in answers)
    fs_exits = sum(a.get("fullscreen_exits") or 0 for a in answers)
    long_pauses = sum(1 for a in answers if (a.get("time_to_first_answer_ms") or 0) >= _LATENCY_MS)
    typed = sum(
        1 for a in answers
        if a.get("typed_only") or (not a.get("audio_ref") and not a.get("video_ref") and a.get("answer_text"))
    )

    focus_threshold = 2000 if is_l2 else _FOCUS_LOSS_MS
    if focus_events and focus_ms >= focus_threshold:
        if is_l2:
            sev = "high" if (focus_ms >= 10000 or focus_events >= 2) else "medium"
        else:
            sev = "high" if (focus_ms >= 20000 or focus_events >= 5) else "medium"
            
        flags.append(_flag(
            "tab_switching", sev, "Left the interview tab while answering",
            f"Switched away {focus_events}× for about {round(focus_ms / 1000)}s total during answers — "
            "a common sign of looking answers up elsewhere.",
        ))
    if pastes:
        flags.append(_flag(
            "paste", "high" if is_l2 else "medium", "Pasted text during the interview",
            f"{pastes} paste event(s) were detected on the interview page.",
        ))
    if fs_exits:
        flags.append(_flag(
            "fullscreen_exit", "medium" if is_l2 else "low", "Exited full screen",
            f"Left full-screen mode {fs_exits}× during the interview.",
        ))
        
    latency_threshold = 2 if is_l2 else 3
    if long_pauses >= (1 if is_l2 else 2):
        flags.append(_flag(
            "answer_latency", "high" if (is_l2 and long_pauses >= latency_threshold) else ("medium" if long_pauses >= latency_threshold else "low"), "Long pauses before answering",
            f"{long_pauses} answers began only after a pause of 12s or more.",
        ))
        
    if typed and answers and typed >= max(1, len(answers) // (3 if is_l2 else 2)):
        flags.append(_flag(
            "typed_answers", "medium" if is_l2 else "low", "Answers typed, not spoken",
            f"{typed} of {len(answers)} answers were submitted as text — there is no audio to verify the speaker.",
        ))

    # ------------------------------------------------------------------
    # 3. Transcript LLM pass
    # ------------------------------------------------------------------
    llm: Dict[str, Any] = {}
    if run_llm:
        try:
            llm = await _llm_transcript_pass(interview.get("transcript") or [])
        except Exception as exc:
            logger.warning(f"integrity LLM pass failed for {interview.get('id')}: {exc}")

    aa = llm.get("ai_assistance_likelihood")
    if isinstance(aa, (int, float)):
        if aa >= 0.7:
            flags.append(_flag(
                "ai_generated_text", "high", "Answers read like AI-generated text",
                llm.get("ai_assistance_reason")
                or "Delivery was consistently over-structured and generic across answers, with little hesitation.",
            ))
        elif aa >= 0.45:
            flags.append(_flag(
                "ai_generated_text", "medium", "Some answers may be AI-assisted",
                llm.get("ai_assistance_reason")
                or "A few answers were unusually polished and complete for spoken delivery.",
            ))
    if llm.get("follow_up_handling") in ("weak", "evasive"):
        flags.append(_flag(
            "follow_up_handling", "medium", "Struggled with follow-up questions",
            llm.get("follow_up_reason")
            or "Follow-ups asking for specifics were answered generically or deflected — consistent with rehearsed "
               "or assisted answers.",
        ))
    if llm.get("consistency_note"):
        flags.append(_flag(
            "consistency", "low", "Answer style shifts during the interview",
            str(llm["consistency_note"]),
        ))

    score = min(100, sum(_SEV_WEIGHT.get(f["severity"], 0) for f in flags))
    return {
        "score": score,
        "level": _level(score, flags, is_l2=is_l2),
        "flags": flags,
        "signals": {
            "distinct_ips": ips,
            "distinct_devices": len(uas),
            "email_verify_failures": verify_fails,
            "focus_lost_count": focus_events,
            "focus_lost_ms": focus_ms,
            "paste_count": pastes,
            "fullscreen_exits": fs_exits,
            "long_pause_answers": long_pauses,
            "typed_answers": typed,
            "ai_assistance_likelihood": aa if isinstance(aa, (int, float)) else None,
        },
        "analyzed_at": datetime.utcnow().isoformat(),
        "version": "integrity-v1",
    }


async def _llm_transcript_pass(transcript: List[dict]) -> Dict[str, Any]:
    if not transcript:
        return {}
    lines = []
    for t in transcript:
        role = "Interviewer" if t.get("role") == "ai" else "Candidate"
        lines.append(f"{role}: {t.get('text', '')}")
    body = "\n".join(lines)[:12000]

    system = (
        "You are an interview-integrity analyst. Judge ONLY whether the candidate's answers were "
        "genuinely spoken/improvised, or read aloud from an AI tool or a prepared script. "
        + FAIRNESS_RULES +
        "\n\nWHAT IS NOT SUSPICIOUS (never penalise): non-native English, accents, nervousness, "
        "short or simple answers, small vocabulary, going off-topic, being wrong.\n\n"
        "GENUINE SPOKEN answers almost always contain SOME of: filler words (um, uh, like, you know, "
        "I mean), false starts, self-correction, contractions, unfinished sentences, tangents, "
        "concrete personal detail ('at my last internship', 'the bug was in the payment webhook'), "
        "and uneven structure.\n\n"
        "READ-ALOUD / AI-ASSISTED answers instead show: clean written prose (topic sentence -> "
        "parallel list of points -> wrap-up), NO disfluencies at all, textbook phrasing, exhaustive "
        "coverage that is implausible to produce live, and no first-person specifics. The near-total "
        "ABSENCE of any spoken markers across THREE OR MORE answers is the single strongest signal.\n\n"
        "Scale for ai_assistance_likelihood: 0.0-0.2 clearly spoken; 0.3-0.45 mostly spoken with 1-2 "
        "suspiciously clean answers; 0.5-0.7 most answers read like written text with no disfluencies; "
        "0.75-1.0 every substantive answer is polished written prose with zero spoken markers."
    )
    user = f"""INTERVIEW TRANSCRIPT
{body}

For each substantive candidate answer, silently note whether it contains ANY spoken-language markers.
Then score the interview as a whole.

Return STRICT JSON:
{{
  "spoken_markers_seen": "none | few | many",
  "ai_assistance_likelihood": 0.0-1.0,
  "ai_assistance_reason": "one sentence citing the concrete pattern, or empty string",
  "follow_up_handling": "strong | adequate | weak | evasive | none",
  "follow_up_reason": "one sentence, or empty string",
  "consistency_note": "one sentence ONLY if answer style shifts markedly mid-interview, else empty string"
}}
"""
    data = await _chat_json(system, user, temperature=0.0, timeout=60.0)
    try:
        data["ai_assistance_likelihood"] = float(data.get("ai_assistance_likelihood"))
    except (TypeError, ValueError):
        data["ai_assistance_likelihood"] = None
    return data
