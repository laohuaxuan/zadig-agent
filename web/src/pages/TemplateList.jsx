import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteTemplate, fetchTemplates } from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import Pagination, { usePager } from "../Pagination.jsx";

const COLUMNS = [
  { key: "display_name", label: "名称", truncate: true },
  { key: "name", label: "标识", truncate: true },
  { key: "category", label: "类型" },
  { key: "description", label: "描述", truncate: true },
  { key: "updated_at", label: "更新时间" },
];

const CATEGORY_LABEL = {
  workflow: "工作流",
  general: "通用",
};

export default function TemplateList() {
  const { permissions } = useAuth();
  const pager = usePager("page-size-templates");
  const [state, setState] = useState({ loading: true, error: "", items: [] });
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      const data = await fetchTemplates({ pageNum: pager.page, pageSize: pager.pageSize });
      pager.setTotal(data.total || 0);
      setState({ loading: false, error: "", items: data.items || [] });
    } catch (err) {
      pager.setTotal(0);
      const message = String(err?.message || "加载失败");
      const hint =
        message === "Not Found" || message === "Method Not Allowed"
          ? "模板接口不可用，请确认 webapi 已重启并包含最新代码。"
          : message;
      setState({ loading: false, error: hint, items: [] });
    }
  }, [pager.page, pager.pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  async function onDelete() {
    if (!pending) return;
    setBusy(pending.name);
    try {
      await deleteTemplate(pending.name);
      setPending(null);
      await load();
    } catch (err) {
      setState((prev) => ({ ...prev, error: err.message }));
    } finally {
      setBusy("");
    }
  }

  const hideEmptyLoadError =
    state.items.length === 0 &&
    (state.error === "Not Found" ||
      state.error === "Method Not Allowed" ||
      state.error.includes("模板接口不可用"));

  return (
    <section>
      <div className="page-head">
        <div>
          <h1 className="page-title">模板列表</h1>
          <p className="page-desc">供 Agent 使用的 JSON 模板，配置保存在 MySQL，可在页面新建、导入与编辑。</p>
        </div>
        {permissions.can_manage_templates ? (
          <Link className="primary-btn" to="/templates/new">
            新建 / 导入
          </Link>
        ) : null}
      </div>
      {state.error && !hideEmptyLoadError ? (
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
                {COLUMNS.map((col) => (
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
                  <td colSpan={COLUMNS.length + 1} className="empty">
                    暂无模板，点击右上角新建或导入。
                  </td>
                </tr>
              ) : (
                state.items.map((row) => (
                  <tr key={row.name}>
                    {COLUMNS.map((col) => {
                      const value =
                        col.key === "category"
                          ? CATEGORY_LABEL[row.category] || row.category || "—"
                          : row[col.key] || (col.key === "display_name" ? row.name : "—") || "—";
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
                          <Link className="link-btn" to={`/templates/${encodeURIComponent(row.name)}`}>
                            编辑
                          </Link>
                          {row.deletable ? (
                            <button type="button" className="link-btn danger" onClick={() => setPending(row)}>
                              删除
                            </button>
                          ) : null}
                        </>
                      ) : (
                        <Link className="link-btn" to={`/templates/${encodeURIComponent(row.name)}`}>
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
          <div className="dialog" role="alertdialog" aria-labelledby="del-template-title" aria-modal="true">
            <h2 id="del-template-title">删除模板</h2>
            <p>确认删除 {pending.display_name || pending.name}？此操作会从数据库移除该配置。</p>
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
