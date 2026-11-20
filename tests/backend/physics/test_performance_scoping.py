"""Performance routes honour project scoping (404, never 403) and the role policy."""
import pytest

from . import deficit_synth as ds

Q = "start=2026-03-18T00:00:00Z&end=2026-03-21T00:00:00Z"
BODY = {"pi_warning": 0.93, "pi_critical": 0.85, "deficit_min_clear_hours": 3}


@pytest.fixture
def plants(db_session, two_projects, users_mode):
    out = {}
    for tag, park in (("a", "PARK_A"), ("b", "PARK_B"), ("x", None)):
        plant, _, strs = ds.make_plant(db_session)
        plant.park_id = park
        db_session.commit()
        out[tag] = (plant.id, strs[0].id)
    return out


def _login(make_user, login, role, project_ids):
    make_user(f"{role}{len(project_ids)}@axalon.test", role, project_ids=project_ids)
    return login(f"{role}{len(project_ids)}@axalon.test")


@pytest.mark.parametrize("tag", ["b", "x"])  # another project's park, and a plant with no park
def test_other_park_and_parkless_plants_are_404(client, plants, two_projects, make_user, login, tag):
    pid, sid = plants[tag]
    viewer = _login(make_user, login, "viewer", [two_projects["p1"]])
    op = _login(make_user, login, "operator", [two_projects["p1"]])
    assert client.get(f"/api/v1/performance/{pid}?{Q}", headers=viewer).status_code == 404
    assert client.get(f"/api/v1/strings/{sid}/peers?{Q}", headers=viewer).status_code == 404
    assert client.post(f"/api/v1/performance/{pid}/scan?{Q}", headers=op).status_code == 404
    assert client.put(f"/api/v1/performance/{pid}/thresholds", json=BODY, headers=op).status_code == 404


def test_own_park_is_visible_and_writable(client, plants, two_projects, make_user, login):
    pid, _ = plants["a"]
    viewer = _login(make_user, login, "viewer", [two_projects["p1"]])
    op = _login(make_user, login, "operator", [two_projects["p1"]])
    assert client.get(f"/api/v1/performance/{pid}?{Q}", headers=viewer).status_code == 200
    assert client.put(f"/api/v1/performance/{pid}/thresholds", json=BODY, headers=op).status_code == 200


def test_technician_cannot_write(client, plants, two_projects, make_user, login):
    pid, _ = plants["a"]
    tech = _login(make_user, login, "technician", [two_projects["p1"]])
    assert client.put(f"/api/v1/performance/{pid}/thresholds", json=BODY, headers=tech).status_code == 403
    assert client.post(f"/api/v1/performance/{pid}/scan?{Q}", headers=tech).status_code == 403


def test_tracker_plant_thresholds_still_settable(client, plants, db_session, two_projects, make_user, login):
    from solardoctor.physics.models import Plant
    from solardoctor.physics.tracker import TRACKER_MARKER
    pid, _ = plants["a"]
    plant = db_session.get(Plant, pid)
    plant.location = f"Pune {TRACKER_MARKER}"
    db_session.commit()
    op = _login(make_user, login, "operator", [two_projects["p1"]])
    assert client.put(f"/api/v1/performance/{pid}/thresholds", json=BODY, headers=op).status_code == 200
