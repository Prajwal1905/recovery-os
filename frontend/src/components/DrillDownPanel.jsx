import { useEffect, useState } from "react";

const API_BASE = "http://localhost:8000";
const API_KEY = "recovery-os-demo-key-2026";

export default function DrillDownPanel({ failureId, onClose }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [promiseDate, setPromiseDate] = useState("");
  const [recordingPromise, setRecordingPromise] = useState(false);
  const [promiseMsg, setPromiseMsg] = useState(null);

  const loadAudit = () => {
    if (!failureId) return;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/failures/${failureId}/audit`, {
      headers: { "X-API-Key": API_KEY },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load audit trail");
        return res.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setPromiseMsg(null);
    setPromiseDate("");
    loadAudit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [failureId]);

  const submitPromise = async () => {
    if (!promiseDate) return;
    setRecordingPromise(true);
    setPromiseMsg(null);
    try {
      const res = await fetch(`${API_BASE}/failures/${failureId}/promise`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
        body: JSON.stringify({ promised_date: promiseDate }),
      });
      if (!res.ok) throw new Error("Failed to record promise");
      setPromiseMsg("Promise recorded successfully.");
      loadAudit();
    } catch (e) {
      setPromiseMsg(`Error: ${e.message}`);
    } finally {
      setRecordingPromise(false);
    }
  };

  if (!failureId) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-lg overflow-y-auto bg-white shadow-2xl">
        <div className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <div>
            <h2 className="text-sm font-bold text-slate-900">Failure trace</h2>
            <p className="font-mono text-xs text-slate-400">{failureId}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-5">
          {loading && (
            <div className="py-10 text-center text-sm text-slate-400">
              Loading trace...
            </div>
          )}
          {error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}

          {data && (
            <>
              <div className="mb-6">
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  Current status
                </div>
                <span className="inline-block rounded-full bg-indigo-100 px-3 py-1 text-xs font-bold uppercase tracking-wide text-indigo-700">
                  {data.current_status}
                </span>
              </div>

              {/* Promise-to-pay panel */}
              <div className="mb-6 rounded-xl bg-amber-50 p-4 ring-1 ring-amber-200">
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-amber-700">
                  Promise-to-pay tracker
                </h3>
                <p className="mb-3 text-xs text-amber-800">
                  Record a customer commitment ("I'll pay by X"). The system
                  auto-detects broken promises and escalates.
                </p>
                <div className="flex gap-2">
                  <input
                    type="date"
                    value={promiseDate}
                    onChange={(e) => setPromiseDate(e.target.value)}
                    className="flex-1 rounded-lg border border-amber-300 px-3 py-2 text-sm"
                  />
                  <button
                    onClick={submitPromise}
                    disabled={recordingPromise || !promiseDate}
                    className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:bg-slate-300"
                  >
                    {recordingPromise ? "Saving..." : "Record"}
                  </button>
                </div>
                {promiseMsg && (
                  <p className="mt-2 text-xs text-amber-800">{promiseMsg}</p>
                )}
              </div>

              {data.actions_taken?.length > 0 && (
                <div className="mb-6">
                  <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
                    Actions taken
                  </h3>
                  <div className="space-y-2">
                    {data.actions_taken.map((a, i) => (
                      <div
                        key={i}
                        className="rounded-xl bg-slate-50 p-3 text-sm"
                      >
                        <div className="mb-1 flex items-center justify-between">
                          <span className="font-semibold text-slate-900">
                            {a.action_type}
                          </span>
                          <span className="text-xs text-slate-400">
                            {a.confidence != null
                              ? `${(a.confidence * 100).toFixed(0)}% confidence`
                              : ""}
                          </span>
                        </div>
                        {a.explanation && (
                          <p className="mb-1 text-xs leading-relaxed text-slate-600">
                            {a.explanation}
                          </p>
                        )}
                        <div className="flex gap-4 text-xs text-slate-400">
                          <span>
                            outcome:{" "}
                            <b className="text-slate-600">{a.outcome || "—"}</b>
                          </span>
                          {a.recovered_amount != null && (
                            <span>
                              recovered:{" "}
                              <b className="text-emerald-600">
                                ₹{a.recovered_amount}
                              </b>
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
                  Audit trail ({data.audit_trail?.length || 0} events)
                </h3>
                <div className="space-y-3 border-l-2 border-slate-200 pl-4">
                  {data.audit_trail?.map((e, i) => (
                    <div key={i} className="relative">
                      <div className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-indigo-500" />
                      <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
                        {e.event_type}
                      </div>
                      <div className="mb-1 text-[11px] text-slate-400">
                        {new Date(e.timestamp).toLocaleString()}
                      </div>
                      <pre className="whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 text-[11px] text-slate-600">
                        {JSON.stringify(e.payload, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
