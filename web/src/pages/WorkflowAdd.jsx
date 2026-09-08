import { useEffect, useMemo, useState } from "react";
import ScrollSelect from "../components/ScrollSelect.jsx";
import SearchableSelect from "../components/SearchableSelect.jsx";
import SubmitToast from "../components/SubmitToast.jsx";
import {
  checkProjectWorkflow,
  fetchProjectBuildServices,
  fetchProjectEnvironments,
  submitWorkflowApplication,
} from "../api.js";
import { fetchAllProjectEnvironments, loadWorkflowAddOptions, mapEnvironmentOptions } from "../utils/projectFormCache.js";
import { registryOptionLabel } from "../utils/integrationOptions.js";

const DEPLOY_ENV_TYPE_OPTIONS = [
  { value: "false", label: "测试环境" },
  { value: "true", label: "生产环境" },
];

const INITIAL_FORM = {
  project_key: "",
  project_name: "",
  environment: "",
  workflow_name: "",
  registry_id: "",
  registry_label: "",
  service_name: "",
  service_module: "",
  build_name: "",
  image_name: "",
  deploy_production: false,
  deploy_env_name: "",
};

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

export default function WorkflowAdd() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [options, setOptions] = useState({
    projects: [],
    registries: [],
    buildServices: [],
    environments: [],
    deployEnvironments: [],
  });
  const [optionsLoading, setOptionsLoading] = useState({
    bootstrap: true,
    environments: false,
    buildServices: false,
    deployEnvironments: false,
    workflowCheck: false,
  });
  const [workflowCheck, setWorkflowCheck] = useState({ exists: false, message: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [zadig, setZadig] = useState(null);

  const environmentOptions = useMemo(
    () => mapEnvironmentOptions(options.environments),
    [options.environments],
  );

  const deployEnvironmentOptions = useMemo(
    () => mapEnvironmentOptions(options.deployEnvironments),
    [options.deployEnvironments],
  );

  const selectedBuildService = useMemo(
    () => options.buildServices.find((item) => item.service_name === form.service_name),
    [options.buildServices, form.service_name],
  );

  const selectedRegistry = useMemo(
    () =>
      options.registries.find((item) => String(item.registry_id || item.id || "") === form.registry_id),
    [options.registries, form.registry_id],
  );

  function resetForm() {
    setForm({ ...INITIAL_FORM });
    setWorkflowCheck({ exists: false, message: "" });
    setOptions((prev) => ({ ...prev, deployEnvironments: [] }));
  }

  useEffect(() => {
    let cancelled = false;

    loadWorkflowAddOptions()
      .then((data) => {
        if (cancelled) return;
        setOptions((prev) => ({
          ...prev,
          projects: data.projects || [],
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
    if (!form.project_key) {
      setOptions((prev) => ({ ...prev, environments: [], buildServices: [], deployEnvironments: [] }));
      return;
    }
    setOptionsLoading((prev) => ({ ...prev, environments: true, buildServices: true }));
    Promise.all([fetchAllProjectEnvironments(form.project_key), fetchProjectBuildServices(form.project_key)])
      .then(([envItems, buildData]) => {
        setOptions((prev) => ({
          ...prev,
          environments: envItems,
          buildServices: buildData.items || [],
        }));
        setForm((prev) => {
          const names = envItems.map((item) => item.env_name);
          const nextEnv = prev.environment && names.includes(prev.environment) ? prev.environment : names[0] || "";
          return nextEnv === prev.environment ? prev : { ...prev, environment: nextEnv };
        });
      })
      .catch(() => {
        setOptions((prev) => ({ ...prev, environments: [], buildServices: [] }));
      })
      .finally(() => setOptionsLoading((prev) => ({ ...prev, environments: false, buildServices: false })));
  }, [form.project_key]);

  useEffect(() => {
    if (!form.project_key) {
      return;
    }
    setOptionsLoading((prev) => ({ ...prev, deployEnvironments: true }));
    fetchProjectEnvironments(form.project_key, { production: form.deploy_production })
      .then((data) => {
        const items = data.items || [];
        setOptions((prev) => ({ ...prev, deployEnvironments: items }));
        setForm((prev) => {
          const names = items.map((item) => item.env_name);
          if (prev.deploy_env_name && names.includes(prev.deploy_env_name)) {
            return prev;
          }
          return { ...prev, deploy_env_name: names[0] || "" };
        });
      })
      .catch(() => {
        setOptions((prev) => ({ ...prev, deployEnvironments: [] }));
        setForm((prev) => ({ ...prev, deploy_env_name: "" }));
      })
      .finally(() => setOptionsLoading((prev) => ({ ...prev, deployEnvironments: false })));
  }, [form.project_key, form.deploy_production]);

  useEffect(() => {
    const name = form.workflow_name.trim();
    if (!form.project_key || !name) {
      setWorkflowCheck({ exists: false, message: "" });
      return;
    }
    const timer = setTimeout(async () => {
      setOptionsLoading((prev) => ({ ...prev, workflowCheck: true }));
      try {
        const data = await checkProjectWorkflow(form.project_key, name);
        setWorkflowCheck({
          exists: Boolean(data.exists),
          message: data.exists ? `项目 ${form.project_key} 中已存在工作流 ${name}` : "",
        });
      } catch (err) {
        setWorkflowCheck({ exists: false, message: err.message });
      } finally {
        setOptionsLoading((prev) => ({ ...prev, workflowCheck: false }));
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [form.project_key, form.workflow_name]);

  function registryLabel(item) {
    const address = String(item.address || item.url || "").trim().replace(/\/+$/, "");
    const namespace = String(item.namespace || "").trim();
    if (address && namespace) return `${address}/${namespace}`;
    return address || item.registry_id || item.id || "";
  }

  function update(key, value) {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "project_key") {
        const project = options.projects.find((item) => item.project_key === value);
        next.project_name = project?.project_name || value;
        next.service_name = "";
        next.service_module = "";
        next.build_name = "";
        next.image_name = "";
        next.deploy_env_name = "";
      }
      if (key === "deploy_production") {
        next.deploy_env_name = "";
      }
      if (key === "registry_id") {
        const registry = options.registries.find(
          (item) => String(item.registry_id || item.id || "") === value,
        );
        next.registry_label = registry ? registryLabel(registry) : value;
      }
      if (key === "service_name") {
        const match = options.buildServices.find((item) => item.service_name === value);
        next.service_module = match?.service_module || value;
        next.build_name = match?.build_name || "";
        next.image_name = match?.image_name || match?.service_module || value;
      }
      return next;
    });
  }

  function buildPayload() {
    if (workflowCheck.exists) {
      throw new Error(workflowCheck.message || "工作流名称已存在");
    }
    const match =
      selectedBuildService ||
      options.buildServices.find((item) => item.service_name === form.service_name);
    return {
      application_type: "add_workflow",
      project_key: form.project_key,
      project_name: form.project_name || form.project_key,
      environment: form.environment,
      workflow_name: form.workflow_name.trim(),
      registry_id: form.registry_id,
      registry_label: form.registry_label,
      service_name: form.service_name,
      service_module: form.service_module || match?.service_module || form.service_name,
      build_name: form.build_name || match?.build_name || "",
      image_name: form.image_name || match?.image_name || form.service_name,
      deploy_production: Boolean(form.deploy_production),
      deploy_env_name: form.deploy_env_name,
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
      const data = await submitWorkflowApplication(payload);
      const item = data.item || {};
      setSuccess(
        item.serial_no
          ? `添加工作流申请 ${item.serial_no} 已提交，等待审批`
          : `项目 ${payload.project_key} 添加工作流申请已提交`,
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
      <h1 className="page-title">添加工作流</h1>
      <p className="page-desc">
        向已有 Helm 项目添加构建部署工作流，提交后将进入审批流程，审批通过后由 Agent 自动创建工作流。
      </p>
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
              <FieldLabel required>环境</FieldLabel>
              <ScrollSelect
                required
                disabled={!form.project_key}
                loading={Boolean(form.project_key && optionsLoading.environments)}
                optionCount={environmentOptions.length + 1}
                value={form.environment}
                onChange={(e) => update("environment", e.target.value)}
              >
                <option value="">
                  {form.project_key
                    ? optionsLoading.environments
                      ? "加载中…"
                      : environmentOptions.length
                        ? "请选择"
                        : "当前项目暂无环境"
                    : "请先选择项目"}
                </option>
                {environmentOptions.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </ScrollSelect>
            </label>
            <label className="span-2">
              <FieldLabel required>工作流名称</FieldLabel>
              <input
                required
                disabled={!form.project_key}
                value={form.workflow_name}
                onChange={(e) => update("workflow_name", e.target.value)}
                placeholder={form.project_key ? "my-service-dev" : "请先选择项目"}
              />
              {optionsLoading.workflowCheck ? <span className="field-hint">正在校验工作流名称…</span> : null}
              {workflowCheck.message ? <span className="field-hint error-text">{workflowCheck.message}</span> : null}
            </label>
          </div>
        </section>

        <section className="form-section">
          <h2>构建</h2>
          <div className="form-grid">
            <label className="span-2">
              <FieldLabel required>镜像仓库</FieldLabel>
              <SearchableSelect
                required
                placeholder="搜索并选择镜像仓库"
                value={form.registry_id}
                onChange={(e) => update("registry_id", e.target.value)}
                options={options.registries.map((item) => {
                  const id = String(item.registry_id || item.id || "");
                  return { value: id, label: registryOptionLabel(item) };
                })}
                emptyText="未找到匹配镜像仓库"
              />
              {selectedRegistry?.remark ? (
                <span className="field-hint">{selectedRegistry.remark}</span>
              ) : null}
            </label>
            <label className="span-2">
              <FieldLabel required>服务组件</FieldLabel>
              <SearchableSelect
                required
                disabled={!form.project_key}
                loading={Boolean(form.project_key && optionsLoading.buildServices)}
                placeholder={form.project_key ? "搜索并选择服务组件" : "请先选择项目"}
                value={form.service_name}
                onChange={(e) => update("service_name", e.target.value)}
                options={options.buildServices.map((item) => ({
                  value: item.service_name,
                  label: item.label,
                }))}
                emptyText="未找到匹配服务组件"
              />
              {selectedBuildService ? (
                <span className="field-hint">
                  构建：{selectedBuildService.build_name} · 镜像：{selectedBuildService.image_name}
                </span>
              ) : null}
            </label>
          </div>
        </section>

        <section className="form-section">
          <h2>部署</h2>
          <div className="form-grid">
            <label>
              <FieldLabel required>环境类型</FieldLabel>
              <ScrollSelect
                required
                optionCount={DEPLOY_ENV_TYPE_OPTIONS.length}
                value={String(form.deploy_production)}
                onChange={(e) => update("deploy_production", e.target.value === "true")}
              >
                {DEPLOY_ENV_TYPE_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </ScrollSelect>
            </label>
            <label>
              <FieldLabel required>部署环境</FieldLabel>
              <SearchableSelect
                required
                disabled={!form.project_key}
                loading={Boolean(form.project_key && optionsLoading.deployEnvironments)}
                placeholder={
                  form.project_key
                    ? optionsLoading.deployEnvironments
                      ? "加载中…"
                      : deployEnvironmentOptions.length
                        ? "搜索并选择部署环境"
                        : "当前类型下无可用环境"
                    : "请先选择项目"
                }
                value={form.deploy_env_name}
                onChange={(e) => update("deploy_env_name", e.target.value)}
                options={deployEnvironmentOptions}
                emptyText="未找到匹配环境"
              />
            </label>
          </div>
          <p className="field-hint">
            与 Zadig 流水线部署阶段一致：先选环境类型（测试/生产），部署环境列表从 Zadig 对应接口加载。
          </p>
        </section>

        <div className="form-actions sticky-actions">
          <button
            type="submit"
            className="primary-btn"
            disabled={
              saving ||
              workflowCheck.exists ||
              !form.project_key ||
              !form.workflow_name.trim() ||
              !form.registry_id ||
              !form.service_name ||
              !form.deploy_env_name
            }
          >
            {saving ? "提交中…" : "提交申请"}
          </button>
        </div>
      </form>
    </section>
  );
}
