import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  approveWorkflow,
  fetchWorkflowCounts,
  fetchWorkflowInstance,
  fetchWorkflowTasks,
  rejectWorkflow,
  replyWorkflowExecution,
  revokeWorkflow,
  streamWorkflowExecution,
} from "../api.js";
import { PanelLoading } from "../components/LoadingIndicator.jsx";
import ScrollSelect from "../components/ScrollSelect.jsx";

const WORKFLOW_BOXES = [
  { id: "todo", label: "任务/待办" },
  { id: "done", label: "已办" },
  { id: "cc", label: "抄送我" },
  { id: "initiated", label: "已发起" },
];

const WORKFLOW_PAGE_SIZES = [10, 20, 50, 100];
const WORKFLOW_POLL_IDLE_MS = 8000;
const WORKFLOW_POLL_ACTIVE_MS = 3000;

const STATUS_CLASS = {
  pending: "wf-status-pending",
  approved: "wf-status-approved",
  rejected: "wf-status-rejected",
  revoked: "wf-status-revoked",
  completed: "wf-status-approved",
  awaiting_execution: "wf-status-pending",
  executing: "wf-status-pending",
  execution_failed: "wf-status-rejected",
};

function workflowStatusClass(item) {
  return STATUS_CLASS[item?.status_key || item?.status] || "";
}

function formatDateTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function relativeTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days > 0) return `${days}天前`;
  const hours = Math.floor(diff / 3600000);
  if (hours > 0) return `${hours}小时前`;
  const mins = Math.floor(diff / 60000);
  if (mins > 0) return `${mins}分钟前`;
  return "刚刚";
}

const FLOW_STEP_STATUS_LABEL = {
  done: "已完成",
  pending: "待审批",
  upcoming: "待到达",
  rejected: "已驳回",
  failed: "失败",
  cancelled: "已取消",
};

function flowStepStatusLabel(step) {
  if (step.name === "Agent 执行") {
    if (step.status === "failed") return "失败";
    if (step.status === "pending") return step.action_label || "待执行";
    if (step.action_label === "执行中") return "执行中";
    if (step.status === "done") return "已完成";
  }
  return FLOW_STEP_STATUS_LABEL[step.status] || step.status;
}

function formatAgentMeta(meta) {
  if (!meta) return "";
  const name = meta.name || meta.agent || "zadig_bot";
  const parts = [`Agent: ${name}`];
  if (meta.id) parts.push(`ID: ${meta.id}`);
  parts.push(`Model: ${meta.model || "-"}`);
  parts.push(`Provider: ${meta.provider || "-"}`);
  return parts.join(" | ");
}

function resolveAgentMeta(application, executionContext, agentMetaState) {
  return (
    agentMetaState ||
    application?.agent_meta ||
    executionContext?.agent ||
    application?.execution_context?.agent ||
    null
  );
}

function AgentInfoPanel({ meta }) {
  if (!meta?.name && !meta?.agent && !meta?.model) return null;
  const name = meta.name || meta.agent || "—";
  return (
    <dl className="workflow-kv workflow-agent-resources workflow-agent-info">
      <div className="workflow-kv-row">
        <dt>Agent</dt>
        <dd>
          {name}
          {meta.is_default ? <span className="wf-tag wf-tag-default">默认</span> : null}
        </dd>
      </div>
      {meta.id ? (
        <div className="workflow-kv-row">
          <dt>标识</dt>
          <dd className="workflow-kv-mono">{meta.id}</dd>
        </div>
      ) : null}
      <div className="workflow-kv-row">
        <dt>模型</dt>
        <dd>
          {meta.model || "—"}
          {meta.primary_model && meta.primary_model !== meta.model ? (
            <span className="wf-muted"> · 主模型 {meta.primary_model} 不可用，已切换备用</span>
          ) : null}
        </dd>
      </div>
      <div className="workflow-kv-row">
        <dt>提供商</dt>
        <dd>{meta.provider || "—"}</dd>
      </div>
      {meta.base_url ? (
        <div className="workflow-kv-row">
          <dt>API</dt>
          <dd className="workflow-kv-mono">{meta.base_url}</dd>
        </div>
      ) : null}
    </dl>
  );
}

