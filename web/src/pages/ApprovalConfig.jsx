import { useCallback, useEffect, useState } from "react";
import {
  createApprovalTemplate,
  deleteApprovalTemplate,
  fetchApprovalTemplate,
  fetchApprovalTemplates,
  updateApprovalTemplate,
  warmupFeishuUsers,
} from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import FeishuAssigneePicker from "../components/FeishuAssigneePicker.jsx";
import ScrollSelect from "../components/ScrollSelect.jsx";
import { PanelLoading } from "../components/LoadingIndicator.jsx";

const WORKFLOW_SECTIONS = [
  {
    key: "create_project",
    workflowType: "Helm项目申请",
    label: "创建项目",
    description:
      "用户提交 Helm 项目创建申请后，按模板配置的多级审批链依次流转至各级审批人。",
    defaultName: "Helm 项目多级审批",
  },
  {
    key: "add_service",
    workflowType: "Helm添加服务申请",
    label: "添加新服务",
    description:
      "用户向已有 Helm 项目添加服务时，按模板配置的多级审批链依次流转至各级审批人。",
    defaultName: "Helm 添加服务多级审批",
  },
  {
    key: "add_workflow",
    workflowType: "Helm添加工作流申请",
    label: "添加工作流",
    description:
      "用户向已有 Helm 项目添加工作流时，按模板配置的多级审批链依次流转至各级审批人。",
    defaultName: "Helm 添加工作流多级审批",
  },
  {
    key: "add_environment",
    workflowType: "Helm添加环境申请",
    label: "添加新环境",
    description:
      "用户向已有 Helm 项目添加测试或生产环境时，按模板配置的多级审批链依次流转至各级审批人。",
    defaultName: "Helm 添加环境多级审批",
  },
];

const APPROVAL_MODE_LABEL = {
  any: "一人通过即可",
  all: "需要所有人通过",
};

function sectionByKey(key) {
  return WORKFLOW_SECTIONS.find((item) => item.key === key) || WORKFLOW_SECTIONS[0];
}

function emptyLevel(n) {
  return {
    level: n,
    name: `${n}级审批`,
    approval_mode: "any",
    assignee_ids: [],
    assignees: [],
    cc_user_ids: [],
    cc_users: [],
  };
}

function emptyForm(section = WORKFLOW_SECTIONS[0]) {
  return {
    name: section.defaultName,
    workflow_type: section.workflowType,
    enabled: true,
    is_default: true,
    levels: [emptyLevel(1)],
  };
}

function mapDetailToForm(data) {
  return {
    name: data.name,
    workflow_type: data.workflow_type,
    enabled: data.enabled,
    is_default: data.is_default,
    levels: (data.levels || []).map((lv) => ({
      level: lv.level,
      name: lv.name,
      approval_mode: lv.approval_mode || "any",
      assignee_ids: (lv.assignees || []).map((a) => a.user_id),
      assignees: lv.assignees || [],
      cc_user_ids: (lv.cc_users || []).map((a) => a.user_id),
      cc_users: lv.cc_users || [],
    })),
  };
}

