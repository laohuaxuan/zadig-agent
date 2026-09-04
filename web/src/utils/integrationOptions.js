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

export function registryOptionLabel(item) {
  const id = String(item?.registry_id || item?.id || "");
  const address = String(item?.address || "").trim();
  const namespace = String(item?.namespace || "").trim();
  const base = address && namespace ? `${namespace}/${address}` : address || namespace || id;
  return withAuxLabel(base || id, item?.remark);
}

export function serviceTemplateOptionLabel(item) {
  return withAuxLabel(item?.name, item?.remark);
}
