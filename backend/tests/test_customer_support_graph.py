from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.customer_support_graph import _answer_is_grounded, _classify, _generate_answer, _respond, _retrieve_faq


def test_classifies_customer_job_and_booking_questions():
    assert _classify({"message": "What is the status of my latest request?"})["intent"] == "job_status"
    assert _classify({"message": "When is my technician scheduled to arrive?"})["intent"] == "appointment"
    assert _classify({"message": "How do I create a new service request?"})["intent"] == "service_creation"


def test_greeting_and_thanks_are_small_talk():
    assert _classify({"message": "Good morning!"})["intent"] == "small_talk"
    assert _classify({"message": "Thanks"})["intent"] == "small_talk"
    response = _respond({"intent": "small_talk", "message": "hello", "faqs": []})
    assert "Welcome to FieldOps Support" in response["answer"]
    assert response["escalate"] is False
    assert _classify({"message": "Goodbye!"})["intent"] == "small_talk"


def test_informal_and_typo_prone_queries_route_to_relevant_intents():
    assert _classify({"message": "when technician come"})["intent"] == "appointment"
    assert _classify({"message": "when will my technican arrive"})["intent"] == "appointment"
    assert _classify({"message": "why my job not assigned"})["intent"] == "delays_reassignment"
    assert _classify({"message": "where is my technician now"})["intent"] == "technician_tracking"
    assert _classify({"message": "wat services u provide"})["intent"] == "service_catalog"


def test_similar_wording_routes_to_distinct_faq_and_live_intents():
    examples = {
        "What is FieldOps used for?": "fieldops_overview",
        "What services does FieldOps offer?": "service_catalog",
        "How do I create a service request?": "service_creation",
        "What is my job status?": "job_status",
        "When will my technician arrive?": "appointment",
        "What is a closure report?": "closure_report_explanation",
        "Where can I download my closure report?": "job_completion",
        "What does In Progress mean?": "status_explanation",
        "How does technician tracking work?": "tracking_explanation",
        "Where is my technician?": "technician_tracking",
        "How are appointments scheduled?": "appointment_process",
        "How do I get notifications?": "notifications",
        "My service request is not showing": "request_history",
    }
    assert {message: _classify({"message": message})["intent"] for message in examples} == examples


def test_vague_follow_up_reuses_the_previous_customer_topic():
    assert _classify({
        "message": "What about that?",
        "history": [{"sender": "customer", "content": "What is FieldOps used for?"}],
    })["intent"] == "fieldops_overview"


def test_faq_search_matches_alternate_question_and_keywords():
    row = SimpleNamespace(
        id=7, faq_key="available_services", tenant_id=None, question="What services does FieldOps offer?", category="services",
        alternate_questions=["Which services can I book?"],
        keywords=["services", "available", "service types"],
        answer="Choose from the service selector.",
    )
    query = MagicMock()
    query.filter.return_value = query
    query.limit.return_value = query
    query.all.return_value = [row]
    db = MagicMock()
    db.query.return_value = query
    result = _retrieve_faq({"db": db, "tenant_id": "tenant-1", "message": "wat services u provide"})
    assert result["faqs"][0]["id"] == 7
    assert result["faqs"][0]["answer"] == row.answer


def test_faq_search_rejects_generic_keyword_only_and_incompatible_category():
    row = SimpleNamespace(
        id=8, faq_key="available_services", tenant_id=None,
        question="What services does FieldOps offer?", alternate_questions=[],
        keywords=["service", "offer"], category="services", answer="Service selector answer.",
    )
    query = MagicMock()
    query.filter.return_value = query
    query.limit.return_value = query
    query.all.return_value = [row]
    db = MagicMock()
    db.query.return_value = query
    assert _retrieve_faq({"db": db, "tenant_id": "tenant-1", "intent": "general_faq", "message": "service"})["faqs"] == []
    assert _retrieve_faq({"db": db, "tenant_id": "tenant-1", "intent": "fieldops_overview", "message": "What is FieldOps used for?"})["faqs"] == []


def test_overview_and_catalog_render_from_their_own_approved_sources():
    overview = _respond({
        "intent": "fieldops_overview", "message": "What is FieldOps used for?",
        "faqs": [{"id": 41, "faq_key": "fieldops_overview", "category": "overview", "score": 1.0,
                  "question": "What is FieldOps used for?", "answer": "FieldOps helps customers manage their service requests."}],
    })
    assert overview["answer"] == "FieldOps helps customers manage their service requests."
    assert "selector" not in overview["answer"].lower()
    catalog = _respond({"intent": "service_catalog", "message": "What services does FieldOps offer?", "faqs": []})
    assert "HVAC Repair" in catalog["answer"]
    assert catalog["components"][0]["type"] == "service_catalog"


