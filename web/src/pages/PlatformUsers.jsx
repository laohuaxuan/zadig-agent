import { useEffect, useMemo, useState } from "react";
import {
  deletePlatformUser,
  fetchPlatformUsers,
  resetPlatformUserPassword,
  updatePlatformUser,
  updatePlatformUserStatus,
} from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import RolePermissionHelp from "../components/RolePermissionHelp.jsx";
import ScrollSelect from "../components/ScrollSelect.jsx";
import {
  PASSWORD_RULE_HINT,
  ROLE_OPTIONS,
  authSourceLabel,
  displayUserEmail,
  isFeishuUser,
  roleLabel,
  validateEditUserInput,
} from "../utils/userHelpers.js";

const PAGE_SIZE = 20;

export default function PlatformUsers() {
  const { user, permissions } = useAuth();
  const canModifyUsers = permissions.can_modify_users;
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [editModal, setEditModal] = useState(null);
  const [editFormMessage, setEditFormMessage] = useState("");
  const [resetPasswordResult, setResetPasswordResult] = useState(null);

  const editableRoleOptions = useMemo(
    () => (user?.role === "admin" ? ROLE_OPTIONS.filter((opt) => opt.value === "watcher") : ROLE_OPTIONS),
    [user?.role],
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  async function load(nextPage = page, nextKeyword = keyword) {
    setLoading(true);
    setError("");
    try {
      const data = await fetchPlatformUsers({ keyword: nextKeyword, page: nextPage, pageSize: PAGE_SIZE });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(page, keyword);
  }, [page]);

  function onSearch() {
    setPage(1);
    load(1, keyword);
  }

  async function submitEditUser(event) {
    event.preventDefault();
    if (!editModal) return;
    setEditFormMessage("");
    const err = validateEditUserInput(editModal, isFeishuUser(editModal));
    if (err) {
      setEditFormMessage(err);
      return;
    }
    try {
      await updatePlatformUser(editModal.id, {
        display_name: String(editModal.display_name || "").trim(),
        phone: String(editModal.phone || "").trim(),
        email: editModal.email,
        role: editModal.role,
      });
      setEditModal(null);
      setMessage("用户信息已更新");
      await load();
    } catch (err) {
      setEditFormMessage(err.message);
    }
  }

  async function toggleUserOffline(item) {
    const nextStatus = item.status === "disabled" ? "active" : "disabled";
    const label = nextStatus === "disabled" ? "下线" : "上线";
    if (!window.confirm(`确认${label}用户「${item.display_name || item.name}」？`)) return;
    try {
      await updatePlatformUserStatus(item.id, nextStatus);
      setMessage(`用户已${label}`);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleResetPassword(item) {
    if (isFeishuUser(item)) {
      setError("飞书用户密码由飞书管理");
      return;
    }
    const label = item.display_name || item.name;
    if (!window.confirm(`确认重置用户「${label}」的密码？将生成新的随机密码。`)) return;
    try {
      const data = await resetPlatformUserPassword(item.id);
      setResetPasswordResult({
        username: item.name,
        display_name: label,
        password: data.password || "",
      });
      setMessage("密码重置成功，请妥善保存新密码");
    } catch (err) {
      setError(err.message);
    }
  }

  async function onDelete(id, name) {
    if (!window.confirm(`确认删除用户「${name}」？此操作不可撤销。`)) return;
    try {
      await deletePlatformUser(id);
      setMessage("用户删除成功");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card">
      <div className="table-head">
        <h2>用户管理</h2>
        <div className="row">
          <button type="button" className="btn-secondary" onClick={() => load()}>
            刷新
          </button>
        </div>
      </div>
      {!canModifyUsers ? (
        <p className="muted-text user-manage-hint">管理员仅可查看用户信息，修改请联系超级管理员。</p>
      ) : null}
      {error ? <div className="banner error">{error}</div> : null}
      {message ? <div className="banner success">{message}</div> : null}
      <div className="toolbar">
        <input
          placeholder="搜索用户名/显示名/手机号/邮箱"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSearch();
          }}
        />
      </div>
      <div className="table-wrap">
        <table className="data-list-table">
          <thead>
            <tr>
              <th className="col-truncate col-name">用户名</th>
              <th className="col-truncate col-display_name">显示名</th>
              <th className="col-source">来源</th>
              <th className="col-truncate col-phone">手机号</th>
              <th className="col-truncate col-email">邮箱</th>
              <th className="col-role">角色</th>
              <th className="col-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="empty-cell">
                  加载用户列表...
                </td>
              </tr>
            ) : (
              <>
                {items.map((item) => {
                  const isSelf = Number(item.id) === Number(user?.id);
                  const offline = item.status === "disabled";
                  const email = displayUserEmail(item);
                  return (
                    <tr key={item.id} className={offline ? "row-disabled" : ""}>
                      <td className="cell-truncate" title={item.name || undefined}>
                        {item.name}
                        {offline ? <span className="status-tag">已下线</span> : null}
                      </td>
                      <td className="cell-truncate" title={item.display_name || item.name || undefined}>
                        {item.display_name || item.name}
                      </td>
                      <td>{authSourceLabel(item)}</td>
                      <td className="cell-truncate" title={item.phone || undefined}>
                        {item.phone || ""}
                      </td>
                      <td className="cell-truncate" title={email || undefined}>
                        {email}
                      </td>
                      <td>{item.role_label || roleLabel(item.role)}</td>
                      <td className="row-actions">
                        {canModifyUsers ? (
                          <>
                            <button
                              type="button"
                              className="link-btn"
                              onClick={() => {
                                setEditFormMessage("");
                                setEditModal({
                                  id: item.id,
                                  name: item.name,
                                  display_name: item.display_name || item.name,
                                  phone: item.phone || "",
                                  email: item.email || "",
                                  role: item.role,
                                  auth_source: item.auth_source || "local",
                                });
                              }}
                            >
                              修改
                            </button>
                            {!isSelf ? (
                              <>
                                <span className="btn-spacing">|</span>
                                <button type="button" className="link-btn" onClick={() => toggleUserOffline(item)}>
                                  {offline ? "上线" : "下线"}
                                </button>
                              </>
                            ) : null}
                            {isFeishuUser(item) ? (
                              <>
                                <span className="btn-spacing">|</span>
                                <span className="muted-text" title="飞书用户密码由飞书管理">
                                  飞书账号
                                </span>
                              </>
                            ) : (
                              <>
                                <span className="btn-spacing">|</span>
                                <button type="button" className="link-btn" onClick={() => handleResetPassword(item)}>
                                  重置密码
                                </button>
                              </>
                            )}
                            {!isSelf ? (
                              <>
                                <span className="btn-spacing">|</span>
                                <button
                                  type="button"
                                  className="link-btn danger-link"
                                  onClick={() => onDelete(item.id, item.display_name || item.name)}
                                >
                                  删除
                                </button>
                              </>
                            ) : null}
                          </>
                        ) : (
                          <span className="muted-text">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-cell">
                      暂无用户
                    </td>
                  </tr>
                ) : null}
              </>
            )}
          </tbody>
        </table>
      </div>
      <div className="pager pager-bottom">
        <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
          上一页
        </button>
        <span>
          第 {page} 页 / 共 {totalPages} 页
        </span>
        <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
          下一页
        </button>
      </div>

      {editModal ? (
        <div className="modal-overlay" onClick={() => setEditModal(null)}>
          <div className="modal modal-form-dialog" onClick={(e) => e.stopPropagation()}>
            <h3>修改用户 - {editModal.name}</h3>
            <form onSubmit={submitEditUser} className="modal-form">
              {editFormMessage ? <div className="form-message form-message-error">{editFormMessage}</div> : null}
              <div className="form-group">
                <label>用户名</label>
                <input className="readonly-input" value={editModal.name} readOnly />
              </div>
              <div className="form-group">
                <label>显示名 *</label>
                <input
                  required
                  value={editModal.display_name}
                  onChange={(e) => setEditModal({ ...editModal, display_name: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>手机号{isFeishuUser(editModal) ? "" : " *"}</label>
                <input
                  required={!isFeishuUser(editModal)}
                  readOnly={isFeishuUser(editModal)}
                  className={isFeishuUser(editModal) ? "readonly-input" : ""}
                  value={editModal.phone || ""}
                  onChange={(e) => setEditModal({ ...editModal, phone: e.target.value })}
                  placeholder={isFeishuUser(editModal) ? "来自飞书通讯录" : "11 位手机号"}
                />
              </div>
              <div className="form-group">
                <label>角色 *</label>
                <ScrollSelect
                  optionCount={3}
                  value={editModal.role}
                  onChange={(e) => setEditModal({ ...editModal, role: e.target.value })}
                >
                  {editableRoleOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </ScrollSelect>
                <RolePermissionHelp selected={editModal.role} options={editableRoleOptions} />
              </div>
              {displayUserEmail(editModal) ? (
                <div className="form-group">
                  <label>邮箱</label>
                  <input className="readonly-input" type="email" value={displayUserEmail(editModal)} readOnly />
                  <p className="form-hint">邮箱不可在此修改</p>
                </div>
              ) : null}
              <p className="form-hint">
                {isFeishuUser(editModal)
                  ? "飞书用户密码由飞书管理，不可在此重置。"
                  : "修改用户信息时不可更改密码，请使用「重置密码」。"}
              </p>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setEditModal(null)}>
                  取消
                </button>
                <button type="submit">保存</button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {resetPasswordResult ? (
        <div className="modal-overlay" onClick={() => setResetPasswordResult(null)}>
          <div className="modal modal-form-dialog" onClick={(e) => e.stopPropagation()}>
            <h3>密码重置成功</h3>
            <div className="modal-form">
              <div className="form-group">
                <label>用户名</label>
                <input className="readonly-input" value={resetPasswordResult.username} readOnly />
              </div>
              <div className="form-group">
                <label>显示名</label>
                <input className="readonly-input" value={resetPasswordResult.display_name} readOnly />
              </div>
              <div className="form-group">
                <label>新密码（仅显示一次，请妥善保存）</label>
                <div className="password-input-row auth-password-row">
                  <input className="readonly-input" value={resetPasswordResult.password} readOnly />
                  <button
                    type="button"
                    className="password-toggle-btn"
                    title="复制密码"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(resetPasswordResult.password);
                        setMessage("密码已复制");
                      } catch {
                        setError("复制失败，请手动复制");
                      }
                    }}
                  >
                    复制
                  </button>
                </div>
                <span className="hint-text">{PASSWORD_RULE_HINT}</span>
              </div>
              <div className="modal-actions">
                <button type="button" onClick={() => setResetPasswordResult(null)}>
                  我已保存
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
