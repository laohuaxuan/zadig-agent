import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { activateZadigInstance, deleteZadigInstance, fetchZadigInstances } from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import Pagination, { usePager } from "../Pagination.jsx";

export default function ZadigList() {
  const { permissions } = useAuth();
  const canManage = permissions.can_manage_zadig;
  const pager = usePager("page-size-zadig");
  const [state, setState] = useState({ loading: true, error: "", items: [] });
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      const data = await fetchZadigInstances({ pageNum: pager.page, pageSize: pager.pageSize });
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

  async function onActivate(id) {
    setBusy(id);
    try {
      await activateZadigInstance(id);
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
      await deleteZadigInstance(pending.id);
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
          <h1 className="page-title">Zadig 列表</h1>
          <p className="page-desc">可配置多个 Zadig 实例，同时仅有一个生效。创建项目、资源同步和 MCP 均使用当前生效实例。</p>
        </div>
        {canManage ? (
          <Link className="primary-btn" to="/zadig/new">
            新增 Zadig
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
                <th className="col-truncate col-remark">备注</th>
                <th className="col-truncate col-base_url">Base URL</th>
                <th className="col-truncate col-api_key">API Token</th>
                <th className="col-status">状态</th>
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {state.items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="empty">
                    尚未配置 Zadig。
                  </td>
                </tr>
              ) : (
                state.items.map((row) => (
                  <tr key={row.id || row.base_url}>
                    <td className="cell-truncate" title={row.name || undefined}>
                      {row.name || "—"}
                      {row.is_active ? <span className="tag">生效中</span> : null}
                    </td>
                    <td className="cell-truncate" title={row.remark || undefined}>
                      {row.remark || "—"}
                    </td>
                    <td className="cell-truncate" title={row.base_url || undefined}>
                      {row.base_url || "—"}
                    </td>
                    <td className="cell-truncate" title={row.api_token_masked || undefined}>
                      {row.api_token_masked || "—"}
                    </td>
                    <td>
                      <span className={`status ${row.available ? "ok" : "bad"}`}>
                        {row.available ? "可用" : row.error || "不可用"}
                      </span>
                    </td>
                    <td className="row-actions">
                      {row.id ? (
                        canManage ? (
                          <>
                            <Link className="link-btn" to={`/zadig/${row.id}/edit`}>
                              编辑
                            </Link>
                            {!row.is_active ? (
                              <button
                                type="button"
                                className="link-btn"
                                disabled={busy === row.id}
                                onClick={() => onActivate(row.id)}
                              >
                                设为生效
                              </button>
                            ) : null}
                            <button type="button" className="link-btn danger" onClick={() => setPending(row)}>
                              删除
                            </button>
                          </>
                        ) : (
                          <span className="muted-text">—</span>
                        )
                      ) : canManage ? (
                        <Link className="link-btn" to="/zadig/new">
                          去配置
                        </Link>
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
          <div className="dialog" role="alertdialog" aria-labelledby="del-zadig-title" aria-modal="true">
            <h2 id="del-zadig-title">删除 Zadig</h2>
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
