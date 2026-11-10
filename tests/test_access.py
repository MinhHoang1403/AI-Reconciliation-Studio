import io
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from studio import access
from studio.access import validate_deployment


def deployment():
    return [
        {
            "Id": "synthetic-" + service,
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "ai-reconciliation-studio",
                    "com.docker.compose.service": service,
                }
            },
            "NetworkSettings": {
                "Ports": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18180"}]}
                if service == "frontend"
                else {}
            },
        }
        for service in ("frontend", "backend", "worker", "postgres")
    ]


def test_actual_loopback_deployment_required():
    assert validate_deployment(deployment()) == "synthetic-frontend"


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "192.168.1.2", "::1"])
def test_nonlocal_demo_fails_closed(bind):
    items = deployment()
    items[0]["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostIp"] = bind
    with pytest.raises(ValueError):
        validate_deployment(items)


def test_incomplete_or_foreign_project_proof_rejected():
    with pytest.raises(ValueError):
        validate_deployment(deployment()[:-1])
    items = deployment()
    items[0]["Config"]["Labels"]["com.docker.compose.project"] = "other-project"
    with pytest.raises(ValueError):
        validate_deployment(items)


def test_wrong_frontend_port_rejected():
    items = deployment()
    items[0]["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"] = "18181"
    with pytest.raises(ValueError):
        validate_deployment(items)


@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "missing",
        "malformed",
        "tampered",
        "backend_changed",
        "frontend_changed",
        "offline",
        "disabled",
    ],
)
def test_proof_lifecycle_fails_closed(monkeypatch, tmp_path, failure):
    """A cookie cannot substitute for host proof bound to both live instances."""
    monkeypatch.setattr(access.settings, "instance_path", tmp_path / "instance")
    monkeypatch.setattr(access.settings, "demo_proof_path", tmp_path / "proof")
    monkeypatch.setattr(access.settings, "local_demo_access", failure != "disabled")
    access.settings.instance_path.write_text("synthetic-instance")
    payload = json.dumps({"instance": "synthetic-instance", "frontend_id": "a" * 64})
    signature = "0" * 64 if failure == "tampered" else access.proof_signature(payload)
    access.settings.demo_proof_path.write_text(
        json.dumps({"payload": payload, "signature": signature})
    )
    if failure == "missing":
        access.settings.demo_proof_path.unlink()
    elif failure == "malformed":
        access.settings.demo_proof_path.write_text("not json")
    elif failure == "backend_changed":
        access.settings.instance_path.write_text("next-synthetic-instance")

    def open_health(url, timeout):
        assert url == "http://frontend:8080/health" and timeout == 2
        if failure == "offline":
            raise OSError("synthetic unavailable")
        return nullcontext(
            SimpleNamespace(
                headers={
                    "X-Studio-Instance": ("b" if failure == "frontend_changed" else "a") * 12,
                }
            )
        )

    monkeypatch.setattr(
        access.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=open_health)
    )
    assert access._demo_allowed() is (failure == "none")


def test_rejected_reverification_revokes_previous_proof(monkeypatch, tmp_path):
    monkeypatch.setattr(access.settings, "demo_proof_path", tmp_path / "proof")
    access.settings.demo_proof_path.write_text("previous synthetic activation")
    monkeypatch.setattr(access.sys, "stdin", io.StringIO(json.dumps(deployment()[:-1])))
    with pytest.raises(ValueError):
        access.activate_demo()
    assert not access.settings.demo_proof_path.exists()
