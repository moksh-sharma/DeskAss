import { useStore } from "@/store/useStore";

export function Toast() {
  const toast = useStore((s) => s.toast);
  const clearToast = useStore((s) => s.clearToast);
  if (!toast) return null;

  const color =
    toast.kind === "error"
      ? "border-red-200/70 bg-red-50/80 text-severity-critical"
      : toast.kind === "success"
        ? "border-emerald-200/70 bg-emerald-50/80 text-severity-healthy"
        : "border-sky-200/70 bg-sky-50/80 text-severity-info";

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center">
      <div
        className={`pointer-events-auto flex max-w-lg items-center gap-3 rounded-2xl border px-5 py-3.5 text-sm shadow-glass backdrop-blur-xl ${color}`}
      >
        <span className="flex-1 font-medium">{toast.message}</span>
        <button onClick={clearToast} className="text-xs font-bold uppercase tracking-wider opacity-60 hover:opacity-100">
          Dismiss
        </button>
      </div>
    </div>
  );
}
