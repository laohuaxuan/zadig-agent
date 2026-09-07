import { useEffect, useMemo, useRef, useState } from "react";
import ScrollSelect from "../components/ScrollSelect.jsx";
import SearchableSelect from "../components/SearchableSelect.jsx";
import SubmitToast from "../components/SubmitToast.jsx";
import ValuesFilePicker from "../components/ValuesFilePicker.jsx";
import {
  checkProjectService,
  fetchClusterNamespaces,
  fetchCodeBranches,
  fetchCodeNamespaces,
  fetchCodeRepos,
  fetchProjectEnvironment,
  submitServiceApplication,
} from "../api.js";
import { fetchAllProjectEnvironments, isProductionEnvironment, loadServiceAddOptions, mapEnvironmentOptions } from "../utils/projectFormCache.js";
import {
  clusterOptionLabel,
  codeSourceOptionLabel,
  serviceTemplateOptionLabel,
} from "../utils/integrationOptions.js";

const ENV_TYPE_OPTIONS = [
  { value: "false", label: "测试环境" },
  { value: "true", label: "生产环境" },
];

const DEFAULT_ENV_NAME = {
  false: "dev",
  true: "prod",
};

const INITIAL_FORM = {
  project_key: "",
  project_name: "",
  service_name: "",
  template_name: "",
  environment_mode: "existing",
  environment: "",
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
};

const VAR_TYPES = [
  { value: "string", label: "字符串" },
  { value: "choice", label: "单选" },
  { value: "multi-select", label: "多选" },
];

function defaultWorkflowName(serviceName, environment) {
  const svc = String(serviceName || "").trim();
  const env = String(environment || "dev").trim();
  if (!svc) return "";
  return env ? `${svc}-${env}` : svc;
}

function defaultNamespace(projectKey, environment) {
  const key = String(projectKey || "").trim();
  const env = String(environment || "dev").trim();
  if (!key || !env) return "";
  return `${key}-${env}`;
}

