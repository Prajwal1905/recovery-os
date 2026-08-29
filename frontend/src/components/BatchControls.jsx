export default function BatchControls({
  persona,
  setPersona,
  batchLimit,
  setBatchLimit,
  chaseCapacity,
  setChaseCapacity,
  onRun,
  loading,
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end gap-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <Field label="Merchant persona">
        <select
          value={persona}
          onChange={(e) => setPersona(e.target.value)}
          className="min-w-[220px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        >
          <option value="">All merchants</option>
          <option value="aggressive_d2c">UrbanCart D2C (aggressive)</option>
          <option value="relationship_b2b">
            LedgerFlow B2B SaaS (relationship)
          </option>
          <option value="neutral_midmarket">Kirana Konnect (neutral)</option>
        </select>
      </Field>
      <Field label="Batch size">
        <input
          type="number"
          value={batchLimit}
          onChange={(e) => setBatchLimit(e.target.value)}
          className="w-24 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
      </Field>
      <Field label="Chase capacity">
        <input
          type="number"
          value={chaseCapacity}
          onChange={(e) => setChaseCapacity(e.target.value)}
          className="w-24 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
      </Field>
      <button
        onClick={onRun}
        disabled={loading}
        className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {loading ? "Running..." : "Run Batch"}
      </button>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {label}
      </label>
      {children}
    </div>
  );
}
