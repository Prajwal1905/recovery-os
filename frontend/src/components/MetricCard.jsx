export default function MetricCard({ label, value, accent = false }) {
  return (
    <div
      className={
        accent
          ? "rounded-2xl bg-gradient-to-br from-indigo-600 to-indigo-700 p-5 shadow-sm"
          : "rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200"
      }
    >
      <div
        className={
          accent
            ? "text-xs font-semibold uppercase tracking-wide text-indigo-200"
            : "text-xs font-semibold uppercase tracking-wide text-slate-400"
        }
      >
        {label}
      </div>
      <div
        className={
          accent
            ? "mt-1 text-2xl font-bold text-white"
            : "mt-1 text-2xl font-bold text-slate-900"
        }
      >
        {value}
      </div>
    </div>
  );
}
