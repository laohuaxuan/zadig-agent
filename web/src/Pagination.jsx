import { useEffect, useState } from "react";
import ScrollSelect from "./components/ScrollSelect.jsx";

export const PAGE_SIZES = [10, 20, 50, 100];

export function usePager(storageKey, defaultSize = 10) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(() => {
    const raw = Number(localStorage.getItem(storageKey));
    return PAGE_SIZES.includes(raw) ? raw : defaultSize;
  });
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const raw = Number(localStorage.getItem(storageKey));
    setPage(1);
    setPageSize(PAGE_SIZES.includes(raw) ? raw : defaultSize);
    setTotal(0);
  }, [storageKey, defaultSize]);

  useEffect(() => {
    const pages = Math.max(1, Math.ceil((total || 0) / pageSize) || 1);
    if (page > pages) setPage(pages);
  }, [page, pageSize, total]);

  function changePageSize(next) {
    const size = Number(next);
    localStorage.setItem(storageKey, String(size));
    setPageSize(size);
    setPage(1);
  }

  return { page, setPage, pageSize, setPageSize: changePageSize, total, setTotal };
}

export default function Pagination({ page, pageSize, total, onPageChange, onPageSizeChange }) {
  const pages = Math.max(1, Math.ceil((total || 0) / pageSize) || 1);
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);

  return (
    <div className="pager">
      <p className="total">
        共 {total} 条{total ? `，当前 ${from}-${to}` : ""}
      </p>
      <label className="pager-size">
        每页
        <ScrollSelect
          className="pager-size-select"
          optionCount={PAGE_SIZES.length}
          value={String(pageSize)}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </ScrollSelect>
        条
      </label>
      <div className="pager-nav">
        <button type="button" className="config-btn" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          上一页
        </button>
        <span>
          {page} / {pages}
        </span>
        <button type="button" className="config-btn" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
          下一页
        </button>
      </div>
    </div>
  );
}
