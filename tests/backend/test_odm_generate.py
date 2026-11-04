"""In-platform orthomosaic generation via NodeODM.

Covers: disabled-when-unconfigured, upload validation, job state transitions,
failure + cancel paths, and registration of the downloaded ortho through the
same ingestion path as a manual upload. NodeODM is faked — no network.
"""
from __future__ import annotations

import io
import shutil
import uuid
import zipfile
from pathlib import Path

import pytest

from axalon.api.support import odm_jobs
from axalon.api.support.jobs import _create_job, _get_job, _update_job
from axalon.api.support.paths import ORTHO_DIR, OUTPUT_DIR
from axalon.core.odm_client import NodeODMClient

REPO_ROOT = Path(__file__).resolve().parents[2]
RGB_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sample_mission" / "rgb"


# ── helpers ──────────────────────────────────────────────────────────────────
def _park() -> str:
    return f"ODM_{uuid.uuid4().hex[:8]}"


def _geotiff_bytes() -> bytes:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    buf = io.BytesIO()
    data = np.full((3, 16, 16), 128, dtype="uint8")
    with rasterio.MemoryFile() as mem:
        with mem.open(
            driver="GTiff", width=16, height=16, count=3, dtype="uint8",
            crs="EPSG:4326", transform=from_origin(72.87, 19.08, 0.0001, 0.0001),
        ) as dst:
            dst.write(data)
        buf.write(mem.read())
    return buf.getvalue()


def _zip_of(paths, arcdir: str = "mission/rgb") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in paths:
            zf.write(p, f"{arcdir}/{Path(p).name}")
    return buf.getvalue()


def _gps_zip() -> bytes:
    return _zip_of(sorted(RGB_FIXTURES.glob("*.jpg")))


def _no_gps_zip(tmp_path) -> bytes:
    from PIL import Image
    paths = []
    for i in range(6):
        p = tmp_path / f"plain_{i}.jpg"
        Image.new("RGB", (8, 8)).save(p)
        paths.append(p)
    return _zip_of(paths)


@pytest.fixture
def odm_env(monkeypatch, odm_fakes):
    """Configure ODM and route the worker's client to a fresh FakeNodeODM."""
    monkeypatch.setenv("AXALON_NODEODM_URL", "http://odm.test:3000")
    fake = odm_fakes.FakeNodeODM(orthophoto=_geotiff_bytes())
    monkeypatch.setattr(
        odm_jobs, "get_odm_client",
        lambda: NodeODMClient("http://odm.test:3000", session=fake, sleep=lambda _s: None),
    )
    monkeypatch.setattr(odm_jobs, "_sleep", lambda _s: None)
    return fake


def _post_zip(client, park_id: str, data: bytes, name: str = "flight.zip", **form):
    return client.post(
        f"/parks/{park_id}/orthos/generate",
        files={"images": (name, data, "application/zip")},
        data=form,
    )


# ── capability flag / disabled ───────────────────────────────────────────────
def test_health_reports_odm_not_configured(client, monkeypatch):
    monkeypatch.delenv("AXALON_NODEODM_URL", raising=False)
    body = client.get("/health").json()
    assert body["capabilities"]["odm"]["configured"] is False
    assert "AXALON_NODEODM_URL" in body["capabilities"]["odm"]["message"]


def test_health_reports_odm_configured(client, monkeypatch):
    monkeypatch.setenv("AXALON_NODEODM_URL", "http://odm.test:3000")
    body = client.get("/health").json()
    assert body["capabilities"]["odm"] == {"configured": True, "message": None}


def test_generate_is_disabled_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv("AXALON_NODEODM_URL", raising=False)
    resp = _post_zip(client, _park(), _gps_zip())
    assert resp.status_code == 503
    assert "AXALON_NODEODM_URL" in resp.json()["detail"]


# ── request validation ──────────────────────────────────────────────────────
def test_generate_requires_a_source(client, odm_env):
    resp = client.post(f"/parks/{_park()}/orthos/generate", data={})
    assert resp.status_code == 400


