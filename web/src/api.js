function errorMessage(data, status) {
  const detail = data.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join("；");
  }
  return detail || data.error || `请求失败 ${status}`;
}

let authToken = typeof localStorage !== "undefined" ? localStorage.getItem("zadig_auth_token") || "" : "";

export function getAuthToken() {
  return authToken || (typeof localStorage !== "undefined" ? localStorage.getItem("zadig_auth_token") || "" : "");
}

export function setAuthToken(token) {
  authToken = token || "";
  if (typeof localStorage === "undefined") return;
  if (token) localStorage.setItem("zadig_auth_token", token);
  else localStorage.removeItem("zadig_auth_token");
}

function withAuthHeaders(headers = {}) {
  const token = getAuthToken();
  if (!token) return headers;
  // 平台网关会拦截 Authorization: Bearer，改用后端已支持的 X-Access-Token。
  return { ...headers, "X-Access-Token": token };
}

async function request(path, options = {}) {
  const headers = withAuthHeaders(options.headers || {});
  const resp = await fetch(path, { ...options, headers, credentials: "include" });
  const data = await resp.json().catch(() => ({}));
  if (resp.status === 401) {
    setAuthToken("");
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }
  if (!resp.ok || data.ok === false) {
    throw new Error(errorMessage(data, resp.status));
  }
  return data;
}

function withPage(path, { pageNum = 1, pageSize = 10 } = {}) {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("page_num", String(pageNum));
  url.searchParams.set("page_size", String(pageSize));
  return `${url.pathname}${url.search}`;
}

export function syncIntegrationResource(resourceType) {
  const url = new URL("/api/integration/sync", window.location.origin);
  if (resourceType) url.searchParams.set("resource_type", resourceType);
  return request(`${url.pathname}${url.search}`, { method: "POST" });
}

export function fetchCodeSources(params) {
  return request(withPage("/api/code-sources", params));
}

export function fetchClusters(params) {
  return request(withPage("/api/clusters", params));
}

export function fetchClusterNamespaces(cluster) {
  return request(`/api/clusters/${encodeURIComponent(cluster)}/namespaces`);
}

export function fetchRegistries(params) {
  return request(withPage("/api/registries", params));
}

export function fetchServiceTemplates(params) {
  return request(withPage("/api/service-templates", params));
}

export function updateIntegrationRemark(resourceType, resourceKey, remark) {
  return request(`/api/integration-resources/${encodeURIComponent(resourceType)}/${encodeURIComponent(resourceKey)}/remark`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ remark }),
  });
}

export function fetchCodeNamespaces(codehost) {
  return request(`/api/code-sources/${encodeURIComponent(codehost)}/namespaces`);
}

export function fetchCodeRepos(codehost, namespace) {
  const url = new URL(`/api/code-sources/${encodeURIComponent(codehost)}/repos`, window.location.origin);
  url.searchParams.set("namespace", namespace);
  return request(`${url.pathname}${url.search}`);
}

export function fetchCodeBranches(codehost, namespace, repo) {
  const url = new URL(`/api/code-sources/${encodeURIComponent(codehost)}/branches`, window.location.origin);
  url.searchParams.set("namespace", namespace);
  url.searchParams.set("repo", repo);
  return request(`${url.pathname}${url.search}`);
}

export function fetchCodeTree(codehost, namespace, repo, branch, path = "") {
  const url = new URL(`/api/code-sources/${encodeURIComponent(codehost)}/tree`, window.location.origin);
  url.searchParams.set("namespace", namespace);
  url.searchParams.set("repo", repo);
  url.searchParams.set("branch", branch);
  if (path) url.searchParams.set("path", path);
  return request(`${url.pathname}${url.search}`);
}

export function fetchProjectRoles() {
  return request("/api/project-roles");
}

export function fetchUserOptions() {
  const url = new URL("/api/users", window.location.origin);
  url.searchParams.set("all_users", "true");
  return request(`${url.pathname}${url.search}`);
}

export function fetchApplicant() {
  return request("/api/applicant");
}

export function createProject(body) {
  return request("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function submitApplication(payload) {
  return request("/api/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payload }),
  });
}

export function fetchProjects(params) {
  return request(withPage("/api/projects", params));
}

export function checkProjectService(projectKey, name, { environment = "", production = false, environmentMode = "existing" } = {}) {
  const url = new URL(`/api/projects/${encodeURIComponent(projectKey)}/services/check`, window.location.origin);
  url.searchParams.set("name", name);
  if (environment) {
    url.searchParams.set("environment", environment);
  }
  url.searchParams.set("production", production ? "true" : "false");
  url.searchParams.set("environment_mode", environmentMode);
  return request(`${url.pathname}${url.search}`);
}

