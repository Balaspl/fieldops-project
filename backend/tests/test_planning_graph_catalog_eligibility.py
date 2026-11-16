"""Regression tests for provider service-catalogue filtering in the Planning Agent.

These tests exercise the organization-discovery node directly. The fake database
returns rows for each ORM model and applies the active-offering predicate in the
same way the database does for ServiceCatalogItem queries.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any, Iterable
from unittest.mock import patch

import pytest

from app.models import Organization, ServiceCatalogItem, Technician


planning_graph = importlib.import_module(
    "app.services.ai.FieldOpsAI.graph.planning_graph"
)


class _FakeQuery:
    def __init__(self, model: type, rows: Iterable[Any]) -> None:
        self.model = model
        self.rows = list(rows)
        self.filter_calls: list[tuple[Any, ...]] = []
        self.join_calls: list[tuple[Any, ...]] = []

    def join(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        self.join_calls.append(args)
        return self

    def filter(self, *criteria: Any) -> "_FakeQuery":
        self.filter_calls.append(criteria)
        if self.model is ServiceCatalogItem:
            # The production query has ServiceCatalogItem.is_active.is_(True).
            self.rows = [row for row in self.rows if row.is_active is True]
        return self

    def all(self) -> list[Any]:
        return list(self.rows)


class _FakeDatabase:
    def __init__(
        self,
        *,
        technicians: Iterable[Any],
        offerings: Iterable[Any] = (),
        organizations: Iterable[Any],
    ) -> None:
        self.rows_by_model = {
            Technician: list(technicians),
            ServiceCatalogItem: list(offerings),
            Organization: list(organizations),
        }
        self.queries: list[_FakeQuery] = []

    def query(self, model: type) -> _FakeQuery:
        query = _FakeQuery(model, self.rows_by_model.get(model, ()))
        self.queries.append(query)
        return query

    def queried_model_types(self) -> list[type]:
        return [query.model for query in self.queries]


def _technician(tenant_id: str, technician_id: int) -> Any:
    return SimpleNamespace(
        tenant_id=tenant_id,
        technician_id=technician_id,
        technician_skill="Plumbing, Tap Repair, Leaking Tap",
    )


def _organization(tenant_id: str, name: str) -> Any:
    return SimpleNamespace(
        id=tenant_id,
        name=name,
        site_latitude=13.0827,
        site_longitude=80.2707,
        settings={},
    )


def _offering(
    tenant_id: str,
    *,
    service_type: str = "Plumbing",
    category: str = "Tap Repair",
    issue: str = "Leaking Tap",
    is_active: bool = True,
) -> Any:
    return SimpleNamespace(
        tenant_id=tenant_id,
        service_type=service_type,
        category=category,
        issue=issue,
        is_active=is_active,
    )


def _run_organization_node(db: _FakeDatabase, *, marketplace: bool = True,
                           include_taxonomy: bool = True) -> dict[str, Any]:
    job_requirement: dict[str, Any] = {
        "required_skill": "Plumbing",
        "service": "Plumbing",
        "service_type": "Plumbing",
        "requires_catalog_offering": marketplace,
    }
    if include_taxonomy:
        job_requirement.update(
            {"category": "Tap Repair", "issue": "Leaking Tap"}
        )

    state = {
        "job_id": 501,
        "job_requirement": job_requirement,
        "customer_coordinates": (13.0827, 80.2707),
        "db": db,
    }

    with (
        patch.object(planning_graph, "get_database", return_value=(db, False)),
        patch.object(planning_graph, "haversine_distance", return_value=3.0),
    ):
        return planning_graph.find_nearest_organizations_node(state)


def test_marketplace_booking_only_includes_provider_with_exact_active_offering() -> None:
    db = _FakeDatabase(
        technicians=[
            _technician("provider-a", 1),
            _technician("provider-b", 2),
        ],
        offerings=[
            _offering("provider-a"),
            _offering("provider-b", issue="Blocked Drain"),
        ],
        organizations=[
            _organization("provider-a", "Provider A"),
            _organization("provider-b", "Provider B"),
        ],
    )

    result = _run_organization_node(db)

    assert [item["id"] for item in result["eligible_organizations"]] == [
        "provider-a"
    ]
    assert ServiceCatalogItem in db.queried_model_types()


def test_multiple_providers_with_the_same_active_offering_are_both_eligible() -> None:
    db = _FakeDatabase(
        technicians=[
            _technician("provider-a", 1),
            _technician("provider-b", 2),
        ],
        offerings=[
            _offering("provider-a"),
            _offering("provider-b", service_type=" plumbing ", category="TAP REPAIR"),
        ],
        organizations=[
            _organization("provider-a", "Provider A"),
            _organization("provider-b", "Provider B"),
        ],
    )

    result = _run_organization_node(db)

    assert {item["id"] for item in result["eligible_organizations"]} == {
        "provider-a",
        "provider-b",
    }


def test_inactive_offering_does_not_make_provider_eligible() -> None:
    db = _FakeDatabase(
        technicians=[_technician("provider-a", 1)],
        offerings=[_offering("provider-a", is_active=False)],
        organizations=[_organization("provider-a", "Provider A")],
    )

    result = _run_organization_node(db)

    assert result["eligible_organizations"] == []
    offering_query = next(
        query for query in db.queries if query.model is ServiceCatalogItem
    )
    assert offering_query.filter_calls, "The active-offering filter must be applied."


def test_marketplace_booking_without_category_or_issue_fails_closed() -> None:
    db = _FakeDatabase(
        technicians=[_technician("provider-a", 1)],
        offerings=[_offering("provider-a")],
        organizations=[_organization("provider-a", "Provider A")],
    )

    result = _run_organization_node(db, include_taxonomy=False)

    assert result["eligible_organizations"] == []
    assert ServiceCatalogItem not in db.queried_model_types()


def test_non_marketplace_planning_keeps_existing_skill_based_behavior() -> None:
    db = _FakeDatabase(
        technicians=[
            _technician("provider-a", 1),
            _technician("provider-b", 2),
        ],
        offerings=[],
        organizations=[
            _organization("provider-a", "Provider A"),
            _organization("provider-b", "Provider B"),
        ],
    )

    result = _run_organization_node(db, marketplace=False)

    assert {item["id"] for item in result["eligible_organizations"]} == {
        "provider-a",
        "provider-b",
    }
    assert ServiceCatalogItem not in db.queried_model_types()
