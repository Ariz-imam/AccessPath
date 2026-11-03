from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = PROJECT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("ACCESSPATH_DB_PATH", str(DATA_DIR / "accesspath.db"))).expanduser().resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AccessPath MVP API",
    description="Accessibility-aware campus routing with simulated infrastructure failures and barrier reports.",
    version="0.2.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# A small, hand-mapped demo graph. Coordinates are schematic SVG coordinates, not GPS coordinates.
NODES: list[dict[str, Any]] = [
    {"id": "GATE", "name": "Main Gate", "floor": "Outdoor", "x": 65, "y": 365, "kind": "entrance", "dx": 0, "dy": 24},
    {"id": "JUNCTION", "name": "Path Junction", "floor": "Outdoor", "x": 175, "y": 365, "kind": "junction", "dx": 0, "dy": 24},
    {"id": "RAMP_BOTTOM", "name": "Ramp Bottom", "floor": "Outdoor", "x": 265, "y": 325, "kind": "ramp", "dx": -10, "dy": 23},
    {"id": "RAMP_TOP", "name": "Ramp Top", "floor": "Ground Floor", "x": 345, "y": 255, "kind": "ramp", "dx": -12, "dy": -15},
    {"id": "NORTH_ENT", "name": "North Entrance", "floor": "Ground Floor", "x": 430, "y": 255, "kind": "entrance", "dx": 0, "dy": -16},
    {"id": "LOBBY_G", "name": "Main Lobby", "floor": "Ground Floor", "x": 510, "y": 255, "kind": "junction", "dx": 0, "dy": -16},
    {"id": "E1_G", "name": "Elevator E1 · Ground", "floor": "Ground Floor", "x": 610, "y": 255, "kind": "elevator", "dx": 0, "dy": -16},
    {"id": "STAIR_G", "name": "Stairs · Ground", "floor": "Ground Floor", "x": 510, "y": 315, "kind": "stairs", "dx": 0, "dy": 22},
    {"id": "SOUTH_APPROACH", "name": "South Approach", "floor": "Outdoor", "x": 370, "y": 365, "kind": "junction", "dx": 0, "dy": 24},
    {"id": "SOUTH_ENT", "name": "South Entrance", "floor": "Ground Floor", "x": 770, "y": 255, "kind": "entrance", "dx": 0, "dy": -16},
    {"id": "SOUTH_CORR", "name": "South Corridor", "floor": "Ground Floor", "x": 690, "y": 255, "kind": "corridor", "dx": 0, "dy": -16},
    {"id": "E2_G", "name": "Elevator E2 · Ground", "floor": "Ground Floor", "x": 850, "y": 255, "kind": "elevator", "dx": 0, "dy": -16},
    {"id": "STAIR_F1", "name": "Stairs · First", "floor": "First Floor", "x": 510, "y": 120, "kind": "stairs", "dx": 0, "dy": -15},
    {"id": "E1_F1", "name": "Elevator E1 · First", "floor": "First Floor", "x": 610, "y": 95, "kind": "elevator", "dx": 0, "dy": -15},
    {"id": "FIRST_CORR", "name": "First-Floor Corridor", "floor": "First Floor", "x": 720, "y": 95, "kind": "corridor", "dx": 0, "dy": -15},
    {"id": "E2_F1", "name": "Elevator E2 · First", "floor": "First Floor", "x": 850, "y": 95, "kind": "elevator", "dx": 0, "dy": -15},
    {"id": "CS_DEPT", "name": "Computer Science", "floor": "First Floor", "x": 750, "y": 145, "kind": "destination", "dx": 0, "dy": 22},
    {"id": "LIBRARY", "name": "Library", "floor": "First Floor", "x": 875, "y": 145, "kind": "destination", "dx": 0, "dy": 22},
]

