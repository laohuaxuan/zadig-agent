/** 将单行描述按序号、分号等拆成多行，便于阅读；已有换行则原样返回。 */
export function normalizeDescription(text) {
  const raw = String(text || "").trim();
  if (!raw || raw.includes("\n")) return raw;

  let result = raw;
  // 冒号/分号后接序号列表
  result = result.replace(/([：:；;])\s*(?=\d+\.\s)/g, "$1\n");
  // 序号项之间换行
  result = result.replace(/(?<=\S)\s+(?=\d+\.\s)/g, "\n");
  // 行内 Markdown 小标题
  result = result.replace(/\s+(?=#{1,6}\s)/g, "\n");
  return result;
}
