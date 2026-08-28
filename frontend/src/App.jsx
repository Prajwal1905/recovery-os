import React, { useState, useEffect } from "react";
import axios from "axios";
import "./App.css";

const API_BASE = "http://localhost:8000";

function formatINR(amount) {
  if (amount === null || amount === undefined) return "-";
  return `₹${Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function App() {
  const [merchants, setMerchants] = useState([]);
  const [selectedPersona, setSelectedPersona] = useState("");
  const [batchLimit, setBatchLimit] = useState(30);
  const [chaseCapacity, setChaseCapacity] = useState(15);
  const [batchResult, setBatchResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedFailure, setSelectedFailure] = useState(null);
  const [auditData, setAuditData] = useState(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [showCounterfactual, setShowCounterfactual] = useState({});

  useEffect(() => {
    axios.get(`${API_BASE}/merchants`).then((res) => setMerchants(res.data)).catch(() => {});
  }, []);

  const runBatch = async () => {
    setLoading(true);
    setError(null);
    setBatchResult(null);
    try {
      const res = await axios.post(`${API_BASE}/batch/run`, {
        merchant_persona: selectedPersona || null,
        batch_limit: Number(batchLimit),
        chase_capacity: Number(chaseCapacity),
      });
      setBatchResult(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const openDrilldown = async (failureId) => {
    setSelectedFailure(failureId);
    setAuditLoading(true);
    setAuditData(null);
    try {
      const res = await axios.get(`${API_BASE}/failures/${failureId}/audit`);
      setAuditData(res.data);
    } catch (e) {
      setAuditData({ error: e.message });
    } finally {
      setAuditLoading(false);
    }
  };

  const toggleCounterfactual = (failureId) => {
    setShowCounterfactual((prev) => ({ ...prev, [failureId]: !prev[failureId] }));
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Recovery OS</h1>
        <p className="subtitle">AI Revenue Recovery Agent — portfolio triage, bounded actions, audit trail</p>
      </header>

      <section className="controls">
        <div className="control-group">
          <label>Merchant</label>
          <select value={selectedPersona} onChange={(e) => setSelectedPersona(e.target.value)}>
            <option value="">All merchants</option>
            {merchants.map((m) => (
              <option key={m.id} value={m.persona}>
                {m.name} ({m.persona}) — aggressiveness {m.stopping_aggressiveness}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>Batch size</label>
          <input
            type="number"
            value={batchLimit}
            min={5}
            max={200}
            onChange={(e) => setBatchLimit(e.target.value)}
          />
        </div>

        <div className="control-group slider-group">
          <label>
            Chase capacity: <strong>{chaseCapacity}</strong>
          </label>
          <input
            type="range"
            min={1}
            max={batchLimit}
            value={chaseCapacity}
            onChange={(e) => setChaseCapacity(e.target.value)}
          />
          <p className="hint">Drag to change how many cases get chased — re-run to see re-triage live.</p>
        </div>

        <button className="run-btn" onClick={runBatch} disabled={loading}>
          {loading ? "Running batch..." : "Run Batch"}
        </button>
      </section>

      {error && <div className="error-box">Error: {error}</div>}

      {batchResult && (
        <>
          <section className="summary-cards">
            <div className="card">
              <span className="card-label">Batch size</span>
              <span className="card-value">{batchResult.summary.batch_size}</span>
            </div>
            <div className="card">
              <span className="card-label">Total batch value</span>
              <span className="card-value">{formatINR(batchResult.summary.total_batch_value)}</span>
            </div>
            <div className="card chase">
              <span className="card-label">Chased</span>
              <span className="card-value">{batchResult.summary.chased_count}</span>
            </div>
            <div className="card stop">
              <span className="card-label">Stopped</span>
              <span className="card-value">{batchResult.summary.stopped_count}</span>
            </div>
            <div className="card">
              <span className="card-label">Expected recovery</span>
              <span className="card-value">{formatINR(batchResult.summary.total_expected_recovery)}</span>
            </div>
            <div className="card recovered">
              <span className="card-label">Simulated recovered</span>
              <span className="card-value">{formatINR(batchResult.summary.total_simulated_recovered)}</span>
            </div>
            <div className="card">
              <span className="card-label">Razorpay API calls</span>
              <span className="card-value">
                {batchResult.summary.api_calls_successful}/{batchResult.summary.api_calls_made}
              </span>
            </div>
          </section>

          <section className="results-table-wrap">
            <h2>Ranked Failures</h2>
            <table className="results-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Amount</th>
                  <th>Prob.</th>
                  <th>Score</th>
                  <th>Decision</th>
                  <th>Action</th>
                  <th>Explanation</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {batchResult.results.map((r) => (
                  <React.Fragment key={r.failure_id}>
                    <tr
                      className={r.decision === "chase" ? "row-chase" : "row-stop"}
                      onClick={() => openDrilldown(r.failure_id)}
                    >
                      <td>{r.rank}</td>
                      <td>{formatINR(r.amount)}</td>
                      <td>{r.probability_of_success}</td>
                      <td>{r.priority_score}</td>
                      <td>
                        <span className={`badge ${r.decision}`}>{r.decision}</span>
                      </td>
                      <td>{r.llm_action || r.likely_action || "-"}</td>
                      <td className="explanation-cell">
                        {r.llm_explanation || r.stop_reason || "-"}
                      </td>
                      <td>
                        {r.decision === "stop_chasing" && (
                          <button
                            className="cf-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleCounterfactual(r.failure_id);
                            }}
                          >
                            {showCounterfactual[r.failure_id] ? "Hide" : "What if we'd chased?"}
                          </button>
                        )}
                      </td>
                    </tr>
                    {showCounterfactual[r.failure_id] && (
                      <tr className="counterfactual-row">
                        <td colSpan={8}>
                          <div className="counterfactual-box">
                            <strong>Counterfactual (from retrieved precedent):</strong>{" "}
                            {r.top_precedent_summary || "No precedent available."}
                            <br />
                            <span className="cf-note">
                              This is the most similar past case retrieved by the RAG layer — its actual
                              outcome is what informed this stop/chase decision's expected value.
                            </span>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </section>

          <section className="exceptions-section">
            <h2>Exception List ({batchResult.summary.exception_count})</h2>
            <p className="hint">Cases the system chose not to recover — shown honestly, never hidden.</p>
            <ul className="exceptions-list">
              {batchResult.summary.exceptions.map((exc) => (
                <li key={exc.failure_id}>
                  <strong>{formatINR(exc.amount)}</strong> — {exc.reason}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      {selectedFailure && (
        <div className="drilldown-overlay" onClick={() => setSelectedFailure(null)}>
          <div className="drilldown-panel" onClick={(e) => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setSelectedFailure(null)}>
              ×
            </button>
            <h2>Audit Trail</h2>
            <p className="failure-id-label">Failure ID: {selectedFailure}</p>
            {auditLoading && <p>Loading...</p>}
            {auditData && !auditData.error && (
              <>
                <p>
                  Current status: <span className="badge">{auditData.current_status}</span>
                </p>
                <h3>Trail</h3>
                <ul className="audit-trail">
                  {auditData.audit_trail.map((entry, i) => (
                    <li key={i}>
                      <div className="audit-timestamp">{entry.timestamp}</div>
                      <div className="audit-event">{entry.event_type}</div>
                      <pre className="audit-payload">{JSON.stringify(entry.payload, null, 2)}</pre>
                    </li>
                  ))}
                </ul>
                <h3>Actions Taken</h3>
                <ul className="actions-list">
                  {auditData.actions_taken.map((a, i) => (
                    <li key={i}>
                      <strong>{a.action_type}</strong> — outcome: {a.outcome}
                      {a.recovered_amount ? ` — recovered ${formatINR(a.recovered_amount)}` : ""}
                      <br />
                      <span className="action-explanation">{a.explanation}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {auditData?.error && <p className="error-box">Error: {auditData.error}</p>}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;