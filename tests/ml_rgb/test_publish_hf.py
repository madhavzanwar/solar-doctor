import json
import sys
import types

import pytest

from ml.rgb import publish_hf


def _bundle(tmp_path, extra=()):
    (tmp_path / "config.json").write_text(json.dumps({"arch": "hf_dinov2"}))
    (tmp_path / "model.safetensors").write_bytes(b"x")
    for name in extra:
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


class FakeApi:
    calls: list = []
    public = False

    def __init__(self, token=None):
        pass

    def repo_exists(self, repo):
        return FakeApi.public

    def repo_info(self, repo):
        return types.SimpleNamespace(private=not FakeApi.public)

    def create_repo(self, repo, **kw):
        FakeApi.calls.append(("create", kw))

    def upload_file(self, **kw):
        FakeApi.calls.append(("upload", kw["path_in_repo"]))


@pytest.fixture
def fake_hf(monkeypatch):
    FakeApi.calls, FakeApi.public = [], False
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(HfApi=FakeApi))
    monkeypatch.setenv("HF_TOKEN", "dummy")
    return FakeApi


def test_refuses_dataset_images(tmp_path):
    with pytest.raises(SystemExit, match="unexpected files"):
        publish_hf.files_to_upload(_bundle(tmp_path, ["Bird (1).jpg"]))


def test_dry_run_never_touches_network(tmp_path, fake_hf):
    assert publish_hf.main(["--bundle", str(_bundle(tmp_path)), "--dry-run"]) == 0
    assert fake_hf.calls == []


def test_upload_is_private_with_transformers_card(tmp_path, fake_hf):
    assert publish_hf.main(["--bundle", str(_bundle(tmp_path))]) == 0
    assert ("create", {"repo_type": "model", "private": True, "exist_ok": True}) in fake_hf.calls
    assert ("upload", "README.md") in fake_hf.calls and ("upload", "model.safetensors") in fake_hf.calls


def test_refuses_existing_public_repo(tmp_path, fake_hf):
    fake_hf.public = True
    assert publish_hf.main(["--bundle", str(_bundle(tmp_path))]) == 3
    assert fake_hf.calls == []
