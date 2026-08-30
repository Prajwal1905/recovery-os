import { useState, useMemo } from "react";

export default function CapacitySlider({ results, onCapacityChange }) {
  const maxCapacity = results.length;
  const [capacity, setCapacity] = useState(
    results.filter((r) => r.decision === "chase").length || Math.ceil(maxCapacity / 2)
  );

  const simulated = useMemo(() => {
    return results.map((r) => {
      const originallyChased = r.decision === "chase";
      const withinCapacity = r.rank <= capacity;
      const wouldChase = originallyChased && withinCapacity;
      return { ...r, simulatedDecision: wouldChase ? "chase" : "stop" };
    });
  }, [results, capacity]);

  const chasedCount = simulated.filter((r) => r.simulatedDecision === "chase").length;
  const expectedRecovery = simulated
    .filter((r) => r.simulatedDecision === "chase")
    .reduce((sum, r) => sum + (r.expected_recovery_value || 0), 0);

  const handleChange = (e) => {
    const val = Number(e.target.value);
    setCapacity(val);
    if (onCapacityChange) onCapacityChange(val, simulated);
  };

  return (
    <div className="mb-8 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900">Try it yourself: chase capacity</h3>
          <p className="text-xs text-slate-400">
            Drag to change how many cases the team can chase this batch — watch the portfolio re-triage live.
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-indigo-600">{capacity}</div>
          <div className="text-[11px] text-slate-400">capacity</div>
        </div>
      </div>

      <input
        type="range"
        min={1}
        max={maxCapacity}
        value={capacity}
        onChange={handleChange}
        className="w-full accent-indigo-600"
      />

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-emerald-50 p-3">
          <div className="text-[11px] font-semibold uppercase text-emerald-700">Now chasing</div>
          <div className="text-xl font-bold text-emerald-800">{chasedCount} cases</div>
        </div>
        <div className="rounded-xl bg-indigo-50 p-3">
          <div className="text-[11px] font-semibold uppercase text-indigo-700">Expected recovery</div>
          <div className="text-xl font-bold text-indigo-800">₹{expectedRecovery.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
        </div>
      </div>
    </div>
  );
}