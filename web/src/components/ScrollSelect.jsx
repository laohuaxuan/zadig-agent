import { Children, useEffect, useId, useMemo, useRef, useState } from "react";

const MAX_VISIBLE = 10;
const OPTION_HEIGHT = 44;

function parseOptions(children) {
  const options = [];
  Children.forEach(children, (child) => {
    if (!child || child.type !== "option") return;
    const label = child.props.children;
    options.push({
      value: String(child.props.value ?? ""),
      label: label == null || label === "" ? " " : String(label),
      disabled: Boolean(child.props.disabled),
    });
  });
  return options;
}

function optionLabel(options, value) {
  const selected = options.find((item) => item.value === String(value ?? ""));
  if (selected) return selected.label;
  const placeholder = options.find((item) => !item.value);
  return placeholder?.label || "请选择";
}

export default function ScrollSelect({
  loading = false,
  loadingLabel = "正在加载中…",
  optionCount = 0,
  nativeDropdown = false,
  className = "",
  value = "",
  disabled = false,
  required = false,
  name,
  id: idProp,
  onFocus,
  onBlur,
  onChange,
  children,
}) {
  const autoId = useId();
  const id = idProp || autoId;
  const wrapRef = useRef(null);
  const listRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const options = useMemo(() => parseOptions(children), [children]);
  const selectedIndex = options.findIndex((item) => item.value === String(value ?? ""));
  const visibleCount = Math.min(Math.max(optionCount || options.length, 1), MAX_VISIBLE);

  useEffect(() => {
    if (!open) return undefined;
    function onDocumentMouseDown(event) {
      if (!wrapRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocumentMouseDown);
    return () => document.removeEventListener("mousedown", onDocumentMouseDown);
  }, [open]);

  useEffect(() => {
    if (!open || activeIndex < 0 || !listRef.current) return;
    listRef.current.children[activeIndex]?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex]);

  function emitChange(nextValue) {
    onChange?.({ target: { value: nextValue, name } });
  }

  function openMenu(preferredIndex = -1) {
    if (disabled || loading) return;
    setOpen(true);
    const startIndex = preferredIndex >= 0 ? preferredIndex : Math.max(selectedIndex, 0);
    setActiveIndex(startIndex);
  }

  function commit(index) {
    const item = options[index];
    if (!item || item.disabled) return;
    emitChange(item.value);
    setOpen(false);
    setActiveIndex(index);
  }

  function moveActive(step) {
    if (!options.length) return;
    setActiveIndex((current) => {
      let next = current < 0 ? (step > 0 ? 0 : options.length - 1) : current + step;
      while (next >= 0 && next < options.length && options[next].disabled) {
        next += step;
      }
      if (next < 0 || next >= options.length) return current;
      return next;
    });
  }

  function handleTriggerKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) openMenu(Math.max(selectedIndex, 0));
      else moveActive(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) openMenu(Math.max(selectedIndex, 0));
      else moveActive(-1);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) {
        openMenu(Math.max(selectedIndex, 0));
        return;
      }
      if (activeIndex >= 0) commit(activeIndex);
      return;
    }
    if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        setOpen(false);
      }
    }
  }

  if (loading) {
    return (
      <select
        id={id}
        name={name}
        disabled
        className={`scroll-select scroll-select-native${className ? ` ${className}` : ""}`}
        value=""
      >
        <option value="">{loadingLabel}</option>
      </select>
    );
  }

  if (nativeDropdown) {
    return (
      <select
        id={id}
        name={name}
        required={required}
        disabled={disabled}
        className={`scroll-select scroll-select-native${className ? ` ${className}` : ""}`}
        value={value ?? ""}
        onFocus={onFocus}
        onBlur={onBlur}
        onChange={onChange}
      >
        {children}
      </select>
    );
  }

  return (
    <div
      ref={wrapRef}
      className={`scroll-select-wrap${open ? " is-open" : ""}${disabled ? " is-disabled" : ""}${
        className ? ` ${className}` : ""
      }`}
    >
      {required ? (
        <input
          tabIndex={-1}
          aria-hidden="true"
          className="scroll-select-validator"
          value={value ?? ""}
          required={required}
          onChange={() => {}}
        />
      ) : null}
      <button
        type="button"
        id={id}
        name={name}
        disabled={disabled}
        className="scroll-select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          if (open) setOpen(false);
          else openMenu();
        }}
        onFocus={onFocus}
        onBlur={onBlur}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className="scroll-select-value">{optionLabel(options, value)}</span>
        <span className="scroll-select-caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open ? (
        <ul
          ref={listRef}
          className="scroll-select-menu"
          role="listbox"
          aria-labelledby={id}
          style={{ maxHeight: visibleCount * OPTION_HEIGHT }}
          onKeyDown={handleTriggerKeyDown}
        >
          {options.map((item, index) => (
            <li
              key={`${item.value}-${index}`}
              role="option"
              aria-selected={item.value === String(value ?? "")}
              className={`scroll-select-option${index === activeIndex ? " is-active" : ""}${
                item.value === String(value ?? "") ? " is-selected" : ""
              }${item.disabled ? " is-disabled" : ""}`}
              onMouseEnter={() => !item.disabled && setActiveIndex(index)}
              onMouseDown={(event) => {
                event.preventDefault();
                commit(index);
              }}
            >
              {item.label}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
