import type { SealCheck } from "./components/VerificationSeal";
import type { Verification } from "./api";

// Bốn vòng của con dấu kiểm chứng, mỗi vòng gom các phép kiểm cùng một ý của backend
// (recon_verification.py). Chưa có lần đối soát thì mọi vòng ở trạng thái "chưa kiểm".
const RINGS = [
  { label: "Mỗi dòng nằm trong đúng một kết quả", codes: ["COVERAGE_A", "COVERAGE_B"] },
  { label: "Tổng tiền từng bên được bảo toàn", codes: ["AMOUNT_A", "AMOUNT_B"] },
  { label: "Số kết quả theo loại cộng đủ tổng", codes: ["COUNTS"] },
  { label: "Loại kết quả đúng với dữ liệu", codes: ["KIND_RULES"] },
] as const;

export type SealRing = SealCheck & { detail: string };

export function sealChecks(verification: Verification | null | undefined): SealRing[] {
  return RINGS.map((ring) => {
    const found = verification?.checks.filter((check) => (ring.codes as readonly string[]).includes(check.code)) ?? [];
    if (found.length === 0) return { label: ring.label, state: "pending", detail: "" };
    const failed = found.filter((check) => !check.passed);
    return {
      label: ring.label,
      state: failed.length ? "failed" : "passed",
      detail: failed.map((check) => check.detail).join("; "),
    };
  });
}
