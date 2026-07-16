/**
 * CsvProcessor.jsx
 * ----------------
 * Two-view CSV processing flow:
 *
 *   View 1 — Upload
 *     CSV file picker + prompt textarea + Submit button.
 *     On submit, calls POST /process-csv/ and transitions to View 2.
 *
 *   View 2 — Preview
 *     Paginated table of the processed output (first 50 rows from backend).
 *     Shows total row count and column names.
 *     Two actions:
 *       - Download  → GET /download-processed-csv/{task_id}
 *       - Refine    → show a new prompt textarea, submit to
 *                     POST /refine-csv/{task_id}, loop back to View 2
 *                     with the new task_id.
 *
 * Props:
 *   baseUrl  string  — API base URL (trailing slash will be stripped)
 *   onBack   fn      — called when the user wants to return to the main form
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

// Rows shown per page in the preview table
const PAGE_SIZE = 20;

// Polling interval in ms
const POLL_MS = 2500;

// ---------------------------------------------------------------------------
// Shared style tokens — keeps inline styles consistent throughout
// ---------------------------------------------------------------------------
const S = {
  page: {
    fontFamily:  "'DM Sans', 'Segoe UI', sans-serif",
    minHeight:   "100vh",
    background:  "#020617",
    color:       "#f1f5f9",
    padding:     "32px 24px",
  },
  card: {
    background:   "#0f172a",
    border:       "1px solid #1e293b",
    borderRadius: 12,
    padding:      "24px 28px",
    marginBottom: 24,
  },
  label: {
    display:      "block",
    fontSize:     "0.78rem",
    fontWeight:   700,
    color:        "#475569",
    letterSpacing:"0.07em",
    textTransform:"uppercase",
    marginBottom: 8,
  },
  input: {
    width:        "100%",
    background:   "#1e293b",
    border:       "1px solid #334155",
    borderRadius: 8,
    color:        "#f1f5f9",
    fontSize:     "0.9rem",
    padding:      "10px 14px",
    boxSizing:    "border-box",
    outline:      "none",
  },
  textarea: {
    width:        "100%",
    background:   "#1e293b",
    border:       "1px solid #334155",
    borderRadius: 8,
    color:        "#f1f5f9",
    fontSize:     "0.88rem",
    padding:      "10px 14px",
    lineHeight:   1.6,
    resize:       "vertical",
    minHeight:    120,
    boxSizing:    "border-box",
    outline:      "none",
  },
  btnPrimary: {
    background:   "linear-gradient(135deg, #0ea5e9, #6366f1)",
    border:       "none",
    borderRadius: 8,
    color:        "#fff",
    padding:      "10px 24px",
    fontWeight:   700,
    fontSize:     "0.9rem",
    cursor:       "pointer",
    letterSpacing:"0.02em",
  },
  btnSecondary: {
    background:   "none",
    border:       "1px solid #1e293b",
    borderRadius: 8,
    color:        "#94a3b8",
    padding:      "9px 20px",
    fontWeight:   600,
    fontSize:     "0.88rem",
    cursor:       "pointer",
  },
  btnDanger: {
    background:   "none",
    border:       "1px solid #450a0a",
    borderRadius: 6,
    color:        "#f87171",
    padding:      "6px 14px",
    fontSize:     "0.82rem",
    cursor:       "pointer",
  },
  error: {
    background:   "#ef444415",
    border:       "1px solid #ef444440",
    borderRadius: 8,
    padding:      "12px 16px",
    color:        "#fca5a5",
    fontSize:     "0.88rem",
    marginBottom: 16,
  },
  muted: { color: "#475569", fontSize: "0.82rem" },
};

// ---------------------------------------------------------------------------
// Sub-component: progress indicator shown while Gemini is processing
// ---------------------------------------------------------------------------
function ProcessingIndicator({ runtimeSec }) {
  return (
    <div style={{ textAlign: "center", padding: "40px 20px" }}>
      <div style={{
        width:  40, height: 40,
        borderRadius: "50%",
        border: "3px solid #1e293b",
        borderTop: "3px solid #0ea5e9",
        animation: "spin 0.9s linear infinite",
        margin: "0 auto 16px",
      }} />
      <p style={{ color: "#94a3b8", margin: 0, fontSize: "0.95rem" }}>
        Processing your CSV
        {runtimeSec > 0 && (
          <span style={S.muted}> — {runtimeSec}s elapsed</span>
        )}
      </p>
      <p style={{ ...S.muted, marginTop: 6 }}>
        This may take up to a minute for large files.
      </p>
      {/* CSS keyframe injected inline */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: paginated preview table
