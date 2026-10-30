"""Explicit two-document synthetic live acceptance through the existing application API.

Never resets allowance or retries a provider POST. State and raw fixtures remain ignored.
Rerun reads/reuses the same project and dataset refs. Caller revokes temporary allowance
in finally, even if a provider/validation gate fails.
"""

import hashlib
import json
import time
from html.parser import HTMLParser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1] / "runtime" / "document-acceptance"
HEADERS = ["Transaction ID", "Date", "Amount", "Description"]
# Manually labelled strings; never infer these from an extraction or fix its values.
ORACLE = {
    "pdf": [
        ["000123", "2026-10-01", "1234.50", "Paid"],
        ["000124", "2026-10-02", "-20.00", "Refund"],
        ["000125", "2026-10-03", "", "Pending"],
    ],
    "docx": [
        ["000701", "2026-10-04", "1.234,50", "Priority A"],
        ["000702", "2026-10-05", "0,00", "Standard"],
        ["000703", "2026-10-06", "-12,75", "Refund"],
    ],
}


def table_cells(markdown: str) -> list[list[str]]:
    """Read markdown table cells without coercing IDs, amount strings or missing cells."""
    if "<table" in markdown.lower():

        class Cells(HTMLParser):
            def __init__(self) -> None:
                super().__init__(convert_charrefs=True)
                self.rows: list[list[str]] = []
                self.row: list[str] | None = None
                self.cell: list[str] | None = None

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag == "tr":
                    self.row = []
                elif tag in {"td", "th"} and self.row is not None:
                    self.cell = []

            def handle_data(self, data: str) -> None:
                if self.cell is not None:
                    self.cell.append(data)

            def handle_endtag(self, tag: str) -> None:
                if tag in {"td", "th"} and self.cell is not None and self.row is not None:
                    self.row.append("".join(self.cell).strip())
                    self.cell = None
                elif tag == "tr" and self.row is not None:
                    self.rows.append(self.row)
                    self.row = None

        parser = Cells()
        parser.feed(markdown)
        return parser.rows
    rows = []
    for line in markdown.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [v.strip() for v in line.strip().strip("|").split("|")]
        if all(set(v) <= set("-: ") for v in cells):
            continue
        rows.append(cells)
    return rows


def main() -> None:
    if not all((ROOT / f"synthetic-transactions.{ext}").is_file() for ext in ORACLE):
        raise SystemExit(
            "BLOCKED: synthetic fixtures missing; do not create a project or provider job"
        )
    state_path = ROOT / "acceptance.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    def save() -> None:
        temp = ROOT / "acceptance.tmp"
        temp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(state_path)

    with httpx.Client(
        base_url="http://127.0.0.1:18180", timeout=20, headers={"Origin": "http://127.0.0.1:18180"}
    ) as client:
        client.get("/api/session").raise_for_status()
        if "project_id" not in state:
            response = client.post(
                "/api/projects",
                json={
                    "name": "Kiểm tra tài liệu tổng hợp",
                    "business_scope": "synthetic-document-acceptance",
                    "classification": "TEST",
                },
            )
            response.raise_for_status()
            state["project_id"] = response.json()["id"]
            save()
        for extension in ["pdf", "docx"]:
            path = ROOT / f"synthetic-transactions.{extension}"
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if extension not in state:
                mime = (
                    "application/pdf"
                    if extension == "pdf"
                    else ("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                )
                response = client.post(
                    "/api/datasets/uploads",
                    data={"project_id": state["project_id"]},
                    files={"files": (path.name, raw, mime)},
                )
                if not response.is_success:
                    raise SystemExit("BLOCKED upload: " + response.json().get("code", "HTTP_ERROR"))
                item = response.json()["items"][0]
                state[extension] = {
                    "dataset_id": item["id"],
                    "sha256": sha,
                    "job_id": item.get("job_id"),
                }
                save()
            entry = state[extension]
            assert entry["sha256"] == sha, "Source fixture changed; refuse another parse"
            deadline = time.monotonic() + 180
            while True:
                response = client.get(f"/api/datasets/{entry['dataset_id']}/documents")
                response.raise_for_status()
                artifacts = response.json()
                if artifacts:
                    break
                if entry.get("job_id"):
                    job = client.get(f"/api/jobs/{entry['job_id']}").json()
                    if job["status"] in {"FAILED", "BLOCKED", "CANCELLED"}:
                        raise SystemExit("BLOCKED document job: " + str(job["error_code"]))
                if time.monotonic() >= deadline:
                    raise SystemExit("BLOCKED: result not ready; never resubmit a paid job")
                time.sleep(2)
            assert len(artifacts) == 1
            artifact = artifacts[0]
            extraction = artifact["extraction"]
            assert artifact["source_file"]["sha256"] == sha
            assert extraction["verification_status"] == "UNVERIFIED_EXTRACTION"
            assert 1 <= len(extraction["pages"]) <= 2
            actual = [row for p in extraction["pages"] for row in table_cells(p["markdown"])]
            entry["artifact_id"] = artifact["artifact"]["id"]
            entry["provider_job_id"] = extraction["provider_job_id"]
            entry["pages"] = len(extraction["pages"])
            entry["usage"] = extraction["usage"]
            entry["live_parse"] = "PASS"
            entry["validation"] = "PASS" if actual == [HEADERS, *ORACLE[extension]] else "FAIL"
            save()
            print(
                f"{extension.upper()}: LIVE PARSE PASS; pages={entry['pages']}; "
                f"oracle={entry['validation']}; quality=UNVERIFIED_EXTRACTION",
                flush=True,
            )
            if entry["validation"] != "PASS":
                print("Observed synthetic table cells:", actual, flush=True)
                raise SystemExit(
                    "BLOCKED: extraction differs from fixed oracle; never repair values"
                )
        state["integration"] = "PASS"
        save()
        print("PASS: scoped document refs/checksums, fixed oracle and unverified quality")


if __name__ == "__main__":
    main()
