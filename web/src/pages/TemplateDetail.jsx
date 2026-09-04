import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { fetchTemplate, updateTemplate } from "../api.js";
import ScrollSelect from "../components/ScrollSelect.jsx";

const SOURCE_LABEL = {
  mysql: "页面配置",
  file: "仓库文件",
};

export default function TemplateDetail() {
  const { templateName } = useParams();
  const navigate = useNavigate();
  const [meta, setMeta] = useState(null);
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    fetchTemplate(templateName)
      .then((data) => {
        const item = data.item;
        setMeta(item);
        setForm({
          display_name: item.display_name || "",
          description: item.description || "",
          category: item.category || "workflow",
          bodyText: JSON.stringify(item.body || {}, null, 2),
        });
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [templateName]);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (!meta?.editable) return;
    setSaving(true);
    setError("");
    try {
      const body = JSON.parse(form.bodyText);
      if (!body || typeof body !== "object" || Array.isArray(body)) {
        throw new Error("模板 JSON 必须是对象");
      }
      await updateTemplate(templateName, {
        display_name: form.display_name,
        description: form.description,
        category: form.category,
        body,
      });
      navigate("/templates");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <section className="skill-detail-page">
        <div className="skeleton-list" aria-busy="true">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      </section>
    );
  }

  if (!meta || !form) {
    return (
      <section className="skill-detail-page">
        <div className="banner error" role="alert">
          {error || "模板不存在"}
        </div>
        <Link className="link-btn" to="/templates">
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
            标识 {meta.name} · 来源 {SOURCE_LABEL[meta.source] || meta.source}
            {meta.file ? ` · 文件 ${meta.file}` : ""}
          </p>
        </div>
        <Link className="config-btn" to="/templates">
          返回列表
        </Link>
      </div>
      {readonly ? (
        <div className="banner" role="status">
          此模板来自{SOURCE_LABEL[meta.source] || "外部来源"}，仅可查看，不可在此页面编辑。
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
          <input
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            readOnly={readonly}
            disabled={readonly}
          />
        </label>
        <label>
          类型
          <ScrollSelect
            optionCount={2}
            value={form.category}
            onChange={(e) => update("category", e.target.value)}
            disabled={readonly}
          >
            <option value="workflow">工作流</option>
            <option value="general">通用</option>
          </ScrollSelect>
        </label>
        <label>
          模板 JSON
          <textarea
            className="skill-content-editor"
            rows={16}
            value={form.bodyText}
            onChange={(e) => update("bodyText", e.target.value)}
            readOnly={readonly}
            disabled={readonly}
            spellCheck={false}
          />
        </label>
        {meta.updated_at ? <p className="field-hint">更新时间：{meta.updated_at}</p> : null}
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
