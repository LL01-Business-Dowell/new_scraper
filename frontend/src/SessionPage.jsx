/**
 * SessionPage.jsx
 * ---------------
 * Chat interface for a single CSV session opened in a new tab.
 *
 * Features:
 *   - File upload on any message (CSV, XLSX, PDF, DOCX, TXT)
 *   - Per-message download buttons:
 *       "Download as DOCX" for text/report responses
 *       "Download as CSV"  for data transformation responses
 *       Both buttons when output_type is "both"
 *   - Live CSV table updates when AI transforms the data
 *   - Full message history persisted via backend (CRUD/Datacube)
 *   - Ctrl+Enter to send
 *
 * Props:
 *   sessionId  string  — from URL param
 *   baseUrl    string  — API base URL
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

const PAGE_SIZE = 20;

// Accepted file extensions for upload
const ACCEPTED_EXTENSIONS = ".csv,.xlsx,.xls,.pdf,.docx,.txt";

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const S = {
  page: {
    fontFamily:   "'DM Sans', 'Segoe UI', sans-serif",
    minHeight:    "100vh",
    background:   "#020617",
    color:        "#f1f5f9",
    display:      "flex",
    flexDirection:"column",
  },
  header: {
    background:   "#0f172a",
    borderBottom: "1px solid #1e293b",
    padding:      "14px 24px",
    display:      "flex",
    alignItems:   "center",
    gap:          16,
    flexShrink:   0,
  },
  body: {
    display:   "flex",
    flex:      1,
    overflow:  "hidden",
    minHeight: 0,
  },
  chatPanel: {
    width:        400,
    flexShrink:   0,
    borderRight:  "1px solid #1e293b",
    display:      "flex",
    flexDirection:"column",
    background:   "#0a1628",
    minHeight:    0,
  },
  tablePanel: {
    flex:       1,
    overflowY:  "auto",
    padding:    "20px 24px",
    background: "#020617",
  },
  muted: { color: "#475569", fontSize: "0.8rem" },
  error: {
    background:   "#ef444415",
    border:       "1px solid #ef444440",
    borderRadius: 8,
    padding:      "10px 14px",
    color:        "#fca5a5",
    fontSize:     "0.83rem",
    margin:       "8px 14px",
  },
  btnSmall: {
    background:   "none",
    border:       "1px solid #1e293b",
    borderRadius: 6,
    color:        "#94a3b8",
    padding:      "4px 10px",
    fontSize:     "0.72rem",
    fontWeight:   600,
    cursor:       "pointer",
    letterSpacing:"0.03em",
  },
};

// ---------------------------------------------------------------------------
// CSV download helper (client-side)
// ---------------------------------------------------------------------------
function downloadCsvFromRows(columns, rows, sessionId) {
  const escape  = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const header  = columns.join(",");
  const rowsStr = rows.map((r) => columns.map((c) => escape(r[c])).join(","));
  const csv     = [header, ...rowsStr].join("\n");
  const blob    = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url     = URL.createObjectURL(blob);
  const a       = document.createElement("a");
  a.href        = url;
  a.download    = `session_${sessionId.slice(0, 8)}_data.csv`;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

// ---------------------------------------------------------------------------
// Sub-component: message bubble
// ---------------------------------------------------------------------------
function MessageBubble({ msg, msgIndex, sessionId, baseUrl, csvColumns, csvRows }) {
  const BASE    = (baseUrl || "").replace(/\/+$/, "");
  const isUser  = msg.role === "user";
  const outType = msg.output_type || "text";

  // Download DOCX from backend
  async function handleDocxDownload() {
    try {
      const resp = await axios.get(
        `${BASE}/sessions/${sessionId}/download-docx/${msgIndex}`,
        { responseType: "blob" }
      );
      const url  = URL.createObjectURL(
        new Blob([resp.data], {
          type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        })
      );
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `report_${sessionId.slice(0, 8)}_msg${msgIndex}.docx`;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error("DOCX download failed:", err.message);
      alert("Failed to download DOCX. Please try again.");
    }
  }

  return (
    <div style={{
      display:       "flex",
      flexDirection: isUser ? "row-reverse" : "row",
      gap:           8,
      marginBottom:  14,
      padding:       "0 14px",
    }}>
      {/* Avatar */}
      <div style={{
        width:          26,
        height:         26,
        borderRadius:   "50%",
        background:     isUser ? "#6366f1" : "#0ea5e9",
        display:        "flex",
        alignItems:     "center",
        justifyContent: "center",
        fontSize:       "0.68rem",
        fontWeight:     700,
        flexShrink:     0,
        color:          "#fff",
        alignSelf:      "flex-start",
        marginTop:      3,
      }}>
        {isUser ? "U" : "AI"}
      </div>

      {/* Bubble */}
      <div style={{
        maxWidth:     "82%",
        background:   isUser ? "#1e1b4b" : "#0f172a",
        border:       `1px solid ${isUser ? "#4338ca44" : "#1e293b"}`,
        borderRadius: isUser ? "12px 2px 12px 12px" : "2px 12px 12px 12px",
        padding:      "10px 13px",
        fontSize:     "0.84rem",
        lineHeight:   1.65,
        color:        "#e2e8f0",
      }}>

        {/* Attached file badge */}
        {msg.attached_filename && (
          <div style={{
            fontSize:     "0.72rem",
            color:        "#f59e0b",
            marginBottom: 6,
            fontWeight:   600,
          }}>
            Attached: {msg.attached_filename}
          </div>
        )}

        {/* Message text — preserve whitespace for reports */}
        <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          {msg.content}
        </div>

        {/* Download buttons for assistant messages */}
        {!isUser && (outType === "text" || outType === "both") && (
          <button
            onClick={handleDocxDownload}
            style={{ ...S.btnSmall, marginTop: 10, marginRight: 6 }}
          >
            Download as DOCX
          </button>
        )}
        {!isUser && (outType === "csv" || outType === "both") && msg.csv_updated && (
          <button
            onClick={() => downloadCsvFromRows(csvColumns, csvRows, sessionId)}
            style={{ ...S.btnSmall, marginTop: 10 }}
          >
            Download as CSV
          </button>
        )}

        {/* CSV updated badge */}
        {msg.csv_updated && (
          <div style={{
            fontSize:   "0.7rem",
            color:      "#4ade80",
            fontWeight: 600,
            marginTop:  8,
          }}>
            Table updated
          </div>
        )}

        {/* Error notice */}
        {msg.error && (
          <div style={{ fontSize: "0.72rem", color: "#f87171", marginTop: 6 }}>
            {msg.error}
          </div>
        )}

        {/* Timestamp */}
        <div style={{
          ...S.muted,
          fontSize:  "0.67rem",
          marginTop: 6,
          textAlign: isUser ? "right" : "left",
        }}>
          {msg.timestamp
            ? new Date(msg.timestamp).toLocaleTimeString([], {
                hour: "2-digit", minute: "2-digit",
              })
            : ""}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: paginated CSV table
