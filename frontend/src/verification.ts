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

/** Gộp con dấu của nhiều cặp: hỏng nếu một cặp hỏng, chưa kiểm nếu một cặp chưa kiểm. */
export function mergeSealChecks(pairs: { name: string; verification: Verification | null | undefined }[]): SealRing[] {
  const perPair = pairs.map((pair) => sealChecks(pair.verification));
  const first = perPair[0] ?? sealChecks(null);
  return first.map((ring, index) => {
    const states = perPair.map((rings) => rings[index]?.state ?? "pending");
    const failed = perPair.flatMap((rings, pairIndex) =>
      rings[index]?.state === "failed" ? [`${pairs[pairIndex]?.name ?? "?"}: ${rings[index]?.detail ?? ""}`] : [],
    );
    return {
      label: ring.label,
      state: failed.length ? "failed" : states.every((state) => state === "passed") ? "passed" : "pending",
      detail: failed.join("; "),
    };
  });
}
