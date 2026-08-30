import { useState } from "react";
import BatchControls from "./components/BatchControls";
import MetricCard from "./components/MetricCard";
import PolicyPanel from "./components/PolicyPanel";
import RankedTable from "./components/RankedTable";
import ExceptionList from "./components/ExceptionList";
import DrillDownPanel from "./components/DrillDownPanel";
import CapacitySlider from "./components/CapacitySlider";

const API_BASE = "http://localhost:8000";

export default function App() {
  const [persona, setPersona] = useState("");
  const [batchLimit, setBatchLimit] = useState(30);
  const [chaseCapacity, setChaseCapacity] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [selectedFailureId, setSelectedFailureId] = useState(null);

  const runBatch = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/batch/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": "recovery-os-demo-key-2026",
        },
        body: JSON.stringify({
          merchant_persona: persona || null,
          batch_limit: Number(batchLimit),
          chase_capacity: chaseCapacity ? Number(chaseCapacity) : null,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Batch run failed");
      }
      const json = await res.json();
      setData(json);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const summary = data?.summary;
  const results = data?.results || [];
  const sortedResults = [...results].sort(
    (a, b) => (b.priority_score ?? -1e9) - (a.priority_score ?? -1e9),
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <div className="mb-8">
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">
            Recovery OS
          </h1>
          <p className="mt-1 max-w-xl text-sm leading-relaxed text-slate-500">
            AI-driven revenue recovery — portfolio triage, RAG-grounded
            reasoning, and a per-merchant learned policy that adapts chase
            aggressiveness automatically.
          </p>
        </div>

        <BatchControls
          persona={persona}
          setPersona={setPersona}
          batchLimit={batchLimit}
          setBatchLimit={setBatchLimit}
          chaseCapacity={chaseCapacity}
          setChaseCapacity={setChaseCapacity}
          onRun={runBatch}
          loading={loading}
        />

        {error && (
          <div className="mb-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            Error: {error}
          </div>
        )}

        {!summary && !loading && (
          <div className="rounded-2xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-400">
            Configure a batch above and click "Run Batch" to see results.
          </div>
        )}

        {summary && (
          <>
            <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetricCard label="Batch size" value={summary.batch_size} />
              <MetricCard label="Chased" value={summary.chased_count} />
              <MetricCard label="Stopped" value={summary.stopped_count} />
              <MetricCard
                label="Batch value"
                value={`₹${summary.total_batch_value.toLocaleString()}`}
              />
              <MetricCard
                label="Expected recovery"
                value={`₹${summary.total_expected_recovery.toLocaleString()}`}
              />
              <MetricCard
                label="Simulated recovered"
                value={`₹${summary.total_simulated_recovered.toLocaleString()}`}
                accent
              />
              <MetricCard
                label="Recovery rate"
                value={`${(summary.recovery_rate_of_chased_value * 100).toFixed(1)}%`}
              />
              <MetricCard
                label="Razorpay API calls"
                value={`${summary.api_calls_successful}/${summary.api_calls_made}`}
              />
            </div>

            <PolicyPanel policy={summary.policy} />
            <CapacitySlider results={sortedResults} />
            <RankedTable
              results={sortedResults}
              onSelectFailure={setSelectedFailureId}
            />
            <ExceptionList exceptions={summary.exceptions} />
          </>
        )}
      </div>

      <DrillDownPanel
        failureId={selectedFailureId}
        onClose={() => setSelectedFailureId(null)}
      />
    </div>
  );
}
