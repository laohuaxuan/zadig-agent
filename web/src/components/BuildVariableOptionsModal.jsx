import { useMemo, useState } from "react";

function normalizeOptionRows(options) {
  const rows = (options || []).map((item) => String(item ?? "").trim());
  return rows.length ? rows : [""];
}

export default function BuildVariableOptionsModal({
  open,
  type = "choice",
  initialKey = "",
  initialOptions = [],
  initialDescription = "",
  onClose,
  onConfirm,
}) {
  if (!open) return null;

  const typeLabel = type === "multi-select" ? "多选" : "单选";

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className="dialog build-var-options-dialog"
        role="dialog"
        aria-labelledby="build-var-options-title"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="dialog-head">
          <h2 id="build-var-options-title">{typeLabel}</h2>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <BuildVariableOptionsForm
          key={`${type}-${initialKey}-${initialOptions.join("|")}-${initialDescription}`}
          typeLabel={typeLabel}
          initialKey={initialKey}
          initialOptions={initialOptions}
          initialDescription={initialDescription}
          onClose={onClose}
          onConfirm={onConfirm}
        />
      </div>
    </div>
  );
}

function BuildVariableOptionsForm({
  typeLabel,
  initialKey,
  initialOptions,
  initialDescription,
  onClose,
  onConfirm,
}) {
  const [key, setKey] = useState(initialKey);
  const [description, setDescription] = useState(initialDescription);
  const [optionRows, setOptionRows] = useState(() => normalizeOptionRows(initialOptions));

  const canAddOption = useMemo(
    () => optionRows.length > 0 && optionRows.every((item) => item.trim()),
    [optionRows],
  );

  const filledOptions = useMemo(
    () => optionRows.map((item) => item.trim()).filter(Boolean),
    [optionRows],
  );

  const canConfirm = Boolean(key.trim()) && optionRows.length > 0 && optionRows.every((item) => item.trim());

  function updateOption(index, value) {
    setOptionRows((current) => current.map((item, i) => (i === index ? value : item)));
  }

  function removeOption(index) {
    setOptionRows((current) => {
      if (current.length <= 1) return [""];
      return current.filter((_, i) => i !== index);
    });
  }

  function addOption() {
    if (!canAddOption) return;
    setOptionRows((current) => [...current, ""]);
  }

  function handleConfirm() {
    if (!canConfirm) return;
    onConfirm?.({
      key: key.trim(),
      options: filledOptions,
      description: description.trim(),
    });
  }

  return (
    <>
      <div className="build-var-options-field">
        <label htmlFor="build-var-options-key">变量名称</label>
        <input
          id="build-var-options-key"
          value={key}
          onChange={(event) => setKey(event.target.value)}
          placeholder={`${typeLabel}变量名称`}
        />
      </div>

      <div className="build-var-options-field">
        <label>可选值</label>
        <div className="build-var-option-list">
          {optionRows.map((item, index) => (
            <div className="build-var-option-row" key={`option-${index}`}>
              <input
                value={item}
                onChange={(event) => updateOption(index, event.target.value)}
                placeholder="请输入可选值"
              />
              <button
                type="button"
                className="build-var-option-remove"
                aria-label="删除可选值"
                onClick={() => removeOption(index)}
              >
                −
              </button>
            </div>
          ))}
        </div>
        <button type="button" className="build-var-option-add" disabled={!canAddOption} onClick={addOption}>
          + 新建可选值
        </button>
      </div>

      <div className="build-var-options-field">
        <label htmlFor="build-var-options-description">描述</label>
        <textarea
          id="build-var-options-description"
          rows={4}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="变量描述"
        />
      </div>

      <div className="dialog-actions">
        <button type="button" className="config-btn" onClick={onClose}>
          取消
        </button>
        <button type="button" className="primary-btn" disabled={!canConfirm} onClick={handleConfirm}>
          确定
        </button>
      </div>
    </>
  );
}
