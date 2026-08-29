export default function RankedTable({ results, onSelectFailure }) {
  if (results.length === 0) return null;

  return (
    <div className="mb-8">
      <h3 className="mb-3 text-sm font-bold text-slate-900">
        Ranked failures ({results.length})
      </h3>
      <p className="mb-2 text-xs text-slate-400">
        Click any row to see its full precedent + audit trail.
      </p>
      <div className="overflow-hidden rounded-2xl bg-white ring-1 ring-slate-200">
        <div className="max-h-[520px] overflow-y-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 bg-slate-50">
              <tr>
                {[
                  "#",
                  "Decision",
                  "Amount",
                  "Prob",
                  "Priority",
                  "Action",
                  "Reason / Explanation",
                ].map((h) => (
                  <th
                    key={h}
                    className="border-b border-slate-200 px-4 py-3 text-left text-[11px] font-bold uppercase tracking-wide text-slate-400"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {results.map((r) => {
                const wasChased = r.decision === "chase";
                const finalAction = wasChased
                  ? r.llm_action || r.likely_action
                  : "stop_chasing";
                const isChase = wasChased && finalAction !== "stop_chasing";
                return (
                  <tr
                    key={r.failure_id}
                    onClick={() => onSelectFailure(r.failure_id)}
                    className={
                      isChase
                        ? "cursor-pointer border-b border-slate-100 bg-emerald-50/40 hover:bg-emerald-100/60"
                        : "cursor-pointer border-b border-slate-100 hover:bg-slate-100"
                    }
                  >
                    <td className="px-4 py-3 text-slate-500">{r.rank}</td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          isChase
                            ? "inline-block rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-emerald-700"
                            : "inline-block rounded-full bg-rose-100 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-rose-700"
                        }
                      >
                        {isChase ? "Chase" : "Stop"}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-900">
                      ₹{r.amount.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-slate-700">
                      {(r.probability_of_success * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-3 text-slate-700">
                      {r.priority_score}
                    </td>
                    <td className="px-4 py-3 text-slate-700">{finalAction}</td>
                    <td className="max-w-[380px] px-4 py-3 text-xs leading-relaxed text-slate-500">
                      {r.llm_explanation || r.stop_reason}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
