import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createTemplate, importTemplate } from "../api.js";
import ScrollSelect from "../components/ScrollSelect.jsx";

const INIT = {
  name: "",
  display_name: "",
  description: "",
  category: "workflow",
  bodyText: '{\n  \n}',
};

function formatSaveError(err) {
  const message = String(err?.message || "保存失败");
  if (message === "Method Not Allowed") {
    return "模板接口不可用，请确认 webapi 已重启并包含最新代码。";
  }
  if (message.includes("已存在")) {
    return `${message}。请更换标识后重试。`;
  }
  return message;
}

function parseBody(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    throw new Error("模板 JSON 不能为空");
  }
  const data = JSON.parse(trimmed);
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("模板 JSON 必须是对象");
  }
  return data;
}

export default function TemplateCreate() {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [form, setForm] = useState(INIT);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const body = parseBody(form.bodyText);
      await createTemplate({
        name: form.name,
        display_name: form.display_name,
        description: form.description,
        category: form.category,
        body,
      });
      navigate("/templates");
    } catch (err) {
      setError(formatSaveError(err));
    } finally {
      setSaving(false);
    }
  }

  async function onImportFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setSaving(true);
    setError("");
    try {
      const text = await file.text();
      const data = parseBody(text);
      const hasMeta = Boolean(form.name.trim() || data.name);
      if (hasMeta && form.name.trim()) {
        await importTemplate({
          name: form.name,
          display_name: form.display_name,
          description: form.description,
          category: form.category,
          body: data,
        });
        navigate("/templates");
        return;
      }
      await importTemplate({ body: data });
      navigate("/templates");
    } catch (err) {
      setError(formatSaveError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="skill-detail-page">
      <div className="page-head">
        <div>
          <h1 className="page-title">新建 / 导入模板</h1>
          <p className="page-desc">创建 Agent 可用的 JSON 模板，或从文件导入。工作流模板可包含 {"{workflow_name}"} 等占位符。</p>
        </div>
        <Link className="config-btn" to="/templates">
          返回列表
        </Link>
      </div>
      {error ? (
        <div className="banner error" role="alert">
          {error}
        </div>
      ) : null}
      <form className="form-card skill-detail-form" onSubmit={onSubmit}>
        <label>
          标识
          <input
            required
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            placeholder="例如 workflow_build_deploy"
          />
        </label>
        <label>
          显示名称
          <input value={form.display_name} onChange={(e) => update("display_name", e.target.value)} placeholder="可选" />
        </label>
        <label>
          描述
          <input value={form.description} onChange={(e) => update("description", e.target.value)} placeholder="模板用途说明" />
        </label>
        <label>
          类型
          <ScrollSelect optionCount={2} value={form.category} onChange={(e) => update("category", e.target.value)}>
            <option value="workflow">工作流</option>
            <option value="general">通用</option>
          </ScrollSelect>
        </label>
        <label>
          模板 JSON
          <textarea
            className="skill-content-editor"
            rows={16}
            required
            value={form.bodyText}
            onChange={(e) => update("bodyText", e.target.value)}
            placeholder='{"stages": [...]}'
            spellCheck={false}
          />
        </label>
        <div className="form-actions">
          <button type="button" className="config-btn" disabled={saving} onClick={() => fileRef.current?.click()}>
            从文件导入
          </button>
          <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={onImportFile} />
          <button type="submit" className="primary-btn" disabled={saving}>
            {saving ? "保存中…" : "创建模板"}
          </button>
        </div>
      </form>
    </section>
  );
}
