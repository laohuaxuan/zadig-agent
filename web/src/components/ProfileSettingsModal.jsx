import { useEffect, useState } from "react";
import { fetchUserInfo, updateUserProfile } from "../api.js";
import {
  PASSWORD_RULE_ERROR,
  isExternalAuthUser,
  isFeishuUser,
  isPasswordValid,
} from "../utils/userHelpers.js";

export default function ProfileSettingsModal({ open, onClose, onSaved }) {
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: "", text: "" });

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setForm(null);
    setMessage({ type: "", text: "" });
    fetchUserInfo()
      .then((data) => {
        const item = data.item || {};
        setForm({
          name: item.name || "",
          display_name: item.display_name || item.name || "",
          phone: item.phone || "",
          email: item.email || "",
          auth_source: item.auth_source || "local",
          new_password: "",
          confirm_password: "",
          password_message: "",
          confirm_message: "",
        });
      })
      .catch((err) => {
        setMessage({ type: "error", text: err.message || "加载个人信息失败" });
      })
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  function onProfilePasswordChange(value) {
    if (!form) return;
    const nextPwd = value.slice(0, 24);
    const passwordMessage = !nextPwd ? "" : isPasswordValid(nextPwd) ? "密码格式正确" : PASSWORD_RULE_ERROR;
    const confirm = form.confirm_password || "";
    const confirmMessage = !confirm ? "" : nextPwd === confirm ? "两次密码一致" : "两次输入的密码不一致";
    setForm({
      ...form,
      new_password: nextPwd,
      password_message: passwordMessage,
      confirm_message: confirmMessage,
    });
  }

  function onProfileConfirmPasswordChange(value) {
    if (!form) return;
    const nextConfirm = value.slice(0, 24);
    const pwd = form.new_password || "";
    const confirmMessage = !nextConfirm ? "" : pwd === nextConfirm ? "两次密码一致" : "两次输入的密码不一致";
    setForm({
      ...form,
      confirm_password: nextConfirm,
      confirm_message: confirmMessage,
    });
  }

  async function submit(e) {
    e.preventDefault();
    if (!form) return;
    const isExternalAuth = isExternalAuthUser(form);
    const newPassword = (form.new_password || "").trim();
    const confirmPassword = (form.confirm_password || "").trim();
    if ((newPassword || confirmPassword) && isExternalAuth) {
      setMessage({ type: "error", text: "飞书账号请在飞书客户端修改密码" });
      return;
    }
    if (newPassword || confirmPassword) {
      if (!isPasswordValid(newPassword)) {
        setForm({ ...form, password_message: PASSWORD_RULE_ERROR });
        setMessage({ type: "error", text: PASSWORD_RULE_ERROR });
        return;
      }
      if (newPassword !== confirmPassword) {
        setForm({ ...form, confirm_message: "两次输入的密码不一致" });
        setMessage({ type: "error", text: "两次输入的密码不一致" });
        return;
      }
    }
    const payload = {
      phone: isExternalAuth ? undefined : form.phone,
      email: isExternalAuth ? undefined : form.email,
    };
    if (newPassword && !isExternalAuth) {
      payload.new_password = newPassword;
      payload.confirm_password = confirmPassword;
    }
    setSaving(true);
    setMessage({ type: "", text: "" });
    try {
      const data = await updateUserProfile(payload);
      onSaved(data.item || {
        display_name: data.display_name || form.display_name,
        phone: data.phone ?? form.phone,
        email: data.email ?? form.email,
      });
      onClose();
    } catch (err) {
      setMessage({ type: "error", text: err.message || "保存失败" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-form-dialog" onClick={(e) => e.stopPropagation()}>
        <h3>个人设置</h3>
        {loading || !form ? (
          <p className="form-hint">正在加载...</p>
        ) : (
          <form onSubmit={submit} className="modal-form">
            {message.text ? (
              <p className={`form-message${message.type === "error" ? " form-message-error" : ""}`}>{message.text}</p>
            ) : null}
            <div className="form-group">
              <label>用户名</label>
              <input className="readonly-input" value={form.name} readOnly />
            </div>
            <div className="form-group">
              <label>显示名</label>
              <input className="readonly-input" value={form.display_name} readOnly />
              <p className="form-hint">显示名由飞书同步，不可修改</p>
            </div>
            <div className="form-group">
              <label>手机号</label>
              {isExternalAuthUser(form) ? (
                <>
                  <input className="readonly-input" value={form.phone || ""} readOnly />
                  <p className="form-hint">
                    {isFeishuUser(form) ? "飞书账号手机号由飞书同步，不可修改" : "手机号不可修改"}
                  </p>
                </>
              ) : (
                <input
                  required
                  value={form.phone || ""}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              )}
            </div>
            <div className="form-group">
              <label>邮箱</label>
              {isExternalAuthUser(form) ? (
                <>
                  <input className="readonly-input" type="email" value={form.email} readOnly />
                  <p className="form-hint">
                    {isFeishuUser(form) ? "飞书账号邮箱由飞书同步，不可修改" : "邮箱不可修改"}
                  </p>
                </>
              ) : (
                <input
                  required
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              )}
            </div>
            {!isExternalAuthUser(form) && (
              <>
                <div className="form-group">
                  <label>新密码（可选）</label>
                  <input
                    type="password"
                    value={form.new_password}
                    onChange={(e) => onProfilePasswordChange(e.target.value)}
                    placeholder="留空则不修改密码"
                    maxLength={24}
                  />
                  {form.password_message ? (
                    <span className={`hint-text ${isPasswordValid(form.new_password) ? "valid" : "invalid"}`}>
                      {form.password_message}
                    </span>
                  ) : null}
                </div>
                <div className="form-group">
                  <label>确认新密码</label>
                  <input
                    type="password"
                    value={form.confirm_password}
                    onChange={(e) => onProfileConfirmPasswordChange(e.target.value)}
                    placeholder="再次输入新密码"
                    maxLength={24}
                  />
                  {form.confirm_message ? (
                    <span
                      className={`hint-text ${form.new_password === form.confirm_password ? "valid" : "invalid"}`}
                    >
                      {form.confirm_message}
                    </span>
                  ) : null}
                </div>
              </>
            )}
            {isExternalAuthUser(form) && (
              <p className="form-hint">飞书用户请在飞书客户端修改账号密码。</p>
            )}
            <div className="modal-actions">
              <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
                取消
              </button>
              <button type="submit" disabled={saving}>
                {saving ? "保存中..." : "保存"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