// ---------------------------------------------------------------------------
function PreviewTable({ columns, rows, totalRows }) {
  const [page, setPage] = useState(0);
  const pageCount = Math.ceil(rows.length / PAGE_SIZE);
  const pageRows  = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  if (!columns.length || !rows.length) {
    return (
      <p style={{ ...S.muted, textAlign: "center", padding: "20px 0" }}>
        No preview data available.
      </p>
    );
  }

  return (
    <div>
      {/* Row count summary */}
      <p style={{ ...S.muted, marginBottom: 12 }}>
        Showing{" "}
        <strong style={{ color: "#f1f5f9" }}>{rows.length}</strong> preview
        rows of{" "}
        <strong style={{ color: "#f1f5f9" }}>{totalRows}</strong> total
        {totalRows > rows.length && (
          <span> (download the CSV to see all rows)</span>
        )}
      </p>

      {/* Scrollable table */}
      <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid #1e293b" }}>
        <table style={{
          width:           "100%",
          borderCollapse: "collapse",
          fontSize:        "0.82rem",
          whiteSpace:      "nowrap",
        }}>
          <thead>
            <tr style={{ background: "#0d1b2e" }}>
              {columns.map((col) => (
                <th key={col} style={{
                  padding:    "10px 14px",
                  textAlign:  "left",
                  color:      "#94a3b8",
                  fontWeight: 700,
                  borderBottom: "1px solid #1e293b",
                  letterSpacing: "0.04em",
                }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr
                key={ri}
                style={{ background: ri % 2 === 0 ? "#0f172a" : "#0d1623" }}
              >
                {columns.map((col) => (
                  <td key={col} style={{
                    padding:     "9px 14px",
                    color:       "#cbd5e1",
                    borderBottom:"1px solid #1e293b",
                    maxWidth:    240,
                    overflow:    "hidden",
                    textOverflow:"ellipsis",
                  }}>
                    {String(row[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination controls */}
      {pageCount > 1 && (
        <div style={{
          display:        "flex",
          alignItems:     "center",
          justifyContent: "center",
          gap:            12,
          marginTop:      16,
        }}>
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{
              ...S.btnSecondary,
              opacity: page === 0 ? 0.4 : 1,
              cursor:  page === 0 ? "not-allowed" : "pointer",
            }}
          >
            Previous
          </button>
          <span style={S.muted}>
            Page {page + 1} of {pageCount}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page === pageCount - 1}
            style={{
              ...S.btnSecondary,
              opacity: page === pageCount - 1 ? 0.4 : 1,
              cursor:  page === pageCount - 1 ? "not-allowed" : "pointer",
            }}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function CsvProcessor({ baseUrl, onBack }) {
  const BASE = (baseUrl || "").replace(/\/+$/, "");

  // View state: "upload" | "processing" | "preview"
  const [view, setView] = useState("upload");

  // Upload form
  const [csvFile,    setCsvFile]    = useState(null);
  const [prompt,     setPrompt]     = useState("");
  const [submitError, setSubmitError] = useState(null);

  // Active task
  const [taskId,      setTaskId]      = useState(null);
  const [runtimeSec,  setRuntimeSec]  = useState(0);
  const [taskError,   setTaskError]   = useState(null);

  // Preview data (populated from polling response)
  const [columns,     setColumns]     = useState([]);
  const [previewRows, setPreviewRows] = useState([]);
  const [totalRows,   setTotalRows]   = useState(0);

  // Refinement form
  const [showRefine,    setShowRefine]    = useState(false);

  // Sessions list — loaded from backend and shown below the preview
  const [sessions,      setSessions]      = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [allCsvRows,    setAllCsvRows]    = useState([]);  // full row set for session creation
  const [refinePrompt,  setRefinePrompt]  = useState("");
  const [refineError,   setRefineError]   = useState(null);
  const [refineRunning, setRefineRunning] = useState(false);

  const fileInputRef = useRef(null);
  const pollRef      = useRef(null);

  // ---------------------------------------------------------------------------
  // Start polling a task ID
  // ---------------------------------------------------------------------------
  function startPolling(tid) {
    // Clear any existing poll
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const r = await axios.get(`${BASE}/process-csv-progress/${tid}`);
        const d = r.data;

        if (d.runtime_seconds !== undefined) setRuntimeSec(d.runtime_seconds);

        if (d.error) {
          setTaskError(d.error);
          setView("preview");   // show preview view with error banner
          clearInterval(pollRef.current);
          return;
        }

        if (d.ready) {
          setColumns(d.columns || []);
          setPreviewRows(d.preview_rows || []);
          setTotalRows(d.row_count || 0);
          setAllCsvRows(d.preview_rows || []);  // store for session creation
          setView("preview");
          loadSessions();   // refresh sessions list when new result is ready
          clearInterval(pollRef.current);
          return;
        }

        // Still running — keep polling
        if (!d.running && !d.ready && !d.error) {
          // Task stopped without a ready flag — surface a generic error
          setTaskError("Processing stopped unexpectedly. Please try again.");
          setView("preview");
          clearInterval(pollRef.current);
        }

      } catch (err) {
        console.error("[CsvProcessor] Poll error:", err.message);
        setTaskError("Lost connection to server while processing.");
        setView("preview");
        clearInterval(pollRef.current);
      }
    }, POLL_MS);
  }

  // Clean up poll on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Submit initial upload
  // ---------------------------------------------------------------------------
  // Load existing sessions from backend
  async function loadSessions() {
    setSessionsLoading(true);
    try {
      const r = await axios.get(`\${BASE}/sessions/`);
      setSessions(r.data?.sessions || []);
    } catch (err) {
      console.error("[CsvProcessor] Failed to load sessions:", err.message);
    } finally {
      setSessionsLoading(false);
    }
  }

  // Create a new session from current output and open it in a new tab
  async function handleNewSession() {
    if (!columns.length) return;
    setCreatingSession(true);
    try {
      const fd = new FormData();
      fd.append("source_task_id", taskId || "manual");
      fd.append("csv_columns", JSON.stringify(columns));
      fd.append("csv_rows", JSON.stringify(allCsvRows));
      const r = await axios.post(`\${BASE}/sessions/`, fd);
      const { session_id } = r.data;
      // Open in new tab at /session/{session_id}
      window.open(`/session/\${session_id}`, "_blank");
      // Refresh sessions list
      loadSessions();
    } catch (err) {
      const msg = err.response?.data?.error || err.message;
      console.error("[CsvProcessor] Failed to create session:", msg);
      alert(`Failed to create session: ${msg}`);
    } finally {
      setCreatingSession(false);
    }
  }

  // Load sessions on mount
  useEffect(() => { loadSessions(); }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitError(null);

    const file = fileInputRef.current?.files[0];
    if (!file) {
      setSubmitError("Please choose a CSV file.");
      return;
    }
    if (!prompt.trim()) {
      setSubmitError("Please enter a processing prompt.");
      return;
    }

    const formData = new FormData();
    formData.append("file",   file);
    formData.append("prompt", prompt.trim());

    try {
      const r = await axios.post(`${BASE}/process-csv/`, formData);
      const newTaskId = r.data.task_id;
      setTaskId(newTaskId);
      setTaskError(null);
      setView("processing");
      startPolling(newTaskId);
    } catch (err) {
      const msg = err.response?.data?.error || err.message;
      console.error("[CsvProcessor] Submit error:", msg);
      setSubmitError(`Failed to start processing: ${msg}`);
    }
  }

  // ---------------------------------------------------------------------------
  // Submit refinement prompt
  // ---------------------------------------------------------------------------
  async function handleRefine(e) {
    e.preventDefault();
    setRefineError(null);

    if (!refinePrompt.trim()) {
      setRefineError("Please enter a refinement prompt.");
      return;
    }

    setRefineRunning(true);

    const formData = new FormData();
    formData.append("prompt", refinePrompt.trim());

    try {
      const r = await axios.post(`${BASE}/refine-csv/${taskId}`, formData);
      const newTaskId = r.data.task_id;

      // Reset preview state and start polling the new task
      setTaskId(newTaskId);
      setTaskError(null);
      setColumns([]);
      setPreviewRows([]);
      setTotalRows(0);
      setShowRefine(false);
      setRefinePrompt("");
      setRefineRunning(false);
      setView("processing");
      startPolling(newTaskId);

    } catch (err) {
      const msg = err.response?.data?.error || err.message;
      console.error("[CsvProcessor] Refine error:", msg);
      setRefineError(`Refinement failed: ${msg}`);
      setRefineRunning(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Download the processed CSV
  // ---------------------------------------------------------------------------
  async function handleDownload() {
    if (!taskId) return;
    try {
      const r = await axios.get(
        `${BASE}/download-processed-csv/${taskId}`,
        { responseType: "blob" }
      );
      const url = URL.createObjectURL(new Blob([r.data], { type: "text/csv" }));
      const a   = document.createElement("a");
      a.href    = url;
      a.download = `processed_${taskId}.csv`;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error("[CsvProcessor] Download error:", err.message);
      alert("Download failed. Please try again.");
    }
  }

  // ---------------------------------------------------------------------------
  // Reset everything and go back to upload view
  // ---------------------------------------------------------------------------
  function handleStartOver() {
    if (pollRef.current) clearInterval(pollRef.current);
    setCsvFile(null);
    setPrompt("");
    setSubmitError(null);
    setTaskId(null);
    setRuntimeSec(0);
    setTaskError(null);
    setColumns([]);
    setPreviewRows([]);
    setTotalRows(0);
    setShowRefine(false);
    setRefinePrompt("");
    setRefineError(null);
    setRefineRunning(false);
    setView("upload");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  // ---------------------------------------------------------------------------
  // Shared header
  // ---------------------------------------------------------------------------
  function Header({ subtitle }) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 28 }}>
        <button onClick={onBack} style={S.btnSecondary}>
          Back
        </button>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.4rem", fontWeight: 700 }}>
            CSV Processor
          </h2>
          {subtitle && (
            <p style={{ margin: 0, ...S.muted }}>{subtitle}</p>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Upload view
  // ---------------------------------------------------------------------------
  if (view === "upload") {
    return (
      <div style={S.page}>
        <div style={{ maxWidth: 680, margin: "0 auto" }}>
          <Header subtitle="Upload a CSV and describe what to do with it." />

          {submitError && (
            <div style={S.error}>{submitError}</div>
          )}

          <div style={S.card}>
            <form onSubmit={handleSubmit}>

              {/* File picker */}
              <div style={{ marginBottom: 20 }}>
                <label style={S.label}>CSV File</label>
                <div style={{
                  border:       "2px dashed #1e293b",
                  borderRadius: 8,
                  padding:      "20px",
                  textAlign:    "center",
                  cursor:       "pointer",
                  background:   "#0d1117",
                }}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    type="file"
                    accept=".csv"
                    ref={fileInputRef}
                    style={{ display: "none" }}
                    onChange={(e) => setCsvFile(e.target.files[0] || null)}
                  />
                  {csvFile ? (
                    <span style={{ color: "#0ea5e9", fontWeight: 600 }}>
                      {csvFile.name}
                    </span>
                  ) : (
                    <span style={{ color: "#475569" }}>
                      Click to choose a CSV file
                    </span>
                  )}
                </div>
              </div>

              {/* Prompt */}
              <div style={{ marginBottom: 24 }}>
                <label style={S.label}>What should be done with this CSV?</label>
                <textarea
                  style={S.textarea}
                  rows={6}
                  placeholder={
                    "Describe what to do with the data.\n\n" +
                    "Examples:\n" +
                    "  Add a 'Full Name' column by combining First Name and Last Name\n" +
                    "  Remove all rows where Status is Inactive\n" +
                    "  Normalise all phone numbers to E.164 format"
                  }
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  required
                />
              </div>

              <button type="submit" style={S.btnPrimary}>
                Process CSV
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Processing view
  // ---------------------------------------------------------------------------
  if (view === "processing") {
    return (
      <div style={S.page}>
        <div style={{ maxWidth: 680, margin: "0 auto" }}>
          <Header subtitle="Processing your file..." />
          <div style={S.card}>
            <ProcessingIndicator runtimeSec={runtimeSec} />
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Preview view
  // ---------------------------------------------------------------------------
  return (
    <div style={S.page}>
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <Header subtitle="Review the processed data below." />

        {/* Error banner */}
        {taskError && (
          <div style={S.error}>
            Processing error: {taskError}
          </div>
        )}

        {/* Action toolbar */}
        {!taskError && (
          <div style={{
            display:        "flex",
            alignItems:     "center",
            gap:            12,
            marginBottom:   20,
            flexWrap:       "wrap",
          }}>
            <button onClick={handleDownload} style={S.btnPrimary}>
              Download CSV
            </button>
            <button
              onClick={() => {
                setShowRefine((v) => !v);
                setRefineError(null);
              }}
              style={S.btnSecondary}
            >
              {showRefine ? "Cancel Refinement" : "Refine with New Prompt"}
            </button>
            <button onClick={handleStartOver} style={S.btnSecondary}>
              Start Over
            </button>
            <button
              onClick={handleNewSession}
              disabled={creatingSession || !columns.length}
              style={{
                ...S.btnPrimary,
                opacity: creatingSession || !columns.length ? 0.6 : 1,
                cursor:  creatingSession || !columns.length ? "not-allowed" : "pointer",
              }}
            >
              {creatingSession ? "Creating..." : "Start a New Session"}
            </button>
          </div>
        )}

        {/* Reset button when there's an error */}
        {taskError && (
          <button onClick={handleStartOver} style={{ ...S.btnSecondary, marginBottom: 20 }}>
            Start Over
          </button>
        )}

        {/* Refinement form */}
        {showRefine && !taskError && (
          <div style={{ ...S.card, borderColor: "#0ea5e944" }}>
            <p style={{ margin: "0 0 12px", fontWeight: 600, fontSize: "0.95rem" }}>
              Describe how to further improve this output:
            </p>
            {refineError && (
              <div style={{ ...S.error, marginBottom: 12 }}>{refineError}</div>
            )}
            <form onSubmit={handleRefine}>
              <textarea
                style={{ ...S.textarea, marginBottom: 14 }}
                rows={4}
                placeholder={
                  "Example: Sort the results by last name alphabetically\n" +
                  "Example: Remove any rows where email is empty"
                }
                value={refinePrompt}
                onChange={(e) => setRefinePrompt(e.target.value)}
                required
                disabled={refineRunning}
              />
              <button
                type="submit"
                style={{
                  ...S.btnPrimary,
                  opacity: refineRunning ? 0.6 : 1,
                  cursor:  refineRunning ? "not-allowed" : "pointer",
                }}
                disabled={refineRunning}
              >
                {refineRunning ? "Submitting..." : "Apply Refinement"}
              </button>
            </form>
          </div>
        )}

        {/* Sessions list */}
        <div style={{ ...S.card, marginTop: 0 }}>
          <div style={{
            display:        "flex",
            alignItems:     "center",
            justifyContent: "space-between",
            marginBottom:   16,
          }}>
            <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700 }}>
              Sessions
            </h3>
            <button
              onClick={loadSessions}
              style={{
                background:   "none",
                border:       "1px solid #1e293b",
                borderRadius: 6,
                color:        "#64748b",
                padding:      "4px 12px",
                fontSize:     "0.78rem",
                cursor:       "pointer",
              }}
            >
              Refresh
            </button>
          </div>

          {sessionsLoading ? (
            <p style={{ color: "#475569", fontSize: "0.85rem" }}>Loading sessions...</p>
          ) : sessions.length === 0 ? (
            <p style={{ color: "#475569", fontSize: "0.85rem" }}>
              No sessions yet. Use "Start a New Session" after processing a CSV.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {sessions.map((s) => (
                <div key={s.session_id} style={{
                  background:   "#1e293b",
                  borderRadius: 8,
                  padding:      "12px 16px",
                  display:      "flex",
                  alignItems:   "center",
                  justifyContent:"space-between",
                  gap:          12,
                }}>
                  <div style={{ minWidth: 0 }}>
                    <p style={{
                      margin:       "0 0 3px",
                      fontWeight:   600,
                      fontSize:     "0.88rem",
                      overflow:     "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace:   "nowrap",
                    }}>
                      {s.title || "Untitled Session"}
                    </p>
                    <p style={{ margin: 0, color: "#475569", fontSize: "0.75rem" }}>
                      {s.row_count} rows · {s.message_count} messages ·{" "}
                      {s.created_at
                        ? new Date(s.created_at).toLocaleString()
                        : ""}
                    </p>
                  </div>
                  <button
                    onClick={() => window.open(`/session/\${s.session_id}`, "_blank")}
                    style={{
                      background:   "none",
                      border:       "1px solid #334155",
                      borderRadius: 6,
                      color:        "#94a3b8",
                      padding:      "5px 14px",
                      fontSize:     "0.8rem",
                      cursor:       "pointer",
                      flexShrink:   0,
                    }}
                  >
                    Open
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Preview table */}
        {!taskError && (
          <div style={S.card}>
            <PreviewTable
              columns={columns}
              rows={previewRows}
              totalRows={totalRows}
            />
          </div>
        )}

      </div>
    </div>
  );
}