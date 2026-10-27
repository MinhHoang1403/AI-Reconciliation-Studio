import pytest
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
