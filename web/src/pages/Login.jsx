import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../AuthContext.jsx";

function EyeToggleIcon({ open }) {
  if (open) {
    return (
      <svg className="eye-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="currentColor"
          d="M12 5c-5 0-9.27 3.11-11 7 1.73 3.89 6 7 11 7s9.27-3.11 11-7c-1.73-3.89-6-7-11-7zm0 12a5 5 0 1 1 0-10 5 5 0 0 1 0 10zm0-8a3 3 0 1 0 .001 6.001A3 3 0 0 0 12 9z"
        />
      </svg>
    );
  }
  return (
    <svg className="eye-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M2.1 3.51 3.51 2.1l18.38 18.39-1.41 1.41-3.05-3.05A12.4 12.4 0 0 1 12 19c-5 0-9.27-3.11-11-7a13.3 13.3 0 0 1 4.2-5.17L2.1 3.51zM12 7a5 5 0 0 1 4.9 3.96l-1.55-1.55A3 3 0 0 0 12 9c-.38 0-.74.08-1.07.21L9.3 7.58A4.9 4.9 0 0 1 12 7zm-8.86 5c.98 1.98 3.05 3.84 5.94 4.7l-1.7-1.7A5 5 0 0 1 7.1 9.96L4.4 7.26A11.5 11.5 0 0 0 3.14 12zM14.9 12.8l-2.7-2.7.1-.1a3 3 0 0 1 2.6 2.8z"
      />
    </svg>
  );
}

function FeishuIcon() {
  return (
    <svg className="third-party-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M6.5 3h11A2.5 2.5 0 0 1 20 5.5v13A2.5 2.5 0 0 1 17.5 21h-11A2.5 2.5 0 0 1 4 18.5v-13A2.5 2.5 0 0 1 6.5 3zm1.8 5.2-2.1 3.9h1.6l.5-1.1h2.4l.5 1.1h1.6l-2.1-3.9H8.3zm.2 2.4.7-1.3.7 1.3H8.5zm6.2-2.4 2.8 3.9V8.3h-1.4v2.1l-1.9-2.7h-1.5v3.9h1.4V9.1l1.9 2.7h1.5V8.3h-1.4z"
      />
    </svg>
  );
}

export default function Login() {
  const { user, loading, providers, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [name, setName] = useState("admin");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showLocalLogin, setShowLocalLogin] = useState(false);

  useEffect(() => {
    const feishuError = params.get("feishu_error");
    if (feishuError) setError(feishuError);
  }, [params]);

  useEffect(() => {
    if (!loading && user) navigate("/", { replace: true });
  }, [loading, user, navigate]);

  useEffect(() => {
    if (!loading) {
      setShowLocalLogin(!providers.feishu_enabled && providers.local_login_enabled);
    }
  }, [loading, providers.feishu_enabled, providers.local_login_enabled]);

  async function onSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(name, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="auth-container">
        <div className="auth-card auth-card-feishu-only skeleton" aria-busy="true" />
      </div>
    );
  }

  const feishuEnabled = providers.feishu_enabled;
  const localEnabled = providers.local_login_enabled ?? providers.root_login_enabled;

  return (
    <div className="auth-container">
      <div className="auth-card auth-card-feishu-only">
        <h1>Zadig Agent</h1>
        {error ? (
          <div className="auth-error" role="alert">
            {error}
          </div>
        ) : null}

        {!showLocalLogin ? (
          <>
            <p className="form-hint">请使用飞书账号完成身份认证</p>
            {feishuEnabled ? (
              <button
                type="button"
                className="third-party-btn third-party-btn-feishu third-party-btn-feishu-primary"
                disabled={submitting}
                onClick={() => {
                  window.location.href = "/api/login/feishu";
                }}
              >
                <FeishuIcon />
                <span>{submitting ? "登录中..." : "飞书认证登录"}</span>
              </button>
            ) : (
              <p className="form-hint">飞书登录未配置，请联系管理员。</p>
            )}
            {localEnabled ? (
              <div className="auth-links">
                <button type="button" className="link-btn" onClick={() => setShowLocalLogin(true)}>
                  账号密码登录
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <>
            <p className="form-hint">使用本地账号登录</p>
            <form onSubmit={onSubmit}>
              <div>
                <label htmlFor="login-username">用户名</label>
                <input
                  id="login-username"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  autoFocus
                  placeholder="admin"
                  autoComplete="username"
                />
              </div>
              <div>
                <label htmlFor="login-password">密码</label>
                <div className="password-input-row auth-password-row">
                  <input
                    id="login-password"
                    type={passwordVisible ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    placeholder="请输入密码"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    className="password-toggle-btn"
                    onClick={() => setPasswordVisible((v) => !v)}
                    aria-label={passwordVisible ? "隐藏密码" : "显示密码"}
                  >
                    <EyeToggleIcon open={passwordVisible} />
                  </button>
                </div>
              </div>
              <button type="submit" disabled={submitting}>
                {submitting ? "登录中..." : "登录"}
              </button>
            </form>
            {feishuEnabled ? (
              <div className="auth-links">
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => {
                    setShowLocalLogin(false);
                    setPassword("");
                    setError("");
                  }}
                >
                  返回飞书登录
                </button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
