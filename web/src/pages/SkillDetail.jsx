import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { fetchMcpSkill, fetchSkill, updateMcpSkill, updateSkill } from "../api.js";
import ScrollSelect from "../components/ScrollSelect.jsx";
import { normalizeDescription } from "../utils/formatDescription.js";

const SOURCE_LABEL = {
  mysql: "页面配置",
  file: "仓库文件",
  builtin: "内置工具",
};

export default function SkillDetail({ kind }) {
  const { skillName } = useParams();
  const navigate = useNavigate();
  const listPath = kind === "mcp" ? "/mcp" : "/skills";
  const [meta, setMeta] = useState(null);
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetcher = kind === "mcp" ? fetchMcpSkill : fetchSkill;
    setLoading(true);
    setError("");
    fetcher(skillName)
      .then((data) => {
        const item = data.item;
        setMeta(item);
        if (kind === "mcp") {
          setForm({
            display_name: item.display_name || "",
            description: normalizeDescription(item.description),
            transport: item.transport || "stdio",
            command: item.command || "",
            argsText: (item.args || []).join(", "),
            url: item.url || "",
          });
        } else {
          setForm({
            display_name: item.display_name || "",
            description: normalizeDescription(item.description),
            content: item.content || "",
          });
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [kind, skillName]);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (!meta?.editable) return;
    setSaving(true);
    setError("");
    try {
      if (kind === "mcp") {
        await updateMcpSkill(skillName, {
          display_name: form.display_name,
          description: form.description,
          transport: form.transport,
          command: form.command,
          url: form.url,
          args: form.argsText
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        });
      } else {
        await updateSkill(skillName, form);
      }
      navigate(listPath);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <section>
        <div className="skeleton-list" aria-busy="true">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      </section>
    );
  }

  if (!meta || !form) {
    return (
      <section>
        <div className="banner error" role="alert">
          {error || "技能不存在"}
        </div>
        <Link className="link-btn" to={listPath}>
          返回列表
        </Link>
      </section>
    );
  }

  const readonly = !meta.editable;

  return (
    <section className="skill-detail-page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{meta.display_name || meta.name}</h1>
          <p className="page-desc">
            标识 {meta.name}
            {kind === "mcp" ? (
              <>
                {" "}
                · 来源 {SOURCE_LABEL[meta.source] || meta.source}
                {meta.module ? ` · 模块 ${meta.module}` : ""}
              </>
            ) : null}
            {meta.file ? ` · 文件 ${meta.file}` : ""}
          </p>
        </div>
        <Link className="config-btn" to={listPath}>
          返回列表
        </Link>
      </div>
      {readonly && kind === "mcp" ? (
        <div className="banner" role="status">
          此技能来自{SOURCE_LABEL[meta.source] || "外部来源"}，仅可查看，不可在此页面编辑。
        </div>
      ) : null}
      {error ? (
        <div className="banner error" role="alert">
          {error}
        </div>
      ) : null}
      <form className="form-card skill-detail-form" onSubmit={onSubmit}>
        <label>
          标识
          <input value={meta.name} readOnly disabled />
        </label>
        <label>
          显示名称
          <input
            value={form.display_name}
            onChange={(e) => update("display_name", e.target.value)}
            readOnly={readonly}
            disabled={readonly}
          />
        </label>
        <label>
          描述
          <textarea
            className="skill-description-field"
            rows={5}
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            readOnly={readonly}
            disabled={readonly}
          />
        </label>
        {kind === "skill" ? (
          <label>
            技能内容
            <textarea
              className="skill-content-editor"
              rows={24}
              value={form.content}
              onChange={(e) => update("content", e.target.value)}
              readOnly={readonly}
              disabled={readonly}
            />
          </label>
        ) : (
          <>
            <label>
              传输方式
              <ScrollSelect
                optionCount={2}
                value={form.transport}
                onChange={(e) => update("transport", e.target.value)}
                disabled={readonly}
              >
                <option value="stdio">stdio</option>
                <option value="sse">sse</option>
              </ScrollSelect>
            </label>
            {form.transport === "stdio" ? (
              <>
                <label>
                  启动命令
                  <input
                    value={form.command}
                    onChange={(e) => update("command", e.target.value)}
                    readOnly={readonly}
                    disabled={readonly}
                  />
                </label>
                <label>
                  参数（逗号分隔）
                  <input
                    value={form.argsText}
                    onChange={(e) => update("argsText", e.target.value)}
                    readOnly={readonly}
                    disabled={readonly}
                  />
                </label>
              </>
            ) : (
              <label>
                SSE 地址
                <input
                  value={form.url}
                  onChange={(e) => update("url", e.target.value)}
                  readOnly={readonly}
                  disabled={readonly}
                />
              </label>
            )}
          </>
        )}
        {meta.updated_at ? (
          <p className="field-hint">更新时间：{meta.updated_at}</p>
        ) : null}
        {!readonly ? (
          <div className="form-actions">
            <button type="submit" className="primary-btn" disabled={saving}>
              {saving ? "保存中…" : "保存修改"}
            </button>
          </div>
        ) : null}
      </form>
    </section>
  );
}