function TemplateForm({
  editorMode,
  form,
  setForm,
  isEditable,
  canModify,
  saving,
  showMessage,
  onSubmit,
  onCancelEdit,
  onStartEdit,
  onClose,
  onDelete,
  updateLevel,
  addLevel,
  removeLevel,
}) {
  const section = WORKFLOW_SECTIONS.find((item) => item.workflowType === form.workflow_type);

  return (
    <form className={`approval-template-form${isEditable ? "" : " approval-template-form-readonly"}`} onSubmit={onSubmit}>
      <div className="approval-form-head">
        <h3 className="approval-form-title">
          {editorMode === "create" ? "新建模板" : editorMode === "edit" ? "编辑模板" : "模板详情"}
        </h3>
        <div className="approval-form-actions">
          {editorMode === "view" && canModify ? (
            <>
              <button type="button" className="btn-secondary" onClick={onStartEdit}>
                编辑
              </button>
              {onDelete ? (
                <button type="button" className="btn-secondary field-delete-btn" onClick={onDelete}>
                  删除
                </button>
              ) : null}
            </>
          ) : null}
          {editorMode === "edit" ? (
            <button type="button" className="btn-secondary" onClick={onCancelEdit}>
              取消
            </button>
          ) : null}
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
      </div>
      <div className="approval-template-meta">
        <label className="approval-field-full">
          适用场景
          <span className="approval-readonly-value">{section?.label || form.workflow_type}</span>
        </label>
        <label className="approval-field-full">
          模板名称
          {isEditable ? (
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          ) : (
            <span className="approval-readonly-value">{form.name}</span>
          )}
        </label>
        <div className="approval-template-flags">
          <label className="checkbox-row">
            <input
              type="checkbox"
              disabled={!isEditable}
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            />
            启用
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              disabled={!isEditable}
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
            />
            设为默认模板
          </label>
        </div>
      </div>
      <div className="approval-levels-head">
        <h3>审批层级</h3>
        {isEditable ? (
          <button type="button" className="btn-secondary" onClick={addLevel}>
            添加层级
          </button>
        ) : null}
      </div>
      {form.levels.map((lv, index) => (
        <div key={`level-${lv.level}-${index}`} className="approval-level-block">
          <div className="approval-level-title">
            <strong>第 {lv.level} 级</strong>
            {isEditable && form.levels.length > 1 ? (
              <button type="button" className="link-btn danger-link" onClick={() => removeLevel(index)}>
                删除
              </button>
            ) : null}
          </div>
          <div className="approval-level-fields">
            <label>
              节点名称
              {isEditable ? (
                <input type="text" value={lv.name} onChange={(e) => updateLevel(index, { name: e.target.value })} />
              ) : (
                <span className="approval-readonly-value">{lv.name}</span>
              )}
            </label>
            <label>
              审批方式
              {isEditable ? (
                <ScrollSelect
                  optionCount={2}
                  value={lv.approval_mode || "any"}
                  onChange={(e) => updateLevel(index, { approval_mode: e.target.value })}
                >
                  <option value="any">一人通过即可</option>
                  <option value="all">需要所有人通过</option>
                </ScrollSelect>
              ) : (
                <span className="approval-readonly-value">{APPROVAL_MODE_LABEL[lv.approval_mode] || lv.approval_mode}</span>
              )}
            </label>
            <label className="approval-field-full">
              审批人（飞书成员或本地账号，可多选）
              <FeishuAssigneePicker
                showMessage={showMessage}
                readOnly={!isEditable}
                value={lv.assignee_ids}
                initialUsers={lv.assignees}
                onChange={(ids) => updateLevel(index, { assignee_ids: ids })}
              />
            </label>
            <label className="approval-field-full">
              抄送（飞书成员或本地账号，可多选）
              <FeishuAssigneePicker
                showMessage={showMessage}
                readOnly={!isEditable}
                value={lv.cc_user_ids}
                initialUsers={lv.cc_users}
                onChange={(ids) => updateLevel(index, { cc_user_ids: ids })}
                variant="cc"
              />
            </label>
          </div>
        </div>
      ))}
      {isEditable ? (
        <div className="modal-actions">
          {editorMode === "create" ? (
            <button type="button" className="btn-secondary" onClick={onCancelEdit}>
              取消
            </button>
          ) : null}
          <button type="submit" disabled={saving}>
            {saving ? "保存中..." : "保存配置"}
          </button>
        </div>
      ) : null}
    </form>
  );
}