def test_generate_rejects_both_sources(client, odm_env):
    resp = _post_zip(client, _park(), _gps_zip(), source_job_id="batch-abc")
    assert resp.status_code == 400


def test_generate_rejects_non_zip_upload(client, odm_env):
    resp = _post_zip(client, _park(), b"hello", name="flight.tar")
    assert resp.status_code == 400


def test_generate_rejects_corrupt_zip(client, odm_env):
    resp = _post_zip(client, _park(), b"PK-not-really")
    assert resp.status_code == 400


def test_generate_rejects_too_few_images(client, odm_env):
    resp = _post_zip(client, _park(), _zip_of(sorted(RGB_FIXTURES.glob("*.jpg"))[:2]))
    assert resp.status_code == 400
    assert "at least" in resp.json()["detail"]
    assert odm_env.calls == []


def test_generate_rejects_bad_options(client, odm_env):
    resp = _post_zip(client, _park(), _gps_zip(), orthophoto_resolution_cm="0")
    assert resp.status_code == 400
    resp = _post_zip(client, _park(), _gps_zip(), sensor="lidar")
    assert resp.status_code == 400


def test_generate_unknown_source_job_404(client, odm_env):
    resp = client.post(
        f"/parks/{_park()}/orthos/generate", data={"source_job_id": "batch-doesnotexist"},
    )
    assert resp.status_code == 404


# ── happy path ───────────────────────────────────────────────────────────────
def test_generate_from_zip_runs_task_and_registers_ortho(client, odm_env):
    # Arrange
    park_id = _park()

    # Act — TestClient runs the background task before returning
    resp = _post_zip(client, park_id, _gps_zip(), orthophoto_resolution_cm="3")

    # Assert — request accepted as a queued job
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert job_id.startswith("odm-")

    status = client.get(f"/parks/{park_id}/orthos/generate/{job_id}").json()
    assert status["state"] == "succeeded"
    assert status["progress"] == 1.0
    assert status["error"] is None
    assert status["ortho_name"] == f"{job_id.replace('-', '_')}.tif"

    t = odm_env.task_uuid
    paths = odm_env.paths()
    assert paths[0] == "POST /task/new/init"
    assert paths[1] == f"POST /task/new/upload/{t}"
    assert f"POST /task/new/commit/{t}" in paths
    assert paths.index(f"POST /task/new/commit/{t}") < paths.index(f"GET /task/{t}/info")
    assert paths[-2:] == [f"GET /task/{t}/download/orthophoto.tif", "POST /task/remove"]
    uploaded = sum(len(c.file_names) for c in odm_env.calls if "/upload/" in c.path)
    assert uploaded == len(list(RGB_FIXTURES.glob("*.jpg")))

    # Registered exactly like a manual upload: listed, with metadata + bounds
    orthos = client.get(f"/park/{park_id}/orthos").json()["orthos"]
    assert [o["name"] for o in orthos] == [status["ortho_name"]]
    assert orthos[0]["crs"] == "EPSG:4326"

    # Scratch images are cleaned up
    assert not (OUTPUT_DIR / "odm" / job_id).exists()
    shutil.rmtree(ORTHO_DIR / park_id, ignore_errors=True)


def test_generate_reuses_images_of_existing_job(client, odm_env):
    # Arrange — a finished batch job whose extracted images live in OUTPUT_DIR/<job_id>
    park_id = _park()
    source_job = f"batch-{uuid.uuid4().hex[:8]}"
    rgb_dir = OUTPUT_DIR / source_job / "mission" / "rgb"
    shutil.copytree(RGB_FIXTURES, rgb_dir)
    _create_job(source_job, park_id)
    _update_job(source_job, state="succeeded")

    # Act
    resp = client.post(
        f"/parks/{park_id}/orthos/generate", data={"source_job_id": source_job},
    )

    # Assert
    assert resp.status_code == 202, resp.text
    status = client.get(f"/parks/{park_id}/orthos/generate/{resp.json()['job_id']}").json()
    assert status["state"] == "succeeded"
    assert rgb_dir.exists(), "source inspection images must not be deleted"
    shutil.rmtree(OUTPUT_DIR / source_job, ignore_errors=True)
    shutil.rmtree(ORTHO_DIR / park_id, ignore_errors=True)


