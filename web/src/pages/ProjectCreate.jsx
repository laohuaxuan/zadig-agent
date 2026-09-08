import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import BuildVariableOptionsModal from "../components/BuildVariableOptionsModal.jsx";
import ScrollSelect from "../components/ScrollSelect.jsx";
import SearchableSelect from "../components/SearchableSelect.jsx";
import SubmitToast from "../components/SubmitToast.jsx";
import ValuesFilePicker from "../components/ValuesFilePicker.jsx";
import {
  fetchApplicant,
  submitApplication,
  fetchClusterNamespaces,
  fetchCodeBranches,
  fetchCodeNamespaces,
  fetchCodeRepos,
} from "../api.js";
import { loadCreateProjectOptions } from "../utils/projectFormCache.js";
import {
  clusterOptionLabel,
  codeSourceOptionLabel,
  serviceTemplateOptionLabel,
} from "../utils/integrationOptions.js";

const APPLICANT_ROLE = "project-admin";

const VAR_TYPES = [
  { value: "string", label: "字符串" },
  { value: "choice", label: "单选" },
  { value: "multi-select", label: "多选" },
];

const VAR_SCOPES = [
  { value: "env", label: "环境变量" },
  { value: "build", label: "构建变量" },
];

function slugKey(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/^(\d)/, "p-$1")
    .slice(0, 63);
}

function emptyUserRow() {
  return { uid: "", role: "" };
}

function zadigUserLabel(users, uid, fallback = "—") {
  const item = (users || []).find((user) => user.uid === uid);
  if (!item) return fallback;
  return `${item.name || item.account} (${item.account})`;
}

function emptyVarRow() {
  return { key: "", type: "string", value: "", options: "", multi_value: [], scope: "env", description: "" };
}

function isChoiceLikeType(type) {
  return type === "choice" || type === "multi-select";
}