export default function ApprovalConfig() {
  const { permissions } = useAuth();
  const canModify = permissions.can_modify_approval_config;
  const [activeSectionKey, setActiveSectionKey] = useState(WORKFLOW_SECTIONS[0].key);
  const activeSection = sectionByKey(activeSectionKey);
  const [templates, setTemplates] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [editorMode, setEditorMode] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const isEditable = editorMode === "create" || editorMode === "edit";
  const modalOpen = editorMode !== null;

  const showMessage = useCallback((text, type = "success") => {
    if (type === "error") {
      setError(text);
      setMessage("");
    } else {
      setMessage(text);
      setError("");
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const data = await fetchApprovalTemplates(activeSection.workflowType);
      setTemplates(data.items || []);
    } finally {
      setTemplatesLoading(false);
    }
  }, [activeSection.workflowType]);

  useEffect(() => {
    loadTemplates().catch((err) => showMessage(err.message, "error"));
  }, [loadTemplates, showMessage]);

  useEffect(() => {
    warmupFeishuUsers().catch(() => {});
  }, []);

  function closeModal() {
    setEditorMode(null);
    setSelectedId(null);
    setForm(emptyForm(activeSection));
  }

  function switchSection(key) {
    if (key === activeSectionKey) return;
    closeModal();
    setActiveSectionKey(key);
    setError("");
    setMessage("");
  }

  async function loadDetail(id, mode = "view") {
    setDetailLoading(true);
    try {
      const data = await fetchApprovalTemplate(id);
      setSelectedId(id);
      setEditorMode(mode);
      setForm(mapDetailToForm(data.item));
    } finally {
      setDetailLoading(false);
    }
  }

  function startCreate() {
    setSelectedId(null);
    setEditorMode("create");
    setForm(emptyForm(activeSection));
  }

  function startEdit() {
    setEditorMode("edit");
  }

  async function cancelEdit() {
    if (editorMode === "edit" && selectedId) {
      await loadDetail(selectedId, "view");
      return;
    }
    closeModal();
  }

  function handleClose() {
    if (editorMode === "edit") {
      cancelEdit();
      return;
    }
    closeModal();
  }

  function handleOverlayClick() {
    if (editorMode === "create" || editorMode === "edit") return;
    closeModal();
  }

  function updateLevel(index, patch) {
    setForm((prev) => ({
      ...prev,
      levels: prev.levels.map((lv, i) => (i === index ? { ...lv, ...patch } : lv)),
    }));
  }

  function addLevel() {
    setForm((prev) => ({
      ...prev,
      levels: [...prev.levels, emptyLevel(prev.levels.length + 1)],
    }));
  }

  function removeLevel(index) {
    setForm((prev) => ({
      ...prev,
      levels: prev.levels
        .filter((_, i) => i !== index)
        .map((lv, i) => ({ ...lv, level: i + 1, name: lv.name || `${i + 1}级审批` })),
    }));
  }

  async function saveTemplate(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        workflow_type: form.workflow_type,
        enabled: form.enabled,
        is_default: form.is_default,
        levels: form.levels.map((lv) => ({
          level: lv.level,
          name: lv.name,
          approval_mode: lv.approval_mode || "any",
          assignee_ids: lv.assignee_ids.map(Number).filter(Boolean),
          cc_user_ids: lv.cc_user_ids.map(Number).filter(Boolean),
        })),
      };
      if (selectedId) {
        await updateApprovalTemplate(selectedId, payload);
        showMessage("审批模板已更新");
        await loadDetail(selectedId, "view");
      } else {
        const data = await createApprovalTemplate(payload);
        showMessage("审批模板已创建");
        await loadDetail(data.item.id, "view");
      }
      await loadTemplates();
    } catch (err) {
      showMessage(err.message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!selectedId || !window.confirm("确认删除该模板？")) return;
    try {
      await deleteApprovalTemplate(selectedId);
      showMessage("模板已删除");
      closeModal();
      await loadTemplates();
    } catch (err) {
      showMessage(err.message, "error");
    }
  }

  return (
    <section className="card approval-config-page">
      <div className="table-head">
        <h2>审批配置</h2>
        {canModify ? (
          <button type="button" className="btn-secondary" onClick={startCreate}>
            新建模板
          </button>
        ) : null}
      </div>
      <div className="approval-config-tabs" role="tablist" aria-label="审批场景">
        {WORKFLOW_SECTIONS.map((section) => (
          <button
            key={section.key}
            type="button"
            role="tab"
            aria-selected={section.key === activeSectionKey}
            className={section.key === activeSectionKey ? "approval-config-tab active" : "approval-config-tab"}
            onClick={() => switchSection(section.key)}
          >
            {section.label}
          </button>
        ))}
      </div>
      <p className="wf-muted approval-config-desc">{activeSection.description}</p>
      {error ? <div className="banner error">{error}</div> : null}
      {message ? <div className="banner success">{message}</div> : null}
      {templatesLoading ? (
        <PanelLoading label="加载审批模板..." />
      ) : templates.length === 0 ? (
        <div className="approval-template-cards-empty empty-panel">
          {canModify ? `暂无「${activeSection.label}」模板，请点击「新建模板」` : `暂无「${activeSection.label}」模板`}
        </div>
      ) : (
        <div className="approval-template-cards">
          {templates.map((tpl) => (
            <button key={tpl.id} type="button" className="approval-template-card" onClick={() => loadDetail(tpl.id, "view")}>
              <div className="approval-template-card-top">
                <strong className="approval-template-card-title">{tpl.name}</strong>
                <div className="approval-template-card-badges">
                  {tpl.is_default ? <span className="approval-template-badge default">默认</span> : null}
                  {!tpl.enabled ? <span className="approval-template-badge disabled">已停用</span> : null}
                </div>
              </div>
              <span className="approval-template-card-meta">{activeSection.label}</span>
              <span className="approval-template-card-hint">点击查看详情</span>
            </button>
          ))}
        </div>
      )}

      {modalOpen ? (
        <div className="modal-overlay" onClick={handleOverlayClick}>
          <div className="modal modal-wide approval-template-modal" onClick={(e) => e.stopPropagation()}>
            {detailLoading ? (
              <PanelLoading label="加载模板详情..." />
            ) : (
              <TemplateForm
                editorMode={editorMode}
                form={form}
                setForm={setForm}
                isEditable={canModify && isEditable}
                canModify={canModify}
                saving={saving}
                showMessage={showMessage}
                onSubmit={saveTemplate}
                onCancelEdit={cancelEdit}
                onStartEdit={startEdit}
                onClose={handleClose}
                onDelete={selectedId ? handleDelete : null}
                updateLevel={updateLevel}
                addLevel={addLevel}
                removeLevel={removeLevel}
              />
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
