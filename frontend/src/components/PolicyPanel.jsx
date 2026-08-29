export default function PolicyPanel({ policy }) {
  const merchants = Object.values(policy || {});
  if (merchants.length === 0) return null;

  return (
    <div className="mb-8">
      <h3 className="mb-3 text-sm font-bold text-slate-900">Per-merchant learned policy</h3>
      <div className="space-y-2">
        {merchants.map((p, i) => (
          <div
            key={i}
            className="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-xl bg-white p-4 text-sm ring-1 ring-slate-200"
          >
            <span className="font-semibold text-slate-900">{p.merchant_name}</span>
            <Stat label="aggressiveness used" value={p.aggressiveness_used_this_batch} />
            <Stat
              label="reward"
              value={`${p.reward_this_batch >= 0 ? "+" : ""}${p.reward_this_batch}`}
              positive={p.reward_this_batch >= 0}
            />
            <Stat label="bandit's current best" value={p.bandit_summary.current_best_aggressiveness} />
            <Stat label="batches learned from" value={p.bandit_summary.total_batches_run} />
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value, positive }) {
  return (
    <span className="text-slate-500">
      {label}:{" "}
      <b className={positive === undefined ? "text-slate-900" : positive ? "text-emerald-600" : "text-rose-600"}>
        {value}
      </b>
    </span>
  );
}