"""Per-project access: non-admins only see parks/inspections/faults/missions of
their projects. Out-of-scope detail requests are 404 (never 403) so a user
cannot probe which ids exist."""
import pytest


@pytest.fixture
def north_operator(client, users_mode, make_user, login, two_projects):
    make_user("op@axalon.test", "operator", project_ids=[two_projects["p1"]])
    return login("op@axalon.test")


@pytest.fixture
def admin(client, users_mode, make_user, login):
    make_user("admin@axalon.test", "admin")
    return login("admin@axalon.test")


def test_park_list_scoped(client, north_operator, admin):
    mine = client.get("/parks", headers=north_operator).json()
    assert [p["id"] for p in mine["parks"]] == ["PARK_A"]
    assert mine["total"] == 1
    everything = client.get("/parks", headers=admin).json()
    assert {p["id"] for p in everything["parks"]} == {"PARK_A", "PARK_B", "PARK_X"}


@pytest.mark.parametrize(
    "path",
    [
        "/park/{park}",
        "/park/{park}/grid",
        "/park/{park}/trend",
        "/park/{park}/recurring",
        "/park/{park}/orthos",
        "/park/{park}/diff?inspection_a={job}&inspection_b={job}",
        "/parks/{park}/faults",
        "/parks/{park}/inspections/{job}/diff/{job}",
    ],
)
@pytest.mark.parametrize("tag", ["b", "x"])  # other project, and unassigned (admin-only)
def test_park_detail_out_of_scope_is_404(client, north_operator, two_projects, path, tag):
    url = path.format(park=f"PARK_{tag.upper()}", job=two_projects[f"job_{tag}"])
    assert client.get(url, headers=north_operator).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/park/{park}",
        "/park/{park}/grid",
        "/park/{park}/trend",
        "/parks/{park}/faults",
        "/park/{park}/diff?inspection_a={job}&inspection_b={job}",
    ],
)
def test_park_detail_in_scope_is_ok(client, north_operator, two_projects, path):
    url = path.format(park="PARK_A", job=two_projects["job_a"])
    assert client.get(url, headers=north_operator).status_code == 200


def test_park_grid_png_scoped(client, north_operator):
    assert client.get("/park/PARK_B/grid/png", headers=north_operator).status_code == 404


def test_job_endpoints_scoped(client, north_operator, two_projects):
    job_b = two_projects["job_b"]
    for url in (f"/status/{job_b}", f"/map/{job_b}", f"/corrections/{job_b}",
                f"/report/{job_b}", f"/results/{job_b}/x.jpg", f"/image/{job_b}/x_annotated.jpg"):
        assert client.get(url, headers=north_operator).status_code == 404, url
    assert client.post(
        f"/corrections/{job_b}", json={"class_": "cell", "bbox_norm": [0, 0, 1, 1]}, headers=north_operator,
    ).status_code == 404
    assert client.get(f"/status/{two_projects['job_a']}", headers=north_operator).status_code == 200
    assert client.get(f"/corrections/{two_projects['job_a']}", headers=north_operator).status_code == 200


def test_unknown_job_is_404_for_scoped_user(client, north_operator):
    assert client.get("/corrections/batch-nope", headers=north_operator).status_code == 404


def test_fault_mutations_scoped(client, north_operator, two_projects):
    fb = two_projects["fault_b"]
    assert client.patch(f"/faults/{fb}", json={"status": "resolved"}, headers=north_operator).status_code == 404
    assert client.get(f"/faults/{fb}/comments", headers=north_operator).status_code == 404
    assert client.post(f"/faults/{fb}/comments", json={"body": "x"}, headers=north_operator).status_code == 404


def test_missions_scoped(client, north_operator, admin, two_projects):
    names = [m["name"] for m in client.get("/missions", headers=north_operator).json()]
    assert names == ["mission-a"]
    assert client.get("/missions?park_id=PARK_B", headers=north_operator).json() == []
    assert client.get(f"/missions/{two_projects['mission_b']}", headers=north_operator).status_code == 404
    assert client.delete(f"/missions/{two_projects['mission_b']}", headers=north_operator).status_code == 404
    assert client.post("/missions", json={"name": "m", "park_id": "PARK_B"}, headers=north_operator).status_code == 404
    assert client.post("/missions", json={"name": "m"}, headers=north_operator).status_code == 404
    assert len(client.get("/missions", headers=admin).json()) == 3


def test_analytics_overview_scoped(client, north_operator):
    overview = client.get("/analytics/overview", headers=north_operator).json()
    assert [row["park"]["id"] for row in overview] == ["PARK_A"]


def test_projects_scoped(client, north_operator, two_projects):
    listed = client.get("/projects", headers=north_operator).json()
    assert [p["id"] for p in listed] == [two_projects["p1"]]
    assert client.get(f"/projects/{two_projects['p2']}", headers=north_operator).status_code == 404
    assert client.get(f"/projects/{two_projects['p1']}", headers=north_operator).status_code == 200


def test_operator_cannot_move_park_out_of_reach(client, north_operator, two_projects):
    assert client.patch(
        "/park/PARK_A", json={"project_id": two_projects["p2"]}, headers=north_operator,
    ).status_code == 404
    assert client.patch("/park/PARK_B", json={"name": "mine now"}, headers=north_operator).status_code == 404


def test_scoped_upload_to_foreign_park_is_404(client, north_operator):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "x")
    buf.seek(0)
    r = client.post(
        "/batch",
        files={"images": ("m.zip", buf, "application/zip")},
        data={"park_id": "PARK_B"},
        headers=north_operator,
    )
    assert r.status_code == 404


def test_user_without_projects_sees_nothing(client, users_mode, make_user, login, two_projects):
    make_user("lonely@axalon.test", "viewer")
    h = login("lonely@axalon.test")
    assert client.get("/parks", headers=h).json()["parks"] == []
    assert client.get("/missions", headers=h).json() == []
    assert client.get("/projects", headers=h).json() == []
    assert client.get("/analytics/overview", headers=h).json() == []


def test_off_mode_scoping_is_a_noop(client, two_projects):
    assert client.get("/parks").json()["total"] == 3
    assert client.get("/park/PARK_X").status_code == 200
    assert len(client.get("/missions").json()) == 3
