import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronsUpDown, FolderPlus, Layers, Settings2 } from "lucide-react";

import { formatCount } from "../format";
import { navigate } from "../navigation";
import { openWorkspace } from "../workspace";
import { useWorkspaces } from "../WorkspaceContext";

// Bộ chọn phiên làm việc: ở đầu thanh bên trên máy tính, ở dải đầu trang trên điện thoại.
// Bấm mở danh sách phiên; chọn phiên khác thì mở phiên đó từ Dashboard. Cuối danh sách có
// "Tạo phiên mới" và "Quản lý phiên" (trang /phien).

type Props = { variant: "rail" | "bar" };

export function WorkspaceSwitcher({ variant }: Props) {
  const { workspaces, current } = useWorkspaces();
  const [open, setOpen] = useState(false);
  // Vị trí danh sách: ngay dưới nút, căn trái theo nút (đo khi mở).
  const [place, setPlace] = useState({ top: 0, left: 0 });
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  // Đóng khi bấm ra ngoài hoặc nhấn Esc (trả focus về nút).
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    const close = () => setOpen(false);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  return (
    <div className="workspace-switch" data-variant={variant} ref={root}>
      <button
        ref={button}
        className="workspace-switch__button"
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Phiên làm việc: ${current.name}. Đổi phiên`}
        title={variant === "rail" ? `Phiên: ${current.name}` : undefined}
        onClick={() => {
          const rect = button.current?.getBoundingClientRect();
          if (rect) setPlace({ top: rect.bottom + 6, left: rect.left });
          setOpen((value) => !value);
        }}
      >
        <Layers className="workspace-switch__icon" aria-hidden="true" size={20} strokeWidth={1.8} />
        <span className="workspace-switch__text rail__label">
          <span className="workspace-switch__name">{current.name}</span>
          <span className="workspace-switch__domain">{current.domain_label}</span>
        </span>
        <ChevronsUpDown className="workspace-switch__chevron rail__label" aria-hidden="true" size={16} />
      </button>

      {open && (
        <div className="workspace-switch__menu" id={menuId} style={place}>
          <ul aria-label="Các phiên làm việc">
            {workspaces.map((item) => {
              const here = item.id === current.id;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className="workspace-switch__item"
                    aria-current={here ? "true" : undefined}
                    onClick={() => (here ? setOpen(false) : openWorkspace(item.id))}
                  >
                    <span className="workspace-switch__item-text">
                      <span className="workspace-switch__item-name">{item.name}</span>
                      <span className="workspace-switch__item-meta">
                        {formatCount(item.datasets)} tệp · {formatCount(item.reconciliations)} lần đối soát
                      </span>
                    </span>
                    {here && <Check aria-label="Đang mở" size={16} />}
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="workspace-switch__actions">
            <button type="button" className="workspace-switch__action" onClick={() => go("/phien#tao")}>
              <FolderPlus aria-hidden="true" size={17} /> Tạo phiên mới
            </button>
            <button type="button" className="workspace-switch__action" onClick={() => go("/phien")}>
              <Settings2 aria-hidden="true" size={17} /> Quản lý phiên
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
