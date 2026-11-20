import { useEffect, useState } from "react";

import { getProfile, type ObservedKind, type TableProfile } from "../api";
import { formatCount } from "../format";

// Hồ sơ cột: mỗi cột có dạng dữ liệu quan sát được, số ô có giá trị/trống,
// số giá trị khác nhau và vài giá trị mẫu. Dạng chỉ là gợi ý, chưa phải kết luận.

const KIND_LABELS: Record<ObservedKind, string> = {
  CODE: "Mã",
  NUMBER: "Số",
  DATE: "Ngày",
  PHONE: "Điện thoại",
  TEXT: "Chữ",
  EMPTY: "Trống",
};

export function ColumnProfileView({ tableId }: { tableId: string }) {
  const [profile, setProfile] = useState<TableProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getProfile(tableId, controller.signal)
      .then(setProfile)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Lỗi không rõ.");
      });
    return () => controller.abort();
  }, [tableId]);

  if (error) return <p className="notice notice--error" role="alert">{error}</p>;
  if (!profile) return <p className="notice">Đang tải hồ sơ cột…</p>;

  return (
    <div className="profile">
      <p className="profile__summary">
        {formatCount(profile.row_count)} dòng · {profile.columns.length} cột
        {profile.blank_row_count > 0 && ` · ${formatCount(profile.blank_row_count)} dòng trống hoàn toàn`}
      </p>
      <ul className="profile__list">
        {profile.columns.map((column) => {
          const filledShare = profile.row_count ? column.filled_count / profile.row_count : 0;
          return (
            <li key={column.position} className="profile__item">
              <div className="profile__head">
                <h3>{column.name}</h3>
                <span className="kind" data-kind={column.kind}>{KIND_LABELS[column.kind]}</span>
                {column.has_leading_zero && <span className="kind kind--note">Có số 0 ở đầu</span>}
              </div>
              <dl className="profile__stats">
                <div>
                  <dt>Có giá trị</dt>
                  <dd>
                    {formatCount(column.filled_count)}
                    <span className="fill-bar" aria-hidden="true">
                      <span style={{ width: `${filledShare * 100}%` }} />
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Trống</dt>
                  <dd>{formatCount(column.empty_count)}</dd>
                </div>
                <div>
                  <dt>Khác nhau</dt>
                  <dd>{formatCount(column.distinct_count)}</dd>
                </div>
              </dl>
              {column.samples.length > 0 && (
                <p className="profile__samples">
                  {column.samples.map((sample) => (
                    <code key={sample}>{sample}</code>
                  ))}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
