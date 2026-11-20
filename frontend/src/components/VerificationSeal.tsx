import { Check, X } from "lucide-react";

// Con dấu kiểm chứng: mỗi vòng hoa văn guilloche (họa tiết sóng đan nhau như trên tờ tiền)
// ứng với một phép kiểm độc lập sau khi đối soát. Phép kiểm đạt thì vòng liền nét;
// phép kiểm hỏng thì vòng bị đứt và đổi màu cảnh báo.

export type CheckState = "pending" | "passed" | "failed";
export type SealCheck = { label: string; state: CheckState };

type Props = { checks: readonly SealCheck[]; size?: number };

// Thông số từng vòng, từ ngoài vào trong: bán kính, biên độ sóng, số cánh.
const RINGS = [
  { radius: 84, amplitude: 7, petals: 36 },
  { radius: 68, amplitude: 6, petals: 30 },
  { radius: 53, amplitude: 5, petals: 24 },
  { radius: 39, amplitude: 4, petals: 18 },
] as const;

const LINES_PER_RING = 5;
const SAMPLES = 360;

/** Vẽ một đường sóng khép kín quanh tâm: r(θ) = bán kính + biên độ · sin(số cánh · θ + lệch pha). */
function wavePath(radius: number, amplitude: number, petals: number, phase: number): string {
  const points: string[] = [];
  for (let i = 0; i <= SAMPLES; i += 1) {
    const theta = (i / SAMPLES) * Math.PI * 2;
    const r = radius + amplitude * Math.sin(petals * theta + phase);
    points.push(`${(r * Math.cos(theta)).toFixed(2)},${(r * Math.sin(theta)).toFixed(2)}`);
  }
  return `M${points.join("L")}Z`;
}

export function VerificationSeal({ checks, size = 200 }: Props) {
  const anyFailed = checks.some((check) => check.state === "failed");
  const allPassed = checks.length > 0 && checks.every((check) => check.state === "passed");
  const summary = anyFailed ? "Kiểm chứng không đạt" : allPassed ? "Kiểm chứng đạt" : "Chưa kiểm chứng";

  return (
    <svg
      className={`seal seal--${anyFailed ? "failed" : allPassed ? "passed" : "pending"}`}
      viewBox="-100 -100 200 200"
      width={size}
      height={size}
      role="img"
      aria-label={summary}
    >
      {RINGS.map((ring, index) => {
        const state = checks[index]?.state ?? "pending";
        return (
          <g key={ring.radius} className={`seal__ring seal__ring--${state}`}>
            {Array.from({ length: LINES_PER_RING }, (_, line) => (
              <path
                key={line}
                d={wavePath(ring.radius, ring.amplitude, ring.petals, (line * Math.PI * 2) / LINES_PER_RING)}
                pathLength={100}
              />
            ))}
          </g>
        );
      })}
      <circle className="seal__core" r={24} />
      {anyFailed ? (
        <X className="seal__mark" x={-12} y={-12} width={24} height={24} strokeWidth={3} />
      ) : allPassed ? (
        <Check className="seal__mark" x={-12} y={-12} width={24} height={24} strokeWidth={3} />
      ) : null}
    </svg>
  );
}
