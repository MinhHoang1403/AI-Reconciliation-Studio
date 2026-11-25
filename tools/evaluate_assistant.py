"""Đo AI Assistant với Gemini THẬT trên app đang chạy (tốn phí, Owner chạy).

Chạy bộ 10 câu lệnh mẫu (tests/fixtures/assistant/cau-lenh-mau.json), mỗi câu trong một cuộc
trò chuyện mới, rồi so công cụ và tham số Assistant đã gọi với đáp án. Thẻ xác nhận không bao
giờ được bấm, nên dữ liệu không bị thay đổi. Mỗi lượt cũng có trace trên Langfuse để xem lại.

    uv run --locked python tools/evaluate_assistant.py            # app ở 127.0.0.1:18180
    uv run --locked python tools/evaluate_assistant.py --only 6,25 --keep

Chuẩn bị tự động: tải 4 tệp kỳ 1 của bộ mẫu bán hàng và tệp sao-ke-cai-lenh.csv (tải trùng thì
dùng bản đã có), chờ làm sạch xong, đối soát cả chuỗi kỳ 1 nếu chưa có. Mốc đạt của Giai đoạn 6:
≥ 90% câu đạt (docs/PLAN.md).
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "tests" / "fixtures" / "assistant" / "cau-lenh-mau.json"
FILES = [
    ROOT / "tests" / "fixtures" / "sales" / "don-hang-cua-hang.csv",
    ROOT / "tests" / "fixtures" / "sales" / "giao-dich-cong-thanh-toan.csv",
    ROOT / "tests" / "fixtures" / "sales" / "don-hang-san-tmdt.xlsx",
    ROOT / "tests" / "fixtures" / "sales" / "sao-ke-ngan-hang.xlsx",
    ROOT / "tests" / "fixtures" / "assistant" / "sao-ke-cai-lenh.csv",
]
CHANGE_TOOLS = {
    "confirm_mapping",
    "set_column_field",
    "fix_cell",
    "decide_rows",
    "accept_duplicates",
    "set_date_order",
    "choose_candidate",
    "manual_match",
    "unmatch_result",
    "resolve_exceptions",
    "set_note",
}
TURN_TIMEOUT = 240
# Nghỉ giữa các câu để không chạm giới hạn số yêu cầu mỗi phút của khóa Gemini (lỗi 429).
DEFAULT_PAUSE = 5.0


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urllib.request.urlopen(request, timeout=60) as reply:
            raw = reply.read()
            return json.loads(raw) if raw else None

    def upload(self, path: Path) -> Any:
        boundary = uuid.uuid4().hex
        body = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
            + path.read_bytes()
            + f"\r\n--{boundary}--\r\n".encode()
        )
        request = urllib.request.Request(
            self.base + "/api/datasets",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=120) as reply:
            return json.loads(reply.read())


def _busy(dataset: dict[str, Any]) -> bool:
    """Bộ dữ liệu còn đang xử lý. Vừa tải lên thì bộ dữ liệu đang đọc và CHƯA có bảng nào,
    nên phải xét cả trạng thái của bộ dữ liệu, không chỉ của các bảng."""
    return dataset["status"] == "READING" or any(
        table["status"] == "READING"
        or table["mapping_status"] in ("NONE", "MAPPING")
        or table["clean_status"] in ("BUILDING", "SUGGESTING")
        for table in dataset["tables"]
        if table["status"] != "NO_DATA"
    )


def table_ids(api: Api) -> dict[str, str]:
    """Nhãn bảng → mã bảng, giống hệt nhãn hệ thống dùng (audit.table_label)."""
    return {
        (f"{dataset['name']} › {table['sheet_name']}" if table["sheet_name"] else dataset["name"]):
        table["id"]
        for dataset in api.call("GET", "/api/datasets")
        for table in dataset["tables"]
        if table["status"] == "READY"
    }


def prepare(api: Api) -> None:
    """Tải tệp, chờ đọc, ánh xạ, làm sạch xong, đối soát kỳ 1 nếu chưa có."""
    names = {path.name for path in FILES}
    for path in FILES:
        api.upload(path)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        ours = [d for d in api.call("GET", "/api/datasets") if d["original_filename"] in names]
        if len(ours) == len(names) and not any(_busy(dataset) for dataset in ours):
            break
        time.sleep(2)
    else:
        raise RuntimeError("Quá 5 phút mà tệp mẫu chưa xử lý xong.")
    periods = api.call("GET", "/api/recon/periods")
    if periods and not periods[0]["chain_id"]:
        chain = api.call(
            "POST",
            "/api/recon/chains",
            {"table_ids": [table["id"] for table in periods[0]["tables"]]},
        )
        while api.call("GET", f"/api/recon/chains/{chain['id']}")["status"] == "RUNNING":
            time.sleep(2)


def resolve(value: Any, tables: dict[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("$table:"):
        return tables.get(value.removeprefix("$table:"), value)
    return value


def matches(expected: dict[str, Any], actual: dict[str, Any], tables: dict[str, str]) -> bool:
    for key, want in expected.items():
        if want == "*":
            if actual.get(key) in (None, "", []):
                return False
            continue
        got = actual.get(key)
        want = resolve(want, tables)
        if isinstance(want, list) and isinstance(got, list):
            if sorted(map(str, want)) != sorted(map(str, got)):
                return False
        elif str(got) != str(want) and not (want is None and got is None):
            return False
    return True


def judge(
    prompt: dict[str, Any],
    calls: list[dict[str, Any]],
    tables: dict[str, str],
    cards: list[str] | None = None,
) -> list[str]:
    """Các lỗi của một câu (rỗng là đạt)."""
    problems = []
    for expected in prompt["tools"]:
        if not any(
            call["tool"] == expected["name"] and matches(expected["args"], call["args"], tables)
            for call in calls
        ):
            problems.append(f"thiếu {expected['name']} {expected['args']}")
    if prompt.get("any_of") and not any(call["tool"] in prompt["any_of"] for call in calls):
        problems.append(f"không gọi công cụ nào trong {prompt['any_of']}")
    for code in prompt.get("card_contains", []):
        if not any(code in card for card in cards or []):
            problems.append(f"thẻ xác nhận không ghi mã {code} (có thể chọn nhầm dòng)")
    if prompt.get("forbid_change"):
        changed = [call["tool"] for call in calls if call["tool"] in CHANGE_TOOLS]
        if changed:
            problems.append(f"không được đề xuất thay đổi nhưng đã gọi {changed}")
    return problems


def ask(api: Api, text: str) -> tuple[str, list[dict[str, Any]], str, bool, list[str]]:
    thread = api.call("POST", "/api/assistant/threads", {})
    api.call("POST", f"/api/assistant/threads/{thread['id']}/messages", {"text": text})
    deadline = time.monotonic() + TURN_TIMEOUT
    current = api.call("GET", f"/api/assistant/threads/{thread['id']}")
    while current["running"] and time.monotonic() < deadline:
        time.sleep(2)
        current = api.call("GET", f"/api/assistant/threads/{thread['id']}")
    reply = current["messages"][-1]
    calls = [step for step in reply["steps"] if step.get("tool")]
    # FAILED: Gemini không trả lời được (lỗi mạng, 429, 5xx) — lỗi hạ tầng, không phải hiểu sai.
    cards = [f"{card['title']}: {card['detail']}" for card in reply["actions"]]
    return thread["id"], calls, reply["text"], reply["status"] == "FAILED", cards


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:18180")
    parser.add_argument("--only", help="Chỉ chạy các câu này, ví dụ 6,25")
    parser.add_argument("--keep", action="store_true", help="Giữ lại các cuộc trò chuyện đo")
    parser.add_argument("--out", type=Path, help="Ghi kết quả chi tiết ra tệp JSON")
    parser.add_argument(
        "--rejudge",
        type=Path,
        help="Chấm lại các câu trả lời đã lưu (tệp --out), không gọi Gemini",
    )
    parser.add_argument(
        "--pause", type=float, default=DEFAULT_PAUSE, help="Số giây nghỉ giữa các câu"
    )
    options = parser.parse_args()

    api = Api(options.base)
    prompts = json.loads(PROMPTS.read_text(encoding="utf-8"))["prompts"]
    if options.only:
        wanted = {int(item) for item in options.only.split(",")}
        prompts = [prompt for prompt in prompts if prompt["id"] in wanted]
    if options.rejudge:
        saved = {item["id"]: item for item in json.loads(options.rejudge.read_text("utf-8"))}
        tables = table_ids(api)
        ok = 0
        for prompt in prompts:
            item = saved[prompt["id"]]
            problems = (
                [item["problems"][0]] if item.get("gemini_failed")
                else judge(prompt, item["calls"], tables, item.get("cards"))
            )
            ok += not problems
            print(f"{'ĐẠT' if not problems else 'SAI'} #{prompt['id']:>2} {problems or ''}")
        print(f"\nChấm lại: đạt {ok}/{len(prompts)} câu ({ok / max(len(prompts), 1):.0%}).")
        return 0
    try:
        prepare(api)
    except urllib.error.URLError as error:
        print(f"Không kết nối được app ở {options.base}: {error}", file=sys.stderr)
        return 2

    report = []
    passed = 0
    infra = 0
    for index, prompt in enumerate(prompts):
        if index:
            time.sleep(options.pause)
        thread_id, calls, text, failed, cards = ask(api, prompt["text"])
        problems = judge(prompt, calls, table_ids(api), cards)
        if failed:
            infra += 1
            problems = [f"Gemini không trả lời được: {text}"]
        passed += not problems
        mark = "ĐẠT " if not problems else ("LỖI " if failed else "SAI ")
        print(f"{mark}#{prompt['id']:>2} [{prompt['category']}] {prompt['text']}")
        print(f"      gọi: {[call['tool'] for call in calls] or 'không gọi công cụ'}")
        for problem in problems:
            print(f"      lỗi: {problem}")
        report.append(
            {
                "id": prompt["id"],
                "passed": not problems,
                "gemini_failed": failed,
                "problems": problems,
                "calls": calls,
                "cards": cards,
                "answer": text,
            }
        )
        if not options.keep:
            api.call("DELETE", f"/api/assistant/threads/{thread_id}")

    share = passed / max(len(prompts), 1)
    print(f"\nĐạt {passed}/{len(prompts)} câu ({share:.0%}); mốc Giai đoạn 6 là ≥ 90%.")
    if infra:
        print(
            f"{infra} câu hỏng vì Gemini không trả lời được (mạng, 429, 5xx), không phải vì hiểu "
            "sai; chạy lại các câu đó bằng --only khi Gemini ổn định."
        )
    if options.out:
        options.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if share >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
