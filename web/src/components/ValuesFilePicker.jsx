import { useEffect, useMemo, useState } from "react";
import { fetchCodeTree } from "../api.js";

function isValuesFile(item) {
  const name = String(item.name || item.path || "").toLowerCase();
  return name.endsWith(".yaml") || name.endsWith(".yml");
}

function joinPath(base, name) {
  const prefix = String(base || "").trim().replace(/\/+$/, "");
  const part = String(name || "").trim().replace(/^\/+/, "");
  if (!prefix) return part;
  if (!part) return prefix;
  return `${prefix}/${part}`;
}

export default function ValuesFilePicker({ open, repoName, codehost, namespace, repo, branch, value, onClose, onSelect }) {
  const [currentPath, setCurrentPath] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pendingPath, setPendingPath] = useState(value || "");

  const breadcrumbs = useMemo(() => {
    const parts = String(currentPath || "")
      .split("/")
      .map((part) => part.trim())
      .filter(Boolean);
    return [{ label: "仓库根目录", path: "" }, ...parts.map((part, index) => ({
      label: part,
      path: parts.slice(0, index + 1).join("/"),
    }))];
  }, [currentPath]);

  useEffect(() => {
    if (!open) return;
    setPendingPath(value || "");
    setCurrentPath("");
  }, [open, value]);

  useEffect(() => {
    if (!open || !codehost || !namespace || !repo || !branch) return;
    setLoading(true);
    setError("");
    fetchCodeTree(codehost, namespace, repo, branch, currentPath)
      .then((data) => {
        const nodes = (data.items || []).slice().sort((a, b) => {
          const aDir = Boolean(a.is_dir);
          const bDir = Boolean(b.is_dir);
          if (aDir !== bDir) return aDir ? -1 : 1;
          return String(a.name || a.path || "").localeCompare(String(b.name || b.path || ""));
        });
        setItems(nodes);
      })
      .catch((err) => {
        setItems([]);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, [open, codehost, namespace, repo, branch, currentPath]);

  if (!open) return null;

  function openFolder(item) {
    setCurrentPath(item.path || joinPath(currentPath, item.name));
  }

  function selectFile(item) {
    const path = item.path || joinPath(currentPath, item.name);
    setPendingPath(path);
  }

  function confirmSelection() {
    onSelect(pendingPath);
    onClose();
  }

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className="dialog values-picker-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="values-picker-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="dialog-head">
          <h2 id="values-picker-title">选择 {repoName || repo} 的 Values 文件</h2>
          <button type="button" className="link-btn" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <p className="field-hint">浏览代码仓库目录，选择 yaml/yml 格式的 Values 文件。</p>

        <div className="values-breadcrumb">
          {breadcrumbs.map((crumb, index) => (
            <span key={crumb.path || "root"}>
              {index > 0 ? <span className="crumb-sep">/</span> : null}
              <button type="button" className="link-btn" onClick={() => setCurrentPath(crumb.path)}>
                {crumb.label}
              </button>
            </span>
          ))}
        </div>

        {error ? (
          <div className="banner error" role="alert">
            {error}
          </div>
        ) : null}

        <div className="values-tree-panel" aria-busy={loading}>
          {loading ? <p className="field-hint">加载目录中…</p> : null}
          {!loading && items.length === 0 ? <p className="field-hint">当前目录为空。</p> : null}
          {!loading
            ? items.map((item) => {
                const path = item.path || joinPath(currentPath, item.name);
                const isDir = Boolean(item.is_dir);
                const selectable = !isDir && isValuesFile(item);
                return (
                  <button
                    key={path}
                    type="button"
                    className={`values-tree-item${pendingPath === path ? " selected" : ""}${isDir ? " folder" : ""}`}
                    onClick={() => (isDir ? openFolder(item) : selectable ? selectFile(item) : null)}
                    disabled={!isDir && !selectable}
                  >
                    <span className="values-tree-icon">{isDir ? "📁" : "📄"}</span>
                    <span className="values-tree-name">{item.name || path}</span>
                    {isDir ? <span className="values-tree-action">进入</span> : null}
                  </button>
                );
              })
            : null}
        </div>

        <div className="values-selected-row">
          <span className="values-selected-label">已选文件</span>
          <span className="values-selected-path">{pendingPath || "尚未选择"}</span>
        </div>

        <div className="dialog-actions">
          <button type="button" className="config-btn" onClick={onClose}>
            取消
          </button>
          <button type="button" className="primary-btn" disabled={!pendingPath} onClick={confirmSelection}>
            确定
          </button>
        </div>
      </div>
    </div>
  );
}
