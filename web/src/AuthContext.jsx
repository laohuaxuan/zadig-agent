import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchAuthProviders, fetchUserInfo, loginLocal, logout as apiLogout, setAuthToken, getAuthToken } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState({ feishu_enabled: false, local_login_enabled: true, root_login_enabled: true });

  const refresh = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setUser(null);
      return null;
    }
    const data = await fetchUserInfo();
    setUser(data.item || null);
    return data.item || null;
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const feishuToken = params.get("feishu_token");
    if (feishuToken) {
      setAuthToken(feishuToken);
      params.delete("feishu_token");
      const next = `${window.location.pathname}${params.toString() ? `?${params}` : ""}`;
      window.history.replaceState({}, "", next);
    }
    Promise.all([
      fetchAuthProviders().catch(() => ({ feishu_enabled: false, local_login_enabled: true, root_login_enabled: true })),
      getAuthToken() ? refresh().catch(() => null) : Promise.resolve(null),
    ])
      .then(([providerData]) => {
        setProviders(providerData);
      })
      .finally(() => setLoading(false));
  }, [refresh]);

  const login = useCallback(async (name, password) => {
    const data = await loginLocal(name, password);
    if (data.token) setAuthToken(data.token);
    const item = data.item?.permissions ? data.item : await refresh();
    if (item) setUser(item);
    return item;
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      /* ignore */
    }
    setAuthToken("");
    setUser(null);
  }, []);

  useEffect(() => {
    if (!loading && user && Object.keys(user.permissions || {}).length === 0) {
      refresh().catch(() => null);
    }
  }, [loading, user, refresh]);

  const value = useMemo(
    () => ({
      user,
      loading,
      providers,
      refresh,
      login,
      logout,
      permissions: user?.permissions || {},
    }),
    [user, loading, providers, refresh, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
