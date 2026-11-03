"""API and routing regression tests. Run with: python -m pytest -q"""

import pytest

from app import main


def route(client, profile="wheelchair", start="GATE", destination="CS_DEPT"):
    return client.post(
        "/api/route",
        json={"start": start, "destination": destination, "profile": profile},
    )


def set_facility(client, facility_id, status):
    return client.post(
        f"/api/admin/facilities/{facility_id}/status",
        json={"status": status, "note": "automated test"},
    )


def set_edge(client, edge_id, status):
    return client.post(
        f"/api/admin/edges/{edge_id}/status",
        json={"status": status, "note": "automated test"},
    )


def create_facility_report(client, facility_id="E1", description="Elevator is not responding"):
    response = client.post(
        "/api/reports",
        json={
            "facility_id": facility_id,
            "barrier_type": "Elevator unavailable",
            "description": description,
            "reporter_alias": "Test user",
        },
    )
    assert response.status_code == 200
    return response.json()["report"]["id"]


def review(client, report_id, decision):
    return client.post(
        f"/api/reports/{report_id}/review",
        json={"decision": decision, "review_note": "Automated test"},
    )


def test_health_checks_api_and_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "AccessPath", "version": "0.2.0"}


def test_homepage_and_static_assets_are_served(client):
    home = client.get("/")
    stylesheet = client.get("/static/styles.css")
    javascript = client.get("/static/app.js")

    assert home.status_code == 200
    assert "AccessPath" in home.text
    assert stylesheet.status_code == 200
    assert "--teal" in stylesheet.text
    assert javascript.status_code == 200
    assert "calculateRoute" in javascript.text


