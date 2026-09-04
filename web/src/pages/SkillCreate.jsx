import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createMcpSkill, createSkill } from "../api.js";
import ScrollSelect from "../components/ScrollSelect.jsx";

const INIT = {
  skill: { name: "", display_name: "", description: "", content: "" },
  mcp: {
    name: "",
    display_name: "",
    description: "",
    transport: "stdio",
    command: "",
    argsText: "",
    url: "",
  },
};

export default function SkillCreate({ kind }) {
  const navigate = useNavigate();
  const listPath = kind === "mcp" ? "/mcp" : "/skills";
  const [form, setForm] = useState(INIT[kind]);
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
      if (kind === "skill") {
        await createSkill(form);
        navigate("/skills");
      } else {
        await createMcpSkill({
          name: form.name,
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
        navigate("/mcp");
      }
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
          <h1 className="page-title">{kind === "mcp" ? "新建 MCP 技能" : "新建 Skill"}</h1>
          <p className="page-desc">
            {kind === "mcp"
              ? "登记一个可被 Agent 调用的 MCP 服务或工具，保存在 MySQL。"
              : "创建一个 Skill，保存在 MySQL。"}
          </p>
        </div>
        <Link className="config-btn" to={listPath}>
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
            placeholder="例如 workflow-notify"
          />
        </label>
        <label>
          显示名称
          <input
            value={form.display_name}
            onChange={(e) => update("display_name", e.target.value)}
            placeholder="可选"
          />
        </label>
        <label>
          描述
          <textarea
            className="skill-description-field"
            rows={4}
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            placeholder="这个技能做什么；可使用多行，序号列表建议每项一行"
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
              placeholder="给 Agent 的说明或模板"
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
                    required
                    value={form.command}
                    onChange={(e) => update("command", e.target.value)}
                    placeholder="python"
                  />
                </label>
                <label>
                  参数（逗号分隔）
                  <input
                    value={form.argsText}
                    onChange={(e) => update("argsText", e.target.value)}
                    placeholder="./zadig_mcp/server.py"
                  />
                </label>
              </>
            ) : (
              <label>
                SSE 地址
                <input
                  required
                  value={form.url}
                  onChange={(e) => update("url", e.target.value)}
                  placeholder="https://example.com/sse"
                />
              </label>
            )}
          </>
        )}
        <div className="form-actions">
          <button type="submit" className="primary-btn" disabled={saving}>
            {saving ? "创建中…" : "创建"}
          </button>
        </div>
      </form>
    </section>
  );
}
