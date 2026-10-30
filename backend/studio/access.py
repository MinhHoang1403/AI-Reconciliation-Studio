"""Backend authorization and host-verified local demo sessions.

Auto-access needs a proof installed over trusted docker exec after host inspection.
No Docker socket is mounted. Recreating the backend invalidates proof (tmpfs).
"""

import hashlib
import hmac
import json
import secrets
import sys
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import Request, Response
from sqlalchemy.orm import Session

from studio.config import settings
from studio.contracts import WorkspacePolicy
from studio.database import (
    AuditRow,
    MembershipRow,
    SessionRow,
    WorkspaceRow,
    now,
)
from studio.errors import DomainError


@dataclass(frozen=True)
class Actor:
    id: str
    workspace_id: str
    role: str


def session_token_hash(token: str) -> str:
    """Server-keyed session digest; raw bearer cookies never enter PostgreSQL."""
    return hmac.new(
        settings.session_secret.get_secret_value().encode(), token.encode(), hashlib.sha256
    ).hexdigest()


def validate_deployment(containers: list[dict[str, Any]]) -> str:
    """Trust only host Docker inspection, never HTTP headers claiming loopback deployment."""
    services = set()
    frontend_id = ""
    for container in containers:
        labels = container["Config"]["Labels"]
        if labels.get("com.docker.compose.project") != "ai-reconciliation-studio":
            raise ValueError("unexpected project")
        service = labels.get("com.docker.compose.service")
        services.add(service)
        ports = container.get("NetworkSettings", {}).get("Ports", {})
        for bindings in ports.values():
            for binding in bindings or []:
                if binding["HostIp"] != "127.0.0.1":
                    raise ValueError("non-loopback publication")
        if service == "frontend":
            if ports.get("8080/tcp") != [{"HostIp": "127.0.0.1", "HostPort": "18180"}]:
                raise ValueError("unexpected frontend binding")
            frontend_id = container["Id"]
    if services != {"frontend", "backend", "worker", "postgres"} or not frontend_id:
        raise ValueError("incomplete application")
    return frontend_id


def activate_demo() -> None:
    # A rejected reconfiguration must also invalidate a previously valid activation.
    settings.demo_proof_path.unlink(missing_ok=True)
    frontend_id = validate_deployment(json.load(sys.stdin))
    if not settings.local_demo_access:
        raise ValueError("local demo disabled")
    proof = {
        "instance": settings.instance_path.read_text(),
        "frontend_id": frontend_id,
        "verified_at": now().isoformat(),
    }
    settings.demo_proof_path.write_text(json.dumps(proof), encoding="utf-8")
    print("Loopback deployment verified; local demo session enabled.")


def _demo_allowed() -> bool:
    if not settings.local_demo_access:
        return False
    try:
        proof = json.loads(settings.demo_proof_path.read_text())
        if proof["instance"] != settings.instance_path.read_text():
            return False
        # Published ports cannot change without recreating frontend. Bind the proof
        # to its live container identity, so frontend-only recreation also fails closed.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://frontend:8080/health", timeout=2) as health:
            frontend_instance = health.headers.get("X-Studio-Instance", "")
        return bool(
            len(frontend_instance) >= 12 and proof["frontend_id"].startswith(frontend_instance)
        )
    except (OSError, KeyError, ValueError):
        return False


def check_request_origin(request: Request) -> None:
    host = request.headers.get("host", "")
    allowed_hosts = {origin.split("://", 1)[1] for origin in settings.origins}
    if host not in allowed_hosts:
        raise DomainError("HOST_NOT_ALLOWED", "Địa chỉ truy cập không được cho phép.", 403)
    if any(
        header in request.headers for header in ("x-forwarded-host", "forwarded", "x-forwarded-for")
    ):
        raise DomainError(
            "PUBLIC_PROXY_BLOCKED", "Không tự cấp phiên truy cập qua proxy bên ngoài.", 403
        )
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.origins:
        raise DomainError("ORIGIN_NOT_ALLOWED", "Nguồn truy cập không được cho phép.", 403)
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin not in settings.origins:
        raise DomainError("CSRF_REJECTED", "Thao tác ghi cần origin hợp lệ.", 403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise DomainError("CSRF_REJECTED", "Không chấp nhận truy cập khác website.", 403)


def bootstrap_session(request: Request, response: Response, db: Session) -> Actor:
    check_request_origin(request)
    if not _demo_allowed():
        raise DomainError(
            "LOCAL_DEMO_NOT_VERIFIED", "Demo local chưa được xác minh; chạy tools/start.ps1.", 403
        )
    try:
        return authenticate(request, db)
    except DomainError as exc:
        if exc.status != 401:
            raise
    token = secrets.token_urlsafe(40)
    db.add(
        SessionRow(
            token_hash=session_token_hash(token),
            actor_id="demo-owner",
            workspace_id="demo",
            expires_at=now() + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    db.commit()
    response.set_cookie(
        "studio_session",
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/api",
    )
    return Actor("demo-owner", "demo", "owner")


def authenticate(request: Request, db: Session) -> Actor:
    check_request_origin(request)
    header = request.headers.get("authorization", "")
    fallback = settings.access_token.get_secret_value()
    if fallback and hmac.compare_digest(header, "Bearer " + fallback):
        # Explicit operator token, scoped to demo workspace. Never sent to browser bundle.
        return Actor("demo-owner", "demo", "owner")
    token = request.cookies.get("studio_session", "")
    session = db.get(SessionRow, session_token_hash(token)) if token else None
    if session is None or session.expires_at <= now():
        raise DomainError("AUTH_REQUIRED", "Phiên làm việc hết hạn hoặc chưa xác thực.", 401)
    # Existing demo cookies also fail closed if deployment proof is no longer valid.
    if session.actor_id == "demo-owner" and not _demo_allowed():
        raise DomainError("LOCAL_DEMO_NOT_VERIFIED", "Triển khai local cần được xác minh lại.", 403)
    membership = db.get(MembershipRow, (session.workspace_id, session.actor_id))
    if membership is None:
        raise DomainError("WORKSPACE_ACCESS_DENIED", "Không có quyền workspace.", 403)
    return Actor(session.actor_id, session.workspace_id, membership.role)


def require_editor(actor: Actor, db: Session, resource_id: str = "workspace") -> None:
    if actor.role not in {"owner", "editor"}:
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="ACCESS_DENIED",
                resource_id=resource_id,
            )
        )
        db.commit()
        raise DomainError("ROLE_FORBIDDEN", "Chỉ người có quyền chỉnh sửa mới được thực hiện.", 403)


def require_owner(actor: Actor, db: Session, resource_id: str) -> None:
    """Project classification is a workspace-owner decision, independently of visibility."""
    if actor.role != "owner":
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="ACCESS_DENIED",
                resource_id=resource_id,
            )
        )
        db.commit()
        raise DomainError("ROLE_FORBIDDEN", "Chỉ chủ không gian mới được phân loại dự án.", 403)


def seed_demo(db: Session) -> None:
    if db.get(WorkspaceRow, "demo") is None:
        db.add(
            WorkspaceRow(
                id="demo", name="Không gian làm việc local", policy=WorkspacePolicy().model_dump()
            )
        )
        db.flush()
        db.add(MembershipRow(workspace_id="demo", actor_id="demo-owner", role="owner"))
        db.commit()


if __name__ == "__main__":
    activate_demo()
