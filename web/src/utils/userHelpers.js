export const PASSWORD_RULE_ERROR =
  "密码不符合规范（需包含大小写字母、数字、特殊字符，不少于6位且不超过24位）";

export const PASSWORD_RULE_HINT = "密码需包含大小写字母、数字、特殊字符，不少于6位且不超过24位";

export const ROLE_OPTIONS = [
  {
    value: "watcher",
    label: "普通成员",
    desc: "可打开项目管理并申请创建项目、添加服务与工作流，查看和执行与自己相关的审批流；可查看技能、MCP 与模板，不可创建或编辑；可查看 Agent 与 Zadig 管理页面，不可修改。",
  },
  {
    value: "admin",
    label: "管理员",
    desc: "拥有普通成员全部权限；可查看系统集成与审批配置页面，并为创建项目、添加服务与工作流配置审批模板；可新增、编辑和删除自己维护的技能与模板；不可修改 Agent 与 Zadig。",
  },
  {
    value: "root",
    label: "超级管理员",
    desc: "拥有全部权限。",
  },
];

export function roleLabel(role) {
  return ROLE_OPTIONS.find((item) => item.value === role)?.label || role || "-";
}

export function isFeishuUser(user) {
  return String(user?.auth_source || "").toLowerCase() === "feishu";
}

export function isExternalAuthUser(user) {
  return isFeishuUser(user);
}

export function authSourceLabel(user) {
  return isFeishuUser(user) ? "飞书" : "系统";
}

export function displayUserEmail(user) {
  const email = String(user?.email || "").trim();
  if (!email || email.endsWith("@feishu.local")) return "";
  return email;
}

export function isPasswordValid(password) {
  return (
    password.length >= 6 &&
    password.length <= 24 &&
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /\d/.test(password) &&
    /[^A-Za-z0-9]/.test(password)
  );
}

function isValidPhone(phone) {
  return /^1[3-9]\d{9}$/.test(String(phone || "").trim());
}

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(email || "").trim());
}

export function validateEditUserInput(modal, isFeishu) {
  const displayName = String(modal.display_name || "").trim();
  const phone = String(modal.phone || "").trim();
  const email = String(modal.email || "").trim();
  if (!displayName) return "请填写显示名";
  if (displayName.length > 120) return "显示名最长不超过 120 个字符";
  if (isFeishu) {
    if (phone && !isValidPhone(phone)) return "请输入有效的手机号码";
    if (email && !isValidEmail(email)) return "请输入有效的邮箱地址";
  } else {
    if (!phone) return "请填写手机号";
    if (!isValidPhone(phone)) return "请输入有效的手机号码";
    if (!email) return "请填写邮箱";
    if (!isValidEmail(email)) return "请输入有效的邮箱地址";
  }
  return "";
}