def test_close_faq_scores_trigger_clarification_instead_of_guessing():
    result = _respond({
        "intent": "general_faq", "message": "How do I update my request?", "faq_ambiguous": True,
        "faqs": [
            {"id": 1, "question": "How do I change a service request?", "answer": "Edit request."},
            {"id": 2, "question": "How do I check a service request?", "answer": "Open requests."},
        ],
    })
    assert "possible topics" in result["answer"]
    assert result["sources"] == []


def test_one_word_queries_ask_for_more_context():
    result = _respond({"intent": "general_faq", "message": "service", "faq_query_too_broad": True, "faqs": []})
    assert "add a little more detail" in result["answer"].lower()


def test_ai_provider_failure_uses_verified_fallback(monkeypatch):
    import sys
    from types import SimpleNamespace

    fake_orchestrator = SimpleNamespace(ai_orchestrator=SimpleNamespace(execute=MagicMock(side_effect=RuntimeError("provider unavailable"))))
    monkeypatch.setitem(sys.modules, "app.services.ai.FieldOpsAI.runtime.orchestrator", fake_orchestrator)
    fallback = "The approved answer remains available."
    assert _generate_answer({"message": "Where is my request?"}, {"approved_faqs": []}, fallback) == (fallback, False)


def test_generated_live_answer_is_rejected_if_it_invents_eta_or_status():
    facts = {"verified_job_context": [{"status": "CREATED", "assigned": False, "arrival_estimate": None, "closure_report_available": False}]}
    assert not _answer_is_grounded("Your job is ASSIGNED and the technician will arrive at 4 PM.", facts)
    assert _answer_is_grounded("Your request is still awaiting assignment.", facts)


def test_multiple_live_requests_require_customer_clarification():
    result = _respond({
        "intent": "job_status",
        "message": "Check my latest service request",
        "jobs": [
            {"job_id": 101, "request_number": "SR-101", "status": "ASSIGNED", "service_type": "HVAC", "preferred_service_date": None, "assigned": True, "arrival_estimate": None, "completed_at": None},
            {"job_id": 102, "request_number": "SR-102", "status": "PENDING", "service_type": "Plumbing", "preferred_service_date": None, "assigned": False, "arrival_estimate": None, "completed_at": None},
        ],
    })
    assert "multiple service requests" in result["answer"].lower()
    assert result["escalate"] is False


def test_follow_up_uses_job_referenced_in_recent_conversation(monkeypatch):
    import app.services.customer_support_graph as graph_module

    monkeypatch.setattr(graph_module, "_generate_answer", lambda state, evidence, fallback: (fallback, False))
    result = _respond({
        "intent": "appointment",
        "message": "When will he arrive?",
        "history": [{"sender": "assistant", "content": "SR-202 is currently ASSIGNED.", "components": [{"title": "SR-202"}]}],
        "jobs": [
            {"job_id": 101, "request_number": "SR-101", "status": "ASSIGNED", "service_type": "HVAC", "preferred_service_date": None, "assigned": True, "arrival_estimate": None, "completed_at": None},
            {"job_id": 202, "request_number": "SR-202", "status": "EN_ROUTE", "service_type": "Plumbing", "preferred_service_date": None, "assigned": True, "arrival_estimate": "2026-10-23T18:00:00+00:00", "completed_at": None},
        ],
    })
    assert result["sources"][0]["id"] == "SR-202"
    assert result["components"][0]["status"] == "EN_ROUTE"
    assert result["components"][0]["action"] == "service_requests"


def test_unknown_question_falls_back_to_real_support_page():
    result = _respond({"intent": "general_faq", "message": "What is the CEO's private number?", "faqs": []})
    assert result["escalate"] is True
    assert "Support page" in result["answer"]
    assert "phone" not in result["answer"].lower()


def test_identical_follow_up_answer_is_not_repeated_verbatim(monkeypatch):
    import app.services.customer_support_graph as graph_module

    monkeypatch.setattr(graph_module, "_generate_answer", lambda state, evidence, fallback: (fallback, False))
    previous = "Choose from the service selector to request a FieldOps service."
    result = _respond({
        "intent": "general_faq", "message": "How do I make a service request?",
        "faqs": [{"id": 9, "answer": previous}],
        "history": [{"sender": "assistant", "content": previous}],
    })
    assert result["answer"] != previous
    assert "clarify" in result["answer"].lower()