def test_list_generation_jobs_for_park(client, odm_env):
    park_id = _park()
    job_id = _post_zip(client, park_id, _gps_zip()).json()["job_id"]
    jobs = client.get(f"/parks/{park_id}/orthos/generate").json()["jobs"]
    assert [j["job_id"] for j in jobs] == [job_id]
    shutil.rmtree(ORTHO_DIR / park_id, ignore_errors=True)


def test_transient_poll_errors_do_not_fail_the_job(client, odm_env, odm_fakes):
    odm_env.failures[f"GET /task/{odm_env.task_uuid}/info"] = [
        odm_fakes.connection_error() for _ in range(6)
    ]
    park_id = _park()
    job_id = _post_zip(client, park_id, _gps_zip()).json()["job_id"]
    assert _get_job(job_id)["state"] == "succeeded"
    shutil.rmtree(ORTHO_DIR / park_id, ignore_errors=True)


# ── failure paths ────────────────────────────────────────────────────────────
def test_images_without_gps_fail_before_contacting_nodeodm(client, odm_env, tmp_path):
    park_id = _park()
    job_id = _post_zip(client, park_id, _no_gps_zip(tmp_path)).json()["job_id"]
    status = client.get(f"/parks/{park_id}/orthos/generate/{job_id}").json()
    assert status["state"] == "failed"
    assert "GPS" in status["error"]
    assert odm_env.calls == []


def test_nodeodm_task_failure_marks_job_failed(client, odm_env):
    odm_env.info_script[:] = [{"code": 30, "progress": 20, "error": "Not enough overlap"}]
    park_id = _park()
    job_id = _post_zip(client, park_id, _gps_zip()).json()["job_id"]
    status = client.get(f"/parks/{park_id}/orthos/generate/{job_id}").json()
    assert status["state"] == "failed"
    assert "Not enough overlap" in status["error"]
    assert status["ortho_name"] is None
    assert client.get(f"/park/{park_id}/orthos").json()["orthos"] == []
    assert odm_env.paths()[-1] == "POST /task/remove"


def test_unreachable_nodeodm_marks_job_failed(client, odm_env, odm_fakes):
    odm_env.failures["POST /task/new/init"] = [odm_fakes.connection_error() for _ in range(10)]
    park_id = _park()
    job_id = _post_zip(client, park_id, _gps_zip()).json()["job_id"]
    status = _get_job(job_id)
    assert status["state"] == "failed"
    assert "unreachable" in status["message"].lower()


def test_invalid_downloaded_ortho_is_not_registered(client, odm_env):
    odm_env.orthophoto = b"definitely not a geotiff"
    park_id = _park()
    job_id = _post_zip(client, park_id, _gps_zip()).json()["job_id"]
    status = client.get(f"/parks/{park_id}/orthos/generate/{job_id}").json()
    assert status["state"] == "failed"
    assert "GeoTIFF" in status["error"]
    assert client.get(f"/park/{park_id}/orthos").json()["orthos"] == []


# ── cancel ───────────────────────────────────────────────────────────────────
def test_worker_stops_and_removes_task_when_cancelled_mid_poll(odm_env, temp_db, monkeypatch):
    # Arrange — images already on disk; cancel arrives during the first poll wait
    park_id = _park()
    job_id = f"odm-{uuid.uuid4().hex[:12]}"
    _create_job(job_id, park_id)
    work = OUTPUT_DIR / "odm" / job_id
    shutil.copytree(RGB_FIXTURES, work / "images" / "rgb")
    odm_env.info_script[:] = [{"code": 20, "progress": 30}]

    def cancel_on_sleep(_s):
        odm_jobs.cancel_odm_job(job_id)

    monkeypatch.setattr(odm_jobs, "_sleep", cancel_on_sleep)

    # Act
    odm_jobs.run_odm_job(job_id, park_id, work / "images", sensor="auto",
                         options=[])

    # Assert
    job = _get_job(job_id)
    assert job["state"] == "cancelled"
    assert "POST /task/cancel" in odm_env.paths()
    assert "POST /task/remove" in odm_env.paths()
    assert f"GET /task/{odm_env.task_uuid}/download/orthophoto.tif" not in odm_env.paths()
    assert not work.exists()


