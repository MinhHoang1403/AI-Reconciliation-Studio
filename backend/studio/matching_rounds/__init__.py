"""Các vòng khớp của engine đối soát, mỗi vòng một tệp.

Engine (reconciliation.reconcile) làm theo thứ tự:
1. (khóa) Dòng ngoài phạm vi, tiền ra, dòng còn lỗi làm sạch: không tham gia ghép.
2. (khóa) Lựa chọn của người dùng: ghép tay, chọn ca mơ hồ, gỡ ghép.
3. Các vòng khớp trong "rounds" của config/rules/reconciliation.json: chạy đúng thứ tự trong
   tệp, vòng "enabled": false thì bỏ qua. Mặc định: key_match → score_match → group_match.
4. (khóa) Xếp loại phần còn lại: đơn đã hủy, chờ tiền về, chỉ có ở một bên.

Bước khóa không tắt được vì bước kiểm chứng (recon_verification.py) đòi mỗi dòng nằm trong
đúng một kết quả; tắt hay đổi thứ tự các vòng ở bước 3 thì kết quả khác đi nhưng vẫn qua được
kiểm chứng (dòng không được vòng nào ghép sẽ thành "chỉ có ở một bên").

Thêm một vòng mới:
1. Tạo tệp ở thư mục này với hàm `run(left, right, config) -> RoundOutcome` (xem key_match.py
   làm mẫu): chỉ ghép các dòng trong `left`, `right`, mỗi dòng dùng tối đa một lần.
2. Thêm tên vòng vào ROUNDS bên dưới.
3. Thêm {"round": "<tên>", "enabled": true, "note": "..."} vào "rounds" trong
   config/rules/reconciliation.json, đúng vị trí muốn chạy.
4. Viết bài kiểm trong tests/ và chạy toàn bộ bài kiểm đối soát.
"""

from collections.abc import Callable

from studio import config_files
from studio.matching_rounds import group_match, key_match, score_match
from studio.reconciliation import ReconConfig, RoundOutcome, Row

type MatchingRound = Callable[[list[Row], list[Row], ReconConfig], RoundOutcome]

# Tên vòng (dùng trong config/rules/reconciliation.json) → hàm chạy vòng đó.
ROUNDS: dict[str, MatchingRound] = {
    "key_match": key_match.run,
    "score_match": score_match.run,
    "group_match": group_match.run,
}


def check_configured_rounds() -> None:
    """Gọi lúc backend khởi động: tên vòng trong tệp cấu hình phải có trong ROUNDS."""
    unknown = [spec.round for spec in config_files.reconciliation_rules().rounds
               if spec.round not in ROUNDS]
    if unknown:
        raise config_files.ConfigError(
            "rules/reconciliation.json: vòng khớp không có trong code: "
            + ", ".join(unknown)
            + f" (các vòng có: {', '.join(ROUNDS)})"
        )


def enabled_rounds() -> list[MatchingRound]:
    """Các vòng được bật, đúng thứ tự trong tệp cấu hình."""
    check_configured_rounds()
    return [ROUNDS[spec.round] for spec in config_files.reconciliation_rules().rounds
            if spec.enabled]
