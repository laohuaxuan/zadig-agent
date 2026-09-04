import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createZadigInstance, fetchZadigInstance, updateZadigInstance } from "../api.js";

const EMPTY = { name: "", remark: "", base_url: "", api_token: "", is_active: false };

export default function ZadigForm() {
  const { instanceId } = useParams();
  const editing = Boolean(instanceId);
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [masked, setMasked] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!editing) return;
    fetchZadigInstance(instanceId)
      .then((data) => {
        const item = data.item;
        setForm({
          name: item.name || "",
          remark: item.remark || "",
          base_url: item.base_url || "",
          api_token: "",
          is_active: Boolean(item.is_active),
        });
        setMasked(item.api_token_masked || "");
      })
      .catch((err) => setError(err.message));
  }, [instanceId, editing]);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      if (editing) {
        await updateZadigInstance(instanceId, form);
      } else {
        await createZadigInstance(form);
      }
      navigate("/zadig");
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
          <h1 className="page-title">{editing ? "编辑 Zadig" : "新增 Zadig"}</h1>
          <p className="page-desc">保存后写入 MySQL。创建项目、资源同步和 MCP 工具均使用当前生效的 Zadig 实例。</p>
        </div>
        <Link className="config-btn" to="/zadig">
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
          <input required value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="例如 生产环境 Zadig" />
        </label>
        <label>
          备注
          <textarea
            rows={3}
            value={form.remark}
            onChange={(e) => update("remark", e.target.value)}
            placeholder="可选，说明该实例用途、环境等信息"
          />
        </label>
        <label>
          Base URL
          <input
            required
            value={form.base_url}
            onChange={(e) => update("base_url", e.target.value)}
            placeholder="https://zadig.example.com"
          />
        </label>
        <label>
          API Token
          <input
            type="password"
            required={!editing}
            value={form.api_token}
            onChange={(e) => update("api_token", e.target.value)}
            placeholder={editing ? `已保存 ${masked}，留空则不修改` : "Bearer Token"}
            autoComplete="off"
          />
        </label>
        <label className="check-row">
          <input type="checkbox" checked={form.is_active} onChange={(e) => update("is_active", e.target.checked)} />
          设为当前生效 Zadig
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