// ---------------------------------------------------------------------------
function CsvTable({ columns, rows }) {
  const [page, setPage] = useState(0);
  useEffect(() => { setPage(0); }, [rows]);

  if (!columns.length) {
    return (
      <p style={{ ...S.muted, textAlign: "center", padding: "40px 0" }}>
        No CSV data in this session yet.
      </p>
    );
  }

  const pageCount = Math.ceil(rows.length / PAGE_SIZE);
  const pageRows  = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div>
      <p style={{ ...S.muted, marginBottom: 12 }}>
        <strong style={{ color: "#f1f5f9" }}>{rows.length}</strong> rows &middot;{" "}
        {columns.length} columns
      </p>

      <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid #1e293b", marginBottom: 12 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.79rem", whiteSpace: "nowrap" }}>
          <thead>
            <tr style={{ background: "#0d1b2e" }}>
              {columns.map((col) => (
                <th key={col} style={{
                  padding: "9px 13px", textAlign: "left",
                  color: "#94a3b8", fontWeight: 700,
                  borderBottom: "1px solid #1e293b",
                  fontSize: "0.73rem", textTransform: "uppercase", letterSpacing: "0.04em",
                }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr key={ri} style={{ background: ri % 2 === 0 ? "#0f172a" : "#0d1623" }}>
                {columns.map((col) => (
                  <td key={col} style={{
                    padding: "8px 13px", color: "#cbd5e1",
                    borderBottom: "1px solid #1e293b",
                    maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis",
                  }}>
                    {String(row[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12 }}>
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{ ...S.btnSmall, opacity: page === 0 ? 0.35 : 1, cursor: page === 0 ? "not-allowed" : "pointer" }}
          >
            Previous
          </button>
          <span style={S.muted}>{page + 1} / {pageCount}</span>
          <button
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page === pageCount - 1}
            style={{ ...S.btnSmall, opacity: page === pageCount - 1 ? 0.35 : 1, cursor: page === pageCount - 1 ? "not-allowed" : "pointer" }}
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
export default function SessionPage({ sessionId, baseUrl }) {
  const BASE = (baseUrl || "").replace(/\/+$/, "");

  const [loading,    setLoading]    = useState(true);
  const [loadError,  setLoadError]  = useState(null);
  const [title,      setTitle]      = useState("Session");
  const [messages,   setMessages]   = useState([]);
  const [csvColumns, setCsvColumns] = useState([]);
  const [csvRows,    setCsvRows]    = useState([]);

  // Input state
  const [prompt,     setPrompt]     = useState("");
  const [attachedFile, setAttachedFile] = useState(null);  // File object
  const [sending,    setSending]    = useState(false);
  const [sendError,  setSendError]  = useState(null);

  const messagesEndRef = useRef(null);
  const fileInputRef   = useRef(null);

  // ---------------------------------------------------------------------------
  // Load session
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!sessionId) { setLoadError("No session ID."); setLoading(false); return; }
    loadSession();
    // eslint-disable-next-line
  }, [sessionId]);

  async function loadSession() {
    setLoading(true);
    setLoadError(null);
    try {
      const r = await axios.get(`${BASE}/sessions/${sessionId}`);
      const d = r.data;
      setTitle(d.title || "Session");
      setMessages(d.messages || []);
      setCsvColumns(d.csv_columns || []);
      setCsvRows(d.csv_rows || []);
    } catch (err) {
      setLoadError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  }

  // Scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ---------------------------------------------------------------------------
  // Send message
  // ---------------------------------------------------------------------------
  async function handleSend(e) {
    e.preventDefault();
    if (!prompt.trim() || sending) return;

    setSendError(null);
    setSending(true);

    // Optimistic user message
    const optimistic = {
      role:              "user",
      content:           prompt.trim(),
      timestamp:         new Date().toISOString(),
      attached_filename: attachedFile?.name || null,
    };
    setMessages((prev) => [...prev, optimistic]);
    const sentPrompt = prompt.trim();
    const sentFile   = attachedFile;
    setPrompt("");
    setAttachedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";

    try {
      // Use FormData so the file can be included
      const formData = new FormData();
      formData.append("prompt", sentPrompt);
      if (sentFile) formData.append("file", sentFile);

      const r = await axios.post(
        `${BASE}/sessions/${sessionId}/message`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      const d = r.data;

      // Replace optimistic entry with confirmed messages
      setMessages((prev) => [
        ...prev.slice(0, -1),
        d.user_message,
        d.assistant_message,
      ]);

      // Update CSV table if data changed
      if (d.csv_updated && d.csv_rows?.length) {
        setCsvColumns(d.csv_columns || csvColumns);
        setCsvRows(d.csv_rows);
      }

      if (d.error) setSendError(d.error);

    } catch (err) {
      const msg = err.response?.data?.error || err.message;
      setSendError(`Failed to send: ${msg}`);
      // Remove optimistic message and restore prompt
      setMessages((prev) => prev.slice(0, -1));
      setPrompt(sentPrompt);
      setAttachedFile(sentFile);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") handleSend(e);
  }

  // ---------------------------------------------------------------------------
  // Download current CSV state
  // ---------------------------------------------------------------------------
  function handleDownloadCsv() {
    if (!csvRows.length || !csvColumns.length) return;
    downloadCsvFromRows(csvColumns, csvRows, sessionId);
  }

  // ---------------------------------------------------------------------------
  // Loading / error screens
  // ---------------------------------------------------------------------------
  if (loading) {
    return (
      <div style={{ ...S.page, alignItems: "center", justifyContent: "center" }}>
        <div style={{
          width: 36, height: 36, borderRadius: "50%",
          border: "3px solid #1e293b", borderTop: "3px solid #0ea5e9",
          animation: "spin 0.9s linear infinite",
        }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <p style={{ ...S.muted, marginTop: 16 }}>Loading session...</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div style={{ ...S.page, alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div style={{ ...S.error, maxWidth: 480, textAlign: "center" }}>{loadError}</div>
        <button
          onClick={loadSession}
          style={{ marginTop: 14, ...S.btnSmall, padding: "8px 20px" }}
        >
          Retry
        </button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------
  return (
    <div style={S.page}>

      {/* Header */}
      <div style={S.header}>
        <div style={{
          width: 30, height: 30, borderRadius: 8, flexShrink: 0,
          background: "linear-gradient(135deg, #0ea5e9, #6366f1)",
        }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 style={{
            margin: 0, fontSize: "1rem", fontWeight: 700,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {title}
          </h2>
          <p style={{ ...S.muted, margin: 0 }}>
            {csvRows.length} rows &middot; {Math.floor(messages.length / 2)} exchanges
          </p>
        </div>
        <button
          onClick={handleDownloadCsv}
          disabled={!csvRows.length}
          style={{
            ...S.btnSmall,
            padding: "7px 16px",
            opacity: csvRows.length ? 1 : 0.4,
            cursor:  csvRows.length ? "pointer" : "not-allowed",
          }}
        >
          Download CSV
        </button>
      </div>

      {/* Body */}
      <div style={S.body}>

        {/* Left: chat */}
        <div style={S.chatPanel}>

          {/* Message thread */}
          <div style={{ flex: 1, overflowY: "auto", paddingTop: 14 }}>
            {messages.length === 0 && (
              <p style={{ ...S.muted, textAlign: "center", padding: "36px 16px" }}>
                Send a prompt or upload a file to begin.
                The table on the right shows the current CSV state.
              </p>
            )}

            {messages.map((msg, i) => (
              <MessageBubble
                key={i}
                msg={msg}
                msgIndex={i}
                sessionId={sessionId}
                baseUrl={BASE}
                csvColumns={csvColumns}
                csvRows={csvRows}
              />
            ))}

            {/* Sending indicator */}
            {sending && (
              <div style={{ padding: "0 14px 14px", display: "flex", gap: 5, alignItems: "center" }}>
                {[0, 1, 2].map((i) => (
                  <div key={i} style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: "#0ea5e9",
                    animation: `bounce 1s ${i * 0.2}s infinite`,
                  }} />
                ))}
                <style>{`
                  @keyframes bounce {
                    0%, 100% { transform: translateY(0); opacity: 0.4; }
                    50%       { transform: translateY(-4px); opacity: 1; }
                  }
                `}</style>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Send error */}
          {sendError && <div style={S.error}>{sendError}</div>}

          {/* Input area */}
          <form
            onSubmit={handleSend}
            style={{ borderTop: "1px solid #1e293b", padding: "12px 14px", flexShrink: 0 }}
          >
            {/* File attachment row */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <input
                type="file"
                accept={ACCEPTED_EXTENSIONS}
                ref={fileInputRef}
                style={{ display: "none" }}
                onChange={(e) => setAttachedFile(e.target.files[0] || null)}
                disabled={sending}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={sending}
                style={{
                  ...S.btnSmall,
                  padding:  "5px 12px",
                  flexShrink: 0,
                  opacity: sending ? 0.5 : 1,
                  cursor:  sending ? "not-allowed" : "pointer",
                }}
              >
                Attach file
              </button>

              {attachedFile ? (
                <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                  <span style={{
                    ...S.muted,
                    color:        "#f59e0b",
                    overflow:     "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace:   "nowrap",
                    fontSize:     "0.75rem",
                  }}>
                    {attachedFile.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setAttachedFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = "";
                    }}
                    style={{
                      background: "none", border: "none",
                      color: "#475569", cursor: "pointer",
                      fontSize: "0.75rem", flexShrink: 0, padding: 0,
                    }}
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <span style={{ ...S.muted, fontSize: "0.72rem" }}>
                  CSV, Excel, PDF, Word, TXT
                </span>
              )}
            </div>

            {/* Prompt textarea */}
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe what you want to do... (Ctrl+Enter to send)"
              rows={3}
              disabled={sending}
              style={{
                width:        "100%",
                background:   "#1e293b",
                border:       "1px solid #334155",
                borderRadius: 8,
                color:        "#f1f5f9",
                fontSize:     "0.84rem",
                padding:      "9px 12px",
                lineHeight:   1.5,
                resize:       "none",
                outline:      "none",
                boxSizing:    "border-box",
                marginBottom: 8,
              }}
            />

            {/* Send button */}
            <button
              type="submit"
              disabled={sending || !prompt.trim()}
              style={{
                width:        "100%",
                background:   sending || !prompt.trim()
                                ? "#1e293b"
                                : "linear-gradient(135deg, #0ea5e9, #6366f1)",
                border:       "none",
                borderRadius: 8,
                color:        sending || !prompt.trim() ? "#475569" : "#fff",
                padding:      "9px 0",
                fontWeight:   700,
                fontSize:     "0.88rem",
                cursor:       sending || !prompt.trim() ? "not-allowed" : "pointer",
                transition:   "background 0.2s",
              }}
            >
              {sending ? "Processing..." : "Send"}
            </button>
          </form>
        </div>

        {/* Right: CSV table */}
        <div style={S.tablePanel}>
          <CsvTable columns={csvColumns} rows={csvRows} />
        </div>

      </div>
    </div>
  );
}