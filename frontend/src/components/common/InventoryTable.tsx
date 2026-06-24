import type { InventoryItem } from "@/types";

type Column = { key: keyof InventoryItem; label: string };

const DEFAULT_COLUMNS: Column[] = [
  { key: "name", label: "Name" },
  { key: "version", label: "Version" },
  { key: "category", label: "Class" },
  { key: "detail", label: "Manufacturer" },
];

export function InventoryTable({
  items,
  title,
  columns = DEFAULT_COLUMNS,
}: {
  items: InventoryItem[];
  title?: string;
  columns?: Column[];
}) {
  if (!items.length) return null;

  return (
    <div className="mt-3">
      {title && <p className="mb-2 text-xs font-semibold text-content-secondary">{title}</p>}
      <div className="max-h-80 overflow-auto rounded-xl border border-white/55 bg-white/40 backdrop-blur-sm">
        <table className="w-full min-w-[32rem] border-collapse text-left text-xs">
          <thead className="sticky top-0 z-10 border-b border-white/60 bg-white/80 backdrop-blur-sm">
            <tr>
              {columns.map((col) => (
                <th key={col.key} className="px-3 py-2 font-bold text-content-muted">
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((row, i) => (
              <tr
                key={`${row.name}-${i}`}
                className="border-b border-white/35 transition-colors hover:bg-white/50"
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={
                      col.key === "name"
                        ? "px-3 py-2 font-medium text-content-primary"
                        : "px-3 py-2 text-content-secondary"
                    }
                  >
                    {row[col.key] || "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-content-muted">{items.length} item(s)</p>
    </div>
  );
}