function formatExecutionResourcesMeta(ctx) {
  if (!ctx?.skill) return "";
  const skill = ctx.skill.name || "-";
  const template = ctx.workflow_template?.name || "-";
  const mcp = ctx.mcp?.server || "zadig";
  return `Skill: ${skill} | Template: ${template} | MCP: ${mcp}`;
}

function logAwaitingUserInput(logText) {
  const text = String(logText || "");
  if (!text) return false;
  return (
    text.includes("⏸ 等待用户确认") ||
    text.includes("⏸ 等待您的确认") ||
    text.includes("[需要用户确认]") ||
    /请您确认/.test(text) ||
    /请选择/.test(text) ||
    /请确认采用/.test(text)
  );
}

function ExecutionResourcesPanel({ context }) {
  if (!context?.skill) return null;
  const { skill, workflow_template: workflowTemplate, service_template: serviceTemplate, mcp, catalog } = context;
  return (
    <dl className="workflow-kv workflow-agent-resources">
      <div className="workflow-kv-row">
        <dt>Skill</dt>
        <dd>
          {skill.name}
          {skill.display_name && skill.display_name !== skill.name ? `（${skill.display_name}）` : ""}
          {skill.source ? <span className="wf-muted"> · {skill.source}</span> : null}
        </dd>
      </div>
      <div className="workflow-kv-row">
        <dt>工作流模板</dt>
        <dd>
          {workflowTemplate?.name || "—"}
          {workflowTemplate?.display_name && workflowTemplate.display_name !== workflowTemplate.name
            ? `（${workflowTemplate.display_name}）`
            : ""}
          {workflowTemplate?.source ? <span className="wf-muted"> · {workflowTemplate.source}</span> : null}
        </dd>
      </div>
      {serviceTemplate?.name ? (
        <div className="workflow-kv-row">
          <dt>Chart 服务模板</dt>
          <dd>{serviceTemplate.name}</dd>
        </div>
      ) : null}
      <div className="workflow-kv-row">
        <dt>MCP</dt>
        <dd>
          {mcp?.server || "zadig"}
          {mcp?.transport ? ` · ${mcp.transport}` : ""}
          {catalog?.mcp_tools_count != null ? ` · ${catalog.mcp_tools_count} 工具` : ""}
        </dd>
      </div>
    </dl>
  );
}

function FlowStepMarker({ status }) {
  if (status === "done") {
    return (
      <span className="wf-flow-step-check" aria-hidden>
        <svg viewBox="0 0 12 12" focusable="false">
          <path d="M2.5 6.2 L5.1 8.8 L9.5 3.8" />
        </svg>
      </span>
    );
  }
  return <span className="wf-flow-step-dot" aria-hidden />;
}