export function fetchProjectEnvironments(projectKey, { production = false } = {}) {
  const url = new URL(`/api/projects/${encodeURIComponent(projectKey)}/environments`, window.location.origin);
  url.searchParams.set("production", production ? "true" : "false");
  return request(`${url.pathname}${url.search}`);
}

export function fetchProjectEnvironment(projectKey, envName, { production = false } = {}) {
  const url = new URL(
    `/api/projects/${encodeURIComponent(projectKey)}/environments/${encodeURIComponent(envName)}`,
    window.location.origin,
  );
  url.searchParams.set("production", production ? "true" : "false");
  return request(`${url.pathname}${url.search}`);
}

export async function fetchAllProjectEnvironments(projectKey) {
  const key = String(projectKey || "").trim();
  if (!key) return [];
  const [testData, prodData] = await Promise.all([
    fetchProjectEnvironments(key, { production: false }).catch(() => ({ items: [] })),
    fetchProjectEnvironments(key, { production: true }).catch(() => ({ items: [] })),
  ]);
  const seen = new Set();
  const items = [];
  for (const item of [...(testData.items || []), ...(prodData.items || [])]) {
    const name = item.env_name;
    if (name && !seen.has(name)) {
      seen.add(name);
      items.push(item);
    }
  }
  return items;
}

export function submitServiceApplication(payload) {
  return submitApplication({ ...payload, application_type: "add_service" });
}

export function fetchProjectWorkflows(projectKey) {
  return request(`/api/projects/${encodeURIComponent(projectKey)}/workflows`);
}

export function checkProjectWorkflow(projectKey, name) {
  const url = new URL(`/api/projects/${encodeURIComponent(projectKey)}/workflows/check`, window.location.origin);
  url.searchParams.set("name", name);
  return request(`${url.pathname}${url.search}`);
}

export function fetchProjectBuildServices(projectKey) {
  return request(`/api/projects/${encodeURIComponent(projectKey)}/build-services`);
}

export function checkProjectEnvironment(projectKey, name, { production = false } = {}) {
  const url = new URL(
    `/api/projects/${encodeURIComponent(projectKey)}/environments/check`,
    window.location.origin,
  );
  url.searchParams.set("name", name);
  url.searchParams.set("production", production ? "true" : "false");
  return request(`${url.pathname}${url.search}`);
}

export function submitEnvironmentApplication(payload) {
  return submitApplication({ ...payload, application_type: "add_environment" });
}

export function previewEnvironmentApplication(payload) {
  return request("/api/environments/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, application_type: "add_environment" }),
  });
}

export function submitWorkflowApplication(payload) {
  return submitApplication({ ...payload, application_type: "add_workflow" });
}

export function fetchAuthProviders() {
  return request("/api/auth/providers");
}

export function fetchUserInfo() {
  return request("/api/user-info");
}

export function updateUserProfile(body) {
  return request("/api/user-profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function loginLocal(name, password) {
  return request("/api/login/local", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, password }),
  });
}

export function loginRoot(name, password) {
  return loginLocal(name, password);
}

export function logout() {
  return request("/api/logout", { method: "POST" });
}

export function fetchPlatformUsers(params = {}) {
  const url = new URL("/api/platform/users", window.location.origin);
  url.searchParams.set("page", String(params.page || 1));
  url.searchParams.set("page_size", String(params.pageSize || 20));
  if (params.keyword) url.searchParams.set("keyword", params.keyword);
  return request(`${url.pathname}${url.search}`);
}