function parseOptions(text) {
  return String(text || "")
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinContextPath(context, suffix) {
  const base = String(context || "").trim().replace(/\/+$/, "");
  const rest = String(suffix || "").trim().replace(/^\/+/, "");
  if (!base) return rest;
  if (!rest) return base;
  return `${base}/${rest}`;
}

function defaultWorkflowName(projectKey, projectName, environment) {
  const key = projectKeyPrefix(projectKey, projectName);
  const env = String(environment || "dev").trim();
  if (!key) return "";
  return env ? `${key}-${env}` : key;
}

function projectKeyPrefix(projectKey, projectName) {
  const key = String(projectKey || "").trim();
  if (key) return key;
  return slugKey(projectName);
}

function defaultNamespace(projectKey, projectName, environment) {
  const prefix = projectKeyPrefix(projectKey, projectName);
  const env = String(environment || "dev").trim();
  if (!prefix || !env) return prefix || env;
  return `${prefix}-${env}`;
}

function FieldLabel({ children, required = false }) {
  return (
    <span className="field-label">
      {children}
      {required ? (
        <span className="required-mark" aria-hidden="true">
          *
        </span>
      ) : null}
    </span>
  );
}

export default function ProjectCreate() {
  const [form, setForm] = useState({
    project_name: "",
    project_key: "",
    service_name: "",
    template_name: "",
    environment: "dev",
    environment_production: false,
    workflow_name: "",
    cluster_name: "",
    namespace: "",
    codehost_name: "",
    repo_namespace: "",
    repo_name: "",
    branch: "",
    values_file: "",
    values_auto_sync: true,
    build_context_dir: "",
    dockerfile_suffix: "Dockerfile",
    build_variables: [],
    authorized_users: [],
  });
  const [options, setOptions] = useState({
    templates: [],
    clusters: [],
    codehosts: [],
    repoNamespaces: [],
    clusterNamespaces: [],
    repos: [],
    branches: [],
    roles: [],
    users: [],
  });
  const [valuesPickerOpen, setValuesPickerOpen] = useState(false);
  const [optionsModalIndex, setOptionsModalIndex] = useState(-1);
  const envNameTouched = useRef(false);
  const namespaceTouched = useRef(false);
  const projectKeyTouched = useRef(false);
  const serviceNameTouched = useRef(false);
  const workflowNameTouched = useRef(false);
  const [optionsLoading, setOptionsLoading] = useState({
    bootstrap: true,
    clusterNamespaces: false,
    repoNamespaces: false,
    repos: false,
    branches: false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [zadig, setZadig] = useState(null);
  const [applicant, setApplicant] = useState(null);

  const suggestedNamespace = useMemo(
    () => defaultNamespace(form.project_key, form.project_name, form.environment),
    [form.project_key, form.project_name, form.environment],
  );

  const suggestedWorkflowName = useMemo(
    () => defaultWorkflowName(form.project_key, form.project_name, form.environment),
    [form.project_key, form.project_name, form.environment],
  );

  const dockerfilePath = useMemo(
    () => joinContextPath(form.build_context_dir, form.dockerfile_suffix),
    [form.build_context_dir, form.dockerfile_suffix],
  );

  const selectedCluster = useMemo(
    () => options.clusters.find((item) => item.name === form.cluster_name),
    [options.clusters, form.cluster_name],
  );

  useEffect(() => {
    let cancelled = false;
    loadCreateProjectOptions()
      .then((data) => {
        if (cancelled) return;
        setOptions((prev) => ({
          ...prev,
          templates: data.templates || [],
          clusters: data.clusters || [],
          codehosts: data.codehosts || [],
          roles: data.roles || [],
          users: data.users || [],
        }));
        setZadig(data.zadig || null);
        const current = data.applicant;
        if (current?.uid && current.in_zadig_users === true) {
          setApplicant(current);
          setForm((prev) => {
            if (prev.authorized_users.some((row) => row.uid === current.uid)) {
              return prev;
            }
            return {
              ...prev,
              authorized_users: [{ uid: current.uid, role: APPLICANT_ROLE, locked: true }, ...prev.authorized_users],
            };
          });
        } else if (current) {
          setApplicant(current);
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => {
        if (!cancelled) {
          setOptionsLoading((prev) => ({ ...prev, bootstrap: false }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!form.cluster_name) {
      setOptions((prev) => ({ ...prev, clusterNamespaces: [] }));
      setOptionsLoading((prev) => ({ ...prev, clusterNamespaces: false }));
      return;
    }
    setOptionsLoading((prev) => ({ ...prev, clusterNamespaces: true }));
    fetchClusterNamespaces(form.cluster_name)
      .then((data) => setOptions((prev) => ({ ...prev, clusterNamespaces: data.items || [] })))
      .catch((err) => setError(err.message))
      .finally(() => setOptionsLoading((prev) => ({ ...prev, clusterNamespaces: false })));
  }, [form.cluster_name]);

  useEffect(() => {
    if (!form.codehost_name) {
      setOptions((prev) => ({ ...prev, repoNamespaces: [] }));
      setOptionsLoading((prev) => ({ ...prev, repoNamespaces: false }));
      return;
    }
    setOptionsLoading((prev) => ({ ...prev, repoNamespaces: true }));
    fetchCodeNamespaces(form.codehost_name)
      .then((data) => setOptions((prev) => ({ ...prev, repoNamespaces: data.items || [] })))
      .catch((err) => setError(err.message))
      .finally(() => setOptionsLoading((prev) => ({ ...prev, repoNamespaces: false })));
  }, [form.codehost_name]);

  useEffect(() => {
    if (!form.codehost_name || !form.repo_namespace) {
      setOptions((prev) => ({ ...prev, repos: [] }));
      setOptionsLoading((prev) => ({ ...prev, repos: false }));
      return;
    }
    setOptionsLoading((prev) => ({ ...prev, repos: true }));
    fetchCodeRepos(form.codehost_name, form.repo_namespace)
      .then((data) => setOptions((prev) => ({ ...prev, repos: data.items || [] })))
      .catch((err) => setError(err.message))
      .finally(() => setOptionsLoading((prev) => ({ ...prev, repos: false })));
  }, [form.codehost_name, form.repo_namespace]);

  useEffect(() => {
    if (!form.codehost_name || !form.repo_namespace || !form.repo_name) {
      setOptions((prev) => ({ ...prev, branches: [] }));
      setOptionsLoading((prev) => ({ ...prev, branches: false }));
      return;
    }
    setOptionsLoading((prev) => ({ ...prev, branches: true }));
    fetchCodeBranches(form.codehost_name, form.repo_namespace, form.repo_name)
      .then((data) => setOptions((prev) => ({ ...prev, branches: data.items || [] })))
      .catch((err) => setError(err.message))
      .finally(() => setOptionsLoading((prev) => ({ ...prev, branches: false })));
  }, [form.codehost_name, form.repo_namespace, form.repo_name]);

  const searchRepos = useCallback(async (keyword) => {
    if (!form.codehost_name || !form.repo_namespace) return [];
    const data = await fetchCodeRepos(form.codehost_name, form.repo_namespace, {
      key: keyword,
      perPage: 100,
    });
    return (data.items || []).map((item) => ({ value: item.name, label: item.name }));
  }, [form.codehost_name, form.repo_namespace]);

  const searchBranches = useCallback(async (keyword) => {
    if (!form.codehost_name || !form.repo_namespace || !form.repo_name) return [];
    const data = await fetchCodeBranches(form.codehost_name, form.repo_namespace, form.repo_name, {
      key: keyword,
      perPage: 100,
    });
    return (data.items || []).map((item) => ({ value: item.name, label: item.name }));
  }, [form.codehost_name, form.repo_namespace, form.repo_name]);

  const canPickValuesFile = Boolean(form.codehost_name && form.repo_namespace && form.repo_name && form.branch);

  function update(key, value) {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "project_key") {
        projectKeyTouched.current = true;
      }
      if (key === "service_name") {
        serviceNameTouched.current = true;
      }
      if (key === "workflow_name") {
        workflowNameTouched.current = true;
      }
      if (key === "namespace") {
        namespaceTouched.current = true;
      }
      if (key === "cluster_name") {
        if (!namespaceTouched.current) {
          next.namespace = "";
        }
      }
      if (key === "project_name") {
        const derived = slugKey(value);
        if (!projectKeyTouched.current) {
          next.project_key = derived;
        }
        if (!serviceNameTouched.current) {
          next.service_name = derived;
        }
        if (!workflowNameTouched.current) {
          next.workflow_name = defaultWorkflowName(next.project_key, value, next.environment);
        }
      }
      if (key === "project_key") {
        if (!workflowNameTouched.current) {
          next.workflow_name = defaultWorkflowName(value, next.project_name, next.environment);
        }
      }
      if (key === "environment") {
        envNameTouched.current = true;
        if (!workflowNameTouched.current) {
          next.workflow_name = defaultWorkflowName(next.project_key || prev.project_key, next.project_name, value);
        }
      }
      if (key === "repo_name" && value) {
        next.build_context_dir = value;
        next.dockerfile_suffix = "Dockerfile";
        next.values_file = "";
      }
      if (key === "branch") {
        next.values_file = "";
      }
      return next;
    });
  }

  function updateList(name, index, key, value) {
    setForm((prev) => ({
      ...prev,
      [name]: prev[name].map((row, i) => (i === index ? { ...row, [key]: value } : row)),
    }));
  }

  function openOptionsModal(index) {
    setOptionsModalIndex(index);
  }

  function closeOptionsModal() {
    setOptionsModalIndex(-1);
  }

  function handleVariableTypeChange(index, nextType) {
    updateList("build_variables", index, "type", nextType);
    if (isChoiceLikeType(nextType)) {
      openOptionsModal(index);
    }
  }

  function handleOptionsConfirm({ key, options, description }) {
    if (optionsModalIndex < 0) return;
    const optionsText = options.join(",");
    setForm((prev) => ({
      ...prev,
      build_variables: prev.build_variables.map((row, index) => {
        if (index !== optionsModalIndex) return row;
        const next = {
          ...row,
          key,
          options: optionsText,
          description,
        };
        if (row.type === "choice") {
          next.value = options.includes(row.value) ? row.value : options[0] || "";
        }
        if (row.type === "multi-select") {
          next.multi_value = (row.multi_value || []).filter((item) => options.includes(item));
        }
        return next;
      }),
    }));
    closeOptionsModal();
  }

  function toggleMultiValue(index, option) {
    setForm((prev) => ({
      ...prev,
      build_variables: prev.build_variables.map((row, i) => {
        if (i !== index) return row;
        const selected = new Set(row.multi_value || []);
        if (selected.has(option)) selected.delete(option);
        else selected.add(option);
        return { ...row, multi_value: Array.from(selected) };
      }),
    }));
  }

  function addListRow(name, factory) {
    setForm((prev) => ({ ...prev, [name]: [...prev[name], factory()] }));
  }

  function removeListRow(name, index) {
    setForm((prev) => ({
      ...prev,
      [name]: prev[name].filter((_, i) => i !== index),
    }));
  }

  function availableUsers(currentIndex) {
    const selected = new Set(
      form.authorized_users.map((row, index) => (index === currentIndex ? "" : row.uid)).filter(Boolean),
    );
    return options.users.filter((user) => !selected.has(user.uid));
  }

  function buildPayload() {
    const authorized = form.authorized_users.filter((row) => {
      if (row.uid && !row.role) {
        throw new Error("授权用户已选择用户时，角色为必填");
      }
      return row.uid && row.role;
    });
    if (applicant?.uid && applicant.in_zadig_users === true && !authorized.some((row) => row.uid === applicant.uid)) {
      authorized.unshift({ uid: applicant.uid, role: APPLICANT_ROLE });
    }
    const payload = {
      ...form,
      environment_production: false,
      project_key: form.project_key || slugKey(form.project_name),
      service_name: form.service_name || slugKey(form.project_name),
      workflow_name: form.workflow_name || suggestedWorkflowName,
      namespace: form.namespace,
      dockerfile_path: dockerfilePath,
      build_variables: form.build_variables.filter((row) => row.key.trim()),
      authorized_users: authorized,
    };
    delete payload.dockerfile_suffix;
    return payload;
  }

  async function onSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const payload = buildPayload();
      const data = await submitApplication(payload);
      const item = data.item || {};
      setSuccess(
        item.serial_no
          ? `项目申请 ${item.serial_no} 已提交，等待审批`
          : `项目 ${item.project_key || payload.project_key} 申请已提交`,
      );
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <SubmitToast message={success} onClose={() => setSuccess("")} />
      <h1 className="page-title">创建项目</h1>
      <p className="page-desc">填写项目信息后提交申请，系统将交给 Agent 使用 Skill 创建 Helm Chart 项目并配置构建。</p>
      {zadig ? (
        <dl className="info-card zadig-context">
          <div>
            <dt>当前 Zadig</dt>
            <dd>
              {zadig.name || "未命名"}
              {zadig.is_active ? <span className="tag">生效中</span> : null}
            </dd>
          </div>
          <div>
            <dt>地址</dt>
            <dd>{zadig.base_url || "未配置"}</dd>
          </div>
          {zadig.remark ? (
            <div>
              <dt>备注</dt>
              <dd>{zadig.remark}</dd>
            </div>
          ) : null}
          <div>
            <dt>连接状态</dt>
            <dd>
              <span className={`status ${zadig.available ? "ok" : "bad"}`}>
                {zadig.available ? "可用" : zadig.error || "不可用"}
              </span>
            </dd>
          </div>
        </dl>
      ) : null}
      {error ? (
        <div className="banner error" role="alert">
          {error}
        </div>
      ) : null}
      <form className="form-stack" onSubmit={onSubmit}>
        <section className="form-section">
          <h2>基本信息</h2>
          <div className="form-grid">
            <label>
              <FieldLabel required>项目名称</FieldLabel>
              <input required value={form.project_name} onChange={(e) => update("project_name", e.target.value)} placeholder="我的项目" />
            </label>
            <label>
              <FieldLabel required>项目标识</FieldLabel>
              <input required value={form.project_key} onChange={(e) => update("project_key", e.target.value)} placeholder="my-project" />
            </label>
            <label>
              <FieldLabel required>服务名称</FieldLabel>
              <input required value={form.service_name} onChange={(e) => update("service_name", e.target.value)} placeholder="my-service" />
            </label>
            <label>
              <FieldLabel required>服务模板</FieldLabel>
              <ScrollSelect
                required
                optionCount={options.templates.length + 1}
                value={form.template_name}
                onChange={(e) => update("template_name", e.target.value)}
              >
                <option value="">请选择</option>
                {options.templates.map((item) => (
                  <option key={item.name} value={item.name}>
                    {serviceTemplateOptionLabel(item)}
                  </option>
                ))}
              </ScrollSelect>
            </label>
            <label>
              <FieldLabel required>环境</FieldLabel>
              <input value="测试环境" disabled readOnly aria-readonly="true" />
            </label>
            <label>
              <FieldLabel required>环境名称</FieldLabel>
              <input
                required
                value={form.environment}
                onChange={(e) => update("environment", e.target.value)}
                placeholder="dev"
              />
            </label>
            <label>
              <FieldLabel required>工作流名称</FieldLabel>
              <input
                required
                value={form.workflow_name}
                onChange={(e) => update("workflow_name", e.target.value)}
                placeholder={suggestedWorkflowName || "ai-demo-dev"}
              />
            </label>
          </div>
          <p className="field-hint">
            项目标识和服务名称会根据项目名称自动生成，手动修改后将不再自动更新。工作流名称默认为「项目标识-环境名称」，如 {suggestedWorkflowName || "ai-demo-dev"}。
          </p>
        </section>

        <section className="form-section">
          <h2>K8s 集群</h2>
          <div className="form-grid form-grid-align-start">
            <label>
              <FieldLabel required>集群</FieldLabel>
              <SearchableSelect
                required
                placeholder="搜索并选择集群"
                value={form.cluster_name}
                onChange={(e) => update("cluster_name", e.target.value)}
                options={options.clusters.map((item) => ({
                  value: item.name,
                  label: clusterOptionLabel(item),
                }))}
                emptyText="未找到匹配集群"
              />
            </label>
            <label>
              <FieldLabel required>命名空间</FieldLabel>
              <SearchableSelect
                required
                allowCustom
                disabled={!form.cluster_name}
                loading={Boolean(form.cluster_name && optionsLoading.clusterNamespaces)}
                placeholder={
                  !form.cluster_name
                    ? "请先选择集群"
                    : optionsLoading.clusterNamespaces
                      ? "正在加载中…"
                      : "请选择或输入命名空间"
                }
                value={form.namespace}
                onChange={(e) => update("namespace", e.target.value)}
                options={options.clusterNamespaces.map((item) => ({
                  value: item.name,
                  label: item.name,
                }))}
                emptyText="无匹配命名空间，可直接输入新建"
              />
            </label>
          </div>
          {selectedCluster?.description ? (
            <p className="field-hint">{selectedCluster.description}</p>
          ) : null}
          <p className="field-hint">
            选择集群后会从 Zadig 加载已有命名空间；也可直接输入新命名空间。建议：{suggestedNamespace || "项目标识-环境"}
          </p>
        </section>

        <section className="form-section">
          <h2>代码信息</h2>
          <div className="form-grid">
            <label>
              <FieldLabel required>代码源</FieldLabel>
              <SearchableSelect
                required
                placeholder="搜索并选择代码源"
                value={form.codehost_name}
                onChange={(e) => update("codehost_name", e.target.value)}
                options={options.codehosts.map((item) => ({
                  value: item.alias || item.name,
                  label: codeSourceOptionLabel(item),
                }))}
                emptyText="未找到匹配代码源"
              />
            </label>
            <label>
              <FieldLabel required>组织/用户</FieldLabel>
              <SearchableSelect
                required
                disabled={!form.codehost_name}
                loading={Boolean(form.codehost_name && optionsLoading.repoNamespaces)}
                placeholder={form.codehost_name ? "搜索并选择组织/用户" : "请先选择代码源"}
                value={form.repo_namespace}
                onChange={(e) => update("repo_namespace", e.target.value)}
                options={options.repoNamespaces.map((item) => ({
                  value: item.path || item.name,
                  label: item.path || item.name,
                }))}
                emptyText="未找到匹配组织/用户"
              />
            </label>
            <label>
              <FieldLabel required>代码库</FieldLabel>
              <SearchableSelect
                required
                disabled={!form.repo_namespace}
                loading={Boolean(form.repo_namespace && optionsLoading.repos)}
                placeholder={form.repo_namespace ? "搜索并选择代码库" : "请先选择组织/用户"}
                value={form.repo_name}
                onChange={(e) => update("repo_name", e.target.value)}
                options={options.repos.map((item) => ({
                  value: item.name,
                  label: item.name,
                }))}
                onSearch={searchRepos}
                emptyText="未找到匹配代码库"
              />
            </label>
            <label>
              <FieldLabel required>分支</FieldLabel>
              <SearchableSelect
                required
                disabled={!form.repo_name}
                loading={Boolean(form.repo_name && optionsLoading.branches)}
                placeholder={form.repo_name ? "搜索并选择分支" : "请先选择代码库"}
                value={form.branch}
                onChange={(e) => update("branch", e.target.value)}
                options={options.branches.map((item) => ({
                  value: item.name,
                  label: item.name,
                }))}
                onSearch={searchBranches}
                emptyText="未找到匹配分支"
              />
            </label>
            <label className="span-2">
              <FieldLabel>Values 文件</FieldLabel>
              <div className="values-file-field">
                <button
                  type="button"
                  className="config-btn"
                  disabled={!canPickValuesFile}
                  onClick={() => setValuesPickerOpen(true)}
                >
                  {form.values_file ? "重新选择" : "选择文件"}
                </button>
                {form.values_file ? (
                  <div className="values-file-selected">
                    <span className="values-file-path">{form.values_file}</span>
                    <button type="button" className="link-btn danger" onClick={() => update("values_file", "")} aria-label="清除">
                      清除
                    </button>
                  </div>
                ) : (
                  <span className="field-hint">可选。不选择时使用 Helm Chart 模板默认值；选择后将以仓库文件覆盖默认值。</span>
                )}
              </div>
            </label>
            {form.values_file ? (
              <label className="span-2 check-row">
                <input
                  type="checkbox"
                  checked={form.values_auto_sync}
                  onChange={(e) => update("values_auto_sync", e.target.checked)}
                />
                自动同步：Values 以代码库为准，开启后后续更新将以仓库文件为准
              </label>
            ) : null}
            <label>
              <FieldLabel required>构建上下文</FieldLabel>
              <input
                required
                value={form.build_context_dir}
                onChange={(e) => update("build_context_dir", e.target.value)}
                placeholder="选择代码库后自动填充"
              />
            </label>
            <label className="span-2">
              <FieldLabel required>Dockerfile 绝对路径</FieldLabel>
              <div className="path-input">
                <span className="path-prefix">{form.build_context_dir ? `${form.build_context_dir}/` : ""}</span>
                <input
                  required
                  value={form.dockerfile_suffix}
                  onChange={(e) => update("dockerfile_suffix", e.target.value)}
                  placeholder="Dockerfile"
                />
              </div>
            </label>
          </div>
          <p className="field-hint">
            选择代码库后构建上下文会自动设为代码库名称；Dockerfile 路径前缀随构建上下文同步。Values 文件可选，未选择时使用 Chart 默认值。
          </p>
        </section>

        <section className="form-section">
          <div className="section-head">
            <h2>
              变量配置 <span className="optional-mark">（可选）</span>
            </h2>
            <button type="button" className="config-btn" onClick={() => addListRow("build_variables", emptyVarRow)}>
              添加变量
            </button>
          </div>
          {form.build_variables.length === 0 ? (
            <p className="field-hint">
              可选。支持字符串、单选、多选三种类型；构建变量审核通过后将自动写入 Docker 构建参数。
            </p>
          ) : null}
          {form.build_variables.map((row, index) => {
            const choiceOptions = parseOptions(row.options);
            const rowClassName = [
              "build-var-row",
              row.type === "choice" ? "is-choice" : "",
              row.type === "multi-select" ? "is-multi" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <div className={rowClassName} key={`var-${index}`}>
                <ScrollSelect
                  optionCount={VAR_TYPES.length}
                  value={row.type}
                  onChange={(e) => handleVariableTypeChange(index, e.target.value)}
                >
                  {VAR_TYPES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </ScrollSelect>
                <input
                  value={row.key}
                  onChange={(e) => updateList("build_variables", index, "key", e.target.value)}
                  placeholder="变量名"
                />
                {row.type === "string" ? (
                  <input
                    value={row.value}
                    onChange={(e) => updateList("build_variables", index, "value", e.target.value)}
                    placeholder="默认值"
                  />
                ) : (
                  <button type="button" className="config-btn build-var-config-btn" onClick={() => openOptionsModal(index)}>
                    {choiceOptions.length ? `已配置 ${choiceOptions.length} 个可选值` : "配置可选值"}
                  </button>
                )}
                {row.type === "choice" ? (
                  <ScrollSelect
                    optionCount={choiceOptions.length + 1}
                    value={row.value}
                    onChange={(e) => updateList("build_variables", index, "value", e.target.value)}
                  >
                    <option value="">选择默认值</option>
                    {choiceOptions.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </ScrollSelect>
                ) : null}
                {row.type === "multi-select" ? (
                  <div className="multi-select-box">
                    {choiceOptions.length === 0 ? (
                      <span className="field-hint">请先填写选项</span>
                    ) : (
                      choiceOptions.map((item) => (
                        <label key={item} className="check-row">
                          <input
                            type="checkbox"
                            checked={(row.multi_value || []).includes(item)}
                            onChange={() => toggleMultiValue(index, item)}
                          />
                          {item}
                        </label>
                      ))
                    )}
                  </div>
                ) : null}
                <ScrollSelect
                  optionCount={VAR_SCOPES.length}
                  value={row.scope || "env"}
                  onChange={(e) => updateList("build_variables", index, "scope", e.target.value)}
                >
                  {VAR_SCOPES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </ScrollSelect>
                <button type="button" className="link-btn danger" onClick={() => removeListRow("build_variables", index)}>
                  删除
                </button>
              </div>
            );
          })}
        </section>

        <section className="form-section">
          <div className="section-head">
            <h2>
              授权用户 <span className="optional-mark">（可选）</span>
            </h2>
            <button type="button" className="config-btn" onClick={() => addListRow("authorized_users", emptyUserRow)}>
              添加用户
            </button>
          </div>
          <p className="field-hint">
            {applicant?.uid && applicant.in_zadig_users === true
              ? `当前申请用户（${applicant.name || applicant.account}）将自动授权为 ${APPLICANT_ROLE}。可继续添加其他授权用户。`
              : "可选。请从 Zadig 用户列表中选择授权用户；当前登录用户若不在 Zadig 用户中，无需填写。"}
          </p>
          {form.authorized_users.map((row, index) => (
            <div className={`kv-row${row.locked ? " kv-row-readonly" : ""}`} key={`user-${index}`}>
              {row.locked ? (
                <>
                  <label className="kv-field">
                    <FieldLabel>用户</FieldLabel>
                    <div className="readonly-field">
                      {zadigUserLabel(options.users, row.uid, applicant?.name || applicant?.account || row.uid)}
                    </div>
                  </label>
                  <label className="kv-field">
                    <FieldLabel>角色</FieldLabel>
                    <div className="readonly-field">{row.role}</div>
                  </label>
                </>
              ) : (
                <>
                  <label className="kv-field">
                    <FieldLabel>用户</FieldLabel>
                    <SearchableSelect
                      value={row.uid}
                      placeholder="搜索姓名或账号"
                      onChange={(e) => updateList("authorized_users", index, "uid", e.target.value)}
                      options={[
                        ...availableUsers(index).map((user) => ({
                          value: user.uid,
                          label: `${user.name || user.account} (${user.account})`,
                        })),
                        ...(row.uid && !availableUsers(index).some((user) => user.uid === row.uid)
                          ? options.users
                              .filter((user) => user.uid === row.uid)
                              .map((user) => ({
                                value: user.uid,
                                label: `${user.name || user.account} (${user.account})`,
                              }))
                          : []),
                      ]}
                      emptyText="未找到匹配用户"
                    />
                  </label>
                  <label className="kv-field">
                    <FieldLabel required={Boolean(row.uid)}>角色</FieldLabel>
                    <ScrollSelect
                      required={Boolean(row.uid)}
                      optionCount={options.roles.length + 1}
                      value={row.role}
                      onChange={(e) => updateList("authorized_users", index, "role", e.target.value)}
                    >
                      <option value="">选择角色</option>
                      {options.roles.map((role) => (
                        <option key={role.name} value={role.name}>
                          {role.name}
                        </option>
                      ))}
                    </ScrollSelect>
                  </label>
                  <button type="button" className="link-btn danger" onClick={() => removeListRow("authorized_users", index)}>
                    删除
                  </button>
                </>
              )}
            </div>
          ))}
        </section>

        <div className="form-actions sticky-actions">
          <button type="submit" className="primary-btn" disabled={saving}>
            {saving ? "提交中…" : "提交申请"}
          </button>
        </div>
      </form>
      <ValuesFilePicker
        open={valuesPickerOpen}
        repoName={form.repo_name}
        codehost={form.codehost_name}
        namespace={form.repo_namespace}
        repo={form.repo_name}
        branch={form.branch}
        value={form.values_file}
        onClose={() => setValuesPickerOpen(false)}
        onSelect={(path) => update("values_file", path)}
      />
      <BuildVariableOptionsModal
        open={optionsModalIndex >= 0}
        type={form.build_variables[optionsModalIndex]?.type === "multi-select" ? "multi-select" : "choice"}
        initialKey={form.build_variables[optionsModalIndex]?.key || ""}
        initialOptions={parseOptions(form.build_variables[optionsModalIndex]?.options)}
        initialDescription={form.build_variables[optionsModalIndex]?.description || ""}
        onClose={closeOptionsModal}
        onConfirm={handleOptionsConfirm}
      />
    </section>
  );
}
