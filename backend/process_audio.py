import json
import os
import re
import subprocess
from datetime import datetime

import openpyxl
import requests
from dotenv import load_dotenv

# Load environment variables early, forcing override of existing session variables
load_dotenv(".env.local", override=True)
load_dotenv(override=True)


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _now_ts():
    return datetime.utcnow().isoformat() + "Z"


STRICT_MODE = _env_bool("STRICT_MODE", True)

OPENAI_API_KEY = (os.environ.get("OPENAI_API_KEY") or "").strip()
OPENAI_API_BASE = (os.environ.get("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
OPENAI_STT_MODEL = os.environ.get("OPENAI_STT_MODEL", "gpt-4o-transcribe")
OPENAI_RETRY_COUNT = int(_env_float("OPENAI_RETRY_COUNT", 3))

OPENROUTER_API_KEY = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
OPENROUTER_API_URL = (os.environ.get("OPENROUTER_API_URL") or "https://openrouter.ai/api/v1/chat/completions").rstrip("/")
OPENROUTER_ANALYSIS_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-31b-it")
OPENROUTER_HTTP_REFERER = os.environ.get("OPENROUTER_HTTP_REFERER", "http://localhost:8000")
OPENROUTER_TITLE = os.environ.get("OPENROUTER_TITLE", "Voice AI Dashboard")

print("--- HYBRID AUDIO PIPELINE CONFIG ---")
print(f"OpenAI STT model: {OPENAI_STT_MODEL}")
print(f"OpenRouter analysis model: {OPENROUTER_ANALYSIS_MODEL}")
OPENAI_ANALYSIS_MODEL = "gpt-4o"
print(f"OpenAI analysis model: {OPENAI_ANALYSIS_MODEL}")
print(f"OpenAI key present: {bool(OPENAI_API_KEY)}")
print(f"OpenRouter key present: {bool(OPENROUTER_API_KEY)}")

TRANSCRIPT_DIR = "transcripts"
RESULTS_DIR = "results"

EXCEL_FILE = os.path.join(RESULTS_DIR, "analytics_results.xlsx")
CONVERTED_EXCEL_FILE = os.path.join(RESULTS_DIR, "converted_calls.xlsx")
SALES_CRM_FILE = os.path.join(RESULTS_DIR, "sales_crm.xlsx")


def get_weekly_excel_file():
    now = datetime.utcnow()
    year, week_num, _ = now.isocalendar()
    return os.path.join(RESULTS_DIR, f"weekly_calls_{year}_W{week_num}.xlsx")


def get_weekly_sales_file():
    now = datetime.utcnow()
    year, week_num, _ = now.isocalendar()
    return os.path.join(RESULTS_DIR, f"weekly_sales_{year}_W{week_num}.xlsx")


def _extract_json_object(text):
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _normalize_whitespace(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def _split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _strip_transcript_noise(text):
    if not text:
        return ""

    noise_patterns = [
        r"^remember to watch our other .*",
        r"^remember to always be a good customer.*",
        r"^watch our other .*",
        r"^subscribe .*",
        r"^like and share .*",
        r"^role play videos?\.?$",
    ]

    kept = []
    for sentence in _split_sentences(text):
        lowered = sentence.lower()
        if any(re.match(pattern, lowered) for pattern in noise_patterns):
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


def _format_transcript_for_display(text):
    cleaned = _strip_transcript_noise(_normalize_whitespace(text))
    if not cleaned:
        return ""

    cleaned = re.sub(
        r"\b(Call center(?:,)? handling rude customers(?: role play)?\.?)",
        r"\n\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(Call number \w+[^.?!]*[.?!])",
        r"\n\n\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(Call center agent and customer\.?)",
        r"\n\1\n",
        cleaned,
        flags=re.IGNORECASE,
    )

    speaker_starts = [
        "Thank you for calling",
        "Good afternoon",
        "Good morning",
        "Good evening",
        "Finally",
        "I'm very sorry",
        "I completely understand",
        "I understand",
        "May I",
        "Oh, fine",
        "This is",
        "Whatever",
        "Again, I am sorry",
        "Then why do you",
        "No, I'm done",
        "I do understand",
        "Yeah,",
        "Well,",
    ]
    for marker in speaker_starts:
        cleaned = re.sub(rf"\s+({re.escape(marker)})", r"\n\1", cleaned)

    lines = [line.strip(" -") for line in cleaned.splitlines() if line.strip()]
    return "\n".join(lines)


def safe_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text or "")
    return path


def write_excel(path, row):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    new_file = not os.path.exists(path)

    workbook = openpyxl.Workbook() if new_file else openpyxl.load_workbook(path)
    sheet = workbook.active

    if new_file:
        sheet.append(list(row.keys()))

    sheet.append(list(row.values()))
    workbook.save(path)


def _openai_headers():
    return {"Authorization": f"Bearer {OPENAI_API_KEY}"}


def _describe_openai_http_error(response):
    body = (response.text or "").strip()
    if response.status_code == 429:
        lowered = body.lower()
        if "insufficient_quota" in lowered or "exceeded your current quota" in lowered:
            return f"OpenAI quota exceeded. {body[:500]}"
        return f"OpenAI rate limit reached. {body[:500]}"
    return f"{response.status_code} {response.reason}: {body[:500]}"


def openai_transcribe_audio(audio_path):
    if not OPENAI_API_KEY:
        return "", None

    try:
        for attempt in range(1, OPENAI_RETRY_COUNT + 1):
            with open(audio_path, "rb") as audio_file:
                files = {"file": audio_file}
                data = {
                    "model": OPENAI_STT_MODEL,
                    "response_format": "json",
                }
                print(f"Transcribing via OpenAI ({OPENAI_STT_MODEL})... attempt {attempt}/{OPENAI_RETRY_COUNT}")
                response = requests.post(
                    f"{OPENAI_API_BASE}/audio/transcriptions",
                    headers=_openai_headers(),
                    files=files,
                    data=data,
                    timeout=300,
                )

            if response.ok:
                payload = response.json()
                text = payload.get("text") or ""
                return _format_transcript_for_display(text), OPENAI_STT_MODEL

            error_message = _describe_openai_http_error(response)
            print(f"Transcription attempt failed: {error_message}")
            if response.status_code == 429 and attempt < OPENAI_RETRY_COUNT:
                continue
            raise RuntimeError(error_message)
    except Exception as exc:
        print(f"Transcription failed: {exc}")
        return "", None


def _openrouter_headers():
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_HTTP_REFERER,
        "X-Title": OPENROUTER_TITLE,
    }

def openai_analyze_transcript(transcript):
    if not transcript or not OPENAI_API_KEY:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Analyze this transcript and return a valid JSON object matching the requested schema.\n\nTranscript:\n{transcript}"
    # Using a simplified version for now to match OpenRouter's current schema in this file
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "Return only a valid JSON object that matches the requested schema."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    try:
        print("Analyzing via OpenAI (gpt-4o)...")
        res = requests.post(url, headers=headers, json=payload, timeout=90)
        res.raise_for_status()
        return _extract_json_object(res.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"OpenAI analysis failed: {e}")
        return None


def openrouter_analyze_transcript(transcript):
    if not transcript or not OPENROUTER_API_KEY:
        return None

    prompt = f"""
Analyze this transcript and return a valid JSON object:
{{
  "refined_transcript": "string",
  "summary": "string",
  "sentiment": "positive|neutral|negative",
  "sentiment_confidence": 0.0,
  "sentiment_reason": "string",
  "emotion": "string",
  "intents": ["string"],
  "response_text": "string"
}}

Rules:
- refined_transcript: rewrite the transcript as a clean 2-person conversation with speaker labels on separate lines using only `Agent:` and `Customer:`. Preserve meaning, fix obvious transcription mistakes, and do not invent facts.
- The refined transcript must read like a real two-way conversation, not one paragraph.
- summary: concise, factual summary of the call in 1 or 2 sentences only.
- summary must explicitly describe both sides of the conversation: what the customer/lead said and how the agent responded.
- sentiment: must be exactly one of positive, neutral, or negative.
- sentiment_confidence: decimal from 0 to 1.
- sentiment_reason: one short sentence.
- emotion: primary customer emotion.
- intents: 1 to 5 short snake_case tags.
- response_text: short AI response based on the call, 2 to 4 sentences, plain text only.
- If the customer reports a complaint, frustration, billing problem, fraud, mismatch, delay, cancellation, or asks for urgent help, sentiment should usually be negative.
- Use neutral only when the customer is calm, informational, and not clearly satisfied or dissatisfied.
- Use positive only when the customer is clearly satisfied, appreciative, or the issue is resolved successfully.

Transcript:
{transcript}
"""

    payload = {
        "model": OPENROUTER_ANALYSIS_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Return only a valid JSON object that matches the requested schema.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    try:
        print(f"Analyzing via OpenRouter ({OPENROUTER_ANALYSIS_MODEL})...")
        response = requests.post(
            OPENROUTER_API_URL,
            headers=_openrouter_headers(),
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"].get("content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return _extract_json_object(content)
    except Exception as exc:
        print(f"OpenRouter analysis failed: {exc}")
        return None


def _normalize_sentiment_label(value):
    label = str(value or "").strip().lower()
    if "pos" in label:
        return "positive"
    if "neg" in label:
        return "negative"
    return "neutral"


def _sanitize_tag(tag):
    clean = re.sub(r"[^a-z0-9_]+", "_", str(tag or "").strip().lower())
    return clean.strip("_")


def _summarize_transcript_fallback(transcript):
    sentences = _split_sentences(_normalize_whitespace(transcript))
    if not sentences:
        return "Summary not available."
    return " ".join(sentences[:2]).strip()


def _format_two_speaker_transcript(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return ""

    normalized_lines = []
    for line in lines:
        if re.match(r"^(agent|customer)\s*:", line, flags=re.IGNORECASE):
            speaker, content = line.split(":", 1)
            speaker = "Agent" if speaker.strip().lower().startswith("agent") else "Customer"
            content = _normalize_whitespace(content)
            if content:
                normalized_lines.append(f"{speaker}: {content}")
        else:
            normalized_lines.append(_normalize_whitespace(line))

    if any(line.startswith("Agent:") or line.startswith("Customer:") for line in normalized_lines):
        rebuilt = []
        current_speaker = None
        buffer = []

        def flush_buffer():
            if current_speaker and buffer:
                rebuilt.append(f"{current_speaker}: {' '.join(buffer).strip()}")

        for line in normalized_lines:
            if line.startswith("Agent:") or line.startswith("Customer:"):
                flush_buffer()
                current_speaker, content = line.split(":", 1)
                buffer = [content.strip()] if content.strip() else []
            else:
                if not current_speaker:
                    current_speaker = "Agent"
                buffer.append(line)
        flush_buffer()
        return "\n".join(item for item in rebuilt if item.strip())

    sentences = _split_sentences(" ".join(normalized_lines))
    rebuilt = []
    speaker = "Agent"
    for sentence in sentences:
        rebuilt.append(f"{speaker}: {sentence}")
        speaker = "Customer" if speaker == "Agent" else "Agent"
    return "\n".join(rebuilt)


def _infer_sentiment_from_text(transcript, emotion, reason):
    combined = " ".join([transcript or "", emotion or "", reason or ""]).lower()

    negative_markers = [
        "angry", "frustrated", "upset", "complaint", "issue", "problem", "refund",
        "cancel", "delay", "overcharge", "unauthorized", "stolen", "bad experience",
        "concerned", "not working", "wrong", "mismatch", "urgent help",
    ]
    positive_markers = [
        "thank you", "thanks", "resolved", "happy", "great", "excellent",
        "appreciate", "satisfied", "confirmed", "helpful", "glad",
    ]

    negative_score = sum(marker in combined for marker in negative_markers)
    positive_score = sum(marker in combined for marker in positive_markers)

    if negative_score > positive_score:
        return "negative"
    if positive_score > negative_score:
        return "positive"
    return "neutral"


def _finalize_analysis(transcript, analysis):
    analysis = analysis or {}

    refined_transcript = _format_two_speaker_transcript(
        analysis.get("refined_transcript", "") or transcript
    )
    summary = _normalize_whitespace(analysis.get("summary", ""))
    if not summary:
        summary = _summarize_transcript_fallback(refined_transcript or transcript)

    sentiment_reason = _normalize_whitespace(analysis.get("sentiment_reason", ""))
    emotion = _normalize_whitespace(analysis.get("emotion", "")) or "neutral"
    response_text = _normalize_whitespace(analysis.get("response_text", ""))

    intents = analysis.get("intents") or []
    if not isinstance(intents, list):
        intents = []
    intents = [_sanitize_tag(item) for item in intents if _sanitize_tag(item)]

    try:
        sentiment_confidence = float(analysis.get("sentiment_confidence", 0.0))
    except Exception:
        sentiment_confidence = 0.0
    sentiment_confidence = max(0.0, min(1.0, sentiment_confidence))

    model_sentiment = _normalize_sentiment_label(analysis.get("sentiment"))
    inferred_sentiment = _infer_sentiment_from_text(transcript, emotion, sentiment_reason)

    if model_sentiment == "neutral" and inferred_sentiment in {"negative", "positive"}:
        sentiment = inferred_sentiment
        sentiment_confidence = max(sentiment_confidence, 0.7)
    else:
        sentiment = model_sentiment

    if not sentiment_reason:
        if sentiment == "negative":
            sentiment_reason = "The customer is describing a problem or dissatisfaction and asking for help."
        elif sentiment == "positive":
            sentiment_reason = "The customer expresses satisfaction, appreciation, or a successful resolution."
        else:
            sentiment_reason = "The customer communicates in a calm and informational manner without strong positive or negative language."

    return {
        "refined_transcript": refined_transcript or transcript,
        "summary": summary,
        "sentiment": sentiment,
        "sentiment_confidence": sentiment_confidence,
        "sentiment_reason": sentiment_reason,
        "emotion": emotion,
        "intents": intents,
        "response_text": response_text,
    }


def transcribe_file(filepath):
    transcript, _ = openai_transcribe_audio(filepath)
    return transcript


def process_uploaded_audio(audio_path):
    filename = os.path.basename(audio_path)
    base = os.path.splitext(filename)[0]

    transcript, transcript_provider = openai_transcribe_audio(audio_path)
    if not transcript and STRICT_MODE:
        raise RuntimeError("Transcription failed. Check OPENAI_API_KEY and OPENAI_STT_MODEL.")
    transcript_provider = transcript_provider or "failed"

    analysis = None
    if OPENAI_API_KEY:
        analysis = openai_analyze_transcript(transcript)
        analysis_provider = "gpt-4o" if analysis else "failed"
    
    if not analysis:
        analysis = openrouter_analyze_transcript(transcript)
        analysis_provider = OPENROUTER_ANALYSIS_MODEL if analysis else "failed"

    if not analysis and STRICT_MODE:
        raise RuntimeError("AI analysis failed on both OpenAI and OpenRouter. Check API keys.")
    
    if not analysis:
        analysis = {
            "refined_transcript": transcript,
            "summary": "AI analysis unavailable",
            "sentiment": "neutral",
            "sentiment_confidence": 0.0,
            "sentiment_reason": "Analysis unavailable.",
            "emotion": "neutral",
            "intents": [],
            "response_text": "",
        }
        analysis_provider = "failed"
    else:
        analysis_provider = OPENROUTER_ANALYSIS_MODEL

    analysis = _finalize_analysis(transcript, analysis)

    intents = analysis["intents"]
    refined_transcript = analysis["refined_transcript"]
    sentiment_confidence = analysis["sentiment_confidence"]
    summary = analysis["summary"]
    sentiment = analysis["sentiment"]
    sentiment_reason = analysis["sentiment_reason"]
    emotion = analysis["emotion"]
    response_text = analysis["response_text"]

    transcript_path = safe_write(os.path.join(TRANSCRIPT_DIR, base + ".txt"), refined_transcript)

    conversion_words = ["purchase", "order", "buy", "confirmed"]
    is_converted = any(word in (transcript or "").lower() for word in conversion_words)
    is_sales_call = any(intent.endswith("_sales") for intent in intents)

    row = {
        "file": filename,
        "call_id": base,
        "processed_at": _now_ts(),
        "summary": summary,
        "sentiment": sentiment,
        "sentiment_confidence": sentiment_confidence,
        "sentiment_reason": sentiment_reason,
        "intents": json.dumps(intents),
        "response_text": response_text,
        "converted": is_converted,
    }

    write_excel(EXCEL_FILE, row)
    if is_converted:
        write_excel(CONVERTED_EXCEL_FILE, row)
    if is_sales_call:
        write_excel(SALES_CRM_FILE, row)

    write_excel(get_weekly_excel_file(), row)
    if is_sales_call:
        write_excel(get_weekly_sales_file(), row)

    return {
        "call_id": base,
        "transcript": refined_transcript,
        "raw_transcript": transcript,
        "refined_transcript": refined_transcript,
        "transcript_provider": transcript_provider,
        "transcript_refined": True,
        "transcript_refiner": analysis_provider,
        "summary": summary,
        "sentiment": sentiment,
        "sentiment_confidence": max(0.0, min(1.0, sentiment_confidence)),
        "sentiment_reason": sentiment_reason,
        "emotion": emotion,
        "intents": intents,
        "analysis_provider": analysis_provider,
        "response_text": response_text,
        "response_audio_path": "",
        "response_audio_error": "",
        "transcript_path": transcript_path,
        "converted": is_converted,
        "sales_call": is_sales_call,
    }


if __name__ == "__main__":
    print("process_audio.py ready")
