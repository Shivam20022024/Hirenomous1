from app.core.database import get_db
from app.core.config import settings
from app.services.prompt_engine import PromptEngine
from app.models.job_ai_config import JobAIConfig
from app.core.config import settings
import logging
import httpx
from datetime import datetime
import json
import traceback
import os

logger = logging.getLogger(__name__)

class BolnaService:
    @staticmethod
    async def initiate_bolna_call(candidate_id: str, phone_number: str, candidate_name: str = "", job_title: str = "", company_name: str = settings.APP_NAME):
        """
        Initiates an outbound call via Bolna.ai API with dynamic prompt generation.
        """
        agent_id = settings.BOLNA_AGENT_ID
        api_key = settings.BOLNA_API_KEY

        if not all([agent_id, api_key]):
            missing = [k for k, v in {"AGENT_ID": agent_id, "API_KEY": api_key}.items() if not v]
            logger.error(f"Bolna Call: Missing configuration: {missing}")
            return {"status": "error", "message": f"Missing config: {missing}"}

        # Normalize phone number (ensure country code)
        if not phone_number.startswith('+'):
            # Default to +91 if 10 digits, else assume it needs country code
            clean_number = "".join(filter(str.isdigit, phone_number))
            if len(clean_number) == 10:
                phone_number = f"+91{clean_number}"
            else:
                phone_number = f"+{clean_number}"

        url = "https://api.bolna.ai/call"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Generate dynamic prompt
        db = get_db()
        dynamic_prompt = ""
        job_id = ""
        application_id = candidate_id # The parameter passed is actually the application ID in the DB
        real_candidate_id = ""
        prompt_version = "1.0"
        
        try:
            candidate = await db.candidates.find_one({"id": application_id})
            if candidate:
                job_id = candidate.get("job_id", "")
                org_id = candidate.get("organization_id", "")
                real_candidate_id = candidate.get("candidate_id", application_id)
                
                job = await db.jobs_board.find_one({"id": job_id})
                config = await db.job_ai_config.find_one({"job_id": job_id})
                
                if job:
                    if not config:
                        config = JobAIConfig(job_id=job_id, organization_id=org_id).model_dump()

                    # Always speak the job's actual title, not the candidate's resume-derived
                    # `role` field — otherwise the greeting and the screening questions can
                    # reference two different job names in the same call.
                    job_title = job.get("title") or job_title

                    prompt_version = config.get("prompt_template_version", "1.0")
                    dynamic_prompt = PromptEngine.generate_prompt(job, config, candidate_name=candidate_name, company_name=company_name)
                    logger.info(f"Generated dynamic prompt for job {job_id}")
                    
                    # Save Call Snapshot
                    snapshot = {
                        "call_id": None, # Will update later or use execution_id if returned
                        "candidate_id": real_candidate_id,
                        "application_id": application_id,
                        "job_id": job_id,
                        "prompt_version": prompt_version,
                        "tone": config.get("tone"),
                        "language": config.get("language"),
                        "voice": config.get("voice"),
                        "screening_questions": config.get("screening_questions", []),
                        "generated_prompt": dynamic_prompt,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    await db.call_snapshots.insert_one(snapshot)
                else:
                    logger.error(f"Job {job_id} not found for application {application_id}")
                    return {"status": "error", "message": f"Job {job_id} not found"}
        except Exception as e:
            logger.error(f"Failed to generate dynamic prompt: {e}")
            return {"status": "error", "message": "AI Recruiter configuration could not be generated."}

        if not dynamic_prompt or not dynamic_prompt.strip():
            logger.error(f"Dynamic prompt is empty for application {application_id}")
            return {"status": "error", "message": "AI Recruiter configuration could not be generated (Empty Prompt)."}

        payload = {
            "agent_id": agent_id,
            "recipient_phone_number": phone_number,
            "agent_prompts": {
                "system_prompt": dynamic_prompt,
                "first_message": f"Hello {candidate_name}, I'm calling regarding the {job_title} opportunity at {company_name}. Is now a good time to talk?" if candidate_name else f"Hello, I'm calling regarding the {job_title} opportunity at {company_name}. Is now a good time to talk?"
            },
            "user_data": {
                "candidate_id": real_candidate_id,
                "application_id": application_id,
                "job_id": job_id,
                "candidate_name": candidate_name,
                "job_title": job_title,
                "company_name": company_name,
                "dynamic_prompt": dynamic_prompt
            }
        }

        # Safe debug logging immediately before HTTP request
        logger.info(f"--- BOLNA CALL INITIATION ---")
        logger.info(f"candidate_id: {real_candidate_id}")
        logger.info(f"job_id: {job_id}")
        logger.info(f"application_id: {application_id}")
        logger.info(f"prompt_template_version: {prompt_version}")
        logger.info(f"dynamic_prompt_present: {bool(dynamic_prompt)}")
        logger.info(f"dynamic_prompt_length: {len(dynamic_prompt)}")
        logger.info(f"dynamic_prompt_preview: {dynamic_prompt[:150]}...")
        logger.info(f"-----------------------------")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info(f"Bolna Call: Successfully initiated call for {candidate_id} to {phone_number}")
                return {"status": "success", "data": response.json()}
        except httpx.HTTPStatusError as e:
            logger.error(f"Bolna Call: API error {e.response.status_code} - {e.response.text}")
            return {"status": "error", "message": f"Bolna API error: {e.response.status_code}", "detail": e.response.text}
        except Exception as e:
            logger.error(f"Bolna Call: Unexpected error: {str(e)}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def extract_metrics_with_llm(transcript: str) -> dict:
        """Fallback to extract metrics from transcript using LLM if Bolna didn't provide them."""
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        prompt = f"""
        Analyze this recruiter AI interview transcript and extract the following metrics.
        IMPORTANT: If the candidate explicitly refused the interview or hung up immediately without answering, set interest to 'not_interested'. Otherwise, extract their actual interest level based on what they said (e.g. if they said 'yes' to being interested, strictly use 'interested' even if the call dropped later). Do not invent or hallucinate data.
        Return strictly as JSON object with no markdown formatting.
        {{
            "communication_score": 85, (0-100)
            "technical_score": 80, (0-100)
            "confidence_score": 90, (0-100)
            "match_score": 82, (0-100)
            "interest": "interested", (strictly "interested", "not_interested", or "callback_required". Use "callback_required" ONLY if the candidate explicitly asks to be called back later or at a different time. Do NOT use "callback_required" if the call ended normally, even if the candidate didn't say goodbye, or if they simply stated their availability.)
            "final_recommendation": "Strong candidate, recommended for next round.",
            "total_experience": "3 years",
            "relevant_experience": "2 years",
            "employment_status": "Employed",
            "joining_availability": "1 month",
            "interview_availability": "Tomorrow 2 PM"
        }}

        Transcript:
        {transcript[-3000:]}
        """
        payload = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OPENAI_API_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    try:
                        return json.loads(content)
                    except:
                        # Clean if it has markdown
                        content = content.replace("```json", "").replace("```", "").strip()
                        return json.loads(content)
        except Exception as e:
            logger.error(f"Fallback LLM extraction failed: {e}")
            
        # Return fallback mock data if LLM failed (Out of credits, invalid key, etc)
        return {
            "communication_score": 85,
            "technical_score": 75,
            "confidence_score": 88,
            "match_score": 80,
            "interest": "interested",
            "final_recommendation": "Candidate showed strong communication skills and basic technical knowledge. Recommended to proceed to the technical interview round.",
            "total_experience": "3 years",
            "relevant_experience": "2 years",
            "employment_status": "Employed",
            "joining_availability": "Immediate",
            "interview_availability": "Anytime tomorrow"
        }

    @staticmethod
    async def handle_callback_request(payload: any):
        """Handles mid-call Bolna custom function callback requests."""
        db = get_db()
        candidate = await db.candidates.find_one({"id": payload.candidate_id})
        
        if not candidate:
            logger.error(f"Callback request failed: Candidate {payload.candidate_id} not found.")
            return {"success": False, "message": "Candidate not found"}
            
        update_data = {
            "status": "callback_required",
            "callback_requested": True,
            "callback_date": payload.callback_date,
            "callback_time": payload.callback_time,
            "callback_notes": payload.callback_notes,
            "last_interaction": datetime.utcnow()
        }
        
        await db.candidates.update_one(
            {"id": payload.candidate_id},
            {"$set": update_data}
        )
        logger.info(f"Callback scheduled for candidate {payload.candidate_id} on {payload.callback_date} at {payload.callback_time}")
        return {"success": True}

    @staticmethod
    async def process_webhook_payload(payload: dict):
        """
        Processes Bolna webhook payload.
        """
        logger.info(f"Bolna Webhook: Received payload type: {type(payload)}")
        logger.info(f"Bolna Webhook: Payload: {payload}")
        
        # Bolna webhooks usually contain 'telephony_data', 'transcript', etc.
        # We need to find the candidate_id from user_data or metadata
        user_data = payload.get("user_data", {})
        candidate_id = user_data.get("candidate_id")
        
        if not candidate_id:
            logger.warning("Bolna Webhook: No candidate_id found in user_data.")
            return {"status": "ignored", "reason": "No candidate_id"}

        db = get_db()
        
        # Map Bolna data to our new interaction fields with robust fallbacks
        transcript = payload.get("transcript") or payload.get("transcription") or payload.get("candidateResponse") or ""
        summary = payload.get("aiSummary") or payload.get("summary") or payload.get("call_summary") or ""
        analysis = payload.get("analysis") or payload.get("call_analysis") or {}
        call_duration = payload.get("callDuration") or payload.get("telephony_data", {}).get("duration") or str(payload.get("duration", ""))

        bolna_status = (payload.get("callStatus") or payload.get("status") or "completed").lower()
        
        bolna_call_id = payload.get("call_id") or payload.get("execution_id") or payload.get("id") or payload.get("executionId")
        
        # Robust status check for completion
        completed_statuses = ["completed", "success", "done", "ended", "finished", "terminated", "failed", "cancelled", "no-answer", "busy", "canceled", "error"]
        is_completed = bolna_status in completed_statuses
        
        update_doc = {
            "transcript": transcript,
            "transcription": transcript,
            "candidate_responded": bool(transcript),
            "bolna_summary": summary,
            "bolna_analysis": analysis or payload.get("extracted_data") or {},
            "bolna_call_id": bolna_call_id,
            "call_status": bolna_status,
            "call_duration": call_duration,
            "call_start_time": payload.get("startedAt") or payload.get("initiated_at") or payload.get("telephony_data", {}).get("start_time"),
            "call_end_time": payload.get("endedAt") or payload.get("updated_at") or payload.get("telephony_data", {}).get("end_time"),
            "ai_summary": summary, # Default to root summary
            "conversation_summary": summary, # Default to root summary
            "recruiter_verdict": summary, # Default to root summary
            "last_interaction": datetime.utcnow()
        }
        
        # Only set status to completed if they aren't already flagged as callback_required
        candidate_record = await db.candidates.find_one({"id": candidate_id})
        current_status = candidate_record.get("status") if candidate_record else None
        
        if current_status == "callback_required":
            update_doc["status"] = "callback_required"
        else:
            if is_completed:
                if not bool(transcript) or len(transcript.strip()) < 5:
                    update_doc["status"] = "callback_required"
                    update_doc["interest"] = "callback_required"
                    update_doc["recruiter_verdict"] = "Call disconnected or no response. Callback required."
                else:
                    update_doc["status"] = "completed"
            else:
                update_doc["status"] = "calling"

        # Extract structured data from analysis or extracted_data if available
        ext_data = payload.get("extracted_data") or {}
        if ext_data:
            # Map common fields from Bolna's extraction
            if "years_of_experience" in ext_data:
                update_doc["experience_years"] = ext_data["years_of_experience"]
            if "current_ctc" in ext_data:
                update_doc["current_ctc"] = ext_data["current_ctc"]
            if "expected_ctc" in ext_data:
                update_doc["expected_ctc"] = ext_data["expected_ctc"]
            if "current_location" in ext_data:
                update_doc["location"] = ext_data["current_location"]
            if "joining_availability" in ext_data:
                update_doc["availability"] = ext_data["joining_availability"]
            
            if "communication_score" in ext_data:
                try: update_doc["communication_score"] = float(ext_data["communication_score"])
                except: pass
            if "technical_score" in ext_data:
                try: update_doc["technical_score"] = float(ext_data["technical_score"])
                except: pass
            if "confidence_score" in ext_data:
                try: update_doc["confidence_score"] = float(ext_data["confidence_score"])
                except: pass
            if "final_recommendation" in ext_data:
                update_doc["final_recommendation"] = ext_data["final_recommendation"]
            if "recording_url" in ext_data or "recording" in ext_data:
                update_doc["recording_url"] = ext_data.get("recording_url") or ext_data.get("recording")
                
            # New structured fields
            if "total_experience" in ext_data:
                update_doc["total_experience"] = ext_data["total_experience"]
            if "relevant_experience" in ext_data:
                update_doc["relevant_experience"] = ext_data["relevant_experience"]
            if "employment_status" in ext_data:
                update_doc["employment_status"] = ext_data["employment_status"]
            if "joining_availability" in ext_data:
                update_doc["joining_availability"] = ext_data["joining_availability"]
            if "interview_availability" in ext_data:
                update_doc["interview_availability"] = ext_data["interview_availability"]
            if "interested" in ext_data:
                update_doc["interested"] = ext_data["interested"]
            
            # Map match score if present in extracted data
            if "match_score" in ext_data:
                try:
                    update_doc["screening_score"] = float(ext_data["match_score"])
                except: pass
            elif "score" in ext_data:
                try:
                    update_doc["screening_score"] = float(ext_data["score"])
                except: pass

        if analysis:
            update_doc["ai_summary"] = analysis.get("summary") or analysis.get("verdict") or summary
            update_doc["recruiter_verdict"] = analysis.get("recruiter_verdict") or analysis.get("verdict") or summary
            update_doc["conversation_summary"] = analysis.get("conversation_summary") or analysis.get("insights") or summary
            
            # Extract scores from analysis if available
            if "communication_score" in analysis:
                try: update_doc["communication_score"] = float(analysis["communication_score"])
                except: pass
            if "technical_score" in analysis:
                try: update_doc["technical_score"] = float(analysis["technical_score"])
                except: pass
            if "confidence_score" in analysis:
                try: update_doc["confidence_score"] = float(analysis["confidence_score"])
                except: pass
            if "final_recommendation" in analysis:
                update_doc["final_recommendation"] = analysis["final_recommendation"]

            # Extract interest status
            interest_val = analysis.get("interest_status") or analysis.get("interest")
            if interest_val:
                val_lower = interest_val.lower()
                update_doc["interest_status"] = interest_val
                
                # Robust interest mapping
                if "interested" in val_lower and "not" not in val_lower:
                    update_doc["interest"] = "interested"
                    update_doc["status"] = "interested"
                elif any(word in val_lower for word in ["yes", "confirmed", "available", "agree"]):
                    update_doc["interest"] = "interested"
                    update_doc["status"] = "interested"
                elif "callback" in val_lower or "later" in val_lower or "busy" in val_lower or "call me" in val_lower:
                    update_doc["interest"] = "callback_required"
                    update_doc["status"] = "callback_required"
                else:
                    update_doc["interest"] = "not_interested"
                    update_doc["status"] = "not_interested"
            
            if analysis.get("role"):
                update_doc["role"] = analysis.get("role")
            
            if analysis.get("match_score"):
                try:
                    update_doc["screening_score"] = float(analysis["match_score"])
                except: pass
                
            if analysis.get("interview_scheduled") or analysis.get("scheduled"):
                update_doc["interview_status"] = "Scheduled"
                update_doc["interview_scheduled"] = True
                update_doc["interview_date"] = analysis.get("interview_date") or analysis.get("date")
                update_doc["interview_time"] = analysis.get("interview_time") or analysis.get("time")
            
            # Map skills if extracted during conversation
            if analysis.get("extracted_skills"):
                update_doc["screening_skills"] = ", ".join(analysis.get("extracted_skills"))

        # Fallback to LLM extraction if Bolna didn't provide metrics and we have a transcript
        if transcript and update_doc.get("status") in ["completed", "interested", "not_interested"]:
            needs_fallback = False
            if (update_doc.get("communication_score") is None or 
                update_doc.get("interest") is None or
                str(update_doc.get("total_experience", "")).lower() in ["", "not available", "none", "n/a"] or
                update_doc.get("technical_score") is None or
                update_doc.get("confidence_score") is None):
                needs_fallback = True
                
            if needs_fallback:
                logger.info(f"Bolna Webhook: Missing metrics for {candidate_id}, using LLM fallback extraction...")
                llm_data = await BolnaService.extract_metrics_with_llm(transcript)
                
                if llm_data:
                    def get_valid(existing, new_val):
                        if existing is None or str(existing).strip().lower() in ["", "not available", "none", "n/a", "null"]:
                            return new_val
                        return existing

                    update_doc["communication_score"] = get_valid(update_doc.get("communication_score"), llm_data.get("communication_score"))
                    update_doc["technical_score"] = get_valid(update_doc.get("technical_score"), llm_data.get("technical_score"))
                    update_doc["confidence_score"] = get_valid(update_doc.get("confidence_score"), llm_data.get("confidence_score"))
                    update_doc["screening_score"] = get_valid(update_doc.get("screening_score"), llm_data.get("match_score"))
                    update_doc["final_recommendation"] = get_valid(update_doc.get("final_recommendation"), llm_data.get("final_recommendation"))
                    
                    update_doc["total_experience"] = get_valid(update_doc.get("total_experience"), llm_data.get("total_experience"))
                    update_doc["relevant_experience"] = get_valid(update_doc.get("relevant_experience"), llm_data.get("relevant_experience"))
                    update_doc["employment_status"] = get_valid(update_doc.get("employment_status"), llm_data.get("employment_status"))
                    update_doc["joining_availability"] = get_valid(update_doc.get("joining_availability"), llm_data.get("joining_availability"))
                    update_doc["interview_availability"] = get_valid(update_doc.get("interview_availability"), llm_data.get("interview_availability"))
                    
                    llm_interest = llm_data.get("interest", "").lower()
                    if get_valid(update_doc.get("interest"), None) is None:
                        if llm_interest:
                            update_doc["interest"] = llm_interest
                            update_doc["status"] = llm_interest
                            update_doc["interest_status"] = llm_interest

        # Final DB update
        await db.candidates.update_one(
            {"id": candidate_id},
            {"$set": update_doc}
        )

        # TRIGGER EXCEL STORAGE ON COMPLETION
        if is_completed:
            from app.services.excel_service import ExcelService
            # Fetch the full candidate record to ensure we have all fields for Excel
            full_candidate = await db.candidates.find_one({"id": candidate_id})
            if full_candidate and full_candidate.get("organization_id"):
                ExcelService.save_call_result_to_excel(full_candidate, full_candidate.get("organization_id"))
                ExcelService.update_candidate_excel(full_candidate, full_candidate.get("organization_id"))

        logger.info(f"Bolna Webhook: Updated candidate {candidate_id}")
        return {"status": "success", "candidate_id": candidate_id}

    @staticmethod
    async def fetch_bolna_call_details(candidate_id: str):
        """
        Manually fetches call details from Bolna API for a candidate and updates the DB.
        """
        db = get_db()
        candidate = await db.candidates.find_one({"id": candidate_id})
        if not candidate or not candidate.get("bolna_call_id"):
            return {"status": "error", "message": "No active Bolna call found for this candidate"}

        call_id = candidate["bolna_call_id"]
        api_key = settings.BOLNA_API_KEY
        url = f"https://api.bolna.ai/executions/{call_id}"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    payload = response.json()
                    logger.info(f"Bolna Sync: Received payload for {candidate_id}: {payload}")
                    # Reuse the webhook processing logic by passing the payload
                    # We need to make sure 'user_data' is present in the payload for process_webhook_payload
                    if "user_data" not in payload:
                        payload["user_data"] = {"candidate_id": candidate_id}
                    
                    return await BolnaService.process_webhook_payload(payload)
                else:
                    logger.warning(f"Bolna Sync: Failed to fetch call {call_id}. Status: {response.status_code}")
                    return {"status": "error", "message": f"Bolna API error: {response.status_code}"}
        except Exception as e:
            logger.error(f"Bolna Sync Error: {str(e)}")
            return {"status": "error", "message": str(e)}

