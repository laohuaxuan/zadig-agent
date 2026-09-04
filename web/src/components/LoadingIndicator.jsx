export default function LoadingIndicator({ label = "", size = "md", inline = false, className = "" }) {
  const sizeClass = size === "sm" ? "loading-spinner-sm" : size === "lg" ? "loading-spinner-lg" : "";
  return (
    <span
      className={`loading-indicator${inline ? " loading-indicator-inline" : ""}${className ? ` ${className}` : ""}`}
      role="status"
      aria-live="polite"
    >
      <span className={`loading-spinner ${sizeClass}`.trim()} aria-hidden="true" />
      {label ? <span className="loading-indicator-label">{label}</span> : null}
    </span>
  );
}

export function PanelLoading({ label = "加载中..." }) {
  return (
    <div className="panel-loading">
      <LoadingIndicator label={label} />
    </div>
  );
}
