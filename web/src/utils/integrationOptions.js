export function withAuxLabel(name, aux) {
  const text = String(name || "").trim();
  const note = String(aux || "").trim();
  if (!text) return note || "—";
  if (!note) return text;
  return `${text}（${note}）`;
}

export function codeSourceOptionLabel(item) {
  return withAuxLabel(item?.alias || item?.name, item?.remark);
}

export function clusterOptionLabel(item) {
  return withAuxLabel(item?.name, item?.description);
}

export function registryFullPath(item) {
  const id = String(item?.registry_id || item?.id || "");
  const address = String(item?.address || item?.url || "").trim().replace(/\/+$/, "");
  const namespace = String(item?.namespace || "").trim();
  if (address && namespace) return `${address}/${namespace}`;
  return address || namespace || id || "—";
}

export function registryOptionLabel(item) {
  return withAuxLabel(registryFullPath(item), item?.remark);
}

export function serviceTemplateOptionLabel(item) {
  return withAuxLabel(item?.name, item?.remark);
}
