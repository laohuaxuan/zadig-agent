import { fetchClusters, fetchCodeSources, fetchRegistries, fetchServiceTemplates, fetchUsers } from "./api.js";
import { registryFullPath } from "./utils/integrationOptions.js";

function formatTime(value) {
  if (!value) return "—";
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return String(value);
  const ms = num > 1e12 ? num : num * 1000;
  return new Date(ms).toLocaleString("zh-CN", { hour12: false });
}

export const RESOURCES = {
  "code-sources": {
    title: "代码源",
    description: "从 Zadig 同步代码源信息",
    hint: "支持 GitLab、GitHub、Gerrit、Gitee、Perforce、SVN 协议",
    fetch: fetchCodeSources,
    syncType: "code_sources",
    remarkType: "code_source",
    editableRemark: true,
    columns: [
      { key: "alias", label: "标识" },
      { key: "type", label: "类型" },
      { key: "address", label: "地址" },
      { key: "username", label: "用户" },
      { key: "remark", label: "备注" },
      { key: "updated_at", label: "更新时间", render: formatTime },
    ],
  },
  clusters: {
    title: "集群管理",
    description: "从 Zadig 同步 K8s 集群信息",
    hint: "同步系统已接入的 Kubernetes 集群及运行状态",
    fetch: fetchClusters,
    syncType: "clusters",
    columns: [
      { key: "name", label: "名称" },
      { key: "status", label: "状态" },
      { key: "type", label: "接入方式" },
      { key: "provider_name", label: "供应商" },
      { key: "production", label: "生产", render: (v) => (v ? "是" : "否") },
      { key: "description", label: "描述" },
    ],
  },
  registries: {
    title: "镜像仓库",
    description: "从 Zadig 同步镜像仓库信息",
    hint: "同步 ACR / Harbor / DockerHub 等已集成仓库",
    fetch: fetchRegistries,
    syncType: "registries",
    remarkType: "registry",
    editableRemark: true,
    columns: [
      { key: "registry_path", label: "地址/命名空间", render: (_, row) => registryFullPath(row) },
      { key: "provider", label: "提供商" },
      { key: "is_default", label: "默认", render: (v) => (v ? "是" : "否") },
      { key: "remark", label: "备注" },
    ],
  },
  "service-templates": {
    title: "服务模板",
    description: "从 Zadig 同步 Chart 服务模板",
    hint: "同步模板库中的 Helm Chart 模板，如 acr-openxlab 等",
    fetch: fetchServiceTemplates,
    syncType: "service_templates",
    remarkType: "service_template",
    editableRemark: true,
    columns: [
      { key: "name", label: "模板名称" },
      { key: "owner", label: "组织/用户" },
      { key: "namespace", label: "命名空间" },
      { key: "repo", label: "代码库" },
      { key: "path", label: "路径" },
      { key: "branch", label: "分支" },
      { key: "remark", label: "备注" },
    ],
  },
  users: {
    title: "用户管理",
    description: "从 Zadig 同步用户信息",
    hint: "同步系统用户及外部身份源账号",
    fetch: fetchUsers,
    syncType: "users",
    columns: [
      { key: "name", label: "姓名" },
      { key: "account", label: "账号" },
      { key: "identity_type", label: "身份类型" },
      { key: "last_login_time", label: "最近登录", render: formatTime },
    ],
  },
};
