"""Users-mode access for routers built in parallel with the auth work.

Fault photos, work orders, orthomosaic generation, manual park layouts and test
alerts were written against keyless mode, then given role policies and park
scoping when merged. These tests pin that: no cross-project reads, no
share-link access to internal O&M areas, admin-only alert tests.
"""
import pytest


@pytest.fixture
def north_operator(client, users_mode, make_user, login, two_projects):
    make_user("op@axalon.test", "operator", project_ids=[two_projects["p1"]])
    return login("op@axalon.test")


@pytest.fixture
def north_share(client, north_operator, two_projects):
    r = client.post(
        "/share-links",
        json={"project_id": two_projects["p1"], "label": "client", "expires_in_days": 7},
        headers=north_operator,
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


@pytest.mark.parametrize(
    "path",
    [
        "/faults/{fault}/photos",
        "/faults/{fault}/photos/1",
        "/parks/{park}/work-orders",
        "/parks/{park}/orthos/generate",
        "/parks/{park}/orthos/generate/odm-doesnotexist",
        "/park/{park}/layout",
    ],
)
@pytest.mark.parametrize("tag", ["b", "x"])  # other project, and unassigned (admin-only)
def test_out_of_scope_reads_are_404(client, north_operator, two_projects, path, tag):
    url = path.format(park=f"PARK_{tag.upper()}", fault=two_projects[f"fault_{tag}"])

    assert client.get(url, headers=north_operator).status_code == 404


@pytest.mark.parametrize(
    "method, path",
    [
        ("delete", "/faults/{fault}/photos/1"),
        ("delete", "/parks/{park}/orthos/generate/odm-doesnotexist"),
        ("delete", "/park/{park}/layout"),
    ],
)
def test_out_of_scope_writes_are_404(client, north_operator, two_projects, method, path):
    url = path.format(park="PARK_B", fault=two_projects["fault_b"])

    assert getattr(client, method)(url, headers=north_operator).status_code == 404


def test_out_of_scope_photo_upload_is_404(client, north_operator, two_projects):
    files = {"file": ("proof.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")}

    r = client.post(f"/faults/{two_projects['fault_b']}/photos", files=files, headers=north_operator)

    assert r.status_code == 404


def test_out_of_scope_layout_upload_is_404(client, north_operator):
    files = {"file": ("layout.json", b"{}", "application/json")}

    assert client.post("/park/PARK_B/layout", files=files, headers=north_operator).status_code == 404


def test_in_scope_reads_work(client, north_operator, two_projects):
    assert client.get(f"/faults/{two_projects['fault_a']}/photos", headers=north_operator).status_code == 200
    assert client.get("/parks/PARK_A/work-orders", headers=north_operator).status_code == 200
    assert client.get("/park/PARK_A/layout", headers=north_operator).status_code == 200


def test_share_link_sees_own_project_photos_only(client, north_share, two_projects):
    assert client.get(f"/faults/{two_projects['fault_a']}/photos?share={north_share}").status_code == 200
    assert client.get(f"/faults/{two_projects['fault_b']}/photos?share={north_share}").status_code == 404


@pytest.mark.parametrize(
    "path", ["/parks/PARK_A/work-orders", "/parks/PARK_A/orthos/generate", "/park/PARK_A/layout"],
)
def test_share_link_cannot_reach_internal_park_tools(client, north_share, path):
    assert client.get(f"{path}?share={north_share}").status_code == 403


def test_test_alert_is_admin_only(client, north_operator, make_user, login):
    make_user("admin@axalon.test", "admin")
    admin = login("admin@axalon.test")

    assert client.post("/alerts/test", headers=north_operator).status_code == 403
    assert client.post("/alerts/test", headers=admin).status_code == 200