def test_campus_graph_is_consistent_and_exposes_expected_entities(client):
    payload = client.get("/api/map").json()
    assert len(payload["nodes"]) == 18
    assert len(payload["edges"]) == 19
    assert {facility["id"] for facility in payload["facilities"]} == {"E1", "E2"}
    node_ids = {node["id"] for node in payload["nodes"]}
    for edge in payload["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids
        assert edge["distance_m"] > 0


def test_default_wheelchair_route_is_feasible_and_avoids_stairs(client):
    response = route(client)
    assert response.status_code == 200
    result = response.json()
    assert result["accessible"] is True
    assert result["distance_m"] == 169
    assert "e_e1_vertical" in {edge["id"] for edge in result["edges"]}
    assert all(edge["type"] != "stairs" and edge["steps"] is False for edge in result["edges"])


def test_cane_profile_can_choose_stairs_when_their_generalized_cost_is_lower(client):
    response = route(client, profile="cane")
    assert response.status_code == 200
    result = response.json()
    assert any(edge["type"] == "stairs" for edge in result["edges"])


def test_same_start_and_destination_returns_zero_length_route(client):
    response = route(client, start="GATE", destination="GATE")
    assert response.status_code == 200
    result = response.json()
    assert result["node_ids"] == ["GATE"]
    assert result["edges"] == []
    assert result["distance_m"] == 0


def test_unknown_start_node_is_rejected(client):
    response = route(client, start="NOT_A_NODE")
    assert response.status_code == 400
    assert "Unknown start node" in response.json()["detail"]


def test_unknown_profile_is_rejected(client):
    response = route(client, profile="unknown_profile")
    assert response.status_code == 400
    assert "Unknown accessibility profile" in response.json()["detail"]


def test_disabling_e1_reroutes_wheelchair_user_through_e2(client):
    assert set_facility(client, "E1", "unavailable").status_code == 200
    response = route(client)
    assert response.status_code == 200
    result = response.json()
    edge_ids = {edge["id"] for edge in result["edges"]}
    assert result["distance_m"] == 183
    assert "e_e2_vertical" in edge_ids
    assert "e_e1_vertical" not in edge_ids
    assert all(edge["type"] != "stairs" for edge in result["edges"])


def test_disabling_e2_keeps_default_route_through_e1(client):
    assert set_facility(client, "E2", "unavailable").status_code == 200
    response = route(client)
    assert response.status_code == 200
    assert "e_e1_vertical" in {edge["id"] for edge in response.json()["edges"]}


def test_disabling_both_elevators_returns_no_accessible_route(client):
    set_facility(client, "E1", "unavailable")
    set_facility(client, "E2", "unavailable")
    response = route(client)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "NO_ACCESSIBLE_ROUTE"


def test_blocking_north_corridor_reroutes_through_south_elevator(client):
    response = set_edge(client, "e_north_lobby", "blocked")
    assert response.status_code == 200
    result = route(client).json()
    edge_ids = {edge["id"] for edge in result["edges"]}
    assert "e_e2_vertical" in edge_ids
    assert "e_north_lobby" not in edge_ids


def test_pending_report_does_not_change_route_but_verified_report_does(client):
    original = route(client).json()
    report_id = create_facility_report(client)

    pending_map = client.get("/api/map").json()
    assert pending_map["reports"][0]["status"] == "pending"
    assert pending_map["facilities"][0]["status"] == "available"
    assert route(client).json()["node_ids"] == original["node_ids"]

    verified = review(client, report_id, "verify")
    assert verified.status_code == 200
    assert verified.json()["report"]["status"] == "verified"
    verified_map = client.get("/api/map").json()
    e1 = next(f for f in verified_map["facilities"] if f["id"] == "E1")
    assert e1["status"] == "unavailable"
    assert e1["manual_status"] == "available"
    assert "e_e2_vertical" in {edge["id"] for edge in route(client).json()["edges"]}

    resolved = review(client, report_id, "resolve")
    assert resolved.status_code == 200
    assert resolved.json()["report"]["status"] == "resolved"
    assert "e_e1_vertical" in {edge["id"] for edge in route(client).json()["edges"]}


def test_resolving_verified_report_does_not_override_admin_maintenance_outage(client):
    set_facility(client, "E1", "unavailable")
    report_id = create_facility_report(client)
    assert review(client, report_id, "verify").status_code == 200
    assert review(client, report_id, "resolve").status_code == 200

    map_payload = client.get("/api/map").json()
    e1 = next(f for f in map_payload["facilities"] if f["id"] == "E1")
    assert e1["manual_status"] == "unavailable"
    assert e1["status"] == "unavailable"
    assert "e_e2_vertical" in {edge["id"] for edge in route(client).json()["edges"]}


def test_multiple_verified_reports_must_all_be_resolved_before_target_reopens(client):
    first = create_facility_report(client, description="Elevator failed at the ground floor")
    second = create_facility_report(client, description="Elevator still not responding")
    assert review(client, first, "verify").status_code == 200
    assert review(client, second, "verify").status_code == 200

    assert review(client, first, "resolve").status_code == 200
    e1 = next(f for f in client.get("/api/map").json()["facilities"] if f["id"] == "E1")
    assert e1["status"] == "unavailable"

    assert review(client, second, "resolve").status_code == 200
    e1 = next(f for f in client.get("/api/map").json()["facilities"] if f["id"] == "E1")
    assert e1["status"] == "available"


def test_verified_edge_report_blocks_only_reported_segment(client):
    response = client.post(
        "/api/reports",
        json={
            "edge_id": "e_north_lobby",
            "barrier_type": "Path blocked",
            "description": "Construction materials block this corridor",
        },
    )
    assert response.status_code == 200
    report_id = response.json()["report"]["id"]
    assert review(client, report_id, "verify").status_code == 200

    edge = next(e for e in client.get("/api/map").json()["edges"] if e["id"] == "e_north_lobby")
    assert edge["status"] == "blocked"
    assert edge["direct_status"] == "open"
    assert "e_e2_vertical" in {e["id"] for e in route(client).json()["edges"]}

    assert review(client, report_id, "resolve").status_code == 200
    edge = next(e for e in client.get("/api/map").json()["edges"] if e["id"] == "e_north_lobby")
    assert edge["status"] == "open"


def test_rejected_report_does_not_affect_routing(client):
    report_id = create_facility_report(client)
    assert review(client, report_id, "reject").status_code == 200
    assert "e_e1_vertical" in {edge["id"] for edge in route(client).json()["edges"]}


def test_invalid_report_target_combinations_are_rejected(client):
    payload = {"barrier_type": "Path blocked", "description": "A sufficiently long description"}
    neither = client.post("/api/reports", json=payload)
    both = client.post("/api/reports", json={**payload, "edge_id": "e_ramp_slope", "facility_id": "E1"})
    assert neither.status_code == 422
    assert both.status_code == 422


def test_unknown_report_target_is_rejected(client):
    response = client.post(
        "/api/reports",
        json={"edge_id": "does_not_exist", "barrier_type": "Path blocked", "description": "A sufficiently long description"},
    )
    assert response.status_code == 400


def test_report_review_state_transitions_are_enforced(client):
    report_id = create_facility_report(client)
    assert review(client, report_id, "resolve").status_code == 409
    assert review(client, report_id, "under_review").status_code == 200
    assert review(client, report_id, "under_review").status_code == 409
    assert review(client, report_id, "verify").status_code == 200
    assert review(client, report_id, "reject").status_code == 409
    assert review(client, report_id, "resolve").status_code == 200
    assert review(client, report_id, "verify").status_code == 409


def test_unknown_report_id_returns_404(client):
    response = review(client, 999999, "verify")
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        ("/api/admin/facilities/E1/status", {"status": "broken"}),
        ("/api/admin/edges/e_ramp_slope/status", {"status": "closed"}),
    ],
)
def test_invalid_status_values_are_rejected(client, endpoint, body):
    response = client.post(endpoint, json=body)
    assert response.status_code == 422


