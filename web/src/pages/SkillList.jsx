import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteMcpSkill, deleteSkill, fetchMcpSkills, fetchSkills } from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import Pagination, { usePager } from "../Pagination.jsx";

const CONFIG = {
  skill: {
    title: "Skills 列表",
    createTo: "/skills/new",
    detailTo: (name) => `/skills/${encodeURIComponent(name)}`,
    fetch: fetchSkills,
    remove: deleteSkill,
    storageKey: "page-size-skills",
    columns: [
      { key: "display_name", label: "名称", truncate: true },
      { key: "name", label: "标识", truncate: true },
      { key: "description", label: "描述", truncate: true },
      { key: "updated_at", label: "更新时间" },
    ],
  },
  mcp: {
    title: "MCP 技能列表",
    createTo: "/mcp/new",
    detailTo: (name) => `/mcp/${encodeURIComponent(name)}`,
    fetch: fetchMcpSkills,
    remove: deleteMcpSkill,
    storageKey: "page-size-mcp",
    columns: [
      { key: "display_name", label: "名称", truncate: true },
      { key: "name", label: "标识", truncate: true },
      { key: "description", label: "描述", truncate: true },
      { key: "source", label: "来源" },
      { key: "module", label: "模块" },
      { key: "transport", label: "传输" },
    ],
  },
};

export default function SkillList({ kind }) {
  const config = CONFIG[kind];
  const { permissions } = useAuth();
  const pager = usePager(config.storageKey);
  const [state, setState] = useState({ loading: true, error: "", items: [] });
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      const data = await config.fetch({ pageNum: pager.page, pageSize: pager.pageSize });
      pager.setTotal(data.total || 0);
      setState({ loading: false, error: "", items: data.items || [] });
    } catch (err) {
      pager.setTotal(0);
      setState({ loading: false, error: err.message, items: [] });
    }
  }, [config, pager.page, pager.pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  async function onDelete() {
    if (!pending) return;
    setBusy(pending.name);
    try {
      await config.remove(pending.name);
      setPending(null);
      await load();
    } catch (err) {
      setState((prev) => ({ ...prev, error: err.message }));
    } finally {
      setBusy("");
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1 className="page-title">{config.title}</h1>
          <p className="page-desc">
            {kind === "mcp"
              ? "MCP 配置保存在 MySQL；内置工具由系统同步入库，只读展示。"
              : "Skill 配置保存在 MySQL，可在页面新建与编辑。"}
          </p>
        </div>
        {permissions.can_manage_skills ? (
          <Link className="primary-btn" to={config.createTo}>
            新建
          </Link>
        ) : null}
      </div>
      {state.error ? (
        <div className="banner error" role="alert">
          {state.error}
        </div>
      ) : null}
      {state.loading ? (
        <div className="skeleton-list" aria-busy="true" aria-label="加载中">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="skill-list-table">
            <thead>
              <tr>
                {config.columns.map((col) => (
                  <th key={col.key} className={col.truncate ? `col-truncate col-${col.key}` : undefined}>
                    {col.label}
                  </th>
                ))}
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {state.items.length === 0 ? (
                <tr>
                  <td colSpan={config.columns.length + 1} className="empty">
                    暂无技能，点击右上角新建。
                  </td>
                </tr>
              ) : (
                state.items.map((row) => (
                  <tr key={row.name}>
                    {config.columns.map((col) => {
                      const value = row[col.key] || (col.key === "display_name" ? row.name : "—") || "—";
                      return (
                        <td
                          key={col.key}
                          className={col.truncate ? "cell-truncate" : undefined}
                          title={col.truncate && value !== "—" ? value : undefined}
                        >
                          {value}
                        </td>
                      );
                    })}
                    <td className="row-actions">
                      {row.editable ? (
                        <>
                          <Link className="link-btn" to={config.detailTo(row.name)}>
                            编辑
                          </Link>
                          {row.deletable ? (
                            <button type="button" className="link-btn danger" onClick={() => setPending(row)}>
                              删除
                            </button>
                          ) : null}
                        </>
                      ) : (
                        <Link className="link-btn" to={config.detailTo(row.name)}>
                          查看
                        </Link>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
      {!state.loading ? (
        <Pagination
          page={pager.page}
          pageSize={pager.pageSize}
          total={pager.total}
          onPageChange={pager.setPage}
          onPageSizeChange={pager.setPageSize}
        />
      ) : null}
      {pending ? (
        <div className="dialog-backdrop" role="presentation">
          <div className="dialog" role="alertdialog" aria-labelledby="del-skill-title" aria-modal="true">
            <h2 id="del-skill-title">删除技能</h2>
            <p>
              确认删除 {pending.display_name || pending.name}？此操作会从数据库移除该配置。
            </p>
            <div className="form-actions">
              <button type="button" className="config-btn" onClick={() => setPending(null)}>
                取消
              </button>
              <button type="button" className="primary-btn" onClick={onDelete} disabled={busy === pending.name}>
                删除
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
