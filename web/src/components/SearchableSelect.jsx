import { useEffect, useId, useMemo, useRef, useState } from "react";

const MAX_VISIBLE = 10;
const OPTION_HEIGHT = 36;

function normalizeOptions(options) {
  return (options || []).map((item) => {
    if (typeof item === "string") return { value: item, label: item };
    return {
      value: String(item.value ?? ""),
      label: String(item.label ?? item.value ?? ""),
      disabled: Boolean(item.disabled),
    };
  });
}

export default function SearchableSelect({
  value = "",
  onChange,
  options = [],
  placeholder = "",
  loading = false,
  loadingLabel = "正在加载中…",
  disabled = false,
  required = false,
  allowCustom = false,
  emptyText = "无匹配项",
  className = "",
  onFocus,
  onBlur,
  onSearch,
  searchDebounceMs = 300,
  searchingLabel = "正在搜索…",
  name,
  id: idProp,
}) {
  const autoId = useId();
  const id = idProp || autoId;
  const wrapRef = useRef(null);
  const listRef = useRef(null);
  const inputRef = useRef(null);
  const onSearchRef = useRef(onSearch);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [remoteOptions, setRemoteOptions] = useState([]);
  const [searching, setSearching] = useState(false);

  onSearchRef.current = onSearch;

  const normalized = useMemo(() => normalizeOptions(options), [options]);
  const selected = normalized.find((item) => item.value === String(value ?? ""));

  const filtered = useMemo(() => {
    if (onSearch && query.trim()) {
      return remoteOptions;
    }
    const text = query.trim().toLowerCase();
    if (!text) return normalized;
    return normalized.filter(
      (item) => item.label.toLowerCase().includes(text) || item.value.toLowerCase().includes(text),
    );
  }, [normalized, onSearch, query, remoteOptions]);

  const visibleCount = Math.min(Math.max(filtered.length, 1), MAX_VISIBLE);

  useEffect(() => {
    if (!onSearchRef.current || !open) return undefined;
    const text = query.trim();
    if (!text) {
      setRemoteOptions([]);
      setSearching(false);
      return undefined;
    }
    setSearching(true);
    const timer = window.setTimeout(async () => {
      try {
        const result = await onSearchRef.current(text);
        setRemoteOptions(normalizeOptions(result));
      } catch {
        setRemoteOptions([]);
      } finally {
        setSearching(false);
      }
    }, searchDebounceMs);
    return () => window.clearTimeout(timer);
  }, [open, query, searchDebounceMs]);

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

  function displayValue() {
    if (open) return query;
    if (selected) return selected.label;
    return String(value ?? "");
  }

  function openMenu(initialQuery = "") {
    if (disabled || loading) return;
    setQuery(initialQuery);
    setOpen(true);
    const list = onSearch && initialQuery.trim()
      ? remoteOptions
      : initialQuery.trim()
        ? normalized.filter(
            (item) =>
              item.label.toLowerCase().includes(initialQuery.trim().toLowerCase()) ||
              item.value.toLowerCase().includes(initialQuery.trim().toLowerCase()),
          )
        : normalized;
    const selectedIndex = list.findIndex((item) => item.value === String(value ?? ""));
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : list.length ? 0 : -1);
  }

  function commitOption(item) {
    if (!item || item.disabled) return;
    emitChange(item.value);
    setQuery("");
    setOpen(false);
    setActiveIndex(-1);
  }

  function commitCustom(nextValue) {
    const text = String(nextValue ?? "").trim();
    if (!allowCustom && !normalized.some((item) => item.value === text)) return;
    emitChange(text);
    setQuery("");
    setOpen(false);
    setActiveIndex(-1);
  }

  function moveActive(step) {
    if (!filtered.length) return;
    setActiveIndex((current) => {
      let next = current < 0 ? (step > 0 ? 0 : filtered.length - 1) : current + step;
      while (next >= 0 && next < filtered.length && filtered[next].disabled) {
        next += step;
      }
      if (next < 0 || next >= filtered.length) return current;
      return next;
    });
  }

  function handleInputChange(event) {
    const nextQuery = event.target.value;
    setQuery(nextQuery);
    if (!open) setOpen(true);
    if (allowCustom) emitChange(nextQuery);
    if (onSearch && nextQuery.trim()) {
      setActiveIndex(0);
      return;
    }
    const list = nextQuery.trim()
      ? normalized.filter(
          (item) =>
            item.label.toLowerCase().includes(nextQuery.trim().toLowerCase()) ||
            item.value.toLowerCase().includes(nextQuery.trim().toLowerCase()),
        )
      : normalized;
    setActiveIndex(list.length ? 0 : -1);
  }

  function handleInputFocus(event) {
    if (allowCustom) {
      openMenu(selected ? selected.label : String(value ?? ""));
    } else {
      openMenu("");
    }
    onFocus?.(event);
  }

  function handleInputBlur(event) {
    window.setTimeout(() => {
      if (wrapRef.current?.contains(document.activeElement)) return;
      if (allowCustom) {
        commitCustom(query || value);
      } else if (selected) {
        setQuery("");
      }
      setOpen(false);
      onBlur?.(event);
    }, 120);
  }

  function handleInputKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) openMenu(query || displayValue());
      else moveActive(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) openMenu(query || displayValue());
      else moveActive(-1);
      return;
    }
    if (event.key === "Enter") {
      if (!open) {
        openMenu(query || displayValue());
        return;
      }
      event.preventDefault();
      if (activeIndex >= 0 && filtered[activeIndex]) {
        commitOption(filtered[activeIndex]);
        return;
      }
      if (allowCustom) commitCustom(query);
      return;
    }
    if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        setOpen(false);
        setQuery("");
      }
    }
  }

  return (
    <div
      ref={wrapRef}
      className={`searchable-select-wrap${open ? " is-open" : ""}${disabled ? " is-disabled" : ""}${
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
      <div className="searchable-select-input-wrap">
        <input
          ref={inputRef}
          id={id}
          name={name}
          type="text"
          className="searchable-select-input"
          value={displayValue()}
          placeholder={loading ? loadingLabel : searching ? searchingLabel : placeholder}
          disabled={disabled || loading}
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onBlur={handleInputBlur}
          onKeyDown={handleInputKeyDown}
        />
        <button
          type="button"
          className="searchable-select-toggle"
          tabIndex={-1}
          disabled={disabled || loading}
          aria-label="展开选项"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            if (open) {
              setOpen(false);
              setQuery("");
            } else {
              openMenu(selected ? selected.label : String(value ?? ""));
              inputRef.current?.focus();
            }
          }}
        >
          ▾
        </button>
      </div>
      {open && !loading ? (
        <ul
          ref={listRef}
          className="scroll-select-menu searchable-select-menu"
          role="listbox"
          aria-labelledby={id}
          style={{ maxHeight: visibleCount * OPTION_HEIGHT }}
        >
          {searching ? (
            <li className="scroll-select-option is-disabled">{searchingLabel}</li>
          ) : filtered.length === 0 ? (
            <li className="scroll-select-option is-disabled">{emptyText}</li>
          ) : (
            filtered.map((item, index) => (
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
                  commitOption(item);
                }}
              >
                {item.label}
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