def test_delete_cancels_queued_job(client, odm_env):
    park_id = _park()
    job_id = f"odm-{uuid.uuid4().hex[:12]}"
    _create_job(job_id, park_id)
    odm_jobs._write_task_meta(job_id, {"task_uuid": "abc-123"})

    resp = client.delete(f"/parks/{park_id}/orthos/generate/{job_id}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "cancelled"
    assert odm_env.paths() == ["POST /task/cancel", "POST /task/remove"]
    shutil.rmtree(odm_jobs.work_dir(job_id), ignore_errors=True)


def test_delete_finished_job_conflicts(client, odm_env):
    park_id = _park()
    job_id = f"odm-{uuid.uuid4().hex[:12]}"
    _create_job(job_id, park_id)
    _update_job(job_id, state="succeeded")
    assert client.delete(f"/parks/{park_id}/orthos/generate/{job_id}").status_code == 409


def test_status_of_unknown_or_foreign_job_404(client, odm_env):
    park_id = _park()
    assert client.get(f"/parks/{park_id}/orthos/generate/odm-000000000000").status_code == 404
    other = f"odm-{uuid.uuid4().hex[:12]}"
    _create_job(other, "SOME_OTHER_PARK")
    assert client.get(f"/parks/{park_id}/orthos/generate/{other}").status_code == 404
    assert client.delete(f"/parks/{park_id}/orthos/generate/{other}").status_code == 404


# ── restart handling ────────────────────────────────────────────────────────
def test_resume_after_restart_repolls_submitted_and_fails_unsubmitted(odm_env, temp_db, monkeypatch):
    # Arrange — one job already on NodeODM, one interrupted before submission
    park_id = _park()
    submitted = f"odm-{uuid.uuid4().hex[:12]}"
    unsubmitted = f"odm-{uuid.uuid4().hex[:12]}"
    for job_id in (submitted, unsubmitted):
        _create_job(job_id, park_id)
    odm_jobs._write_task_meta(submitted, {"task_uuid": odm_env.task_uuid, "sensor": "rgb"})
    resumed = []

    class ImmediateThread:
        def __init__(self, target, args, kwargs, **_):
            self._run = lambda: target(*args, **kwargs)

        def start(self):
            self._run()

    monkeypatch.setattr(odm_jobs.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(
        odm_jobs, "run_odm_job",
        lambda job_id, park, root, **kw: resumed.append((job_id, park, kw["resume_task_uuid"])),
    )

    # Act
    count = odm_jobs.resume_odm_jobs()

    # Assert
    assert count == 1
    assert resumed == [(submitted, park_id, odm_env.task_uuid)]
    assert _get_job(unsubmitted)["state"] == "failed"
    assert "restart" in _get_job(unsubmitted)["message"]
    shutil.rmtree(odm_jobs.work_dir(submitted), ignore_errors=True)


def test_resumed_job_skips_submission_and_completes(odm_env, temp_db):
    park_id = _park()
    job_id = f"odm-{uuid.uuid4().hex[:12]}"
    _create_job(job_id, park_id)

    odm_jobs.run_odm_job(job_id, park_id, None, sensor="rgb", options=[],
                         resume_task_uuid=odm_env.task_uuid)

    assert _get_job(job_id)["state"] == "succeeded"
    assert "POST /task/new/init" not in odm_env.paths()
    shutil.rmtree(ORTHO_DIR / park_id, ignore_errors=True)