EDGES: list[dict[str, Any]] = [
    {"id": "e_gate_junction", "source": "GATE", "target": "JUNCTION", "distance_m": 28, "type": "walkway", "width_m": 2.4, "slope_pct": 0, "surface": "concrete", "steps": False},
    {"id": "e_junction_ramp_bottom", "source": "JUNCTION", "target": "RAMP_BOTTOM", "distance_m": 18, "type": "walkway", "width_m": 2.0, "slope_pct": 1, "surface": "concrete", "steps": False},
    {"id": "e_ramp_slope", "source": "RAMP_BOTTOM", "target": "RAMP_TOP", "distance_m": 52, "type": "ramp", "width_m": 1.5, "slope_pct": 4, "surface": "concrete", "steps": False},
    {"id": "e_ramp_north", "source": "RAMP_TOP", "target": "NORTH_ENT", "distance_m": 12, "type": "corridor", "width_m": 1.8, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_north_lobby", "source": "NORTH_ENT", "target": "LOBBY_G", "distance_m": 12, "type": "corridor", "width_m": 1.8, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_lobby_e1", "source": "LOBBY_G", "target": "E1_G", "distance_m": 7, "type": "corridor", "width_m": 1.8, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_e1_vertical", "source": "E1_G", "target": "E1_F1", "distance_m": 12, "type": "elevator", "facility_id": "E1", "width_m": 1.1, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_e1_firstcorr", "source": "E1_F1", "target": "FIRST_CORR", "distance_m": 12, "type": "corridor", "width_m": 1.8, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_firstcorr_cs", "source": "FIRST_CORR", "target": "CS_DEPT", "distance_m": 16, "type": "corridor", "width_m": 1.6, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_junction_south", "source": "JUNCTION", "target": "SOUTH_APPROACH", "distance_m": 46, "type": "walkway", "width_m": 2.0, "slope_pct": 1, "surface": "concrete", "steps": False},
    {"id": "e_south_approach_entry", "source": "SOUTH_APPROACH", "target": "SOUTH_ENT", "distance_m": 42, "type": "walkway", "width_m": 1.7, "slope_pct": 2, "surface": "concrete", "steps": False},
    {"id": "e_south_entry_corr", "source": "SOUTH_ENT", "target": "SOUTH_CORR", "distance_m": 15, "type": "corridor", "width_m": 1.8, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_south_corr_e2", "source": "SOUTH_CORR", "target": "E2_G", "distance_m": 8, "type": "corridor", "width_m": 1.8, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_e2_vertical", "source": "E2_G", "target": "E2_F1", "distance_m": 16, "type": "elevator", "facility_id": "E2", "width_m": 1.1, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_e2_firstcorr", "source": "E2_F1", "target": "FIRST_CORR", "distance_m": 12, "type": "corridor", "width_m": 1.8, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_lobby_stairs", "source": "LOBBY_G", "target": "STAIR_G", "distance_m": 4, "type": "corridor", "width_m": 1.2, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_stairs_vertical", "source": "STAIR_G", "target": "STAIR_F1", "distance_m": 7, "type": "stairs", "width_m": 1.2, "slope_pct": 0, "surface": "steps", "steps": True},
    {"id": "e_stairs_firstcorr", "source": "STAIR_F1", "target": "FIRST_CORR", "distance_m": 6, "type": "corridor", "width_m": 1.2, "slope_pct": 0, "surface": "smooth", "steps": False},
    {"id": "e_cs_library", "source": "CS_DEPT", "target": "LIBRARY", "distance_m": 18, "type": "corridor", "width_m": 1.6, "slope_pct": 0, "surface": "smooth", "steps": False},
]

FACILITIES: list[dict[str, Any]] = [
    {"id": "E1", "name": "Elevator E1 (North Core)", "type": "elevator", "description": "Connects the ground floor to the first floor."},
    {"id": "E2", "name": "Elevator E2 (South Core)", "type": "elevator", "description": "Alternative elevator connecting the ground floor to the first floor."},
]

PROFILES: dict[str, dict[str, Any]] = {
    "wheelchair": {
        "label": "Manual wheelchair",
        "description": "Avoid stairs; enforce width and ramp-slope requirements.",
        "min_width_m": 0.9,
        "max_slope_pct": 6.0,
        "avoid_stairs": True,
    },
    "cane": {
        "label": "Cane or walker",
        "description": "Allow stairs where useful, with higher effort cost and configurable limits.",
        "min_width_m": 0.75,
        "max_slope_pct": 10.0,
        "avoid_stairs": False,
    },
    "low_endurance": {
        "label": "Reduced walking endurance",
        "description": "Prefer lower-effort paths and strongly penalize stairs and steep ramps.",
        "min_width_m": 0.75,
        "max_slope_pct": 8.0,
        "avoid_stairs": False,
    },
}

EDGE_BY_ID = {e["id"]: e for e in EDGES}
FACILITY_BY_ID = {f["id"]: f for f in FACILITIES}
NODE_BY_ID = {n["id"]: n for n in NODES}


def now_iso() -> str:
    """Return a timezone-aware UTC timestamp suitable for persistence."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db_conn():
    """Open a short-lived SQLite connection and commit successful operations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def validate_demo_graph() -> None:
    """Fail early if the hand-authored demonstration graph is inconsistent."""
    node_ids = [node["id"] for node in NODES]
    edge_ids = [edge["id"] for edge in EDGES]
    facility_ids = {facility["id"] for facility in FACILITIES}

    if len(node_ids) != len(set(node_ids)):
        raise ValueError("Campus graph contains duplicate node IDs")
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError("Campus graph contains duplicate edge IDs")
    if len(facility_ids) != len(FACILITIES):
        raise ValueError("Campus graph contains duplicate facility IDs")

    node_id_set = set(node_ids)
    for edge in EDGES:
        if edge["source"] not in node_id_set or edge["target"] not in node_id_set:
            raise ValueError(f"Edge {edge['id']} references an unknown node")
        if edge["source"] == edge["target"]:
            raise ValueError(f"Edge {edge['id']} cannot connect a node to itself")
        if float(edge["distance_m"]) <= 0:
            raise ValueError(f"Edge {edge['id']} must have a positive distance")
        if float(edge["width_m"]) < 0 or float(edge["slope_pct"]) < 0:
            raise ValueError(f"Edge {edge['id']} has an invalid width or slope")
        facility_id = edge.get("facility_id")
        if facility_id and facility_id not in facility_ids:
            raise ValueError(f"Edge {edge['id']} references unknown facility {facility_id}")


validate_demo_graph()


def init_db() -> None:
    """Create the local database schema and seed statuses for the demo graph."""
    with db_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS edge_state (
                edge_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('open', 'blocked')),
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS facility_state (
                facility_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('available', 'unavailable')),
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_id TEXT,
                facility_id TEXT,
                barrier_type TEXT NOT NULL,
                description TEXT NOT NULL,
                reporter_alias TEXT NOT NULL DEFAULT 'Anonymous',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'under_review', 'verified', 'rejected', 'resolved')),
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                review_note TEXT NOT NULL DEFAULT '',
                CHECK ((edge_id IS NOT NULL AND facility_id IS NULL)
                    OR (edge_id IS NULL AND facility_id IS NOT NULL))
            );
            CREATE INDEX IF NOT EXISTS idx_reports_status_edge
                ON reports(status, edge_id);
            CREATE INDEX IF NOT EXISTS idx_reports_status_facility
                ON reports(status, facility_id);
            """
        )
        stamp = now_iso()
        for edge in EDGES:
            conn.execute(
                "INSERT OR IGNORE INTO edge_state(edge_id,status,note,updated_at) VALUES(?,?,?,?)",
                (edge["id"], "open", "", stamp),
            )
        for facility in FACILITIES:
            conn.execute(
                "INSERT OR IGNORE INTO facility_state(facility_id,status,note,updated_at) VALUES(?,?,?,?)",
                (facility["id"], "available", "", stamp),
            )


# The default local database is initialized on import so `uvicorn app.main:app` works
# without a separate migration command. Tests override DB_PATH with a temporary file.
init_db()


def _rows_to_state(rows: list[sqlite3.Row], key_name: str) -> dict[str, dict[str, str]]:
    return {
        row[key_name]: {
            "status": row["status"],
            "note": row["note"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    }


def get_current_state() -> dict[str, Any]:
    """Read all routing state in one DB connection for a consistent snapshot."""
    with db_conn() as conn:
        conn.execute("BEGIN")
        edge_rows = conn.execute(
            "SELECT edge_id,status,note,updated_at FROM edge_state"
        ).fetchall()
        facility_rows = conn.execute(
            "SELECT facility_id,status,note,updated_at FROM facility_state"
        ).fetchall()
        reports = [dict(row) for row in conn.execute(
            "SELECT * FROM reports ORDER BY id DESC"
        ).fetchall()]
        active_reports = conn.execute(
            "SELECT id,edge_id,facility_id FROM reports WHERE status='verified'"
        ).fetchall()

    verified_edge_reports: dict[str, list[int]] = {}
    verified_facility_reports: dict[str, list[int]] = {}
    for row in active_reports:
        if row["edge_id"]:
            verified_edge_reports.setdefault(row["edge_id"], []).append(row["id"])
        elif row["facility_id"]:
            verified_facility_reports.setdefault(row["facility_id"], []).append(row["id"])

    return {
        "edge_states": _rows_to_state(edge_rows, "edge_id"),
        "facility_states": _rows_to_state(facility_rows, "facility_id"),
        "reports": reports,
        "verified_edge_reports": verified_edge_reports,
        "verified_facility_reports": verified_facility_reports,
    }


def effective_edge_status(
    edge: dict[str, Any],
    edge_states: dict[str, Any],
    facility_states: dict[str, Any],
    verified_edge_reports: dict[str, list[int]] | None = None,
    verified_facility_reports: dict[str, list[int]] | None = None,
) -> str:
    """Combine direct admin state with independently verified barrier reports."""
    verified_edge_reports = verified_edge_reports or {}
    verified_facility_reports = verified_facility_reports or {}

    direct_status = edge_states.get(edge["id"], {}).get("status", "unknown")
    if direct_status != "open":
        return direct_status
    if verified_edge_reports.get(edge["id"]):
        return "blocked"

    facility_id = edge.get("facility_id")
    if facility_id:
        facility_status = facility_states.get(facility_id, {}).get("status", "unknown")
        if facility_status != "available" or verified_facility_reports.get(facility_id):
            return "blocked"
    return "open"


def edge_cost(edge: dict[str, Any], profile_key: str) -> float:
    """Return generalized route cost; this is not a physical-distance estimate."""
    profile = PROFILES[profile_key]
    cost = float(edge["distance_m"])
    kind = edge["type"]

    if kind == "stairs":
        if profile_key == "low_endurance":
            cost *= 3.2
        elif profile_key == "cane":
            cost *= 2.0
        else:
            cost *= 1.6
    elif kind == "elevator":
        # Demonstration-only proxy for waiting/transition inconvenience.
        cost += 9.0 if profile_key == "wheelchair" else 14.0

    if kind == "ramp":
        cost *= 1.0 + float(edge.get("slope_pct", 0)) / 20.0

    # Surface cost is independent of segment type, so it can be combined with
    # ramp/stairs/elevator costs if a real campus map contains such a combination.
    if edge.get("surface") in {"gravel", "uneven"}:
        cost *= 1.35 if profile_key in {"wheelchair", "low_endurance"} else 1.15

    if profile_key == "low_endurance":
        cost *= 1.12
    return max(cost, 0.001)


def edge_is_feasible(
    edge: dict[str, Any],
    profile_key: str,
    edge_states: dict[str, Any],
    facility_states: dict[str, Any],
    verified_edge_reports: dict[str, list[int]] | None = None,
    verified_facility_reports: dict[str, list[int]] | None = None,
) -> tuple[bool, str | None]:
    """Apply hard accessibility and live-state constraints to a route segment."""
    profile = PROFILES[profile_key]
    status = effective_edge_status(
        edge,
        edge_states,
        facility_states,
        verified_edge_reports,
        verified_facility_reports,
    )
    if status != "open":
        return False, f"{edge['id']} is {status}"
    width_m = edge.get("width_m")
    if width_m is None:
        return False, f"{edge['id']} has no verified width value"
    if float(width_m) < float(profile["min_width_m"]):
        return False, f"{edge['id']} is narrower than this profile's configured minimum width"

    slope_pct = edge.get("slope_pct")
    if slope_pct is None:
        return False, f"{edge['id']} has no verified slope value"
    if float(slope_pct) > float(profile["max_slope_pct"]):
        return False, f"{edge['id']} exceeds this profile's configured slope limit"
    if profile["avoid_stairs"] and (edge.get("steps") or edge["type"] == "stairs"):
        return False, f"{edge['id']} contains stairs"
    return True, None


def compute_route(start: str, destination: str, profile_key: str) -> dict[str, Any]:
    if start not in NODE_BY_ID:
        raise HTTPException(status_code=400, detail=f"Unknown start node: {start}")
    if destination not in NODE_BY_ID:
        raise HTTPException(status_code=400, detail=f"Unknown destination node: {destination}")
    if profile_key not in PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown accessibility profile: {profile_key}")

    if start == destination:
        return {
            "profile": profile_key,
            "start": start,
            "destination": destination,
            "node_ids": [start],
            "nodes": [NODE_BY_ID[start]],
            "edges": [],
            "distance_m": 0,
            "generalized_cost": 0,
            "accessible": True,
            "message": "You are already at the destination.",
        }

    snapshot = get_current_state()
    edge_states = snapshot["edge_states"]
    facility_states = snapshot["facility_states"]
    verified_edge_reports = snapshot["verified_edge_reports"]
    verified_facility_reports = snapshot["verified_facility_reports"]

    graph = nx.Graph()
    graph.add_nodes_from(NODE_BY_ID.keys())
    usable_edges: dict[str, dict[str, Any]] = {}

    for edge in EDGES:
        feasible, _reason = edge_is_feasible(
            edge,
            profile_key,
            edge_states,
            facility_states,
            verified_edge_reports,
            verified_facility_reports,
        )
        if not feasible:
            continue
        graph.add_edge(
            edge["source"],
            edge["target"],
            weight=edge_cost(edge, profile_key),
            edge_id=edge["id"],
        )
        usable_edges[edge["id"]] = edge

    try:
        node_ids = nx.shortest_path(
            graph,
            source=start,
            target=destination,
            weight="weight",
            method="dijkstra",
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NO_ACCESSIBLE_ROUTE",
                "message": "No feasible route is available for the selected profile under current infrastructure conditions.",
                "hint": "Check elevator status, blocked segments, or choose a reachable destination.",
            },
        )

    route_edges: list[dict[str, Any]] = []
    total_distance = 0.0
    total_cost = 0.0
    for source_id, target_id in zip(node_ids, node_ids[1:]):
        graph_data = graph[source_id][target_id]
        edge = usable_edges[graph_data["edge_id"]]
        route_edges.append({
            **edge,
            "status": "open",
            "source_name": NODE_BY_ID[source_id]["name"],
            "target_name": NODE_BY_ID[target_id]["name"],
            "generalized_cost": round(edge_cost(edge, profile_key), 1),
        })
        total_distance += float(edge["distance_m"])
        total_cost += edge_cost(edge, profile_key)

    return {
        "profile": profile_key,
        "start": start,
        "destination": destination,
        "node_ids": node_ids,
        "nodes": [NODE_BY_ID[node_id] for node_id in node_ids],
        "edges": route_edges,
        "distance_m": round(total_distance),
        "generalized_cost": round(total_cost, 1),
        "accessible": True,
        "message": f"Found a feasible route with {len(route_edges)} segments.",
    }


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RouteRequest(InputModel):
    start: str = Field(default="GATE", min_length=1, max_length=80)
    destination: str = Field(default="CS_DEPT", min_length=1, max_length=80)
    profile: str = Field(default="wheelchair", min_length=1, max_length=40)


class StatusNote(InputModel):
    note: str = Field(default="", max_length=300)


class FacilityStatusUpdate(StatusNote):
    status: Literal["available", "unavailable"]


class EdgeStatusUpdate(StatusNote):
    status: Literal["open", "blocked"]


class ReportCreate(InputModel):
    edge_id: str | None = Field(default=None, min_length=1, max_length=100)
    facility_id: str | None = Field(default=None, min_length=1, max_length=100)
    barrier_type: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=4, max_length=800)
    reporter_alias: str = Field(default="Anonymous", max_length=80)

    @model_validator(mode="after")
    def exactly_one_target(self):
        if bool(self.edge_id) == bool(self.facility_id):
            raise ValueError("Provide exactly one of edge_id or facility_id")
        return self


class ReportReview(InputModel):
    decision: Literal["under_review", "verify", "reject", "resolve"]
    review_note: str = Field(default="", max_length=300)


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    # Include a lightweight DB read so this endpoint checks the persistence layer too.
    with db_conn() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "app": "AccessPath", "version": "0.2.0"}


@app.get("/api/map")
def get_map():
    snapshot = get_current_state()
    edge_states = snapshot["edge_states"]
    facility_states = snapshot["facility_states"]
    verified_edge_reports = snapshot["verified_edge_reports"]
    verified_facility_reports = snapshot["verified_facility_reports"]

    edges_out = []
    for edge in EDGES:
        direct_state = edge_states.get(edge["id"], {
            "status": "unknown", "note": "No status record", "updated_at": ""
        })
        effective_status = effective_edge_status(
            edge,
            edge_states,
            facility_states,
            verified_edge_reports,
            verified_facility_reports,
        )
        edges_out.append({
            **edge,
            "status": effective_status,
            "direct_status": direct_state["status"],
            "status_note": direct_state["note"],
            "verified_report_ids": verified_edge_reports.get(edge["id"], []),
            "updated_at": direct_state["updated_at"],
        })

    facilities_out = []
    for facility in FACILITIES:
        direct_state = facility_states.get(facility["id"], {
            "status": "unknown", "note": "No status record", "updated_at": ""
        })
        verified_report_ids = verified_facility_reports.get(facility["id"], [])
        effective_status = (
            "unavailable"
            if direct_state["status"] != "available" or verified_report_ids
            else "available"
        )
        facilities_out.append({
            **facility,
            "status": effective_status,
            "manual_status": direct_state["status"],
            "note": direct_state["note"],
            "verified_report_ids": verified_report_ids,
            "updated_at": direct_state["updated_at"],
        })

    return {
        "nodes": NODES,
        "edges": edges_out,
        "facilities": facilities_out,
        "profiles": PROFILES,
        "reports": snapshot["reports"],
        "map_note": "Schematic demo campus. Coordinates and facility attributes are illustrative, not a verified real-world accessibility survey.",
    }


@app.post("/api/route")
def route(request: RouteRequest):
    return compute_route(request.start, request.destination, request.profile)


@app.post("/api/admin/facilities/{facility_id}/status")
def set_facility_status(facility_id: str, request: FacilityStatusUpdate):
    if facility_id not in FACILITY_BY_ID:
        raise HTTPException(status_code=404, detail="Unknown facility")
    with db_conn() as conn:
        conn.execute(
            """INSERT INTO facility_state(facility_id,status,note,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(facility_id) DO UPDATE SET
                   status=excluded.status, note=excluded.note, updated_at=excluded.updated_at""",
            (facility_id, request.status, request.note, now_iso()),
        )
    snapshot = get_current_state()
    verified_report_ids = snapshot["verified_facility_reports"].get(facility_id, [])
    effective_status = (
        "unavailable"
        if request.status == "unavailable" or verified_report_ids
        else "available"
    )
    return {
        "ok": True,
        "facility_id": facility_id,
        "manual_status": request.status,
        "status": effective_status,
    }


@app.post("/api/admin/edges/{edge_id}/status")
def set_edge_status(edge_id: str, request: EdgeStatusUpdate):
    if edge_id not in EDGE_BY_ID:
        raise HTTPException(status_code=404, detail="Unknown route segment")
    with db_conn() as conn:
        conn.execute(
            """INSERT INTO edge_state(edge_id,status,note,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(edge_id) DO UPDATE SET
                   status=excluded.status, note=excluded.note, updated_at=excluded.updated_at""",
            (edge_id, request.status, request.note, now_iso()),
        )
    snapshot = get_current_state()
    edge = EDGE_BY_ID[edge_id]
    effective_status = effective_edge_status(
        edge,
        snapshot["edge_states"],
        snapshot["facility_states"],
        snapshot["verified_edge_reports"],
        snapshot["verified_facility_reports"],
    )
    return {
        "ok": True,
        "edge_id": edge_id,
        "manual_status": request.status,
        "status": effective_status,
    }


@app.post("/api/reports")
def create_report(request: ReportCreate):
    if request.edge_id and request.edge_id not in EDGE_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown route segment")
    if request.facility_id and request.facility_id not in FACILITY_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown facility")

    reporter_alias = request.reporter_alias or "Anonymous"
    with db_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO reports(edge_id,facility_id,barrier_type,description,reporter_alias,status,created_at)
               VALUES(?,?,?,?,?,'pending',?)""",
            (
                request.edge_id,
                request.facility_id,
                request.barrier_type,
                request.description,
                reporter_alias,
                now_iso(),
            ),
        )
        report_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    return {"ok": True, "report": dict(row)}


REPORT_TRANSITIONS = {
    "pending": {"under_review", "verify", "reject"},
    "under_review": {"verify", "reject"},
    "verified": {"resolve"},
    "rejected": set(),
    "resolved": set(),
}


@app.post("/api/reports/{report_id}/review")
def review_report(report_id: int, request: ReportReview):
    with db_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Report not found")

        current_status = row["status"]
        if request.decision not in REPORT_TRANSITIONS[current_status]:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot change a {current_status} report to {request.decision}",
            )

        # Verified reports act as independent routing restrictions. Resolving a report
        # removes only that report's restriction; it never overwrites a separate admin
        # maintenance status or another verified report for the same target.
        new_status = {
            "under_review": "under_review",
            "verify": "verified",
            "reject": "rejected",
            "resolve": "resolved",
        }[request.decision]
        conn.execute(
            "UPDATE reports SET status=?, reviewed_at=?, review_note=? WHERE id=?",
            (new_status, now_iso(), request.review_note, report_id),
        )
        updated = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()

    return {"ok": True, "report": dict(updated)}
