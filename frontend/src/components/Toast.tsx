import { useStore } from "@/store/useStore";

export function Toast() {
  const toast = useStore((s) => s.toast);
  const clearToast = useStore((s) => s.clearToast);
  if (!toast) return null;

  const color =
    toast.kind === "error"
      ? "border-severity-critical/40 bg-severity-critical/15 text-severity-critical"
      : toast.kind === "success"
        ? "border-severity-healthy/40 bg-severity-healthy/15 text-severity-healthy"
        : "border-severity-info/40 bg-severity-info/15 text-severity-info";

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center">
      <div
        className={`pointer-events-auto flex max-w-lg items-center gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg ${color}`}
      >
        <span className="flex-1">{toast.message}</span>
        <button onClick={clearToast} className="text-xs opacity-70 hover:opacity-100">
          Dismiss
        </button>
      </div>
    </div>
  );
}
