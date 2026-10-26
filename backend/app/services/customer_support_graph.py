"""Read-only, tenant-scoped customer support workflow."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import Text, cast, func, or_
from sqlalchemy.orm import Session

from app.models import CustomerSupportFAQ, ETAHistory, Job, JobClosure, ServiceRequest
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.customer_support import CustomerSupportAnswer


CUSTOMER_SERVICE_TYPES = (
    "HVAC Repair", "Electrical", "Plumbing", "Network Support",
    "General Maintenance", "Appliance Repair", "Roofing & Carpentry",
    "CCTV & Security",
)


class SupportState(TypedDict, total=False):
    db: Session
    tenant_id: str
    customer_id: str
    conversation_id: str
    message: str
    history: list[dict[str, Any]]
    intent: str
    faqs: list[dict[str, Any]]
    jobs: list[dict[str, Any]]
    answer: str
    sources: list[dict[str, Any]]
    escalate: bool
    components: list[dict[str, Any]]
    follow_up_suggestions: list[str]


_INTENT_CATEGORIES = {
    "fieldops_overview": {"overview"},
    "service_catalog": {"services"},
    "service_creation": {"requests"},
    "request_information": {"requests"},
    "request_history": {"portal", "requests"},
    "status_explanation": {"status"},
    "appointment_process": {"appointments"},
    "tracking_explanation": {"tracking"},
    "notifications": {"notifications"},
    "closure_report_explanation": {"reports"},
    "general_faq": {"portal", "requests", "services", "appointments", "tracking", "status", "notifications", "reports", "overview"},
}

_STOPWORDS = {
    "a", "an", "the", "what", "which", "who", "where", "when", "why", "how",
    "do", "does", "did", "is", "are", "can", "could", "would", "will", "i",
    "me", "my", "we", "our", "you", "your", "for", "to", "of", "in", "on",
    "and", "or", "with", "from", "that", "this", "have", "has", "it", "be",
    "please", "tell", "show", "explain", "about", "u",
}


def _normalize_tokens(value: str) -> list[str]:
    """Normalize harmless spelling/format variants while preserving intent words."""
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    aliases = {
        "fieldops": "fieldops", "fieldop": "fieldops", "technican": "technician",
        "technicion": "technician", "tech": "technician", "wat": "what", "services": "service",
        "jobs": "job", "requests": "request", "appointments": "appointment",
        "used": "use", "using": "use", "offers": "offer", "provides": "provide",
        "provided": "provide", "tracking": "track", "tracked": "track",
        "statuses": "status", "updates": "update", "notifications": "notification",
        "reports": "report", "closures": "closure",
    }
    return [aliases.get(token, token) for token in tokens if aliases.get(token, token) not in _STOPWORDS]


def _classify(state: SupportState) -> dict[str, Any]:
    text = re.sub(r"[^a-z0-9\s]", " ", state["message"].casefold()).strip()
    tokens = set(_normalize_tokens(state["message"]))
    asks_personal = bool(re.search(r"\b(my|mine|latest|current|this|that)\b", text))
    if any(phrase in text for phrase in ("not showing", "missing", "cannot see", "can't see", "cant see", "disappeared")) and any(word in tokens for word in ("request", "booking")):
        return {"intent": "request_history"}
    if re.fullmatch(r"(?:hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you|thx|bye|goodbye)(?:\s+there)?(?:\s+how are you)?", text):
        return {"intent": "small_talk"}

    # Definition questions must be separated from lookups about the signed-in
    # customer's own request before applying any broad service/job vocabulary.
    if (not asks_personal and re.search(r"\bwhat does\b.*\bmean\b", text)) or re.search(r"\bwhat is\b.*\b(?:in progress|en route|assigned|unassigned|created|completed|cancelled|closed)\b", text):
        return {"intent": "status_explanation"}
    if ("fieldops" in tokens or "platform" in tokens) and any(x in text for x in ("what is", "used for", "what does", "purpose", "what can")):
        return {"intent": "fieldops_overview"}
    if ("service" in tokens and any(word in tokens for word in ("offer", "provide", "catalog", "available", "book", "have", "list"))) or any(x in text for x in ("what services", "which services", "service types", "service catalog", "what do you offer", "what does fieldops offer", "services do you offer", "services can i book")):
        return {"intent": "service_catalog"}
    if any(x in text for x in ("create a service request", "create service request", "new service request", "submit a request", "book a service", "request a service", "make a service request")):
        return {"intent": "service_creation"}

    if "technician" in tokens and any(word in tokens for word in ("when", "arrive", "arrival", "eta", "come")):
        return {"intent": "appointment"}
    if "report" in tokens or "closure" in tokens:
        if asks_personal or any(x in text for x in ("is the report ready", "download my", "where can i download", "report for job", "report for request")):
            return {"intent": "job_completion"}
        return {"intent": "closure_report_explanation"}
    if "notification" in tokens or "alert" in tokens:
        return {"intent": "notifications"}
    if "appointment" in tokens or "schedule" in tokens:
        if asks_personal or any(x in text for x in ("when is", "when will", "my appointment", "appointment time")):
            return {"intent": "appointment"}
        return {"intent": "appointment_process"}
    if "track" in tokens or (re.search(r"\bwhere\b", text) and "technician" in tokens):
        if asks_personal or any(x in text for x in ("where is the technician", "where is technician")):
            return {"intent": "technician_tracking"}
        return {"intent": "tracking_explanation"}
    if any(word in text for word in ("human", "person", "agent", "contact support", "talk to someone", "my account", "sign in", "login", "password")):
        return {"intent": "account_support"}
    if (any(word in tokens for word in ("unassigned", "delay", "delayed", "late", "reassign", "reject", "accepted")) or "not assigned" in text) and asks_personal:
        return {"intent": "delays_reassignment"}
    if any(word in text for word in ("my status", "status of", "job status", "check my", "my request", "my job", "my technician", "is my job", "other request")) or re.search(r"\b(?:sr[- ]?\d+|job\s*#?\s*\d+)\b", text):
        return {"intent": "job_status"}
    if any(word in text for word in ("completed", "finish", "finished", "closed")) and asks_personal:
        return {"intent": "job_completion"}
    if any(word in text for word in ("create", "book a", "booking", "request a service")):
        return {"intent": "service_creation"}
    if re.search(r"\b(?:what about (?:that|it|those)|tell me more|how so|why\??|and (?:that|it)|can you explain that)\b", text):
        previous_question = next((
            str(item.get("content", "")) for item in reversed(state.get("history", []))
            if item.get("sender") == "customer" and item.get("content")
        ), "")
        if previous_question:
            previous_intent = _classify({"message": previous_question})["intent"]
            if previous_intent not in {"general_faq", "unknown", "small_talk"}:
                return {"intent": previous_intent}
    if not tokens:
        return {"intent": "unknown"}
    return {"intent": "general_faq"}


def _retrieve_faq(state: SupportState) -> dict[str, Any]:
    # Only approved, published content in the customer's tenant or global scope.
    search_message = state["message"]
    tokens = set(_normalize_tokens(search_message))
    if len(tokens) <= 1:
        previous_question = next((
            str(item.get("content", "")) for item in reversed(state.get("history", []))
            if item.get("sender") == "customer" and item.get("content")
        ), "")
        if previous_question:
            search_message = f"{search_message} {previous_question}"
            tokens = set(_normalize_tokens(search_message))
    query = state["db"].query(CustomerSupportFAQ).filter(
        CustomerSupportFAQ.is_published == 1,
        or_(CustomerSupportFAQ.tenant_id.is_(None), CustomerSupportFAQ.tenant_id == state["tenant_id"]),
    ).filter(CustomerSupportFAQ.language == "en")
    if len(tokens) < 2 and state.get("intent") not in {"fieldops_overview", "service_catalog"}:
        return {"faqs": [], "faq_ambiguous": False, "faq_query_too_broad": True}
    rows = query.all()
    # PostgreSQL full-text rank is a second signal when available. Token and
    # alternate-question scoring remains the portable fallback for SQLite and
    # for deployments without a working FTS expression.
    full_text_scores: dict[int, float] = {}
    try:
        if state["db"].get_bind().dialect.name == "postgresql":
            document = func.to_tsvector("english", func.concat_ws(
                " ", CustomerSupportFAQ.question,
                cast(CustomerSupportFAQ.alternate_questions, Text),
                cast(CustomerSupportFAQ.keywords, Text),
            ))
            search = func.plainto_tsquery("english", search_message)
            rank = func.ts_rank_cd(document, search)
            matches = state["db"].query(CustomerSupportFAQ.id, rank).filter(
                CustomerSupportFAQ.is_published == 1,
                or_(CustomerSupportFAQ.tenant_id.is_(None), CustomerSupportFAQ.tenant_id == state["tenant_id"]),
                CustomerSupportFAQ.language == "en",
                document.op("@@")(search),
            ).order_by(rank.desc()).limit(30).all()
            full_text_scores = {faq_id: float(score or 0) for faq_id, score in matches}
    except Exception:
        full_text_scores = {}
    ranked = []
    for row in rows:
        compatible = _INTENT_CATEGORIES.get(state.get("intent", "general_faq"), _INTENT_CATEGORIES["general_faq"])
        category = str(row.category or "").casefold()
        if category not in compatible:
            continue
        phrases = [row.question, *(row.alternate_questions or [])]
        phrase_scores = []
        for phrase in phrases:
            phrase_tokens = set(_normalize_tokens(phrase))
            if phrase_tokens:
                overlap = len(tokens & phrase_tokens)
                precision = overlap / len(tokens)
                recall = overlap / len(phrase_tokens)
                f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
                fuzzy = sum(1 for token in tokens if any(SequenceMatcher(None, token, candidate).ratio() >= 0.82 for candidate in phrase_tokens))
                fuzzy_f1 = 2 * (fuzzy / len(tokens)) * (fuzzy / len(phrase_tokens)) / ((fuzzy / len(tokens)) + (fuzzy / len(phrase_tokens))) if fuzzy else 0
                phrase_scores.append(max(f1, fuzzy_f1 * 0.9))
        keyword_tokens = set(_normalize_tokens(" ".join(row.keywords or [])))
        keyword_coverage = len(tokens & keyword_tokens) / len(tokens) if tokens else 0
        score = max(phrase_scores, default=0) * 0.76 + min(0.14, keyword_coverage * 0.14)
        score += min(0.10, full_text_scores.get(row.id, 0.0) * 0.10)
        if score >= 0.34:
            ranked.append((score, row))
    ranked.sort(key=lambda pair: (pair[0], pair[1].tenant_id is not None), reverse=True)
    candidates = [{"id": row.id, "faq_key": getattr(row, "faq_key", None), "question": row.question,
                   "answer": row.answer, "category": row.category, "score": score}
                  for score, row in ranked[:3]]
    ambiguous = len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.045
    return {"faqs": candidates, "faq_ambiguous": ambiguous, "faq_query_too_broad": False}


def _generate_answer(state: SupportState, evidence: dict[str, Any], fallback: str) -> tuple[str, bool]:
    """Generate customer wording from verified evidence; retain safe fallback."""
    try:
        from app.services.ai.FieldOpsAI.runtime.orchestrator import ai_orchestrator

        result = ai_orchestrator.execute(
            AITask.CUSTOMER_SUPPORT,
            {
                "customer_message": state["message"],
                "approved_faqs": evidence.get("approved_faqs", []),
                "verified_job_context": evidence.get("verified_job_context", []),
                "conversation_context": state.get("history", [])[-8:],
            },
            response_schema=CustomerSupportAnswer,
        )
        answer = result.answer.strip()
        if 8 <= len(answer) <= 3000 and _answer_is_grounded(answer, evidence):
            return answer, bool(result.needs_human_support)
    except Exception:
        # Provider, validation, budget, or circuit-breaker failures all use
        # the same approved, verified text fallback.
        pass
    return fallback, False


def _answer_is_grounded(answer: str, evidence: dict[str, Any]) -> bool:
    """Reject common live-data contradictions before showing generated text."""
    jobs = evidence.get("verified_job_context", [])
    for job in jobs:
        status = str(job.get("status", "")).upper()
        named_statuses = set(re.findall(r"\b(?:CREATED|PENDING|UNASSIGNED|ASSIGNED|EN_ROUTE|ON_SITE|IN_PROGRESS|COMPLETED|CANCELLED|CLOSED)\b", answer.upper()))
        if named_statuses - {status}:
            return False
        if not job.get("arrival_estimate") and re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b", answer, re.IGNORECASE):
            return False
        if not job.get("assigned") and re.search(r"\b(?:technician|tech) (?:is|has been) assigned\b", answer, re.IGNORECASE):
            return False
        if not job.get("closure_report_available") and re.search(r"(?:report|closure).{0,35}\bavailable\b", answer, re.IGNORECASE):
            return False
    return True


def _resolve_jobs(state: SupportState) -> dict[str, Any]:
    requests = state["db"].query(ServiceRequest).filter(
        ServiceRequest.tenant_id == state["tenant_id"],
        ServiceRequest.customer_user_id == state["customer_id"],
    ).order_by(ServiceRequest.updated_at.desc()).limit(30).all()
    jobs_by_id: dict[int, dict[str, Any]] = {}
    request_facts: list[dict[str, Any]] = []
    for request in requests:
        if request.linked_job_id:
            job = state["db"].query(Job).filter(
                Job.id == request.linked_job_id,
                Job.customer_tenant_id == state["tenant_id"],
                Job.customer_id == state["customer_id"],
            ).first()
            if job:
                jobs_by_id[job.id] = _job_facts(job, request.request_number, state["db"])
                continue
        request_facts.append({
            "job_id": request.linked_job_id,
            "request_number": request.request_number,
            "status": request.status,
            "service_type": request.service_type,
            "preferred_service_date": request.preferred_visit_date.isoformat() if request.preferred_visit_date else None,
            "assigned": False,
            "arrival_estimate": None,
            "completed_at": None,
            "closure_report_available": False,
        })
    # Older jobs may not have a service_request link; ownership remains exact.
    for job in state["db"].query(Job).filter(
        Job.customer_tenant_id == state["tenant_id"], Job.customer_id == state["customer_id"]
    ).order_by(Job.created_at.desc()).limit(30).all():
        jobs_by_id.setdefault(job.id, _job_facts(job, None, state["db"]))
    known_request_numbers = {item["request_number"] for item in jobs_by_id.values()}
    return {"jobs": list(jobs_by_id.values()) + [item for item in request_facts if item["request_number"] not in known_request_numbers]}


def _job_facts(job: Job, request_number: str | None, db: Session) -> dict[str, Any]:
    # Deliberately omit technician identity/location and internal notes.
    facts = {
        "job_id": job.id,
        "request_number": request_number,
        "status": job.status,
        "service_type": job.service_type,
        "preferred_service_date": job.preferred_service_date.isoformat() if job.preferred_service_date else None,
        "assigned": job.assigned_technician_id is not None,
        "arrival_estimate": None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "closure_report_available": bool(request_number) and db.query(JobClosure).filter(
            JobClosure.job_id == job.id,
            JobClosure.tenant_id == job.tenant_id,
        ).first() is not None,
    }
    if job.assigned_technician_id is not None:
        eta = db.query(ETAHistory).filter(
            ETAHistory.job_id == job.id,
            ETAHistory.tenant_id == job.tenant_id,
        ).order_by(ETAHistory.calculated_at.desc()).first()
        if eta and eta.calculated_at:
            calculated_at = eta.calculated_at
            if calculated_at.tzinfo is None:
                calculated_at = calculated_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            arrival_at = eta.eta
            if arrival_at.tzinfo is None:
                arrival_at = arrival_at.replace(tzinfo=timezone.utc)
            if now - calculated_at <= timedelta(minutes=5) and arrival_at > now:
                facts["arrival_estimate"] = eta.eta.isoformat()
    return facts


def _respond_once(state: SupportState) -> dict[str, Any]:
    text = state["message"].lower()
    if state["intent"] == "small_talk":
        if any(word in text for word in ("thanks", "thank you", "thx")):
            answer = "You're welcome! Feel free to ask me anything about your FieldOps service request."
        elif any(word in text for word in ("bye", "goodbye")):
            answer = "Goodbye. FieldOps Support is here if you need help with a service request."
        else:
            answer = "Hi! 👋 Welcome to FieldOps Support. I can help with service requests, appointments, technician tracking, job updates, and completion reports. What would you like to know?"
        return {"answer": answer, "sources": [], "escalate": False}
    live_intents = {"appointment", "job_status", "technician_tracking", "delays_reassignment", "job_completion"}
    if state["intent"] in live_intents:
        jobs = state.get("jobs", [])
        if not jobs:
            return {"answer": "I couldnâ€™t find a service request linked to your account. You can submit a support request from the Support page.", "sources": [], "escalate": True}
        explicit_match = next((job for job in jobs if (job["job_id"] is not None and re.search(rf"(?<!\d){re.escape(str(job['job_id']))}(?!\d)", text)) or (job["request_number"] and job["request_number"].lower() in text)), None)
        contextual_matches: list[dict[str, Any]] = []
        for history_item in reversed(state.get("history", [])[-6:]):
            prior_context = (history_item.get("content", "") + " " + " ".join(component.get("title", "") for component in history_item.get("components", []))).lower()
            contextual_matches = [job for job in jobs if (job["request_number"] and job["request_number"].lower() in prior_context) or (job["job_id"] is not None and re.search(rf"(?<!\d){re.escape(str(job['job_id']))}(?!\d)", prior_context))]
            if contextual_matches:
                break
        if "other request" in text or (len(jobs) > 1 and explicit_match is None and len(contextual_matches) != 1):
            choices = "; ".join(f"{job['request_number'] or ('#' + str(job['job_id']))} ({job['status']})" for job in jobs[:5])
            return {"answer": f"I found multiple service requests. Which one do you mean: {choices}?", "sources": [], "escalate": False}
        match = explicit_match or (contextual_matches[-1] if contextual_matches else jobs[0])
        label = match["request_number"] or f"#{match['job_id']}"
        answer = f"Service request {label} is currently {match['status']}."
        if "mean" in text or "explain" in text:
            meanings = {
                "CREATED": "FieldOps has received the request and it is awaiting assignment.",
                "PENDING": "The request is awaiting review or scheduling.",
                "ASSIGNED": "A technician has been assigned.",
                "EN_ROUTE": "The assigned technician is on the way.",
                "ON_SITE": "The technician has arrived at the service location.",
                "IN_PROGRESS": "Work on the service request is underway.",
                "COMPLETED": "The job has been marked complete.",
                "CANCELLED": "The request has been cancelled.",
                "CLOSED": "The job record has been closed.",
            }
            meaning = meanings.get(str(match["status"]).upper())
            if meaning:
                answer += f" {meaning}"
        if match["preferred_service_date"]:
            answer += f" The preferred service date is {match['preferred_service_date']}."
        answer += " A technician is assigned." if match["assigned"] else " A technician has not been assigned yet."
        if any(term in text for term in ("not assigned", "unassigned")):
            answer += " I don’t have a verified reason for the assignment delay in the chat records."
        if any(term in text for term in ("reject", "accepted")):
            answer += " This chat shows the current assignment status but does not include technician acceptance or rejection history."
        answer += " An arrival estimate is currently unavailable." if not match["arrival_estimate"] else f" The latest arrival estimate is {match['arrival_estimate']}."
        if any(word in text for word in ("delay", "delayed", "late")):
            answer += " I donâ€™t have a verified reason for a delay in the chat records."
        if "reassign" in text:
            answer += " I can confirm the current assignment status, but assignment change history isnâ€™t available here."
        if any(word in text for word in ("reschedule", "schedule change", "changed appointment")):
            answer += " Appointment change history isnâ€™t available in chat; please use the Support page for help."
        if match["completed_at"]:
            answer += f" The recorded completion time is {match['completed_at']}."
        elif any(term in text for term in ("when will my service finish", "when will it finish", "when will the job finish", "finish the job")):
            answer += " An estimated completion time is not available in the information I can access."
        if any(word in text for word in ("report", "closure")):
            answer += " A completion report is available for this request." if match.get("closure_report_available") else " A completion report is not available for this request in the customer portal."
        if "technician" in text and re.search(r"\bwhere\b", text):
            answer += " Chat cannot provide the technician's precise live location; open Tracking to view it when live tracking is available."
        fallback = answer
        answer, ai_escalation = _generate_answer(state, {"verified_job_context": [match]}, fallback)
        label = match["request_number"] or f"#{match['job_id']}"
        return {
            "answer": answer,
            "sources": [{"type": "service_request", "id": match["request_number"] or match["job_id"]}],
            "escalate": ai_escalation,
            "components": [{"type": "job_status", "title": label, "job_id": match["job_id"], "status": match["status"], "preferred_service_date": match["preferred_service_date"], "arrival_estimate": match["arrival_estimate"], "completed_at": match["completed_at"], "closure_report_available": match.get("closure_report_available", False), "action": "download_report" if "report" in text and match.get("closure_report_available") else "tracking" if any(word in text for word in ("track", "where is my technician")) else "service_requests"}],
            "follow_up_suggestions": ["How can I track my technician?", "What does this status mean?"],
        }
    if state["intent"] in {"account_support", "support_escalation"}:
        return {"answer": "I canâ€™t make account or booking changes here. Please use the Support page to contact the FieldOps team.", "sources": [], "escalate": True}
    if state.get("faq_ambiguous") and len(state.get("faqs", [])) > 1:
        choices = " or ".join(f'“{item["question"]}”' for item in state["faqs"][:2])
        return {"answer": f"I found a couple of possible topics. Are you asking about {choices}?", "sources": [], "escalate": False}
    if state.get("faq_query_too_broad"):
        return {"answer": "Could you add a little more detail so I can find the right answer?", "sources": [], "escalate": False}
    if state["intent"] == "service_catalog":
        catalog_answer = "The service request form currently offers: " + ", ".join(CUSTOMER_SERVICE_TYPES) + "."
        catalog_source = state.get("faqs", [{}])[0].get("id") if state.get("faqs") else None
        sources = [{"type": "faq", "id": catalog_source}] if catalog_source is not None else []
        return {"answer": catalog_answer, "sources": sources, "escalate": False, "components": [{"type": "service_catalog", "title": "Available service types", "items": list(CUSTOMER_SERVICE_TYPES)}]}
    if state.get("faqs"):
        approved = state["faqs"]
        # High-confidence approved FAQs are returned as authored. This avoids
        # an unnecessary generation call changing a correct topic into another.
        best = approved[0]
        return {"answer": best["answer"], "sources": [{"type": "faq", "id": best["id"]}], "escalate": False}
    return {"answer": "I couldnâ€™t verify an answer from the information available. Please use the Support page to contact the FieldOps team.", "sources": [], "escalate": True}


def _respond(state: SupportState) -> dict[str, Any]:
    """Avoid replaying the same full reply when the customer asks again."""
    response = _respond_once(state)
    latest_answer = next((
        str(item.get("content", "")).strip()
        for item in reversed(state.get("history", []))
        if item.get("sender") == "assistant" and item.get("content")
    ), "")
    normalize = lambda value: re.sub(r"\W+", " ", value.casefold()).strip()
    answer = str(response.get("answer", ""))
    if latest_answer and normalize(answer) == normalize(latest_answer):
        response["answer"] = "I shared the information I can verify above. Is there a specific detail you’d like me to clarify?"
    return response


def _route(state: SupportState) -> str:
    if state["intent"] == "small_talk":
        return "respond"
    return "jobs" if state["intent"] in {"appointment", "job_status", "technician_tracking", "delays_reassignment", "job_completion"} else "faq"


def _decorate_reply(state: SupportState) -> dict[str, Any]:
    """Attach only predefined UI actions and deterministic follow-ups."""
    result: dict[str, Any] = {}
    if state.get("escalate"):
        components = list(state.get("components", []))
        if not any(component.get("type") == "support" for component in components):
            components.append({"type": "support", "title": "Contact FieldOps Support", "action": "support"})
        result["components"] = components
    if not state.get("follow_up_suggestions"):
        if state.get("intent") in {"job_status", "appointment", "technician_tracking", "delays_reassignment", "job_completion"}:
            result["follow_up_suggestions"] = ["How can I track my technician?", "How do I get a completion report?"]
        elif state.get("intent") == "service_catalog":
            result["follow_up_suggestions"] = ["How do I create a service request?", "What is FieldOps used for?"]
        elif state.get("intent") == "small_talk":
            result["follow_up_suggestions"] = ["What services does FieldOps offer?", "How can I check my job status?"]
        else:
            result["follow_up_suggestions"] = ["How can I check my job status?", "How do I contact support?"]
    return result


def build_customer_support_graph():
    graph = StateGraph(SupportState)
    graph.add_node("classify_intent", _classify)
    graph.add_node("retrieve_faq", _retrieve_faq)
    graph.add_node("resolve_customer_job", _resolve_jobs)
    graph.add_node("respond", _respond)
    graph.add_node("decorate_reply", _decorate_reply)
    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges("classify_intent", _route, {"jobs": "resolve_customer_job", "faq": "retrieve_faq", "respond": "respond"})
    graph.add_edge("retrieve_faq", "respond")
    graph.add_edge("resolve_customer_job", "respond")
    graph.add_edge("respond", "decorate_reply")
    graph.add_edge("decorate_reply", END)
    return graph.compile()


customer_support_graph = build_customer_support_graph()
