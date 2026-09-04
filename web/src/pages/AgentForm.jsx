import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createAgent, fetchAgent, updateAgent } from "../api.js";

const EMPTY = {
  name: "",
  api_key: "",
  primary_model: "",
  backup_models: [],
  base_url: "https://openrouter.ai/api/v1",
  is_default: false,
};

export default function AgentForm() {
  const { agentId } = useParams();
  const editing = Boolean(agentId);
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [masked, setMasked] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!editing) return;
    fetchAgent(agentId)
      .then((data) => {
        const item = data.item;
        setForm({
          name: item.name || "",
          api_key: "",
          primary_model: item.primary_model || item.model || "",
          backup_models: item.backup_models?.length ? [...item.backup_models] : [],
          base_url: item.base_url || "",
          is_default: Boolean(item.is_default),
        });
        setMasked(item.api_key_masked || "");
      })
      .catch((err) => setError(err.message));
  }, [agentId, editing]);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function updateBackup(index, value) {
    setForm((prev) => ({
      ...prev,
      backup_models: prev.backup_models.map((item, i) => (i === index ? value : item)),
    }));
  }

  function addBackup() {
    setForm((prev) => ({ ...prev, backup_models: [...prev.backup_models, ""] }));
  }

  function removeBackup(index) {
    setForm((prev) => ({
      ...prev,
      backup_models: prev.backup_models.filter((_, i) => i !== index),
    }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload = {
      ...form,
      model: form.primary_model,
      backup_models: form.backup_models.map((item) => item.trim()).filter(Boolean),
    };
    try {
      if (editing) {
        await updateAgent(agentId, payload);
      } else {
        await createAgent(payload);
      }
      navigate("/agents");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="skill-detail-page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{editing ? "编辑 Agent" : "新增 Agent"}</h1>
          <p className="page-desc">
            同一 Agent 可配置一个主模型和多个备用模型。主模型不可用时，会自动按顺序切换到备用模型。
          </p>
        </div>
        <Link className="config-btn" to="/agents">
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
          名称
          <input required value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="例如 openrouter-main" />
        </label>
        <label>
          主模型
          <input
            required
            value={form.primary_model}
            onChange={(e) => update("primary_model", e.target.value)}
            placeholder="deepseek-v4-flash"
          />
        </label>
        <div className="backup-models-field">
          <div className="backup-models-head">
            <span className="field-label-text">备用模型</span>
            <button type="button" className="config-btn" onClick={addBackup}>
              添加备用模型
            </button>
          </div>
          <p className="field-hint backup-models-hint">主模型不可用时，将按顺序尝试备用模型。</p>
          <div className="backup-models-panel">
            {form.backup_models.length === 0 ? (
              <p className="backup-models-empty">暂无备用模型</p>
            ) : (
              <ul className="backup-models-list">
                {form.backup_models.map((model, index) => (
                  <li className="backup-model-item" key={`backup-${index}`}>
                    <span className="backup-model-order">{index + 1}</span>
                    <input
                      className="backup-model-input"
                      value={model}
                      onChange={(e) => updateBackup(index, e.target.value)}
                      placeholder="例如 gpt-4o-mini"
                    />
                    <button
                      type="button"
                      className="link-btn danger backup-model-remove"
                      onClick={() => removeBackup(index)}
                    >
                      删除
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <label>
          Base URL
          <input required value={form.base_url} onChange={(e) => update("base_url", e.target.value)} placeholder="https://openrouter.ai/api/v1" />
        </label>
        <label>
          API Key
          <input
            type="password"
            required={!editing}
            value={form.api_key}
            onChange={(e) => update("api_key", e.target.value)}
            placeholder={editing ? `已保存 ${masked}，留空则不修改` : "sk-..."}
            autoComplete="off"
          />
        </label>
        <label className="check-row">
          <input type="checkbox" checked={form.is_default} onChange={(e) => update("is_default", e.target.checked)} />
          设为默认 Agent
        </label>
        <div className="form-actions">
          <button type="submit" className="primary-btn" disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </form>
    </section>
  );
}
