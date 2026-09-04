import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";

export function RequirePerm({ perm, fallback = "/workflows", children }) {
  const { permissions } = useAuth();
  if (!permissions[perm]) return <Navigate to={fallback} replace />;
  return children;
}

export function RequireAnyPerm({ perms, fallback = "/workflows", children }) {
  const { permissions } = useAuth();
  if (!perms.some((perm) => permissions[perm])) return <Navigate to={fallback} replace />;
  return children;
}
