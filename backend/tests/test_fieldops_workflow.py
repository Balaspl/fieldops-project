"""
test_fieldops_workflow.py

Comprehensive test suite verifying:
1. Intake Agent (LangGraph): VALID, MISMATCH, UNCLEAR handling with specific job messages.
2. Planning Agent (LangGraph):
   - Eligibility rule (workload < 5).
   - Organization proximity priority + Same organization first.
   - Fallback to next nearest organization.
   - Single technician scenario (total 1, top 3 contains 1).
   - Two technicians scenario (total 2, top 3 contains 2).
   - More than 3 technicians scenario (total > 3, top 3 contains 3).
3. End-to-End Workflow coordination and halting rules.
"""

import pytest
from unittest.mock import MagicMock

from app.services.ai.FieldOpsAI.graph.intake_graph import intake_graph
from app.services.ai.FieldOpsAI.graph.planning_graph import planning_graph
from app.services.ai.FieldOpsAI.graph.workflow import execute_fieldops_workflow


# ─────────────────────────────────────────────────────────────
# 1. INTAKE AGENT TESTS (LangGraph)
# ─────────────────────────────────────────────────────────────

class TestIntakeAgent:
    """Test suite for Intake Agent LangGraph workflow."""

    def test_intake_valid_electrical(self):
        """Selected service matches detected service -> VALID."""
        req = {
            "service": "Electrical",
            "title": "Wiring issue",
            "description": "I need an electrician to repair a wiring issue in my home office.",
            "location": "Anna Nagar, Chennai",
            "priority": "HIGH",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is True
        assert res["error_type"] is None
        assert res["job_requirement"] is not None
        assert res["job_requirement"]["service"] == "Electrical"
        assert res["job_requirement"]["required_skill"] == "Electrical"
        assert res["job_requirement"]["location"] == "Anna Nagar, Chennai"

    def test_intake_valid_plumbing(self):
        """Selected service matches detected service -> VALID."""
        req = {
            "service": "Plumbing",
            "title": "Kitchen drain blockage",
            "description": "The kitchen sink pipe is leaking water all over the floor.",
            "location": "Adyar, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is True
        assert res["job_requirement"] is not None
        assert res["job_requirement"]["service"] == "Plumbing"
        assert res["job_requirement"]["required_skill"] == "Plumbing"

    def test_intake_mismatch_electrical_selected_plumbing_request(self):
        """Selected Electrical, but description requires Plumbing -> MISMATCH."""
        req = {
            "service": "Electrical",
            "title": "Pipe problem",
            "description": "I have a leaking bathroom pipe and faucet.",
            "location": "Velachery, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "mismatch"
        assert res["field"] == "service"
        assert "describes a Plumbing-related problem, but you selected Electrical" in res["message"]
        assert res["detected_value"] == "Plumbing"
        assert res["expected_value"] == "Electrical"
        assert res["job_requirement"] is None

    def test_intake_mismatch_plumbing_selected_electrical_request(self):
        """Selected Plumbing, but description requires Electrical -> MISMATCH."""
        req = {
            "service": "Plumbing",
            "title": "Switch spark",
            "description": "The electrical switchboard sparked and lights went off.",
            "location": "Guindy, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "mismatch"
        assert res["field"] == "service"
        assert "describes a Electrical-related problem, but you selected Plumbing" in res["message"]

    def test_intake_mismatch_image_1_air_conditionar(self):
        """
        Image 1 UI Scenario:
        Title: 'air conditionar is not working properly'
        Description: 'air conditionar is not working properly come and check'
        Selected Service: 'Plumbing'
        """
        req = {
            "service": "Plumbing",
            "title": "air conditionar is not working properly",
            "description": "air conditionar is not working properly come and check",
            "location": "Valli Raman Mini Hall, Kodambakkam, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "mismatch"
        assert res["field"] == "service"
        assert res["message"] == (
            "Your request describes a HVAC-related problem, but you selected Plumbing. "
            "Please select the appropriate Service Type."
        )

    def test_intake_mismatch_title_description_conflict(self):
        """
        Title-Description Conflict Scenario:
        Title: 'Ac repair' (HVAC)
        Description: 'water is leaking from the kitchen sink' (Plumbing)
        Selected Service: 'Plumbing'
        Title and description conflict -> MISMATCH!
        """
        req = {
            "service": "Plumbing",
            "title": "Ac repair",
            "description": "water is leaking from the kitchen sink",
            "location": "4th Avenue, Kodambakkam, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "mismatch"
        assert "title indicates HVAC while description indicates Plumbing" in res["message"]
        assert res["job_requirement"] is None

    def test_intake_mismatch_user_screenshot_ac_title_fan_desc(self):
        """
        User UI Scenario from screenshot:
        Title: 'the ac is not working' (HVAC)
        Description: 'the fan is not working works very slow' (Electrical)
        Selected Service: 'HVAC Repair' (HVAC)
        Title is HVAC, Description is Electrical -> MISMATCH!
        """
        req = {
            "service": "HVAC Repair",
            "title": "the ac is not working",
            "description": "the fan is not working works very slow",
            "location": "4th Avenue, Kodambakkam, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "mismatch"
        assert res["field"] == "service"
        assert "title indicates HVAC while description indicates Electrical" in res["message"]
        assert res["job_requirement"] is None

    def test_intake_all_three_must_match_valid(self):
        """
        All three match scenario:
        Title: 'kitchen sink is water leaking kindly come and fix it' (Plumbing)
        Description: 'kitchen sink is water leaking kindly come and fix it' (Plumbing)
        Selected Service: 'Plumbing' (Plumbing)
        All 3 match -> VALID.
        """
        req = {
            "service": "Plumbing",
            "title": "kitchen sink is water leaking kindly come and fix it",
            "description": "kitchen sink is water leaking kindly come and fix it",
            "location": "4th Avenue, Kodambakkam, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is True
        assert res["error_type"] is None
        assert res["job_requirement"] is not None
        assert res["job_requirement"]["service"] == "Plumbing"
        assert res["job_requirement"]["required_skill"] == "Plumbing"

    def test_intake_unclear_when_description_lacks_service_keywords_despite_title(self):
        """
        Title alone is NOT enough if description lacks recognizable service details.
        Title: 'AC Repair'
        Description: 'I need someone to help me immediately.'
        Selected Service: 'HVAC Repair'
        Description has no service details -> UNCLEAR!
        """
        req = {
            "service": "HVAC Repair",
            "title": "AC Repair",
            "description": "I need someone to help me immediately.",
            "location": "Kodambakkam, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "unclear"
        assert res["field"] == "service"
        assert "The problem could not be understood clearly" in res["message"]
        assert res["job_requirement"] is None

    def test_intake_unclear_image_2_gibberish(self):
        """
        Image 2 UI Scenario:
        Title & Description are unparseable gibberish -> UNCLEAR.
        """
        req = {
            "service": "Network Support",
            "title": "hdjabfksnksviowjgvihniien uiiufofhiowjfioemkfnrfewmflwejiw",
            "description": "hdjabfksnksviowjgvihniien uiiufofhiowjfioemkfnrfewmflwejiwhdfejoqji32",
            "location": "Valli Raman Mini Hall, Kodambakkam, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "unclear"
        assert res["field"] == "service"
        assert res["message"] == (
            "The problem could not be understood clearly. Please provide more specific details "
            "about the problem and select the appropriate Service Type."
        )

    def test_intake_unclear_generic_help(self):
        """Vague request with no service details -> UNCLEAR."""
        req = {
            "service": "Electrical",
            "title": "Help needed",
            "description": "I need help.",
            "location": "T Nagar, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "unclear"
        assert res["field"] == "service"
        assert "The problem could not be understood clearly" in res["message"]
        assert res["job_requirement"] is None

    def test_intake_unclear_short_or_empty_description(self):
        """Description is too short or empty -> UNCLEAR."""
        req = {
            "service": "HVAC",
            "title": "Issue",
            "description": "help",
            "location": "T Nagar, Chennai",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "unclear"
        assert res["field"] == "service"

    def test_intake_unclear_missing_location(self):
        """Location is missing -> UNCLEAR."""
        req = {
            "service": "Plumbing",
            "title": "Leaking pipe",
            "description": "I have a leaking pipe under the sink.",
            "location": "",
        }
        res = intake_graph.invoke({"raw_request": req})

        assert res["valid"] is False
        assert res["error_type"] == "unclear"
        assert res["field"] == "location"
        assert "Customer location is required" in res["message"]


# ─────────────────────────────────────────────────────────────
# 2. PLANNING AGENT TESTS (LangGraph)
# ─────────────────────────────────────────────────────────────

class MockQuery:
    """Mock for SQLAlchemy Query chaining."""
    def __init__(self, items):
        self._items = list(items)

    def filter(self, *args, **kwargs):
        res = list(self._items)
        for arg in args:
            arg_str = str(arg)
            if "tenant_id" in arg_str:
                val = getattr(getattr(arg, "right", None), "value", None)
                if val is not None:
                    res = [x for x in res if getattr(x, "tenant_id", None) == val]
        return MockQuery(res)

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


def _make_mock_db(org_data: list[dict], tech_data: list[dict]):
    """Helper to create a mock SQLAlchemy Session with orgs and techs."""
    mock_db = MagicMock()

    class FakeOrg:
        def __init__(self, id, name, lat, lng):
            self.id = id
            self.name = name
            self.site_latitude = lat
            self.site_longitude = lng
            self.deleted_at = None

    class FakeTech:
        def __init__(self, id, name, tenant_id, skill, workload, lat=None, lng=None, loc=None):
            self.technician_id = id
            self.technician_name = name
            self.tenant_id = tenant_id
            self.technician_skill = skill
            self.current_jobs = workload
            self.latitude = lat
            self.longitude = lng
            self.technician_location = loc

    org_objs = [FakeOrg(**o) for o in org_data]
    tech_objs = [FakeTech(**t) for t in tech_data]

    def mock_query(model):
        if model.__name__ == "Organization":
            return MockQuery(org_objs)
        elif model.__name__ == "Technician":
            return MockQuery(tech_objs)
        return MockQuery([])

    mock_db.query.side_effect = mock_query
    return mock_db


class TestPlanningAgent:
    """Test suite for Planning Agent LangGraph workflow."""

    def test_workload_boundary_strictly_less_than_five(self):
        """
        Workload rule verification:
        workload 4 -> eligible
        workload 5 -> NOT eligible
        workload 6 -> NOT eligible
        """
        org_data = [{"id": 1, "name": "Org Alpha", "lat": 13.0827, "lng": 80.2707}]
        tech_data = [
            {"id": 101, "name": "Tech Four", "tenant_id": 1, "skill": "Electrical", "workload": 4, "lat": 13.083, "lng": 80.271},
            {"id": 102, "name": "Tech Five", "tenant_id": 1, "skill": "Electrical", "workload": 5, "lat": 13.082, "lng": 80.270},
            {"id": 103, "name": "Tech Six", "tenant_id": 1, "skill": "Electrical", "workload": 6, "lat": 13.081, "lng": 80.269},
        ]
        mock_db = _make_mock_db(org_data, tech_data)

        job_req = {
            "service": "Electrical",
            "required_skill": "Electrical",
            "location": "Chennai",
            "site_latitude": 13.0827,
            "site_longitude": 80.2707,
        }

        res = planning_graph.invoke({"job_requirement": job_req, "db": mock_db, "job_id": "TEST-1"})
        planning_res = res["planning_response"]

        assert planning_res["total_eligible_technicians"] == 1
        assert len(planning_res["top_3"]) == 1
        assert planning_res["top_3"][0]["technician_id"] == 101
        assert planning_res["top_3"][0]["workload"] == 4

    def test_same_organization_first_ranking_rule(self):
        """
        Rule: Nearest eligible organization first.
        All eligible technicians from that organization must be ranked before moving to next organization.
        
        Org A (at 13.081, 80.271 - close):
          A1 (dist ~0.3 km)
          A2 (dist ~1.8 km)
        Org B (at 13.095, 80.285 - next nearest):
          B1 (dist ~0.8 km)
          
        Expected order:
        1. A1 (Org A, 0.3 km)
        2. A2 (Org A, 1.8 km)
        3. B1 (Org B, 0.8 km)
        Even though B1 is closer than A2, A2 comes first because same organization priority!
        """
        cust_lat, cust_lng = 13.0800, 80.2700

        org_data = [
            {"id": 1, "name": "Org A (Nearest)", "lat": 13.0810, "lng": 80.2710},
            {"id": 2, "name": "Org B (Next Nearest)", "lat": 13.0950, "lng": 80.2850},
        ]
        tech_data = [
            {"id": 101, "name": "A1", "tenant_id": 1, "skill": "Plumbing", "workload": 1, "lat": 13.0820, "lng": 80.2720},
            {"id": 102, "name": "A2", "tenant_id": 1, "skill": "Plumbing", "workload": 2, "lat": 13.0900, "lng": 80.2800},
            {"id": 201, "name": "B1", "tenant_id": 2, "skill": "Plumbing", "workload": 0, "lat": 13.0850, "lng": 80.2750},
        ]
        mock_db = _make_mock_db(org_data, tech_data)

        job_req = {
            "service": "Plumbing",
            "required_skill": "Plumbing",
            "site_latitude": cust_lat,
            "site_longitude": cust_lng,
        }

        res = planning_graph.invoke({"job_requirement": job_req, "db": mock_db, "job_id": "TEST-2"})
        top_3 = res["planning_response"]["top_3"]

        assert len(top_3) == 3
        assert top_3[0]["technician_name"] == "A1"
        assert top_3[0]["organization_name"] == "Org A (Nearest)"
        assert top_3[0]["rank"] == 1

        assert top_3[1]["technician_name"] == "A2"
        assert top_3[1]["organization_name"] == "Org A (Nearest)"
        assert top_3[1]["rank"] == 2

        assert top_3[2]["technician_name"] == "B1"
        assert top_3[2]["organization_name"] == "Org B (Next Nearest)"
        assert top_3[2]["rank"] == 3

    def test_single_eligible_technician(self):
        """
        User Requirement:
        If only 1 eligible technician exists, dispatcher receives total 1 and top 3 contains that 1 technician.
        Do NOT fabricate technicians.
        """
        org_data = [{"id": 1, "name": "Org Solo", "lat": 13.0827, "lng": 80.2707}]
        tech_data = [
            {"id": 99, "name": "Solo Tech", "tenant_id": 1, "skill": "Electrical", "workload": 2, "lat": 13.083, "lng": 80.271},
        ]
        mock_db = _make_mock_db(org_data, tech_data)

        job_req = {
            "service": "Electrical",
            "required_skill": "Electrical",
            "site_latitude": 13.0827,
            "site_longitude": 80.2707,
        }

        res = planning_graph.invoke({"job_requirement": job_req, "db": mock_db, "job_id": "SOLO-1"})
        planning_res = res["planning_response"]

        assert planning_res["total_eligible_technicians"] == 1
        assert len(planning_res["top_3"]) == 1
        assert planning_res["top_3"][0]["technician_name"] == "Solo Tech"
        assert planning_res["top_3"][0]["rank"] == 1

    def test_two_eligible_technicians(self):
        """
        If exactly 2 eligible technicians exist, return total 2 and top 3 contains 2.
        """
        org_data = [{"id": 1, "name": "Org Pair", "lat": 13.0827, "lng": 80.2707}]
        tech_data = [
            {"id": 1, "name": "Tech One", "tenant_id": 1, "skill": "Electrical", "workload": 1, "lat": 13.083, "lng": 80.271},
            {"id": 2, "name": "Tech Two", "tenant_id": 1, "skill": "Electrical", "workload": 3, "lat": 13.085, "lng": 80.272},
        ]
        mock_db = _make_mock_db(org_data, tech_data)

        job_req = {
            "service": "Electrical",
            "required_skill": "Electrical",
            "site_latitude": 13.0827,
            "site_longitude": 80.2707,
        }

        res = planning_graph.invoke({"job_requirement": job_req, "db": mock_db, "job_id": "PAIR-1"})
        planning_res = res["planning_response"]

        assert planning_res["total_eligible_technicians"] == 2
        assert len(planning_res["top_3"]) == 2
        assert planning_res["top_3"][0]["rank"] == 1
        assert planning_res["top_3"][1]["rank"] == 2

    def test_more_than_three_eligible_technicians(self):
        """
        If 5 eligible technicians exist, total is 5, but top 3 contains exactly 3.
        """
        org_data = [{"id": 1, "name": "Org Multi", "lat": 13.0827, "lng": 80.2707}]
        tech_data = [
            {"id": 1, "name": "Tech 1", "tenant_id": 1, "skill": "Electrical", "workload": 0, "lat": 13.083, "lng": 80.271},
            {"id": 2, "name": "Tech 2", "tenant_id": 1, "skill": "Electrical", "workload": 1, "lat": 13.084, "lng": 80.272},
            {"id": 3, "name": "Tech 3", "tenant_id": 1, "skill": "Electrical", "workload": 2, "lat": 13.085, "lng": 80.273},
            {"id": 4, "name": "Tech 4", "tenant_id": 1, "skill": "Electrical", "workload": 3, "lat": 13.086, "lng": 80.274},
            {"id": 5, "name": "Tech 5", "tenant_id": 1, "skill": "Electrical", "workload": 4, "lat": 13.087, "lng": 80.275},
        ]
        mock_db = _make_mock_db(org_data, tech_data)

        job_req = {
            "service": "Electrical",
            "required_skill": "Electrical",
            "site_latitude": 13.0827,
            "site_longitude": 80.2707,
        }

        res = planning_graph.invoke({"job_requirement": job_req, "db": mock_db, "job_id": "MULTI-1"})
        planning_res = res["planning_response"]

        assert planning_res["total_eligible_technicians"] == 5
        assert len(planning_res["top_3"]) == 3
        assert [t["rank"] for t in planning_res["top_3"]] == [1, 2, 3]

    def test_skip_nearest_org_when_all_technicians_busy(self):
        """
        If Org A is nearest, but all its technicians have workload >= 5,
        Planning moves to Org B.
        """
        org_data = [
            {"id": 1, "name": "Org A (Busy)", "lat": 13.0810, "lng": 80.2710},
            {"id": 2, "name": "Org B (Available)", "lat": 13.0950, "lng": 80.2850},
        ]
        tech_data = [
            {"id": 101, "name": "Busy Tech", "tenant_id": 1, "skill": "HVAC", "workload": 5, "lat": 13.082, "lng": 80.272},
            {"id": 201, "name": "Available Tech", "tenant_id": 2, "skill": "HVAC", "workload": 1, "lat": 13.096, "lng": 80.286},
        ]
        mock_db = _make_mock_db(org_data, tech_data)

        job_req = {
            "service": "HVAC",
            "required_skill": "HVAC",
            "site_latitude": 13.0800,
            "site_longitude": 80.2700,
        }

        res = planning_graph.invoke({"job_requirement": job_req, "db": mock_db, "job_id": "BUSY-1"})
        planning_res = res["planning_response"]

        assert planning_res["total_eligible_technicians"] == 1
        assert len(planning_res["top_3"]) == 1
        assert planning_res["top_3"][0]["technician_name"] == "Available Tech"
        assert planning_res["top_3"][0]["organization_name"] == "Org B (Available)"

    def test_planning_matches_image_3_specification(self):
        """
        Verify planning output structure strictly matches Image 3:
        - job_id is integer (not 'JOB-AUTO')
        - top_3 contains technician_id, rank, confidence, estimated_eta,
          organization_id, organization_name, organization_distance, technician_distance
        """
        org_data = [{"id": 42, "name": "Kiruba", "lat": 13.0827, "lng": 80.2707}]
        tech_data = [
            {"id": 21, "name": "melvin new", "tenant_id": 42, "skill": "HVAC", "workload": 1, "lat": 13.090, "lng": 80.280},
        ]
        mock_db = _make_mock_db(org_data, tech_data)

        job_req = {
            "service": "HVAC",
            "required_skill": "HVAC",
            "site_latitude": 13.0827,
            "site_longitude": 80.2707,
        }

        res = planning_graph.invoke({"job_requirement": job_req, "db": mock_db, "job_id": 144})
        resp = res["planning_response"]

        assert resp["job_id"] == 144
        assert "top_3" in resp
        tech = resp["top_3"][0]
        assert tech["technician_id"] == 21
        assert tech["rank"] == 1
        assert tech["confidence"] == 1.0
        assert isinstance(tech["estimated_eta"], int)
        assert tech["organization_id"] == 42
        assert tech["organization_name"] == "Kiruba"
        assert isinstance(tech["organization_distance"], float)
        assert isinstance(tech["technician_distance"], float)


# ─────────────────────────────────────────────────────────────
# 3. END-TO-END WORKFLOW INTEGRATION TESTS
# ─────────────────────────────────────────────────────────────

class TestWorkflowEndToEnd:
    """End-to-end integration tests using execute_fieldops_workflow."""

    def test_e2e_valid_flow(self):
        """Valid customer request -> Intake -> Planning -> Dispatch Top 3."""
        org_data = [{"id": 1, "name": "City Electric", "lat": 13.0827, "lng": 80.2707}]
        tech_data = [
            {"id": 1, "name": "Arun Kumar", "tenant_id": 1, "skill": "Electrical", "workload": 2, "lat": 13.083, "lng": 80.271},
        ]
        mock_db = _make_mock_db(org_data, tech_data)

        request_data = {
            "service": "Electrical",
            "title": "Short circuit repair",
            "description": "I need an electrician to fix a short circuit in the kitchen wiring.",
            "location": "13.0827, 80.2707",
            "priority": "HIGH",
        }

        res = execute_fieldops_workflow(request_data, db=mock_db, job_id="JOB-5001")

        assert res["valid"] is True
        assert "job_requirement" in res
        assert "planning" in res
        assert res["planning"]["total_eligible_technicians"] == 1
        assert len(res["planning"]["top_3"]) == 1
        assert res["planning"]["top_3"][0]["technician_name"] == "Arun Kumar"

    def test_e2e_mismatch_blocks_planning(self):
        """Mismatch request -> Intake fails -> Planning NEVER called."""
        mock_db = MagicMock()

        request_data = {
            "service": "Electrical",
            "title": "Pipe leakage",
            "description": "I have a leaking bathroom pipe.",
            "location": "Chennai",
        }

        res = execute_fieldops_workflow(request_data, db=mock_db, job_id="JOB-MISMATCH")

        assert res["valid"] is False
        assert res["error_type"] == "mismatch"
        assert "planning" not in res
        # Ensure DB was never queried by planning
        assert mock_db.query.call_count == 0

    def test_e2e_unclear_blocks_planning(self):
        """Unclear request -> Intake fails -> Planning NEVER called."""
        mock_db = MagicMock()

        request_data = {
            "service": "Electrical",
            "title": "Help",
            "description": "I need help.",
            "location": "Chennai",
        }

        res = execute_fieldops_workflow(request_data, db=mock_db, job_id="JOB-UNCLEAR")

        assert res["valid"] is False
        assert res["error_type"] == "unclear"
        assert "planning" not in res
        # Ensure DB was never queried by planning
        assert mock_db.query.call_count == 0


# ─────────────────────────────────────────────────────────────
# 4. API ROUTE TESTS (/planning/workflow/auto-plan)
# ─────────────────────────────────────────────────────────────

class TestWorkflowAPI:
    """Tests for the REST endpoint exposing automated Intake & Planning."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db
        from app.auth.dependencies import get_current_user, AuthenticatedUser
        from app.auth.rbac import UserRole

        self.app = app
        self.user = AuthenticatedUser(
            user_id="disp-user-1",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="jti-123",
        )
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(self.app)

        yield

        self.app.dependency_overrides.clear()

    def test_api_valid_request(self):
        from app.database import get_db

        org_data = [{"id": 1, "name": "Speedy Electricals", "lat": 13.0827, "lng": 80.2707}]
        tech_data = [
            {"id": 10, "name": "Karthik", "tenant_id": 1, "skill": "Electrical", "workload": 2, "lat": 13.083, "lng": 80.271},
        ]
        mock_db = _make_mock_db(org_data, tech_data)
        self.app.dependency_overrides[get_db] = lambda: mock_db

        resp = self.client.post("/planning/workflow/auto-plan", json={
            "service": "Electrical",
            "title": "Short circuit repair",
            "description": "Need an electrician to fix a short circuit in the wiring.",
            "location": "13.0827, 80.2707",
            "priority": "HIGH",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["planning"]["total_eligible_technicians"] == 1
        assert len(data["planning"]["top_3"]) == 1
        assert data["planning"]["top_3"][0]["technician_name"] == "Karthik"

    def test_api_mismatch_returns_400(self):
        from app.database import get_db
        mock_db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: mock_db

        resp = self.client.post("/planning/workflow/auto-plan", json={
            "service": "Electrical",
            "title": "Pipe leakage",
            "description": "I have a leaking bathroom pipe.",
            "location": "Chennai",
        })

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["valid"] is False
        assert detail["error_type"] == "mismatch"
        assert "describes a Plumbing-related problem, but you selected Electrical" in detail["message"]

    def test_api_unclear_returns_400(self):
        from app.database import get_db
        mock_db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: mock_db

        resp = self.client.post("/planning/workflow/auto-plan", json={
            "service": "Electrical",
            "title": "Help",
            "description": "I need help.",
            "location": "Chennai",
        })

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["valid"] is False
        assert detail["error_type"] == "unclear"
        assert "The problem could not be understood clearly" in detail["message"]

