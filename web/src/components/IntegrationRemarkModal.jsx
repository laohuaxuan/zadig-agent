import { useState } from "react";

export default function IntegrationRemarkModal({ open, title, initialRemark = "", saving = false, onClose, onSave }) {
  if (!open) return null;

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className="dialog integration-remark-dialog"
        role="dialog"
        aria-labelledby="integration-remark-title"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-head">
          <h2 id="integration-remark-title">{title}</h2>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <p className="integration-remark-hint">备注会在项目管理等页面的下拉选项中展示，帮助用户识别资源用途。</p>
        <IntegrationRemarkForm key={initialRemark} initialRemark={initialRemark} saving={saving} onClose={onClose} onSave={onSave} />
      </div>
    </div>
  );
}

function IntegrationRemarkForm({ initialRemark, saving, onClose, onSave }) {
  const [remark, setRemark] = useState(initialRemark);
  const trimmed = remark.trim();

  return (
    <>
      <div className="integration-remark-field">
        <label htmlFor="integration-remark-input">备注说明</label>
        <textarea
          id="integration-remark-input"
          rows={6}
          value={remark}
          onChange={(e) => setRemark(e.target.value)}
          placeholder="例如：前端 Monorepo、生产镜像仓库"
          maxLength={500}
        />
        <div className="integration-remark-meta">
          <span className="integration-remark-tip">建议 20 字以内，便于在下拉中快速识别</span>
          <span className="integration-remark-count">{remark.length}/500</span>
        </div>
      </div>
      <div className="dialog-actions">
        <button type="button" className="config-btn" onClick={onClose} disabled={saving}>
          取消
        </button>
        <button type="button" className="primary-btn" onClick={() => onSave(trimmed)} disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </button>
      </div>
    </>
  );
}
