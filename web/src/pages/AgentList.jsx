import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteAgent, fetchAgents, setDefaultAgent } from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import Pagination, { usePager } from "../Pagination.jsx";

export default function AgentList() {
  const { permissions } = useAuth();
  const canManage = permissions.can_manage_agents;
  const pager = usePager("page-size-agents");
  const [state, setState] = useState({ loading: true, error: "", items: [] });
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      const data = await fetchAgents({ pageNum: pager.page, pageSize: pager.pageSize });
      pager.setTotal(data.total || 0);
      setState({ loading: false, error: "", items: data.items || [] });
    } catch (err) {
      pager.setTotal(0);
      setState({ loading: false, error: err.message, items: [] });
    }
  }, [pager.page, pager.pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  async function onDefault(id) {
    setBusy(id);
    try {
      await setDefaultAgent(id);
      await load();
    } catch (err) {
      setState((prev) => ({ ...prev, error: err.message }));
    } finally {
      setBusy("");
    }
  }

  async function onDelete() {
    if (!pending) return;
    setBusy(pending.id);
    try {
      await deleteAgent(pending.id);
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
          <h1 className="page-title">Agent 列表</h1>
          <p className="page-desc">同一 Agent 支持主模型和多个备用模型；主模型不可用时自动切换。默认 Agent 不可用时，会切换到其他 Agent。</p>
        </div>
        {canManage ? (
          <Link className="primary-btn" to="/agents/new">
            新增 Agent
          </Link>
        ) : null}
      </div>
      {state.error ? (
        <div className="banner error" role="alert">
          {state.error}
        </div>
      ) : null}
      {state.loading ? (
        <div className="skeleton-list" aria-busy="true">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-list-table">
            <thead>
              <tr>
                <th className="col-truncate col-name">名称</th>
                <th className="col-truncate col-model">主模型</th>
                <th className="col-truncate col-backup">备用模型</th>
                <th className="col-truncate col-base_url">Base URL</th>
                <th className="col-truncate col-api_key">API Key</th>
                <th className="col-status">状态</th>
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {state.items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty">
                    尚未配置 Agent。
                  </td>
                </tr>
              ) : (
                state.items.map((row) => (
                  <tr key={row.id}>
                    <td className="cell-truncate" title={row.name || undefined}>
                      {row.name}
                      {row.is_default ? <span className="tag">默认</span> : null}
                    </td>
                    <td className="cell-truncate" title={row.primary_model || row.model || undefined}>
                      {row.primary_model || row.model || "—"}
                    </td>
                    <td className="cell-truncate" title={row.backup_models?.length ? row.backup_models.join("、") : undefined}>
                      {row.backup_models?.length ? row.backup_models.join("、") : "—"}
                    </td>
                    <td className="cell-truncate" title={row.base_url || undefined}>
                      {row.base_url || "—"}
                    </td>
                    <td className="cell-truncate" title={row.api_key_masked || undefined}>
                      {row.api_key_masked || "—"}
                    </td>
                    <td className="agent-status-cell">
                      <span
                        className={`status ${row.available ? "ok" : "bad"}`}
                        title={row.available ? "可用" : row.error || "不可用"}
                      >
                        {row.available ? "可用" : row.error || "不可用"}
                      </span>
                    </td>
                    <td className="row-actions">
                      {canManage ? (
                        <>
                          <Link className="link-btn" to={`/agents/${row.id}/edit`}>
                            编辑
                          </Link>
                          {!row.is_default ? (
                            <button type="button" className="link-btn" disabled={busy === row.id} onClick={() => onDefault(row.id)}>
                              设为默认
                            </button>
                          ) : null}
                          <button type="button" className="link-btn danger" onClick={() => setPending(row)}>
                            删除
                          </button>
                        </>
                      ) : (
                        <span className="muted-text">—</span>
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
          <div className="dialog" role="alertdialog" aria-labelledby="del-title" aria-modal="true">
            <h2 id="del-title">删除 Agent</h2>
            <p>确认删除 {pending.name}？此操作会从数据库移除该配置。</p>
            <div className="form-actions">
              <button type="button" className="config-btn" onClick={() => setPending(null)}>
                取消
              </button>
              <button type="button" className="primary-btn" onClick={onDelete} disabled={busy === pending.id}>
                删除
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
