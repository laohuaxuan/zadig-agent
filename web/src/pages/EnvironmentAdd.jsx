import { useEffect, useMemo, useRef, useState } from "react";
import ScrollSelect from "../components/ScrollSelect.jsx";
import SearchableSelect from "../components/SearchableSelect.jsx";
import SubmitToast from "../components/SubmitToast.jsx";
import {
  checkProjectEnvironment,
  fetchClusterNamespaces,
  submitEnvironmentApplication,
} from "../api.js";
import { loadEnvironmentAddOptions } from "../utils/projectFormCache.js";
import { clusterOptionLabel, registryOptionLabel } from "../utils/integrationOptions.js";

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
  environment_production: false,
  environment: "",
  cluster_name: "",
  namespace: "",
  registry_id: "",
  registry_label: "",
};

function defaultNamespace(projectKey, environment) {
  const key = String(projectKey || "").trim();
  const env = String(environment || "dev").trim();
  if (!key || !env) return "";
  return `${key}-${env}`;
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

export default function EnvironmentAdd() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [options, setOptions] = useState({
    projects: [],
    clusters: [],
    registries: [],
    clusterNamespaces: [],
  });
  const namespaceTouched = useRef(false);
  const [optionsLoading, setOptionsLoading] = useState({
    bootstrap: true,
    clusterNamespaces: false,
    environmentCheck: false,
  });
  const [environmentCheck, setEnvironmentCheck] = useState({ exists: false, message: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [zadig, setZadig] = useState(null);

  const suggestedNamespace = useMemo(
    () => defaultNamespace(form.project_key, form.environment),
    [form.project_key, form.environment],
  );

  const selectedRegistry = useMemo(
    () =>
      options.registries.find((item) => String(item.registry_id || item.id || "") === form.registry_id),
    [options.registries, form.registry_id],
  );

  function resetForm() {
    setForm({ ...INITIAL_FORM });
    setEnvironmentCheck({ exists: false, message: "" });
    namespaceTouched.current = false;
    setOptions((prev) => ({ ...prev, clusterNamespaces: [] }));
  }

  useEffect(() => {
    let cancelled = false;

    loadEnvironmentAddOptions()
      .then((data) => {
        if (cancelled) return;
        setOptions((prev) => ({
          ...prev,
          projects: data.projects || [],
          clusters: data.clusters || [],
          registries: data.registries || [],
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
    if (!form.cluster_name) {
      setOptions((prev) => ({ ...prev, clusterNamespaces: [] }));
      return;
    }
    setOptionsLoading((prev) => ({ ...prev, clusterNamespaces: true }));
    fetchClusterNamespaces(form.cluster_name)
      .then((data) => {
        setOptions((prev) => ({ ...prev, clusterNamespaces: data.items || [] }));
      })
      .catch(() => {
        setOptions((prev) => ({ ...prev, clusterNamespaces: [] }));
      })
      .finally(() => setOptionsLoading((prev) => ({ ...prev, clusterNamespaces: false })));
  }, [form.cluster_name]);

  useEffect(() => {
    const name = form.environment.trim();
    if (!form.project_key || !name) {
      setEnvironmentCheck({ exists: false, message: "" });
      return;
    }
    const timer = setTimeout(async () => {
      setOptionsLoading((prev) => ({ ...prev, environmentCheck: true }));
      try {
        const data = await checkProjectEnvironment(form.project_key, name, {
          production: form.environment_production,
        });
        const envType = form.environment_production ? "生产环境" : "测试环境";
        setEnvironmentCheck({
          exists: Boolean(data.exists),
          message: data.exists ? `项目 ${form.project_key} 的${envType}中已存在环境 ${name}` : "",
        });
      } catch (err) {
        setEnvironmentCheck({ exists: false, message: err.message });
      } finally {
        setOptionsLoading((prev) => ({ ...prev, environmentCheck: false }));
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [form.project_key, form.environment, form.environment_production]);

  useEffect(() => {
    if (namespaceTouched.current || !suggestedNamespace) return;
    setForm((prev) => (prev.namespace === suggestedNamespace ? prev : { ...prev, namespace: suggestedNamespace }));
  }, [suggestedNamespace]);

  function update(key, value) {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "project_key") {
        const project = options.projects.find((item) => item.project_key === value);
        next.project_name = project?.project_name || value;
        next.environment = DEFAULT_ENV_NAME[String(next.environment_production)];
        next.namespace = defaultNamespace(value, next.environment);
        namespaceTouched.current = false;
      }
      if (key === "environment_production") {
        const isProduction = value === true || value === "true";
        next.environment_production = isProduction;
        next.environment = DEFAULT_ENV_NAME[String(isProduction)];
        next.namespace = defaultNamespace(next.project_key, next.environment);
        namespaceTouched.current = false;
      }
      if (key === "registry_id") {
        const registry = options.registries.find(
          (item) => String(item.registry_id || item.id || "") === value,
        );
        next.registry_label = registry ? registryOptionLabel(registry) : value;
      }
      if (key === "namespace") {
        namespaceTouched.current = true;
      }
      return next;
    });
  }

  function buildPayload() {
    if (environmentCheck.exists) {
      throw new Error(environmentCheck.message || "环境名称已存在");
    }
    return {
      application_type: "add_environment",
      project_key: form.project_key,
      project_name: form.project_name || form.project_key,
      environment: form.environment.trim(),
      environment_production: Boolean(form.environment_production),
      cluster_name: form.cluster_name,
      namespace: form.namespace.trim(),
      registry_id: form.registry_id,
      registry_label: form.registry_label || (selectedRegistry ? registryOptionLabel(selectedRegistry) : form.registry_id),
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
      const data = await submitEnvironmentApplication(payload);
      const item = data.item || {};
      setSuccess(
        item.serial_no
          ? `添加环境申请 ${item.serial_no} 已提交，等待审批`
          : `项目 ${payload.project_key} 添加环境申请已提交`,
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
      <h1 className="page-title">添加新环境</h1>
      <p className="page-desc">
        向已有 Helm 项目添加测试或生产环境，提交后将进入审批流程，审批通过后由 Agent 自动创建 Zadig 环境。
      </p>
      {zadig ? (
        <dl className="info-card zadig-context">
          <div>
            <dt>当前 Zadig</dt>
            <dd>
              {zadig.name || "未命名"}
              {zadig.base_url ? ` · ${zadig.base_url}` : ""}
            </dd>
          </div>
        </dl>
      ) : null}
      {error ? (
        <div className="alert alert-error" role="alert">
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
              <FieldLabel required>环境类型</FieldLabel>
              <ScrollSelect
                required
                disabled={!form.project_key}
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
            <label className={environmentCheck.exists ? "field-has-error" : undefined}>
              <FieldLabel required>环境名称</FieldLabel>
              <input
                required
                disabled={!form.project_key}
                value={form.environment}
                onChange={(e) => update("environment", e.target.value)}
                placeholder={form.environment_production ? "prod" : "dev"}
                className={environmentCheck.exists ? "field-input-error" : undefined}
                aria-invalid={environmentCheck.exists || undefined}
                aria-describedby={environmentCheck.exists ? "environment-name-conflict" : undefined}
              />
              {optionsLoading.environmentCheck ? <span className="field-hint">正在校验环境名称…</span> : null}
              {environmentCheck.exists && environmentCheck.message ? (
                <div className="field-conflict-alert" id="environment-name-conflict" role="alert">
                  {environmentCheck.message}，请更换环境名称后再提交。
                </div>
              ) : null}
              {!environmentCheck.exists && environmentCheck.message ? (
                <span className="field-hint error-text">{environmentCheck.message}</span>
              ) : null}
            </label>
          </div>
          <p className={`field-hint${environmentCheck.exists ? " error-text" : ""}`}>
            {environmentCheck.exists
              ? `命名空间建议：${suggestedNamespace || "项目标识-环境名称"}。`
              : `环境名称在同一项目的同类型环境（测试/生产）中不可重复；命名空间建议：${suggestedNamespace || "项目标识-环境名称"}。`}
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
                value={form.namespace}
                placeholder={form.cluster_name ? "选择或输入命名空间" : "请先选择集群"}
                onChange={(e) => update("namespace", e.target.value)}
                options={options.clusterNamespaces.map((item) => ({
                  value: item.name,
                  label: item.name,
                }))}
                emptyText="未找到命名空间，可直接输入"
              />
            </label>
            <label>
              <FieldLabel required>镜像仓库</FieldLabel>
              <ScrollSelect
                required
                optionCount={options.registries.length + 1}
                value={form.registry_id}
                onChange={(e) => update("registry_id", e.target.value)}
              >
                <option value="">请选择</option>
                {options.registries.map((item) => (
                  <option key={item.registry_id || item.id} value={item.registry_id || item.id}>
                    {registryOptionLabel(item)}
                    {item.is_default ? "（默认）" : ""}
                  </option>
                ))}
              </ScrollSelect>
            </label>
          </div>
        </section>

        <div className="form-actions sticky-actions">
          <button
            type="submit"
            className="primary-btn"
            disabled={
              saving ||
              optionsLoading.bootstrap ||
              environmentCheck.exists ||
              !form.project_key ||
              !form.environment.trim() ||
              !form.cluster_name ||
              !form.namespace.trim() ||
              !form.registry_id
            }
          >
            {saving ? "提交中…" : "提交申请"}
          </button>
        </div>
      </form>
    </section>
  );
}
