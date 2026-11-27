"""Kiểm phiên làm việc: mỗi phiên là một không gian riêng, không thấy và không ghép lẫn dữ liệu
của phiên khác; tạo, đổi tên, xóa phiên; dữ liệu cũ thuộc phiên đầu tiên."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_phase5 import PERIOD1, PERIOD2

from studio import database, main
from studio.models import ChatMessage, ChatThread, Dataset, MappingMemory

plain = TestClient(main.app)


def open_workspace(name: str) -> tuple[str, TestClient]:
    """Tạo phiên mới; trả về mã phiên và client gửi kèm mã đó như giao diện."""
    reply = plain.post("/api/workspaces", json={"name": name})
    assert reply.status_code == 201, reply.text
    workspace_id: str = reply.json()["id"]
    return workspace_id, TestClient(main.app, headers={"X-Workspace-Id": workspace_id})


def first_workspace() -> tuple[str, TestClient]:
    first = plain.get("/api/workspaces").json()[0]
    return first["id"], TestClient(main.app, headers={"X-Workspace-Id": first["id"]})


def upload(client: TestClient, name: str) -> dict[str, Any]:
    reply = client.post("/api/datasets", files={"file": (name, (FIXTURES / name).read_bytes())})
    assert reply.status_code in (200, 202), reply.text
    dataset: dict[str, Any] = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    return dataset


def run_period(client: TestClient, index: int) -> dict[str, Any]:
    period = client.get("/api/recon/periods").json()[index]
    reply = client.post(
        "/api/recon/chains", json={"table_ids": [table["id"] for table in period["tables"]]}
    )
    assert reply.status_code == 202, reply.text
    chain: dict[str, Any] = client.get(f"/api/recon/chains/{reply.json()['id']}").json()
    assert chain["status"] == "READY", chain
    return chain


# ---------------------------------------------------------------- phiên đầu tiên, quản lý


def test_a_fresh_system_has_one_workspace_and_requests_without_header_use_it() -> None:
    listed = plain.get("/api/workspaces").json()
    assert [item["name"] for item in listed] == ["Phiên làm việc 1"]
    assert listed[0]["domain_label"] == "Bán hàng"
    upload(plain, "don-hang-cua-hang.csv")  # công cụ dòng lệnh không gửi mã phiên
    assert plain.get("/api/workspaces").json()[0]["datasets"] == 1


def test_create_rename_and_names_stay_unique() -> None:
    first_workspace()  # phiên đầu tiên có trước (như sau migration)
    workspace_id, _ = open_workspace("  Cửa hàng   Quận 1 ")
    listed = plain.get("/api/workspaces").json()
    assert listed[-1]["name"] == "Cửa hàng Quận 1"  # gọn khoảng trắng thừa
    assert plain.post("/api/workspaces", json={"name": "cửa hàng quận 1"}).status_code == 409
    assert plain.post("/api/workspaces", json={"name": "   "}).status_code == 422
    renamed = plain.patch(f"/api/workspaces/{workspace_id}", json={"name": "Cửa hàng Q1"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Cửa hàng Q1"
    # Nhật ký của phiên ghi lần tạo và đổi tên; phiên khác không thấy.
    history = TestClient(main.app, headers={"X-Workspace-Id": workspace_id}).get("/api/audit")
    assert [item["action"] for item in history.json()["items"]] == [
        "WORKSPACE_RENAMED",
        "WORKSPACE_CREATED",
    ]
    assert plain.get("/api/audit").json()["total"] == 0


def test_unknown_workspace_is_refused() -> None:
    stranger = TestClient(main.app, headers={"X-Workspace-Id": str(uuid.uuid4())})
    reply = stranger.get("/api/datasets")
    assert reply.status_code == 404
    assert reply.json()["detail"]["code"] == "WORKSPACE_NOT_FOUND"
    # Luồng SSE và liên kết tải tệp gửi mã phiên bằng tham số ?workspace=.
    assert plain.get("/api/datasets", params={"workspace": str(uuid.uuid4())}).status_code == 404


# ---------------------------------------------------------------- tách biệt dữ liệu


def test_each_workspace_sees_only_its_own_data() -> None:
    _, first = first_workspace()
    _, second = open_workspace("Cửa hàng mới")
    mine = upload(first, "don-hang-cua-hang.csv")
    # Cùng một tệp ở phiên khác là bộ dữ liệu riêng, không bị coi là tải trùng.
    theirs = upload(second, "don-hang-cua-hang.csv")
    assert theirs["id"] != mine["id"]
    assert [item["id"] for item in first.get("/api/datasets").json()] == [mine["id"]]
    assert [item["id"] for item in second.get("/api/datasets").json()] == [theirs["id"]]

    # Mở theo mã một đối tượng của phiên khác: như không có.
    table_id = mine["tables"][0]["id"]
    assert second.get(f"/api/datasets/{mine['id']}").status_code == 404
    assert second.get(f"/api/tables/{table_id}/rows").status_code == 404
    assert second.get(f"/api/tables/{table_id}/mapping").status_code == 404
    assert second.delete(f"/api/datasets/{mine['id']}").status_code == 404

    thread = first.post("/api/assistant/threads", json={}).json()
    assert [item["id"] for item in first.get("/api/assistant/threads").json()] == [thread["id"]]
    assert second.get("/api/assistant/threads").json() == []
    assert second.get(f"/api/assistant/threads/{thread['id']}").status_code == 404

    # Nhật ký: mỗi phiên chỉ thấy việc của mình.
    assert {item["object_label"] for item in second.get("/api/audit").json()["items"]} == {
        "Cửa hàng mới",
        "don-hang-cua-hang",
    }
    assert first.get("/api/audit").json()["total"] == 1


def test_mapping_memory_belongs_to_one_workspace() -> None:
    first_id, first = first_workspace()
    _, second = open_workspace("Phiên thử")
    table_id = upload(first, "don-hang-cua-hang.csv")["tables"][0]["id"]
    assert first.post(f"/api/tables/{table_id}/mapping/confirm").status_code == 200
    with database.SessionFactory() as session:
        remembered = session.scalars(select(MappingMemory)).all()
    assert [str(item.workspace_id) for item in remembered] == [first_id]
    # Phiên kia tải cùng cấu trúc: không dùng ánh xạ phiên đầu đã xác nhận.
    other = upload(second, "don-hang-cua-hang.csv")["tables"][0]
    assert second.get(f"/api/tables/{other['id']}/mapping").json()["ai_state"] != "MEMORY"
    again = upload(first, "don-hang-cua-hang-ky-2.csv")["tables"][0]  # cùng cấu trúc, phiên đầu
    assert first.get(f"/api/tables/{again['id']}/mapping").json()["ai_state"] == "MEMORY"


def test_pending_rows_never_cross_into_another_workspace() -> None:
    """Kỳ 1 ở phiên này, kỳ 2 ở phiên khác: kỳ 2 không được nhận dòng chờ tiền về của kỳ 1.
    Cùng bộ tệp đưa vào cùng một phiên thì nhận đủ 28 dòng (test_phase5)."""
    _, first = first_workspace()
    for name in PERIOD1:
        upload(first, name)
    assert sum(run["group_counts"]["pending"] for run in run_period(first, 0)["runs"]) == 28

    _, second = open_workspace("Kỳ 2 riêng")
    for name in PERIOD2:
        upload(second, name)
    periods = second.get("/api/recon/periods").json()
    assert [period["label"][:8] for period in periods] == ["Kỳ 15/10"]
    chain = run_period(second, 0)
    assert sum(run["carried_count"] for run in chain["runs"]) == 0
    # Mỗi phiên chỉ thấy kỳ, lần chạy và báo cáo của mình.
    assert [period["label"][:8] for period in first.get("/api/recon/periods").json()] == [
        "Kỳ 01/10"
    ]
    assert second.get(f"/api/recon/chains/{chain['id']}").status_code == 200
    assert first.get(f"/api/recon/chains/{chain['id']}").status_code == 404
    assert first.get(f"/api/reports/{chain['id']}").status_code == 404
    run_id = chain["runs"][0]["id"]
    assert first.get(f"/api/recon/runs/{run_id}").status_code == 404
    assert all(
        run["chain_id"] != chain["id"] for run in first.get("/api/recon/runs").json()
    )


# ---------------------------------------------------------------- xóa phiên


def test_deleting_a_workspace_removes_everything_inside_but_shared_files() -> None:
    _, first = first_workspace()
    second_id, second = open_workspace("Sẽ xóa")
    kept = upload(first, "giao-dich-cong-thanh-toan.csv")
    gone = upload(second, "giao-dich-cong-thanh-toan.csv")  # cùng tệp gốc trên đĩa
    only_here = upload(second, "don-hang-cua-hang.csv")
    second.post("/api/assistant/threads", json={})
    with database.SessionFactory() as session:
        paths = {
            item.id: Path(item.storage_path) for item in session.scalars(select(Dataset)).all()
        }

    assert plain.delete(f"/api/workspaces/{second_id}").status_code == 204
    assert [item["name"] for item in plain.get("/api/workspaces").json()] == ["Phiên làm việc 1"]
    assert paths[uuid.UUID(kept["id"])].exists()  # phiên còn lại vẫn dùng tệp gốc này
    assert paths[uuid.UUID(gone["id"])] == paths[uuid.UUID(kept["id"])]
    assert not paths[uuid.UUID(only_here["id"])].exists()
    with database.SessionFactory() as session:
        assert session.scalars(select(ChatThread)).all() == []
        assert {str(item.id) for item in session.scalars(select(Dataset))} == {kept["id"]}
    assert second.get("/api/datasets").status_code == 404
    assert first.get(f"/api/datasets/{kept['id']}").status_code == 200


def test_last_or_busy_workspace_cannot_be_deleted() -> None:
    first_id, _ = first_workspace()
    assert plain.delete(f"/api/workspaces/{first_id}").json()["detail"]["code"] == (
        "LAST_WORKSPACE"
    )
    busy_id, busy = open_workspace("Đang chạy")
    thread = busy.post("/api/assistant/threads", json={}).json()
    with database.SessionFactory() as session:
        session.add(
            ChatMessage(
                id=uuid.uuid4(), thread_id=uuid.UUID(thread["id"]), position=0,
                role="assistant", text="", status="RUNNING", attachments=[], steps=[],
                actions=[], links=[],
            )
        )
        session.commit()
    reply = plain.delete(f"/api/workspaces/{busy_id}")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "WORKSPACE_BUSY"


@pytest.mark.parametrize("field", ["datasets", "threads", "reconciliations"])
def test_list_counts_what_is_inside(field: str) -> None:
    _, client = open_workspace("Đếm")
    upload(client, "don-hang-cua-hang.csv")
    client.post("/api/assistant/threads", json={})
    found = next(item for item in plain.get("/api/workspaces").json() if item["name"] == "Đếm")
    assert found[field] == {"datasets": 1, "threads": 1, "reconciliations": 0}[field]
    assert found["last_activity"]
