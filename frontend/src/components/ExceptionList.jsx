export default function ExceptionList({ exceptions }) {
  if (!exceptions || exceptions.length === 0) return null;

  return (
    <div className="mb-8">
      <h3 className="mb-1 text-sm font-bold text-slate-900">
        Honest exception list ({exceptions.length})
      </h3>
      <p className="mb-3 text-xs text-slate-400">
        Cases we chose not to chase, and why.
      </p>
      <div className="overflow-hidden rounded-2xl bg-white ring-1 ring-slate-200">
        <ul>
          {exceptions.slice(0, 10).map((e, i) => (
            <li
              key={i}
              className="border-b border-slate-100 px-4 py-3 text-sm text-slate-600 last:border-none"
            >
              <span className="mr-2 font-semibold text-slate-900">
                ₹{e.amount.toLocaleString()}
              </span>
              {e.reason}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
