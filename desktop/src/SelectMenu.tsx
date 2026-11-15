import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Check, ChevronDown } from "lucide-react";

export type SelectOption = {
  value: string;
  label: string;
};

type Props = {
  /** Accessible name, also used by tests through getByLabel. */
  label: string;
  /** Visible caption above the trigger; omit for an inline control. */
  heading?: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
};

/**
 * Native-looking popup button. The list is drawn by the page so the open and
 * close transition can be animated and the rows can follow the neutral layer
 * scale instead of the macOS select styling.
 */
export function SelectMenu({
  label,
  heading,
  value,
  options,
  onChange,
  disabled = false,
  className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const id = useId();
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const selected = options[selectedIndex];

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  useEffect(() => {
    if (!open || active < 0) return;
    const row = list.current?.querySelector<HTMLElement>(
      `[data-index="${active}"]`,
    );
    row?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const show = () => {
    if (disabled) return;
    setActive(selectedIndex);
    setOpen(true);
  };

  const choose = (index: number) => {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    setOpen(false);
    trigger.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    const last = options.length - 1;
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        show();
      }
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => Math.min(last, Math.max(0, index + step)));
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      setActive(event.key === "Home" ? 0 : last);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(active);
    }
  };

  return (
    <div className={"select-menu " + className} ref={root}>
      {heading && <span className="select-heading">{heading}</span>}
      <button
        ref={trigger}
        type="button"
        className="select-trigger"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={onKeyDown}
      >
        <span>{selected?.label ?? ""}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      <div
        id={id}
        ref={list}
        className="select-popup"
        role="listbox"
        aria-label={label}
        data-open={open ? "true" : "false"}
        aria-hidden={!open}
      >
        <div className="select-popup-inner">
          {options.map((option, index) => (
            <button
              key={option.value || "empty"}
              type="button"
              role="option"
              data-index={index}
              aria-selected={option.value === value}
              tabIndex={-1}
              className={
                "select-option" +
                (option.value === value ? " selected" : "") +
                (index === active && open ? " active" : "")
              }
              onClick={() => choose(index)}
            >
              <span>{option.label}</span>
              {option.value === value && <Check size={13} aria-hidden="true" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
