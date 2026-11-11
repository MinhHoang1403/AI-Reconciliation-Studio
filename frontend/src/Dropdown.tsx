import { ChevronDown, Search } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

// Make room only when opening near the bottom. If the scroll area cannot
// move any further, a compact panel keeps the choices on screen.
function prepareDropdown(trigger: HTMLElement, minimumSpace: number) {
  const room = () => window.innerHeight - trigger.getBoundingClientRect().bottom;
  let container = trigger.parentElement;
  while (container && room() < minimumSpace) {
    if (container.scrollHeight > container.clientHeight &&
      ["auto", "scroll"].includes(getComputedStyle(container).overflowY)) {
      container.scrollBy({ top: Math.ceil(minimumSpace - room()), behavior: "instant" });
    }
    container = container.parentElement;
  }
  trigger.toggleAttribute("data-dropdown-compact", room() < minimumSpace);
}

export function useNativeDropdowns(setKeyboardMode: (mode: "keyboard") => void) {
  useEffect(() => {
    const nativePicker = CSS.supports("appearance", "base-select");
    const popover = "hidePopover" in HTMLElement.prototype;
    const prepare = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof MouseEvent && event.button !== 0) return;
      if (event instanceof KeyboardEvent && ![" ", "Enter", "ArrowDown", "ArrowUp", "Escape"].includes(event.key)) return;
      if (!(event.target instanceof Element)) return;
      const select = event.target.closest("select");
      if (event instanceof KeyboardEvent && event.key === "Escape") {
        // Let the browser dismiss the inner picker before Radix sees Escape.
        if ((nativePicker && select?.matches(":open")) ||
          (popover && event.target.closest(".dropdown-popover:popover-open"))) {
          setKeyboardMode("keyboard");
          event.stopPropagation();
        }
        return;
      }
      if (!nativePicker || !select || select.disabled || select.multiple || select.size > 1) return;
      if (!select.matches(":open")) {
        prepareDropdown(select, Math.min(148, 24 + select.options.length * 40));
      }
    };
    window.addEventListener("mousedown", prepare, true);
    window.addEventListener("keydown", prepare, true);
    return () => {
      window.removeEventListener("mousedown", prepare, true);
      window.removeEventListener("keydown", prepare, true);
    };
  }, [setKeyboardMode]);
}

export const foldDropdownText = (value: string) => value.toLocaleLowerCase("vi").normalize("NFD")
  .replace(/\p{M}/gu, "").replace(/đ/g, "d").replaceAll("_", " ");

export function revealDropdownOption(list: HTMLElement | null, option: HTMLElement | null) {
  if (!list || !option) return;
  const bounds = list.getBoundingClientRect();
  const item = option.getBoundingClientRect();
  if (item.top < bounds.top) list.scrollTop += item.top - bounds.top;
  else if (item.bottom > bounds.bottom) list.scrollTop += item.bottom - bounds.bottom;
}

type DropdownOption = {
  value: string;
  label: string;
  description?: string;
  searchText?: string;
  disabled?: boolean;
};

type DropdownSelection = {
  label: string;
  value: string;
  options: DropdownOption[];
  disabled?: boolean;
  onChange: (value: string) => void;
};

export function DropdownSelect(props: DropdownSelection & { searchLabel: string }) {
  const { label, value, options, disabled, onChange, searchLabel } = props;
  if (options.length > 8 && "showPopover" in HTMLElement.prototype) {
    return <div className="dropdown-labeled">
      <span>{label}</span>
      <SearchableDropdown {...props} searchLabel={searchLabel} />
    </div>;
  }
  return <label>{label}<select aria-label={label} value={value} disabled={disabled}
    onChange={event => onChange(event.target.value)}>
    {options.map(option => <option key={option.value} value={option.value} disabled={option.disabled}>
      {option.label}
    </option>)}
  </select></label>;
}

