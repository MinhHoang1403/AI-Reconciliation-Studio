import { Construction } from "lucide-react";

// Khung chung cho các trang chưa có chức năng: nói rõ trang sẽ làm gì,
// không hiển thị nút hay dữ liệu giả.

type Props = { title: string; summary: string; capabilities: readonly string[] };

export function PlannedPage({ title, summary, capabilities }: Props) {
  return (
    <div className="planned">
      <header className="page__header">
        <h1>{title}</h1>
        <p>{summary}</p>
      </header>
      <section className="planned__body" aria-labelledby="planned-title">
        <Construction aria-hidden="true" size={28} strokeWidth={1.6} />
        <div>
          <h2 id="planned-title">Chức năng đang được xây dựng</h2>
          <p>Khi hoàn thiện, trang này sẽ:</p>
          <ul>
            {capabilities.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