def test_unknown_facility_and_edge_admin_targets_return_404(client):
    facility = client.post("/api/admin/facilities/E99/status", json={"status": "unavailable"})
    edge = client.post("/api/admin/edges/e_missing/status", json={"status": "blocked"})
    assert facility.status_code == 404
    assert edge.status_code == 404


def test_extra_request_fields_and_whitespace_only_report_are_rejected(client):
    unknown = client.post("/api/route", json={"start": "GATE", "destination": "CS_DEPT", "profile": "wheelchair", "admin": True})
    whitespace = client.post(
        "/api/reports",
        json={"facility_id": "E1", "barrier_type": "   ", "description": "    "},
    )
    assert unknown.status_code == 422
    assert whitespace.status_code == 422


def test_admin_edge_block_is_not_cleared_by_resolving_report(client):
    set_edge(client, "e_north_lobby", "blocked")
    report = client.post(
        "/api/reports",
        json={"edge_id": "e_north_lobby", "barrier_type": "Path blocked", "description": "Temporary obstruction on corridor"},
    ).json()["report"]
    assert review(client, report["id"], "verify").status_code == 200
    assert review(client, report["id"], "resolve").status_code == 200
    edge = next(e for e in client.get("/api/map").json()["edges"] if e["id"] == "e_north_lobby")
    assert edge["direct_status"] == "blocked"
    assert edge["status"] == "blocked"


def test_accessibility_hard_constraints_reject_width_slope_and_stairs():
    empty_state = {"synthetic_edge": {"status": "open"}}
    base = {
        "id": "synthetic_edge",
        "source": "A",
        "target": "B",
        "distance_m": 10,
        "type": "corridor",
        "width_m": 1.2,
        "slope_pct": 0,
        "surface": "smooth",
        "steps": False,
    }

    too_narrow = {**base, "width_m": 0.8}
    too_steep = {**base, "slope_pct": 7.0}
    stairs = {**base, "type": "stairs", "steps": True}

    assert main.edge_is_feasible(too_narrow, "wheelchair", empty_state, empty_state)[0] is False
    assert main.edge_is_feasible(too_steep, "wheelchair", empty_state, empty_state)[0] is False
    assert main.edge_is_feasible(stairs, "wheelchair", empty_state, empty_state)[0] is False
    assert main.edge_is_feasible(base, "wheelchair", empty_state, empty_state)[0] is True