export function SearchableDropdown({
  label, value, options, disabled, onChange, searchLabel, panelLabel = label,
  placeholder = searchLabel, emptyMessage = "Không có lựa chọn phù hợp.", extra,
}: DropdownSelection & {
  searchLabel: string;
  panelLabel?: string;
  placeholder?: string;
  emptyMessage?: string;
  extra?: (query: string, close: () => void) => ReactNode;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const term = foldDropdownText(query.trim());
  const filtered = options.filter(option =>
    foldDropdownText(`${option.label} ${option.searchText ?? ""}`).includes(term));
  const enabled = filtered.filter(option => !option.disabled);
  const highlighted = enabled[active];
  const optionId = (option: DropdownOption) => `${listId}-option-${encodeURIComponent(option.value)}`;
  const highlightedId = highlighted && optionId(highlighted);
  const selected = options.find(option => option.value === value);

  useEffect(() => {
    if (open && highlightedId) {
      revealDropdownOption(list.current, document.getElementById(highlightedId));
    }
  }, [highlightedId, open]);

  function close() {
    panel.current?.hidePopover();
    trigger.current?.focus({ preventScroll: true });
  }

  function choose(option: DropdownOption) {
    close();
    onChange(option.value);
  }

  return <div className="dropdown-field">
    <button type="button" ref={trigger} className="dropdown-trigger" disabled={disabled}
      aria-label={label} aria-description={selected?.label} title={selected?.label}
      aria-haspopup="listbox" aria-expanded={open} popoverTarget={`${listId}-popup`}
      onClick={event => {
        if (panel.current?.matches(":popover-open")) return;
        prepareDropdown(event.currentTarget, 184);
        setQuery("");
        setActive(Math.max(0, options.filter(option => !option.disabled).findIndex(option => option.value === value)));
      }}
      onKeyDown={event => {
        if (event.key === "ArrowDown" && !open) {
          event.preventDefault();
          event.currentTarget.click();
        }
      }}>
      <span>{selected?.label ?? "Chọn"}</span><ChevronDown size={15} aria-hidden="true" />
    </button>
    <div ref={panel} id={`${listId}-popup`} popover="auto" role="group"
      aria-label={panelLabel} className="dropdown-panel dropdown-popover"
      onToggle={event => {
        if (event.target !== event.currentTarget) return;
        const next = event.newState === "open";
        setOpen(next);
        if (next) search.current?.focus({ preventScroll: true });
      }}
      onBlur={event => {
        // The trigger's click toggles the popover after focus moves to it.
        if (event.relatedTarget instanceof Node && event.relatedTarget !== trigger.current &&
          !event.currentTarget.contains(event.relatedTarget)) {
          event.currentTarget.hidePopover();
        }
      }}>
      <div className="search-input dropdown-search">
        <Search size={16} aria-hidden="true" />
        <input ref={search} role="combobox" aria-label={searchLabel} aria-expanded={open}
          aria-controls={listId} aria-autocomplete="list" aria-activedescendant={highlightedId}
          maxLength={120} value={query} placeholder={placeholder}
          onChange={event => { setQuery(event.target.value); setActive(0); }}
          onKeyDown={event => {
            if (event.nativeEvent.isComposing) return;
            if (event.key === "Tab" && event.shiftKey) {
              event.preventDefault();
              close();
            } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setActive(index => Math.max(0, Math.min(enabled.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))));
            } else if (event.key === "Enter" && highlighted) {
              event.preventDefault();
              choose(highlighted);
            }
          }} />
      </div>
      <div ref={list} id={listId} role="listbox" aria-label={label} tabIndex={-1} className="dropdown-options">
        {filtered.map(option => <div key={option.value} id={optionId(option)} role="option"
          data-option-value={option.value}
          aria-selected={value === option.value} aria-disabled={Boolean(option.disabled)}
          className={`dropdown-option${highlighted === option ? " highlighted" : ""}`}
          onMouseDown={event => event.preventDefault()} onClick={() => { if (!option.disabled) choose(option); }}>
          <strong>{option.label}</strong>
          {option.description && <span>{option.description}</span>}
        </div>)}
      </div>
      {!filtered.length && <p role="status">{emptyMessage}</p>}
      {extra?.(query, close)}
    </div>
  </div>;
}
