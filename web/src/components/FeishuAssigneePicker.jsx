import { useCallback, useEffect, useRef, useState } from "react";
import { ensureFeishuUser, fetchApproverCandidates, fetchFeishuUsers } from "../api.js";
import LoadingIndicator from "./LoadingIndicator.jsx";

const ROLE_LABEL = { root: "超级管理员", admin: "管理员", watcher: "普通成员" };
const SOURCE_LABEL = { feishu: "飞书", local: "系统" };

function feishuOptionDisplayLabel(label) {
  const text = String(label || "").trim();
  if (!text) return "";
  const withoutPhone = text.replace(/\s+\+?\d[\d\s-]{6,}$/, "").trim();
  return withoutPhone || text;
}

function chipLabel(u) {
  const raw = u.display_name || u.name || u.username || u.email || `用户#${u.user_id || u.id}`;
  return feishuOptionDisplayLabel(raw);
}

function resolveUserSource(u) {
  const raw = String(u?.auth_source || u?.source || "").trim().toLowerCase();
  if (raw === "feishu") return "feishu";
  return "local";
}

function sourceLabel(source) {
  return SOURCE_LABEL[source] || SOURCE_LABEL.local;
}

function userKey(u) {
  const uid = Number(u.user_id || u.id);
  if (uid > 0) return `id:${uid}`;
  if (u.open_id) return `open:${u.open_id}`;
  return `name:${u.username || u.name || u.email}`;
}

function normalizeUser(u) {
  const userId = Number(u.user_id || u.id || 0);
  return {
    ...u,
    user_id: userId > 0 ? userId : 0,
    source: resolveUserSource(u),
    auth_source: resolveUserSource(u),
  };
}

function mergeUserOptions(...lists) {
  const seen = new Set();
  const out = [];
  for (const list of lists) {
    for (const raw of list || []) {
      const u = normalizeUser(raw);
      const key = userKey(u);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(u);
    }
  }
  return out;
}