function WorkflowFlowSteps({ steps, initiatorName }) {
  if (!steps?.length) return null;
  return (
    <div className="wf-flow-steps">
      {steps.map((step, index) => (
        <div key={`${step.level}-${step.name}`} className={`wf-flow-step wf-flow-step-${step.status}`}>
          <div className="wf-flow-step-track">
            <FlowStepMarker status={step.status} />
            {index < steps.length - 1 ? <span className="wf-flow-step-line" aria-hidden /> : null}
          </div>
          <div className="wf-flow-step-body">
            <div className="wf-flow-step-head">
              <strong>{step.name}</strong>
              <span className="wf-flow-step-status">{flowStepStatusLabel(step)}</span>
            </div>
            {step.status === "done" || step.status === "rejected" || step.status === "failed" ? (
              <div className="wf-flow-step-meta">
                <span>{step.actor_name || "-"}</span>
                {step.action_label ? (
                  <span className={step.status === "failed" ? "wf-flow-step-action wf-flow-step-action-failed" : "wf-flow-step-action"}>
                    {step.action_label}
                  </span>
                ) : null}
                {step.processed_at ? <span className="wf-flow-step-time">{relativeTime(step.processed_at)}</span> : null}
              </div>
            ) : (
              <div className="wf-flow-step-assignees">
                {(step.assignees || []).length > 0 ? (
                  step.assignees.map((name) => (
                    <span key={name} className="wf-flow-assignee-chip">
                      {name}
                    </span>
                  ))
                ) : (
                  <span className="wf-flow-assignee-chip">{initiatorName || "未指定审批人"}</span>
                )}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function WorkflowPanel() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeBox, setActiveBox] = useState("todo");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailTab, setDetailTab] = useState("detail");
  const [actionComment, setActionComment] = useState("");
  const [counts, setCounts] = useState({ todo: 0, cc: 0, initiated: 0, initiated_unread: 0, done: 0 });
  const [itemsLoading, setItemsLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [executionLog, setExecutionLog] = useState("");
  const [executionPhase, setExecutionPhase] = useState("idle");
  const [agentMeta, setAgentMeta] = useState(null);
  const [executionContext, setExecutionContext] = useState(null);
  const [userReply, setUserReply] = useState("");
  const logRef = useRef(null);
  const detailCacheRef = useRef(new Map());
  const detailRequestRef = useRef(0);
  const autoResumeAttemptRef = useRef(null);
  const [error, setError] = useState("");
  const [detailRefreshing, setDetailRefreshing] = useState(false);

  const loadCounts = useCallback(async () => {
    const data = await fetchWorkflowCounts();
    setCounts({
      todo: data.todo || 0,
      cc: data.cc || 0,
      initiated: data.initiated || 0,
      initiated_unread: data.initiated_unread || 0,
      done: data.done || 0,
    });
  }, []);

  const loadItems = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setItemsLoading(true);
      setError("");
    }
    try {
      const data = await fetchWorkflowTasks(activeBox, { page, pageSize, keyword: search });
      const nextItems = data.items || [];
      setItems(nextItems);
      setTotal(data.total || 0);
      if (nextItems.length === 0) {
        setSelectedId(null);
        setDetail(null);
        return;
      }
      setSelectedId((prev) => {
        if (prev && nextItems.some((item) => item.instance_id === prev)) return prev;
        return nextItems[0].instance_id;
      });
    } catch (err) {
      if (!silent) setError(err.message);
    } finally {
      if (!silent) setItemsLoading(false);
    }
  }, [activeBox, page, pageSize, search]);

  const loadDetail = useCallback(async (instanceId, { force = false, silent = false } = {}) => {
    if (!instanceId) {
      setDetail(null);
      return;
    }
    const cached = detailCacheRef.current.get(instanceId);
    if (cached && !force) {
      setDetail(cached);
      setActionComment("");
      setDetailLoading(false);
    } else if (!cached) {
      setDetailLoading(true);
    } else if (force && !silent) {
      setDetailRefreshing(true);
    }

    const requestId = ++detailRequestRef.current;
    try {
      const data = await fetchWorkflowInstance(instanceId);
      if (requestId !== detailRequestRef.current) return;
      detailCacheRef.current.set(instanceId, data);
      setDetail(data);
      setActionComment("");
      await loadCounts();
    } catch (err) {
      if (requestId !== detailRequestRef.current) return;
      setError(err.message);
    } finally {
      if (requestId !== detailRequestRef.current) return;
      setDetailLoading(false);
      if (!silent) setDetailRefreshing(false);
    }
  }, [loadCounts]);

  const refreshAll = useCallback(
    async (instanceId = selectedId, { silent = false } = {}) => {
      if (instanceId) detailCacheRef.current.delete(instanceId);
      await Promise.all([loadCounts(), loadItems({ silent })]);
      if (instanceId) await loadDetail(instanceId, { force: true, silent });
    },
    [loadCounts, loadItems, loadDetail, selectedId],
  );

  const pollWorkflow = useCallback(
    async ({ silent = true } = {}) => {
      if (document.visibilityState !== "visible") return;
      await loadCounts().catch(() => {});
      await loadItems({ silent }).catch(() => {});
      if (selectedId) await loadDetail(selectedId, { force: true, silent }).catch(() => {});
    },
    [loadCounts, loadItems, loadDetail, selectedId],
  );

  useEffect(() => {
    const app = searchParams.get("app");
    const raw = Number(searchParams.get("instance") || 0);
    if (raw > 0 && (!app || app === "zadig-agent")) {
      setSelectedId(raw);
      searchParams.delete("instance");
      searchParams.delete("app");
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    loadCounts().catch(() => {});
  }, [loadCounts, activeBox, search]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId, { force: true });
  }, [selectedId, loadDetail]);

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState !== "visible") return;
      pollWorkflow({ silent: false });
    }
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [pollWorkflow]);

  useEffect(() => {
    if (executing) return;

    const activeStatuses = new Set(["pending", "awaiting_execution", "executing"]);
    const statusKey = detail?.instance?.status_key || detail?.instance?.status || "";
    const flowStatus = detail?.application?.flow_status || "";
    const needsFastPoll =
      activeStatuses.has(statusKey) ||
      flowStatus === "执行中" ||
      flowStatus === "待执行" ||
      Boolean(detail?.execution_session?.awaiting_input) ||
      Boolean(detail?.can_approve);

    const intervalMs = needsFastPoll ? WORKFLOW_POLL_ACTIVE_MS : WORKFLOW_POLL_IDLE_MS;
    const timer = window.setInterval(() => {
      pollWorkflow({ silent: true });
    }, intervalMs);

    return () => window.clearInterval(timer);
  }, [
    executing,
    pollWorkflow,
    detail?.instance?.status,
    detail?.instance?.status_key,
    detail?.application?.flow_status,
    detail?.execution_session?.awaiting_input,
    detail?.can_approve,
  ]);

  useEffect(() => {
    if (executing) return;
    const logText = detail?.application?.execution_log || "";
    setExecutionLog(logText);
    setAgentMeta(
      detail?.application?.agent_meta ||
        detail?.application?.execution_context?.agent ||
        null,
    );
    setExecutionContext(detail?.application?.execution_context || null);
    const status = detail?.application?.flow_status || "";
    const serverAwaiting = Boolean(detail?.execution_session?.awaiting_input);
    const logAwaiting = logAwaitingUserInput(logText);
    if (serverAwaiting || (status === "执行中" && logAwaiting)) {
      setExecutionPhase("awaiting_input");
    } else if (status === "执行中") {
      setExecutionPhase("running");
    } else if (status === "已完成" || status === "失败") {
      setExecutionPhase("finished");
    } else if (!executing) {
      setExecutionPhase("idle");
    }
  }, [
    detail?.application?.execution_log,
    detail?.application?.flow_status,
    detail?.application?.agent_meta,
    detail?.application?.execution_context,
    detail?.execution_session?.awaiting_input,
    detail?.instance?.id,
    executing,
  ]);

  useEffect(() => {
    autoResumeAttemptRef.current = null;
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || executing || detailLoading) return;
    if (!detail?.can_resume || detail?.application?.flow_status !== "执行中") return;
    if (autoResumeAttemptRef.current === selectedId) return;
    autoResumeAttemptRef.current = selectedId;
    runExecute({ resume: true });
  }, [
    selectedId,
    executing,
    detailLoading,
    detail?.can_resume,
    detail?.application?.flow_status,
  ]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [executionLog]);

  async function runAction(action) {
    if (!selectedId || acting) return;
    setActing(true);
    setError("");
    try {
      const body = { comment: actionComment };
      if (action === "approve") await approveWorkflow(selectedId, body);
      else await rejectWorkflow(selectedId, body);
      await refreshAll(selectedId);
    } catch (err) {
      setError(err.message);
    } finally {
      setActing(false);
    }
  }

  async function runRevoke() {
    if (!selectedId || acting) return;
    if (!window.confirm("确认撤销该申请？")) return;
    setActing(true);
    try {
      await revokeWorkflow(selectedId);
      await refreshAll(selectedId);
    } catch (err) {
      setError(err.message);
    } finally {
      setActing(false);
    }
  }

  async function runExecute(options = {}) {
    const resume = Boolean(options.resume);
    if (!selectedId || executing) return;
    setExecuting(true);
    setExecutionPhase("running");
    setError("");
    if (!resume) {
      setExecutionLog("");
      setUserReply("");
      setAgentMeta(null);
      setExecutionContext(null);
    }
    try {
      await streamWorkflowExecution(
        selectedId,
        {
          resume,
          onMeta: (event) => {
            if (event?.agent_meta) setAgentMeta(event.agent_meta);
            if (event?.execution_context) setExecutionContext(event.execution_context);
            if (event?.text) {
              setExecutionLog((prev) => (prev.includes(event.text) ? prev : `${prev}${event.text}\n`));
            }
          },
          onLog: (text) => setExecutionLog((prev) => prev + text),
          onInputRequired: (prompt) => {
            setExecutionPhase("awaiting_input");
            if (prompt) {
              setExecutionLog((prev) => `${prev}\n⏸ 等待您的确认，请在下方输入回复。\n`);
            }
          },
          onDone: async (event) => {
            setExecutionPhase("finished");
            if (event.agent_meta) setAgentMeta(event.agent_meta);
            if (event.execution_context) setExecutionContext(event.execution_context);
            if (event.project_url) {
              setExecutionLog((prev) => `${prev}\n项目链接：${event.project_url}\n`);
            }
            detailCacheRef.current.delete(selectedId);
            await refreshAll(selectedId);
          },
          onError: async (event) => {
            setExecutionPhase("finished");
            const message = event.message || "Agent 执行失败";
            setError(message);
            setExecutionLog((prev) =>
              prev.includes("❌ 执行失败") ? prev : `${prev}\n❌ 执行失败：${message}\n`,
            );
            detailCacheRef.current.delete(selectedId);
            await refreshAll(selectedId);
          },
        },
      );
    } catch (err) {
      setExecutionPhase("finished");
      setError(err.message);
      detailCacheRef.current.delete(selectedId);
      await refreshAll(selectedId);
    } finally {
      setExecuting(false);
    }
  }

  async function runReply(event) {
    event.preventDefault();
    const text = userReply.trim();
    if (!selectedId || !text) return;
    const serverAwaiting = Boolean(detail?.execution_session?.awaiting_input);
    if (executionPhase !== "awaiting_input" && !serverAwaiting) return;
    setExecutionPhase("running");
    setExecutionLog((prev) => `${prev}👤 用户：${text}\n`);
    setUserReply("");
    try {
      await replyWorkflowExecution(selectedId, text);
    } catch (err) {
      setExecutionPhase(serverAwaiting ? "awaiting_input" : "finished");
      setError(err.message);
    }
  }

  const application = detail?.application;
  const workflowCompleted = detail?.instance?.status === "completed";
  const showExecutionPanel = Boolean(
    application &&
      (workflowCompleted || executing || application.execution_log || application.flow_status === "执行中"),
  );
  const serverExecuting = application?.flow_status === "执行中";
  const canResume = Boolean(detail?.can_resume && !executing);
  const canExecute = Boolean(detail?.can_execute && !executing && !serverExecuting);
  const isRunning = executing || serverExecuting;
  const serverAwaitingInput = Boolean(detail?.execution_session?.awaiting_input);
  const logAwaiting = logAwaitingUserInput(executionLog || application?.execution_log || "");
  const canReply = Boolean(serverAwaitingInput || (executionPhase === "awaiting_input" && executing));
  const inputLocked = !canReply;
  const resolvedAgentMeta = resolveAgentMeta(application, executionContext, agentMeta);
  const agentMetaLine = formatAgentMeta(resolvedAgentMeta);
  const resourcesMetaLine = formatExecutionResourcesMeta(executionContext || application?.execution_context);

  return (
    <div className="workflow-page">
      <aside className="workflow-nav">
        <ul className="workflow-nav-list">
          {WORKFLOW_BOXES.map((box) => (
            <li key={box.id}>
              <button
                type="button"
                className={activeBox === box.id ? "workflow-nav-item active" : "workflow-nav-item"}
                onClick={() => {
                  setActiveBox(box.id);
                  setPage(1);
                  setSelectedId(null);
                  setDetail(null);
                }}
              >
                <span className="workflow-nav-label">{box.label}</span>
                {box.id === "todo" && counts.todo > 0 ? <span className="wf-badge wf-nav-badge">{counts.todo}</span> : null}
                {box.id === "cc" && counts.cc > 0 ? <span className="wf-badge wf-nav-badge">{counts.cc}</span> : null}
                {box.id === "initiated" && counts.initiated_unread > 0 ? (
                  <span className="wf-badge wf-nav-badge wf-nav-badge-dot" aria-label={`${counts.initiated_unread} 条未读`} />
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="workflow-list-pane">
        <div className="workflow-list-head">
          <div className="workflow-list-head-row">
            <h3>{WORKFLOW_BOXES.find((b) => b.id === activeBox)?.label}</h3>
            <span className="wf-muted">共 {total} 条</span>
          </div>
          <form
            className="workflow-list-search"
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
              setSearch(keyword.trim());
            }}
          >
            <input
              type="text"
              placeholder="搜索标题、单号、摘要、发起人"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              aria-label="搜索审批流"
            />
          </form>
        </div>
        <div className="workflow-list-body">
          {error ? <div className="banner error">{error}</div> : null}
          {itemsLoading ? (
            <PanelLoading label="加载审批列表..." />
          ) : (
            <>
              {items.map((item) => (
                <button
                  key={item.instance_id}
                  type="button"
                  className={`${selectedId === item.instance_id ? "workflow-card active" : "workflow-card"}${item.status === "revoked" ? " workflow-card-revoked" : ""}${item.unread ? " workflow-card-unread" : ""}`}
                  onClick={() => setSelectedId(item.instance_id)}
                  onMouseEnter={() => {
                    if (!detailCacheRef.current.has(item.instance_id)) {
                      fetchWorkflowInstance(item.instance_id)
                        .then((data) => detailCacheRef.current.set(item.instance_id, data))
                        .catch(() => {});
                    }
                  }}
                >
                  <div className="workflow-card-top">
                    <strong>{item.title}</strong>
                    <span className={`wf-status ${workflowStatusClass(item)}`}>{item.status_label}</span>
                  </div>
                  {item.unread ? <span className="wf-card-badge wf-card-badge-dot" aria-label="未读" /> : null}
                  <p className="workflow-card-summary">{item.summary || item.workflow_type}</p>
                  <div className="workflow-card-meta">
                    <span>{item.initiator_name || "-"}</span>
                    <span>{formatDateTime(item.processed_at || item.updated_at || item.created_at)}</span>
                  </div>
                </button>
              ))}
              {items.length === 0 ? <div className="empty-panel">{search ? "未找到匹配的审批" : "暂无记录"}</div> : null}
            </>
          )}
        </div>
        <div className="workflow-list-pager">
          <label className="workflow-page-size">
            每页
            <ScrollSelect
              className="workflow-page-size-select"
              optionCount={WORKFLOW_PAGE_SIZES.length}
              value={String(pageSize)}
              onChange={(e) => {
                setPageSize(Number(e.target.value) || 20);
                setPage(1);
              }}
            >
              {WORKFLOW_PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </ScrollSelect>
            条
          </label>
          <div className="pager">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              上一页
            </button>
            <span>
              第 {page} 页 / 共 {Math.max(1, Math.ceil(total / pageSize))} 页
            </span>
            <button
              type="button"
              disabled={page >= Math.max(1, Math.ceil(total / pageSize))}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </button>
          </div>
        </div>
      </section>

      <section className={`workflow-detail-pane${detail?.is_readonly ? " workflow-detail-readonly" : ""}`}>
        {detailLoading ? (
          <PanelLoading label="加载详情..." />
        ) : !detail?.instance ? (
          <div className="empty-panel">请选择一条流程查看详情</div>
        ) : (
          <>
            {detailRefreshing ? <div className="wf-muted workflow-detail-refresh">正在刷新...</div> : null}
            <div className="workflow-detail-head">
              <div className="workflow-detail-title-row">
                <div>
                  <div className="wf-serial">编号：{detail.instance.serial_no}</div>
                  <h2>
                    {detail.instance.title}
                    <span className={`wf-status ${workflowStatusClass(detail.instance)}`}>{detail.instance.status_label}</span>
                  </h2>
                  <div className="workflow-initiator">
                    <span className="wf-avatar">{(detail.instance.initiator_name || "?").slice(0, 1)}</span>
                    <div>
                      <div>{detail.instance.initiator_name}</div>
                      <div className="wf-muted">
                        {detail.instance.initiator_dept || "Zadig"} · 提交于 {formatDateTime(detail.instance.created_at)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="workflow-tabs">
              <button type="button" className={detailTab === "detail" ? "active" : ""} onClick={() => setDetailTab("detail")}>
                审批详情
              </button>
              <button type="button" className={detailTab === "records" ? "active" : ""} onClick={() => setDetailTab("records")}>
                审批记录
              </button>
              <button type="button" className={detailTab === "comments" ? "active" : ""} onClick={() => setDetailTab("comments")}>
                全文评论
              </button>
            </div>

            {detailTab === "detail" ? (
              <div className="workflow-detail-section">
                {detail.is_readonly ? (
                  <p className="wf-muted workflow-readonly-hint">该流程已结束，当前为只读查看。</p>
                ) : null}
                <h4>审批流程</h4>
                <WorkflowFlowSteps steps={detail.flow_steps} initiatorName={detail.instance.initiator_name} />
                <h4 className="workflow-detail-subtitle">申请信息</h4>
                <dl className="workflow-kv">
                  {(detail.form_data || []).map((field) => (
                    <div key={field.label} className="workflow-kv-row">
                      <dt>{field.label}</dt>
                      <dd>{field.value}</dd>
                    </div>
                  ))}
                  {application?.flow_status ? (
                    <div className="workflow-kv-row">
                      <dt>申请状态</dt>
                      <dd>{application.flow_status}</dd>
                    </div>
                  ) : null}
                  {application?.project_url ? (
                    <div className="workflow-kv-row">
                      <dt>项目链接</dt>
                      <dd>
                        <a href={application.project_url} target="_blank" rel="noreferrer">
                          {application.project_url}
                        </a>
                      </dd>
                    </div>
                  ) : null}
                  {application?.process_message ? (
                    <div className="workflow-kv-row">
                      <dt>处理结果</dt>
                      <dd>{application.process_message}</dd>
                    </div>
                  ) : null}
                </dl>
                {showExecutionPanel ? (
                  <div className="workflow-agent-panel">
                    <div className="workflow-agent-head">
                      <h4 className="workflow-detail-subtitle">Agent 执行</h4>
                      {canExecute ? (
                        <button type="button" className="primary-btn" disabled={executing} onClick={() => runExecute()}>
                          {application?.flow_status === "失败" ? "重新执行" : "开始执行"}
                        </button>
                      ) : null}
                      {canResume ? (
                        <button type="button" className="primary-btn" disabled={executing} onClick={() => runExecute({ resume: true })}>
                          恢复连接
                        </button>
                      ) : null}
                      {isRunning ? <span className="wf-muted">执行中...</span> : null}
                    </div>
                    <p className="field-hint">
                      审批通过后，由申请人手动触发 Agent 创建项目。系统将自动选择 Skill、工作流模板和 MCP 工具；执行过程将按步骤输出。
                    </p>
                    {resolvedAgentMeta ? (
                      <>
                        <h5 className="workflow-agent-section-title">Agent 配置</h5>
                        <AgentInfoPanel meta={resolvedAgentMeta} />
                      </>
                    ) : null}
                    {executionContext || application?.execution_context ? (
                      <>
                        <h5 className="workflow-agent-section-title">执行资源</h5>
                        <ExecutionResourcesPanel context={executionContext || application?.execution_context} />
                      </>
                    ) : null}
                    {application?.flow_status === "失败" && application?.process_message ? (
                      <div className="banner error workflow-agent-error">{application.process_message}</div>
                    ) : null}
                    <textarea
                      ref={logRef}
                      className="workflow-agent-log"
                      readOnly
                      rows={14}
                      value={executionLog}
                      placeholder={
                        serverExecuting && !executionLog
                          ? "Agent 执行中，日志将自动刷新…"
                          : canExecute
                            ? "点击「开始执行」后，这里将显示 Agent 执行过程与结果"
                            : "暂无执行日志"
                      }
                    />
                    {agentMetaLine || resourcesMetaLine ? (
                      <div className="workflow-agent-meta">
                        {agentMetaLine ? <div>{agentMetaLine}</div> : null}
                        {resourcesMetaLine ? <div>{resourcesMetaLine}</div> : null}
                      </div>
                    ) : null}
                    <form className="workflow-agent-reply" onSubmit={runReply}>
                      <input
                        type="text"
                        value={userReply}
                        onChange={(e) => setUserReply(e.target.value)}
                        placeholder={
                          canReply
                            ? "Agent 等待确认，请输入回复（如：方案 1 / 调整服务名称）"
                            : logAwaiting && application?.flow_status === "已完成"
                              ? "执行已结束，如需继续请重新执行 Agent"
                              : logAwaiting && application?.flow_status === "执行中"
                                ? "执行连接已断开，请点击「恢复连接」或等待自动重连"
                                : executionPhase === "finished"
                                  ? "流程已结束，无法继续回复"
                                  : executing
                                    ? "Agent 执行中，请等待..."
                                    : "仅在 Agent 请求确认时可输入回复"
                        }
                        disabled={inputLocked}
                      />
                      <button type="submit" className="config-btn" disabled={!canReply || !userReply.trim()}>
                        发送
                      </button>
                    </form>
                    {application?.project_url ? (
                      <div className="workflow-agent-link">
                        <a className="primary-btn workflow-project-link" href={application.project_url} target="_blank" rel="noreferrer">
                          打开 Zadig 项目
                        </a>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            {detailTab === "records" ? (
              <div className="workflow-detail-section">
                <h4>审批记录</h4>
                <table className="workflow-records-table">
                  <thead>
                    <tr>
                      <th>节点名称</th>
                      <th>审批人</th>
                      <th>审批结果</th>
                      <th>审批时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.records || []).map((row) => (
                      <tr key={row.id || `${row.node_name}-${row.created_at}`}>
                        <td>{row.node_name}</td>
                        <td>{row.user_name || "-"}</td>
                        <td>
                          <span className="wf-record-action">{row.action_label}</span>
                          {row.comment ? <div className="wf-record-comment">{row.comment}</div> : null}
                        </td>
                        <td>
                          <div>{relativeTime(row.created_at)}</div>
                          <div className="wf-muted">{formatDateTime(row.created_at)}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            {detailTab === "comments" ? (
              <div className="workflow-detail-section">
                <h4>全文评论</h4>
                <div className="empty-panel">暂无评论</div>
              </div>
            ) : null}

            {detail.can_approve && !detail.is_readonly ? (
              <div className="workflow-action-bar">
                <textarea
                  rows={3}
                  placeholder="填写审批意见（可选）"
                  value={actionComment}
                  onChange={(e) => setActionComment(e.target.value)}
                />
                <div className="workflow-action-buttons">
                  <button type="button" className="btn-secondary" disabled={acting} onClick={() => runAction("reject")}>
                    驳回
                  </button>
                  <button type="button" className="wf-btn-approve" disabled={acting} onClick={() => runAction("approve")}>
                    审批通过
                  </button>
                </div>
              </div>
            ) : null}

            {detail.can_revoke ? (
              <div className="workflow-action-bar workflow-manage-bar">
                <button type="button" className="btn-secondary danger-link" disabled={acting} onClick={runRevoke}>
                  撤销申请
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