export function createPlatformUser(body) {
  return request("/api/platform/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function updatePlatformUser(id, body) {
  return request(`/api/platform/users/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function updatePlatformUserStatus(id, status) {
  return request(`/api/platform/users/${id}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export function deletePlatformUser(id) {
  return request(`/api/platform/users/${id}`, { method: "DELETE" });
}

export function resetPlatformUserPassword(id) {
  return request(`/api/platform/users/${id}/reset-password`, { method: "POST" });
}

export function fetchApproverCandidates() {
  return request("/api/platform/users/approver-candidates");
}

export function fetchFeishuUsers(q, pageSize = 30) {
  const url = new URL("/api/feishu/users", window.location.origin);
  if (q) url.searchParams.set("q", q);
  url.searchParams.set("page_size", String(pageSize));
  return request(`${url.pathname}${url.search}`);
}

export function warmupFeishuUsers() {
  return request("/api/feishu/warmup", { method: "POST" });
}

export function ensureFeishuUser(body) {
  return request("/api/feishu/users/ensure", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchApprovalTemplates(workflowType = "Helm项目申请") {
  const url = new URL("/api/approval-templates", window.location.origin);
  url.searchParams.set("workflow_type", workflowType);
  return request(`${url.pathname}${url.search}`);
}

export function fetchApprovalTemplate(id) {
  return request(`/api/approval-templates/${id}`);
}

export function createApprovalTemplate(body) {
  return request("/api/approval-templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function updateApprovalTemplate(id, body) {
  return request(`/api/approval-templates/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteApprovalTemplate(id) {
  return request(`/api/approval-templates/${id}`, { method: "DELETE" });
}

export function fetchWorkflowCounts() {
  return request("/api/workflows/counts");
}

export function fetchWorkflowTasks(box, params = {}) {
  const url = new URL("/api/workflows/tasks", window.location.origin);
  url.searchParams.set("box", box);
  url.searchParams.set("page", String(params.page || 1));
  url.searchParams.set("page_size", String(params.pageSize || 20));
  if (params.keyword) url.searchParams.set("keyword", params.keyword);
  return request(`${url.pathname}${url.search}`);
}

export function fetchWorkflowInstance(id) {
  return request(`/api/workflows/instances/${id}`);
}

export function approveWorkflow(id, body) {
  return request(`/api/workflows/instances/${id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function rejectWorkflow(id, body) {
  return request(`/api/workflows/instances/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function revokeWorkflow(id) {
  return request(`/api/workflows/instances/${id}/revoke`, { method: "POST" });
}

export async function streamWorkflowExecution(instanceId, handlers = {}) {
  const { onLog, onDone, onError, onInputRequired, onMeta, signal, resume = false } = handlers;
  const query = resume ? "?resume=1" : "";
  const resp = await fetch(`/api/workflows/instances/${instanceId}/execute/stream${query}`, {
    headers: withAuthHeaders(),
    credentials: "include",
    signal,
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || data.message || `执行失败 ${resp.status}`);
  }
  const reader = resp.body?.getReader();
  if (!reader) throw new Error("无法读取执行流");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      let event;
      try {
        event = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (event.type === "log") onLog?.(event.text || "");
      else if (event.type === "meta") onMeta?.(event);
      else if (event.type === "input_required") onInputRequired?.(event.prompt || "");
      else if (event.type === "done") onDone?.(event);
      else if (event.type === "error") onError?.(event);
      else if (event.type === "ping") {
        /* keep SSE alive during long model calls */
      }
    }
  }
}

export function replyWorkflowExecution(instanceId, message) {
  return request(`/api/workflows/instances/${instanceId}/execute/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export function fetchUsers(params) {
  return request(withPage("/api/users", params));
}

export function fetchSkills(params) {
  return request(withPage("/api/skills", params));
}

export function createSkill(body) {
  return request("/api/skills", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchSkill(name) {
  return request(`/api/skills/${encodeURIComponent(name)}`);
}

export function updateSkill(name, body) {
  return request(`/api/skills/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteSkill(name) {
  return request(`/api/skills/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export function fetchMcpSkills(params) {
  return request(withPage("/api/mcp-skills", params));
}

export function createMcpSkill(body) {
  return request("/api/mcp-skills", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchMcpSkill(name) {
  return request(`/api/mcp-skills/${encodeURIComponent(name)}`);
}

export function updateMcpSkill(name, body) {
  return request(`/api/mcp-skills/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteMcpSkill(name) {
  return request(`/api/mcp-skills/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export function fetchTemplates(params) {
  return request(withPage("/api/templates", params));
}

export function createTemplate(body) {
  return request("/api/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function importTemplate(body) {
  return request("/api/templates/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchTemplate(name) {
  return request(`/api/templates/${encodeURIComponent(name)}`);
}

export function updateTemplate(name, body) {
  return request(`/api/templates/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteTemplate(name) {
  return request(`/api/templates/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export function fetchAgents(params) {
  return request(withPage("/api/agents", params));
}

export function fetchAgent(id) {
  return request(`/api/agents/${encodeURIComponent(id)}`);
}

export function createAgent(body) {
  return request("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function testAgent(body) {
  return request("/api/agents/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function updateAgent(id, body) {
  return request(`/api/agents/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteAgent(id) {
  return request(`/api/agents/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function setDefaultAgent(id) {
  return request(`/api/agents/${encodeURIComponent(id)}/default`, { method: "POST" });
}

export function fetchZadig() {
  return request("/api/zadig");
}

export function fetchZadigInstances(params) {
  return request(withPage("/api/zadig/instances", params));
}

export function fetchZadigInstance(id) {
  return request(`/api/zadig/instances/${encodeURIComponent(id)}`);
}

export function createZadigInstance(body) {
  return request("/api/zadig/instances", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function updateZadigInstance(id, body) {
  return request(`/api/zadig/instances/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteZadigInstance(id) {
  return request(`/api/zadig/instances/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function activateZadigInstance(id) {
  return request(`/api/zadig/instances/${encodeURIComponent(id)}/activate`, { method: "POST" });
}

export function updateZadig(body) {
  return request("/api/zadig", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