def test_effective_edge_status_combines_maintenance_and_verified_reports():
    edge = {
        "id": "edge-1",
        "facility_id": "E1",
    }
    open_edge = {"edge-1": {"status": "open"}}
    available_facility = {"E1": {"status": "available"}}

    assert main.effective_edge_status(edge, open_edge, available_facility) == "open"
    assert main.effective_edge_status(
        edge, open_edge, available_facility, verified_edge_reports={"edge-1": [1]}
    ) == "blocked"
    assert main.effective_edge_status(
        edge, open_edge, available_facility, verified_facility_reports={"E1": [2]}
    ) == "blocked"
    assert main.effective_edge_status(
        edge, open_edge, {"E1": {"status": "unavailable"}}
    ) == "blocked"


def test_physical_distance_is_separate_from_generalized_cost(client):
    result = route(client).json()
    physical_distance = sum(edge["distance_m"] for edge in result["edges"])
    generalized_cost = sum(edge["generalized_cost"] for edge in result["edges"])
    assert result["distance_m"] == physical_distance == 169
    assert result["generalized_cost"] == pytest.approx(generalized_cost)
    assert result["generalized_cost"] != result["distance_m"]


def test_admin_manual_status_and_effective_status_are_both_returned(client):
    set_facility(client, "E1", "unavailable")
    e1 = next(f for f in client.get("/api/map").json()["facilities"] if f["id"] == "E1")
    assert e1["manual_status"] == "unavailable"
    assert e1["status"] == "unavailable"


def test_report_alias_defaults_to_anonymous_when_blank(client):
    response = client.post(
        "/api/reports",
        json={
            "facility_id": "E1",
            "barrier_type": "Elevator unavailable",
            "description": "Elevator has stopped.",
            "reporter_alias": "   ",
        },
    )
    assert response.status_code == 200
    assert response.json()["report"]["reporter_alias"] == "Anonymous"


def test_admin_status_api_reports_effective_state_after_verified_barrier(client):
    report_id = create_facility_report(client, facility_id="E1")
    assert review(client, report_id, "verify").status_code == 200

    response = set_facility(client, "E1", "available")
    assert response.status_code == 200
    assert response.json()["manual_status"] == "available"
    assert response.json()["status"] == "unavailable"


def test_edge_admin_status_api_reports_effective_state_after_verified_barrier(client):
    created = client.post(
        "/api/reports",
        json={"edge_id": "e_north_lobby", "barrier_type": "Path blocked", "description": "Corridor is obstructed."},
    ).json()["report"]
    assert review(client, created["id"], "verify").status_code == 200

    response = set_edge(client, "e_north_lobby", "open")
    assert response.status_code == 200
    assert response.json()["manual_status"] == "open"
    assert response.json()["status"] == "blocked"



def test_missing_accessibility_measurements_fail_closed():
    edge_state = {"synthetic_edge": {"status": "open"}}
    incomplete_width = {
        "id": "synthetic_edge", "type": "corridor", "steps": False,
        "distance_m": 10, "slope_pct": 0,
    }
    incomplete_slope = {
        "id": "synthetic_edge", "type": "corridor", "steps": False,
        "distance_m": 10, "width_m": 1.2,
    }

    width_result = main.edge_is_feasible(incomplete_width, "wheelchair", edge_state, {})
    slope_result = main.edge_is_feasible(incomplete_slope, "wheelchair", edge_state, {})
    assert width_result == (False, "synthetic_edge has no verified width value")
    assert slope_result == (False, "synthetic_edge has no verified slope value")


def test_missing_infrastructure_status_fails_closed():
    edge = {"id": "edge-1", "facility_id": "E1"}
    # A missing direct edge status or facility state must not be assumed operational.
    assert main.effective_edge_status(edge, {}, {"E1": {"status": "available"}}) == "unknown"
    assert main.effective_edge_status(
        edge, {"edge-1": {"status": "open"}}, {}
    ) == "blocked"
