import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import IntegrationRemarkModal from "../components/IntegrationRemarkModal.jsx";
import Pagination, { usePager } from "../Pagination.jsx";
import { updateIntegrationRemark, syncIntegrationResource } from "../api.js";
import { RESOURCES } from "../resources.js";

export default function ResourcePage() {
  const { resourceKey } = useParams();
  const resource = RESOURCES[resourceKey];
  const pager = usePager(`page-size-${resourceKey || "resource"}`);
  const [state, setState] = useState({ loading: false, error: "", data: null });
  const [remarkEditor, setRemarkEditor] = useState(null);
  const [remarkSaving, setRemarkSaving] = useState(false);

  const sync = useCallback(async ({ force = false } = {}) => {
    if (!resource) return;
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      if (force && resource.syncType) {
        await syncIntegrationResource(resource.syncType);
      }
      const data = await resource.fetch({ pageNum: pager.page, pageSize: pager.pageSize });
      pager.setTotal(data.total || 0);
      setState({ loading: false, error: data.sync_error || "", data });
    } catch (err) {
      pager.setTotal(0);
      setState((prev) => ({
        ...prev,
        loading: false,
        error: err instanceof Error ? err.message : "同步失败",
      }));
    }
  }, [resource, pager.page, pager.pageSize]);

  useEffect(() => {
    sync();
  }, [sync]);

  async function onSaveRemark(remark) {
    if (!resource?.remarkType || !remarkEditor?.resource_key) return;
    setRemarkSaving(true);
    setState((prev) => ({ ...prev, error: "" }));
    try {
      await updateIntegrationRemark(resource.remarkType, remarkEditor.resource_key, remark);
      setRemarkEditor(null);
      await sync();
    } catch (err) {
      setState((prev) => ({ ...prev, error: err.message }));
    } finally {
      setRemarkSaving(false);
    }
  }

  if (!resource) {
    return (
      <section>
        <p>未找到该配置项。</p>
        <Link to="/code-sources">返回系统集成</Link>
      </section>
    );
  }

  const items = state.data?.items || [];
  const showActions = Boolean(resource.editableRemark);

  return (
    <section>
      <div className="page-head">
        <div>
          <h1 className="page-title">{resource.title}</h1>
          <p className="page-desc">{resource.description}</p>
        </div>
        <div className="page-actions">
          {state.data?.synced_at ? (
            <span className="sync-meta">
              最近同步 {new Date(state.data.synced_at).toLocaleString("zh-CN", { hour12: false })}
            </span>
          ) : null}
          <button type="button" className="primary-btn" onClick={() => sync({ force: true })} disabled={state.loading}>
            {state.loading ? "同步中…" : "从 Zadig 同步"}
          </button>
        </div>
      </div>

      {state.error ? (
        <div className="banner error" role="alert">
          {state.error}
        </div>
      ) : null}

      {state.loading && !state.data ? (
        <div className="skeleton-list" aria-busy="true" aria-label="正在同步">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {resource.columns.map((col) => (
                  <th key={col.key}>{col.label}</th>
                ))}
                {showActions ? <th>操作</th> : null}
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={resource.columns.length + (showActions ? 1 : 0)} className="empty">
                    暂无数据，点击右上角从 Zadig 同步。
                  </td>
                </tr>
              ) : (
                items.map((row, index) => (
                  <tr key={row.resource_key || row.uid || row.cluster_id || row.registry_id || row.id || index}>
                    {resource.columns.map((col) => (
                      <td key={col.key}>
                        {col.render ? col.render(row[col.key], row) : row[col.key] || "—"}
                      </td>
                    ))}
                    {showActions ? (
                      <td className="row-actions">
                        <button
                          type="button"
                          className="link-btn"
                          onClick={() => setRemarkEditor(row)}
                          disabled={!row.resource_key}
                        >
                          编辑
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
      {state.data ? (
        <Pagination
          page={pager.page}
          pageSize={pager.pageSize}
          total={pager.total}
          onPageChange={pager.setPage}
          onPageSizeChange={pager.setPageSize}
        />
      ) : null}
      <IntegrationRemarkModal
        open={Boolean(remarkEditor)}
        title={`编辑备注 · ${remarkEditor?.alias || remarkEditor?.name || remarkEditor?.namespace || remarkEditor?.resource_key || ""}`}
        initialRemark={remarkEditor?.remark || ""}
        saving={remarkSaving}
        onClose={() => setRemarkEditor(null)}
        onSave={onSaveRemark}
      />
    </section>
  );
}
