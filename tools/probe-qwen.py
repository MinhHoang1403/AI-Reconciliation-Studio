"""Explicit synthetic Qwen probe; no business files, no cloud provider fallback."""

import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    import httpx
    import polars as pl
    from studio.ai_gateway import QwenProvider
    from studio.config import settings
    from studio.contracts import SourceColumn
    from studio.errors import DomainError
    from studio.profiling import default_schema, profile_table

    if not settings.qwen_base_url:
        raise SystemExit("BLOCKED: QWEN_BASE_URL missing")
    with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
        try:
            models = client.get(settings.qwen_base_url.rstrip("/") + "/models")
            print(f"models: HTTP {models.status_code} (not an inference acceptance)")
            if models.is_success:
                body = models.json()
                ids = [m.get("id") for m in body.get("data", [])]
                print("configured model listed:", settings.qwen_model in ids)
        except (httpx.HTTPError, ValueError):
            print("models: NOT VERIFIED")
        frame = pl.DataFrame({"c1": ["000123", "000124"], "c2": ["100.00", "200.00"]})
        profile = profile_table(
            frame,
            [
                SourceColumn(id="c1", name="Order ID", source_index=1),
                SourceColumn(id="c2", name="Gross amount", source_index=2),
            ],
            "synthetic-table",
            "synthetic-workspace",
            "synthetic-artifact",
        )
        provider = QwenProvider(settings, client)
        try:
            proposal = provider.propose(
                profile, default_schema("synthetic-workspace", "synthetic-schema")
            )
        except DomainError as exc:
            raise SystemExit(f"BLOCKED: mapping inference {exc.code}") from None
        known_id = next((d for d in proposal.decisions if d.source_field == "c1"), None)
        if known_id is None or known_id.candidate_target != "reference_id":
            raise SystemExit(
                "NOT VERIFIED: synthetic reference mapping differs from independent oracle"
            )
        print("PASS LIVE: synthetic mapping JSON and semantic validators passed")
        print("proposal status:", proposal.status, "mapping decisions:", len(proposal.decisions))


if __name__ == "__main__":
    main()