export default function FeishuAssigneePicker({
  value,
  onChange,
  initialUsers,
  showMessage,
  searchPlaceholder,
  variant = "primary",
  readOnly = false,
}) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [labels, setLabels] = useState({});
  const [sources, setSources] = useState({});
  const [listWarning, setListWarning] = useState("");
  const wrapRef = useRef(null);
  const debounceRef = useRef(null);
  const abortRef = useRef(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    const map = {};
    const sourceMap = {};
    (initialUsers || []).forEach((u) => {
      const uid = Number(u.user_id || u.id);
      if (uid) {
        map[uid] = chipLabel(u);
        sourceMap[uid] = resolveUserSource(u);
      }
    });
    setLabels((prev) => ({ ...map, ...prev }));
    setSources((prev) => ({ ...sourceMap, ...prev }));
  }, [initialUsers]);

  const fetchUsers = useCallback(
    async (keyword) => {
      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const seq = ++requestSeq.current;

      setLoading(true);
      setListWarning("");
      try {
        const q = keyword.trim();
        const [feishuData, localData] = await Promise.all([
          fetchFeishuUsers(q, 30).catch((err) => {
            if (err.name === "AbortError") throw err;
            return { items: [], warning: err.message || "加载飞书成员失败" };
          }),
          fetchApproverCandidates().catch(() => ({ items: [] })),
        ]);

        if (seq !== requestSeq.current) return;

        const feishuItems = (feishuData.items || []).map((u) => ({ ...u, source: "feishu", auth_source: "feishu" }));
        const localItems = (localData.items || [])
          .map((u) => normalizeUser(u))
          .filter((u) => !q || [u.display_name, u.name, u.email].some((v) => String(v || "").includes(q)));

        const merged = mergeUserOptions(feishuItems, localItems);
        setOptions(merged);
        setListWarning(feishuData.warning || "");

        setLabels((prev) => {
          const next = { ...prev };
          merged.forEach((u) => {
            if (u.user_id) next[u.user_id] = chipLabel(u);
          });
          return next;
        });
        setSources((prev) => {
          const next = { ...prev };
          merged.forEach((u) => {
            if (u.user_id) next[u.user_id] = resolveUserSource(u);
          });
          return next;
        });
      } catch (err) {
        if (err.name === "AbortError") return;
        if (seq !== requestSeq.current) return;
        showMessage?.(err.message, "error");
        setOptions([]);
        setListWarning("");
      } finally {
        if (seq === requestSeq.current) setLoading(false);
      }
    },
    [showMessage],
  );

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const delay = query.trim() ? 300 : 0;
    debounceRef.current = setTimeout(() => {
      fetchUsers(query.trim());
    }, delay);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, open, fetchUsers]);

  useEffect(() => {
    function onDocClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  async function ensureLocalUser(user) {
    if (user.open_id) {
      const data = await ensureFeishuUser({
        open_id: user.open_id,
        name: user.name,
        display_name: user.display_name || user.name,
        email: user.email,
        phone: user.mobile || user.phone,
      });
      return Number(data.user_id);
    }
    if (user.user_id) return Number(user.user_id);
    throw new Error("请从飞书选择成员，或使用本地账号");
  }

  async function toggleUser(user) {
    try {
      const userId = await ensureLocalUser(user);
      if (!userId) return;
      const selected = new Set(value.map(Number));
      if (selected.has(userId)) selected.delete(userId);
      else {
        selected.add(userId);
        setLabels((prev) => ({ ...prev, [userId]: chipLabel({ ...user, user_id: userId }) }));
        setSources((prev) => ({ ...prev, [userId]: resolveUserSource(user) }));
      }
      onChange(Array.from(selected));
    } catch (err) {
      showMessage?.(err.message, "error");
    }
  }

  function removeUser(id) {
    onChange(value.filter((v) => Number(v) !== Number(id)));
  }

  const selectedSet = new Set(value.map(Number));
  const chipClass =
    variant === "cc" ? "feishu-assignee-chip feishu-assignee-chip-cc" : "feishu-assignee-chip feishu-assignee-chip-primary";

  function renderChip(id) {
    return (
      <>
        <span className="feishu-assignee-chip-text">{labels[id] || `用户#${id}`}</span>
        <span className="feishu-assignee-chip-source">{sourceLabel(sources[id] || "local")}</span>
      </>
    );
  }

  if (readOnly) {
    return (
      <div className="feishu-assignee-picker feishu-assignee-picker-readonly">
        {value.length > 0 ? (
          <div className="feishu-assignee-chips">
            {value.map((id) => (
              <span key={id} className={chipClass}>
                {renderChip(id)}
              </span>
            ))}
          </div>
        ) : (
          <span className="wf-muted">未指定</span>
        )}
      </div>
    );
  }

  return (
    <div className="feishu-assignee-picker" ref={wrapRef}>
      {value.length > 0 ? (
        <div className="feishu-assignee-chips">
          {value.map((id) => (
            <span key={id} className={chipClass}>
              {renderChip(id)}
              <button type="button" className="feishu-assignee-chip-remove" onClick={() => removeUser(id)} aria-label="移除">
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <div className="feishu-assignee-search-row">
        <input
          type="text"
          value={query}
          placeholder={searchPlaceholder || "搜索飞书成员或本地账号"}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
        />
        {loading ? <LoadingIndicator label="加载中..." size="sm" inline className="feishu-assignee-loading" /> : null}
      </div>
      {open ? (
        <div className="feishu-assignee-dropdown">
          {loading ? (
            <div className="feishu-assignee-dropdown-loading">
              <LoadingIndicator label="加载中..." size="sm" inline />
            </div>
          ) : options.length === 0 ? (
            <div className="feishu-assignee-option empty">
              {listWarning || (query.trim() ? "未找到匹配成员" : "输入关键词搜索飞书或本地账号")}
            </div>
          ) : (
            options.map((u) => {
              const uid = Number(u.user_id);
              const active = uid > 0 && selectedSet.has(uid);
              return (
                <button
                  key={userKey(u)}
                  type="button"
                  className={active ? "feishu-assignee-option active" : "feishu-assignee-option"}
                  onClick={() => toggleUser(u)}
                >
                  <span className="feishu-assignee-option-name">{u.display_name || u.name}</span>
                  {u.source ? <span className="feishu-assignee-option-meta">{sourceLabel(resolveUserSource(u))}</span> : null}
                  {u.role ? <span className="feishu-assignee-option-meta">{ROLE_LABEL[u.role] || u.role}</span> : null}
                  {u.email && !String(u.email).endsWith("@feishu.local") ? (
                    <span className="feishu-assignee-option-meta">{u.email}</span>
                  ) : null}
                </button>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}