function emptyVarRow() {
  return { key: "", type: "string", value: "", options: "", multi_value: [] };
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

export default function ServiceAdd() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [options, setOptions] = useState({
    projects: [],
    templates: [],
    clusters: [],
    codehosts: [],
    repoNamespaces: [],
    clusterNamespaces: [],
    repos: [],
    branches: [],
    environments: [],
  });
  const workflowNameTouched = useRef(false);
  const namespaceTouched = useRef(false);
  const [valuesPickerOpen, setValuesPickerOpen] = useState(false);
  const [optionsLoading, setOptionsLoading] = useState({
    bootstrap: true,
    clusterNamespaces: false,
    repoNamespaces: false,
    repos: false,
    branches: false,
    environments: false,
    serviceCheck: false,
  });
  const [serviceCheck, setServiceCheck] = useState({ exists: false, blocked: false, message: "", reason: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [zadig, setZadig] = useState(null);

  const suggestedWorkflowName = useMemo(
    () => defaultWorkflowName(form.service_name, form.environment),
    [form.service_name, form.environment],
  );

  const suggestedNamespace = useMemo(
    () => defaultNamespace(form.project_key, form.environment),
    [form.project_key, form.environment],
  );

  const isNewEnvironment = form.environment_mode === "new";

  const dockerfilePath = useMemo(
    () => joinContextPath(form.build_context_dir, form.dockerfile_suffix),
    [form.build_context_dir, form.dockerfile_suffix],
  );

  const selectedCluster = useMemo(
    () => options.clusters.find((item) => item.name === form.cluster_name),
    [options.clusters, form.cluster_name],
  );

  const environmentOptions = useMemo(
    () => mapEnvironmentOptions(options.environments),
    [options.environments],
  );

  const canPickValuesFile = Boolean(form.codehost_name && form.repo_namespace && form.repo_name && form.branch);

  function resetForm() {
    workflowNameTouched.current = false;
    namespaceTouched.current = false;
    setForm({ ...INITIAL_FORM });
    setServiceCheck({ exists: false, blocked: false, message: "", reason: "" });
  }

  useEffect(() => {
    let cancelled = false;

    loadServiceAddOptions()
      .then((data) => {
        if (cancelled) return;
        setOptions((prev) => ({
          ...prev,
          projects: data.projects || [],
          templates: data.templates || [],
          clusters: data.clusters || [],
          codehosts: data.codehosts || [],
        }));
        setZadig(data.zadig || null);
        if (!data.projects?.length && data.projectsError) {
          const message = String(data.projectsError.message || "加载失败");
          setError(
            message === "Not Found" || message === "Method Not Allowed"
              ? "项目列表接口不可用，请确认 webapi 已重启并包含最新代码。"
              : message,
          );
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
    if (!form.project_key || isNewEnvironment) {
      if (!form.project_key) {
        setOptions((prev) => ({ ...prev, environments: [] }));
      }
      return;
    }
    let cancelled = false;
    setOptionsLoading((prev) => ({ ...prev, environments: true }));
    fetchAllProjectEnvironments(form.project_key)
      .then(async (items) => {
        if (cancelled) return;
        setOptions((prev) => ({ ...prev, environments: items }));
        const names = items.map((item) => item.env_name);
        let currentEnv = "";
        setForm((prev) => {
          currentEnv =
            prev.environment && names.includes(prev.environment) ? prev.environment : names[0] || "";
          if (!currentEnv) {
            return { ...prev, environment: "" };
          }
          const envItem = items.find((item) => item.env_name === currentEnv);
          const production = isProductionEnvironment(envItem);
          return prev.environment === currentEnv && prev.environment_production === production
            ? prev
            : { ...prev, environment: currentEnv, environment_production: production };
        });
        if (!currentEnv) {
          return;
        }
        const envItem = items.find((item) => item.env_name === currentEnv);
        const production = isProductionEnvironment(envItem);
        try {
          const data = await fetchProjectEnvironment(form.project_key, currentEnv, { production });
          const detail = data.item || {};
          setForm((prev) => ({
            ...prev,
            environment: currentEnv,
            environment_production: production,
            cluster_name: detail.cluster_name || prev.cluster_name,
            namespace: namespaceTouched.current ? prev.namespace : detail.namespace || prev.namespace,
          }));
        } catch {
          setForm((prev) => ({ ...prev, environment: currentEnv, environment_production: production }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setOptions((prev) => ({ ...prev, environments: [] }));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setOptionsLoading((prev) => ({ ...prev, environments: false }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [form.project_key, isNewEnvironment]);

  useEffect(() => {
    const name = form.service_name.trim();
    if (!form.project_key || !name) {
      setServiceCheck({ exists: false, blocked: false, message: "", reason: "" });
      return;
    }
    const timer = setTimeout(async () => {
      setOptionsLoading((prev) => ({ ...prev, serviceCheck: true }));
      try {
        const data = await checkProjectService(form.project_key, name, {
          environment: form.environment,
          production: form.environment_production,
          environmentMode: form.environment_mode,
        });
        setServiceCheck({
          exists: Boolean(data.blocked ?? data.exists),
          blocked: Boolean(data.blocked ?? data.exists),
          reason: data.reason || "",
          message: data.message || "",
        });
      } catch (err) {
        setServiceCheck({ exists: false, blocked: false, message: err.message, reason: "" });
      } finally {
        setOptionsLoading((prev) => ({ ...prev, serviceCheck: false }));
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [
    form.project_key,
    form.service_name,
    form.environment,
    form.environment_production,
    form.environment_mode,
  ]);

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

  function update(key, value) {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
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
      if (key === "environment_mode") {
        namespaceTouched.current = false;
        if (value === "new") {
          next.environment_production = false;
          next.environment = DEFAULT_ENV_NAME.false;
          next.cluster_name = "";
          next.namespace = defaultNamespace(next.project_key, DEFAULT_ENV_NAME.false);
          namespaceTouched.current = false;
        } else {
          const names = options.environments.map((item) => item.env_name);
          const current = names.includes(next.environment) ? next.environment : names[0] || "";
          next.environment = current;
          const envItem = options.environments.find((item) => item.env_name === current);
          next.environment_production = isProductionEnvironment(envItem);
        }
      }
      if (key === "environment_production") {
        const isProduction = value === true || value === "true";
        next.environment_production = isProduction;
        if (next.environment_mode === "new" && !next.environment.trim()) {
          next.environment = DEFAULT_ENV_NAME[String(isProduction)];
        }
        if (next.environment_mode === "new" && !namespaceTouched.current) {
          next.namespace = defaultNamespace(next.project_key, next.environment);
        }
      }
      if (key === "project_key") {
        namespaceTouched.current = false;
        workflowNameTouched.current = false;
        const project = options.projects.find((item) => item.project_key === value);
        next.project_name = project?.project_name || value;
        next.service_name = "";
        if (!workflowNameTouched.current) {
          next.workflow_name = defaultWorkflowName(next.service_name, next.environment);
        }
      }
      if (key === "service_name" && !workflowNameTouched.current) {
        next.workflow_name = defaultWorkflowName(value, next.environment);
      }
      if (key === "environment") {
        if (!workflowNameTouched.current) {
          next.workflow_name = defaultWorkflowName(next.service_name, value);
        }
        if (next.environment_mode === "new" && !namespaceTouched.current) {
          next.namespace = defaultNamespace(next.project_key, value);
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

  async function onEnvironmentChange(envName) {
    const envItem = options.environments.find((item) => item.env_name === envName);
    const production = isProductionEnvironment(envItem);
    setForm((prev) => ({
      ...prev,
      environment: envName,
      environment_production: production,
      workflow_name: workflowNameTouched.current
        ? prev.workflow_name
        : defaultWorkflowName(prev.service_name, envName),
    }));
    const projectKey = form.project_key;
    if (!projectKey || !envName) return;
    try {
      const data = await fetchProjectEnvironment(projectKey, envName, { production });
      const item = data.item || {};
      setForm((prev) => ({
        ...prev,
        environment: envName,
        environment_production: production,
        cluster_name: item.cluster_name || prev.cluster_name,
        namespace: namespaceTouched.current ? prev.namespace : item.namespace || prev.namespace,
      }));
    } catch {
      /* 保留用户输入 */
    }
  }

  function updateList(name, index, key, value) {
    setForm((prev) => ({
      ...prev,
      [name]: prev[name].map((row, i) => (i === index ? { ...row, [key]: value } : row)),
    }));
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

  function buildPayload() {
    if (serviceCheck.blocked || serviceCheck.exists) {
      throw new Error(serviceCheck.message || "当前无法添加该服务");
    }
    return {
      application_type: "add_service",
      project_key: form.project_key,
      project_name: form.project_name || form.project_key,
      service_name: form.service_name.trim(),
      template_name: form.template_name,
      environment_mode: form.environment_mode,
      environment: form.environment,
      environment_production: form.environment_production,
      workflow_name: form.workflow_name || suggestedWorkflowName,
      cluster_name: form.cluster_name,
      namespace: form.namespace,
      codehost_name: form.codehost_name,
      repo_namespace: form.repo_namespace,
      repo_name: form.repo_name,
      branch: form.branch,
      values_file: form.values_file,
      values_auto_sync: form.values_auto_sync,
      build_context_dir: form.build_context_dir,
      dockerfile_path: dockerfilePath,
      build_variables: form.build_variables.filter((row) => row.key.trim()),
    };
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const payload = buildPayload();
      const data = await submitServiceApplication(payload);
      const item = data.item || {};
      setSuccess(
        item.serial_no
          ? `添加服务申请 ${item.serial_no} 已提交，等待审批`
          : `项目 ${payload.project_key} 添加服务申请已提交`,
      );
      window.scrollTo({ top: 0, behavior: "smooth" });
      resetForm();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <SubmitToast message={success} onClose={() => setSuccess("")} />
      <h1 className="page-title">添加新服务</h1>
      <p className="page-desc">向已有 Helm 项目添加服务，提交后将进入审批流程，审批通过后由 Agent 自动创建服务、构建与工作流。</p>
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
              <SearchableSelect
                required
                value={form.project_key}
                placeholder="搜索并选择 Zadig 项目"
                onChange={(e) => update("project_key", e.target.value)}
                options={options.projects.map((item) => ({
                  value: item.project_key,
                  label: `${item.project_name} (${item.project_key})`,
                }))}
                emptyText="未找到匹配项目"
              />
            </label>
            <label>
              <FieldLabel required>服务名称</FieldLabel>
              <input
                required
                disabled={!form.project_key}
                value={form.service_name}
                onChange={(e) => update("service_name", e.target.value)}
                placeholder={form.project_key ? "my-service" : "请先选择项目"}
              />
              {optionsLoading.serviceCheck ? <span className="field-hint">正在校验服务名称…</span> : null}
              {serviceCheck.message ? <span className="field-hint error-text">{serviceCheck.message}</span> : null}
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
              <FieldLabel required>环境来源</FieldLabel>
              <ScrollSelect
                required
                disabled={!form.project_key}
                optionCount={2}
                value={form.environment_mode}
                onChange={(e) => update("environment_mode", e.target.value)}
              >
                <option value="existing">使用已有环境</option>
                <option value="new">创建新环境</option>
              </ScrollSelect>
            </label>
            {isNewEnvironment ? (
              <>
                <label>
                  <FieldLabel required>环境类型</FieldLabel>
                  <ScrollSelect
                    required
                    optionCount={ENV_TYPE_OPTIONS.length}
                    value={String(form.environment_production)}
                    onChange={(e) => update("environment_production", e.target.value === "true")}
                  >
                    {ENV_TYPE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </ScrollSelect>
                </label>
                <label>
                  <FieldLabel required>环境名称</FieldLabel>
                  <input
                    required
                    value={form.environment}
                    onChange={(e) => update("environment", e.target.value)}
                    placeholder={form.environment_production ? "prod" : "dev"}
                  />
                </label>
              </>
            ) : (
              <label>
                <FieldLabel required>环境</FieldLabel>
                <ScrollSelect
                  required
                  disabled={!form.project_key}
                  loading={Boolean(form.project_key && optionsLoading.environments)}
                  optionCount={environmentOptions.length + 1}
                  value={form.environment}
                  onChange={(e) => onEnvironmentChange(e.target.value)}
                >
                  <option value="">
                    {form.project_key
                      ? optionsLoading.environments
                        ? "加载中…"
                        : environmentOptions.length
                          ? "请选择"
                          : "当前项目暂无环境，请切换为「创建新环境」"
                      : "请先选择项目"}
                  </option>
                  {environmentOptions.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </ScrollSelect>
              </label>
            )}
            <label className="span-2">
              <FieldLabel required>工作流名称</FieldLabel>
              <input
                required
                value={form.workflow_name}
                onChange={(e) => update("workflow_name", e.target.value)}
                placeholder={suggestedWorkflowName || "my-service-dev"}
              />
            </label>
          </div>
          <p className="field-hint">
            工作流名称默认为「服务名称-环境」，如 {suggestedWorkflowName || "my-service-dev"}。
            {isNewEnvironment
              ? ` 创建新环境时 Agent 将自动新建环境并部署服务，命名空间建议：${suggestedNamespace || "项目标识-环境"}。`
              : " 选择已有环境后会尝试自动填充集群与命名空间。"}
          </p>
        </section>

        <section className="form-section">
          <h2>K8s 集群</h2>
          <div className="form-grid form-grid-align-start">
            <label>
              <FieldLabel required>集群</FieldLabel>
              <ScrollSelect
                required
                optionCount={options.clusters.length + 1}
                value={form.cluster_name}
                onChange={(e) => update("cluster_name", e.target.value)}
              >
                <option value="">请选择</option>
                {options.clusters.map((item) => (
                  <option key={item.name || item.id} value={item.name}>
                    {clusterOptionLabel(item)}
                  </option>
                ))}
              </ScrollSelect>
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
                emptyText="无匹配命名空间，可直接输入"
              />
            </label>
          </div>
          {isNewEnvironment ? (
            <p className="field-hint">
              创建新环境时需指定集群与命名空间。命名空间建议：{suggestedNamespace || "项目标识-环境"}
            </p>
          ) : selectedCluster?.description ? (
            <p className="field-hint">{selectedCluster.description}</p>
          ) : null}
        </section>

        <section className="form-section">
          <h2>代码源</h2>
          <div className="form-grid">
            <label>
              <FieldLabel required>代码源</FieldLabel>
              <ScrollSelect
                required
                optionCount={options.codehosts.length + 1}
                value={form.codehost_name}
                onChange={(e) => update("codehost_name", e.target.value)}
              >
                <option value="">请选择</option>
                {options.codehosts.map((item) => (
                  <option key={item.id} value={item.alias || item.name}>
                    {codeSourceOptionLabel(item)}
                  </option>
                ))}
              </ScrollSelect>
            </label>
            <label>
              <FieldLabel required>组织/用户</FieldLabel>
              <ScrollableSelectCompat
                required
                loading={Boolean(form.codehost_name && optionsLoading.repoNamespaces)}
                optionCount={options.repoNamespaces.length + 1}
                value={form.repo_namespace}
                onChange={(e) => update("repo_namespace", e.target.value)}
                options={options.repoNamespaces}
              />
            </label>
            <label>
              <FieldLabel required>代码库</FieldLabel>
              <ScrollSelect
                required
                loading={Boolean(form.repo_namespace && optionsLoading.repos)}
                optionCount={options.repos.length + 1}
                value={form.repo_name}
                onChange={(e) => update("repo_name", e.target.value)}
              >
                <option value="">请选择</option>
                {options.repos.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </ScrollSelect>
            </label>
            <label>
              <FieldLabel required>分支</FieldLabel>
              <ScrollSelect
                required
                loading={Boolean(form.repo_name && optionsLoading.branches)}
                optionCount={options.branches.length + 1}
                value={form.branch}
                onChange={(e) => update("branch", e.target.value)}
              >
                <option value="">请选择</option>
                {options.branches.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </ScrollSelect>
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
                  <span className="field-hint">可选。不选择时使用 Helm Chart 模板默认值。</span>
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
                自动同步：Values 以代码库为准
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
        </section>

        <section className="form-section">
          <div className="section-head">
            <h2>
              构建变量 <span className="optional-mark">（可选）</span>
            </h2>
            <button type="button" className="config-btn" onClick={() => addListRow("build_variables", emptyVarRow)}>
              添加变量
            </button>
          </div>
          {form.build_variables.length === 0 ? (
            <p className="field-hint">可选。支持字符串、单选、多选三种类型。</p>
          ) : null}
          {form.build_variables.map((row, index) => {
            const choiceOptions = parseOptions(row.options);
            return (
              <div className="build-var-row" key={`var-${index}`}>
                <input
                  value={row.key}
                  onChange={(e) => updateList("build_variables", index, "key", e.target.value)}
                  placeholder="变量名"
                />
                <ScrollSelect
                  optionCount={VAR_TYPES.length}
                  value={row.type}
                  onChange={(e) => updateList("build_variables", index, "type", e.target.value)}
                >
                  {VAR_TYPES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </ScrollSelect>
                {row.type === "string" ? (
                  <input
                    value={row.value}
                    onChange={(e) => updateList("build_variables", index, "value", e.target.value)}
                    placeholder="默认值"
                  />
                ) : (
                  <input
                    value={row.options}
                    onChange={(e) => updateList("build_variables", index, "options", e.target.value)}
                    placeholder="选项，逗号分隔"
                  />
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
                <button type="button" className="link-btn danger" onClick={() => removeListRow("build_variables", index)}>
                  删除
                </button>
              </div>
            );
          })}
        </section>

        <div className="form-actions sticky-actions">
          <button
            type="submit"
            className="primary-btn"
            disabled={
              saving ||
              serviceCheck.blocked ||
              serviceCheck.exists ||
              !form.project_key ||
              !form.environment ||
              (!isNewEnvironment && environmentOptions.length === 0)
            }
          >
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
    </section>
  );
}

function ScrollableSelectCompat({ required, loading, optionCount, value, onChange, options }) {
  return (
    <ScrollSelect required={required} loading={loading} optionCount={optionCount} value={value} onChange={onChange}>
      <option value="">请选择</option>
      {options.map((item) => (
        <option key={item.path || item.name} value={item.path || item.name}>
          {item.path || item.name}
        </option>
      ))}
    </ScrollSelect>
  );
}
