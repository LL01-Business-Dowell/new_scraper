/**
 * SearchResults.jsx
 * -----------------
 * Displays results from the /search/ endpoint.
 *
 * Two view modes driven by the "view_type" field Gemini returns:
 *
 *   "table"  — Dynamic table. Columns are derived from whatever keys
 *              Gemini returned. Works for any structured data: people,
 *              businesses, cafes, hospitals, SWOT rows, etc.
 *
 *   "report" — Analysis/report view. Each result object is expected to
 *              have a "section" key (cluster/location name) and a
 *              "content" key with the analysis text. Displayed as
 *              collapsible cards, one per section.
 *
 * The user can also toggle between views manually via the toolbar.
 *
 * Props:
 *   searchPayload  { keyword, report_type, city, country, radius_km }
 *   baseUrl        string
 *   onBack         fn
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// Helper: safely convert any value to a renderable string.
// Gemini sometimes returns nested objects instead of plain strings —
// this prevents React error #31 ("Objects are not valid as React children").
// ---------------------------------------------------------------------------
function safeStr(val) {
  if (val === null || val === undefined) return "";
  if (typeof val === "string")  return val;
  if (typeof val === "number" || typeof val === "boolean") return String(val);
  // Object or array — pretty-print as indented JSON
  try { return JSON.stringify(val, null, 2); }
  catch { return String(val); }
}

// ---------------------------------------------------------------------------
// Styles
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
    padding:      "20px 24px",
    marginBottom: 20,
  },
  muted:   { color: "#475569", fontSize: "0.82rem" },
  error: {
    background:   "#ef444415",
    border:       "1px solid #ef444440",
    borderRadius: 8,
    padding:      "12px 16px",
    color:        "#fca5a5",
    fontSize:     "0.88rem",
    marginBottom: 16,
  },
  btnSecondary: {
    background:   "none",
    border:       "1px solid #1e293b",
    borderRadius: 8,
    color:        "#94a3b8",
    padding:      "8px 18px",
    fontWeight:   600,
    fontSize:     "0.88rem",
    cursor:       "pointer",
  },
  btnCancel: {
    background:   "none",
    border:       "1px solid #450a0a",
    borderRadius: 6,
    color:        "#f87171",
    padding:      "5px 14px",
    fontSize:     "0.8rem",
    cursor:       "pointer",
  },
};

// ---------------------------------------------------------------------------
// Helper: derive a stable, sensible column order from results
// Prioritises commonly important fields; the rest come alphabetically.
// ---------------------------------------------------------------------------
function deriveColumns(results) {
  if (!results || results.length === 0) return [];
  const allKeys = new Set();
  results.forEach((r) => Object.keys(r).forEach((k) => allKeys.add(k)));

  const preferred = [
    "name", "title", "organisation", "hospital", "company",
    "location", "cluster", "area", "address", "phone", "email",
    "website", "linkedin", "rating", "reviews", "category",
    "section", "content", "analysis", "summary",
  ];

  const ordered = preferred.filter((k) => allKeys.has(k));
  const rest    = [...allKeys].filter((k) => !ordered.includes(k)).sort();
  return [...ordered, ...rest];
}

// ---------------------------------------------------------------------------
// Sub-component: dynamic table (any column set)
// ---------------------------------------------------------------------------
function DynamicTable({ results, columns, city }) {
  const [page, setPage] = useState(0);
  useEffect(() => { setPage(0); }, [results.length]);

  if (!results.length) return null;

  /**
   * Simplify cell values for the "section" column in table view.
   * "North Quadrant — Kamla Nagar / Civil Lines" → "North <City>"
   * "Your Cafe — Blue Tokai (North Quadrant, Delhi)" → "Your Cafe — Blue Tokai"
   */
  function simplifyCellValue(col, val) {
    const str = safeStr(val);
    if (col !== "section") return str;
    if (str.startsWith("Your Cafe")) {
      return str.replace(/\s*\([^)]*Quadrant[^)]*\)/i, "").trim();
    }
    const match = str.match(/^(North|South|East|West)/i);
    if (match) {
      const dir = match[1].charAt(0).toUpperCase() + match[1].slice(1).toLowerCase();
      return `${dir} ${city || ""}`.trim();
    }
    return str;
  }

  const pageCount = Math.ceil(results.length / PAGE_SIZE);
  const pageRows  = results.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div>
      <p style={{ ...S.muted, marginBottom: 12 }}>
        <strong style={{ color: "#f1f5f9" }}>{results.length}</strong> results
        &nbsp;&middot;&nbsp;{columns.length} columns
      </p>

      <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid #1e293b" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem", whiteSpace: "nowrap" }}>
          <thead>
            <tr style={{ background: "#0d1b2e" }}>
              {columns.map((col) => (
                <th key={col} style={{
                  padding: "10px 14px", textAlign: "left",
                  color: "#94a3b8", fontWeight: 700,
                  borderBottom: "1px solid #1e293b",
                  fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em",
                }}>
                  {col.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr key={ri} style={{ background: ri % 2 === 0 ? "#0f172a" : "#0d1623" }}>
                {columns.map((col) => {
                  const val = row[col];
                  const str = simplifyCellValue(col, val);
                  const isUrl = typeof val === "string" && safeStr(val).startsWith("http");
                  return (
                    <td key={col} style={{
                      padding: "9px 14px", color: "#cbd5e1",
                      borderBottom: "1px solid #1e293b",
                      maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis",
                      // content/analysis columns wrap instead of truncating
                      whiteSpace: ["content","analysis","summary","description"].includes(col) ? "normal" : "nowrap",
                    }}>
                      {isUrl ? (
                        <a href={str} target="_blank" rel="noopener noreferrer" style={{ color: "#0ea5e9" }}>
                          {str.length > 35 ? str.slice(0, 35) + "..." : str}
                        </a>
                      ) : str}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 16 }}>
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
            style={{ ...S.btnSecondary, opacity: page === 0 ? 0.4 : 1, cursor: page === 0 ? "not-allowed" : "pointer" }}>
            Previous
          </button>
          <span style={S.muted}>{page + 1} / {pageCount}</span>
          <button onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={page === pageCount - 1}
            style={{ ...S.btnSecondary, opacity: page === pageCount - 1 ? 0.4 : 1, cursor: page === pageCount - 1 ? "not-allowed" : "pointer" }}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: report / analysis view
// Each result is expected to have a section label and a content body.
// Falls back gracefully when the structure differs.
// ---------------------------------------------------------------------------
function ReportView({ results, columns, city }) {
  const [expanded, setExpanded] = useState(() =>
    Object.fromEntries(results.map((_, i) => [i, true]))
  );

  if (!results.length) return null;

  const sectionKey = columns.find((c) =>
    ["section", "location", "cluster", "name", "area", "title"].includes(c)
  ) || columns[0];

  const contentKey = columns.find((c) =>
    ["content", "analysis", "summary", "text", "description"].includes(c)
  );

  const otherKeys = columns.filter((c) => c !== sectionKey && c !== contentKey);

  /**
   * Simplify the section label Gemini returns.
   *
   * Gemini returns verbose labels like:
   *   "North Quadrant — Kamla Nagar / Civil Lines / GTB Nagar"
   *   "Your Cafe — Blue Tokai (North Quadrant, Delhi)"
   *
   * We transform them to:
   *   "North Delhi"
   *   "Your Cafe — Blue Tokai" (kept as-is for the cafe card)
   *
   * Rules:
   *   - "Your Cafe —" prefix: keep as-is (strip the quadrant/city suffix)
   *   - "North/South/East/West Quadrant — ...": show "<Direction> <City>"
   *   - Anything else: show as-is
   */
  function simplifyHeader(raw) {
    if (!raw) return raw;

    // Your Cafe card — keep the cafe name, drop the parenthetical quadrant info
    if (raw.startsWith("Your Cafe")) {
      // "Your Cafe — Blue Tokai (North Quadrant, Delhi)" → "Your Cafe — Blue Tokai"
      return raw.replace(/\s*\([^)]*Quadrant[^)]*\)/i, "").trim();
    }

    // Quadrant cards — extract direction word and append city
    const match = raw.match(/^(North|South|East|West)/i);
    if (match) {
      const direction = match[1].charAt(0).toUpperCase() + match[1].slice(1).toLowerCase();
      return `${direction} ${city || ""}`.trim();
    }

    return raw;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {results.map((item, i) => {
        const rawHeader = safeStr(item[sectionKey]) || `Section ${i + 1}`;
        const header    = simplifyHeader(rawHeader);
        const body   = contentKey ? item[contentKey] : null;
        const isOpen = expanded[i] !== false;

        return (
          <div key={i} style={{
            background:   "#0f172a",
            border:       header.startsWith("Your Cafe") ? "1px solid #f59e0b44" : "1px solid #1e293b",
            borderRadius: 10,
            overflow:     "hidden",
          }}>
            {/* Detect if this is the "Your Cafe" card for special styling */}
            {(() => {
              const isCafeCard = header.startsWith("Your Cafe —");
              return null;
            })()}
            {/* Header row */}
            <div onClick={() => setExpanded((e) => ({ ...e, [i]: !isOpen }))}
              style={{
                padding: "14px 18px", display: "flex", alignItems: "center",
                justifyContent: "space-between", cursor: "pointer",
                background:   isOpen
                  ? (header.startsWith("Your Cafe") ? "#1a1500" : "#0d1b2e")
                  : "transparent",
                borderBottom: isOpen ? "1px solid #1e293b" : "none",
              }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{
                  width: 26, height: 26, borderRadius: "50%",
                  background: header.startsWith("Your Cafe") ? "#f59e0b" : "#0ea5e9",
                  color: "#fff",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "0.75rem", fontWeight: 700, flexShrink: 0,
                }}>{i + 1}</span>
                <span style={{
                  fontWeight: 700, fontSize: "0.95rem",
                  color: header.startsWith("Your Cafe") ? "#f59e0b" : "#f1f5f9",
                }}>{header}</span>
              </div>
              <span style={{ color: "#475569", fontSize: "0.8rem" }}>
                {isOpen ? "▲" : "▼"}
              </span>
            </div>

            {/* Body */}
            {isOpen && (
              <div style={{ padding: "16px 18px" }}>
                {/* Supporting fields (not section or content) */}
                {otherKeys.length > 0 && (
                  <div style={{
                    display: "grid", gridTemplateColumns: "1fr 1fr",
                    gap: "6px 20px", marginBottom: body ? 14 : 0,
                    fontSize: "0.83rem", color: "#94a3b8",
                  }}>
                    {otherKeys.map((k) => item[k] ? (
                      <div key={k}>
                        <span style={{ color: "#475569", fontWeight: 600 }}>
                          {k.replace(/_/g, " ")}:{" "}
                        </span>
                        {String(item[k])}
                      </div>
                    ) : null)}
                  </div>
                )}

                {/* Main body text — SWOT section headers get special styling */}
                {body && (
                  <div style={{ fontSize: "0.86rem", color: "#e2e8f0", lineHeight: 1.75 }}>
                    {safeStr(body).split("\n").map((line, li) => {
                      // Detect SWOT category headers (all-caps lines like STRENGTHS)
                      const isHeader = /^(STRENGTHS|WEAKNESSES|OPPORTUNITIES|THREATS|YOUR CAFE:.*)$/.test(line.trim());
                      const headerColors = {
                        STRENGTHS:     "#4ade80",
                        WEAKNESSES:    "#f87171",
                        OPPORTUNITIES: "#60a5fa",
                        THREATS:       "#fb923c",
                      };
                      // YOUR CAFE: line gets accent colour
                      const isCafeHeader = line.trim().startsWith("YOUR CAFE:");
                      if (isCafeHeader) {
                        return (
                          <div key={li} style={{
                            marginBottom: 10,
                            fontWeight:   700,
                            fontSize:     "0.88rem",
                            color:        "#f59e0b",
                            borderBottom: "1px solid #f59e0b44",
                            paddingBottom:6,
                          }}>
                            {line.trim()}
                          </div>
                        );
                      }
                      if (isHeader) {
                        return (
                          <div key={li} style={{
                            marginTop:    li === 0 ? 0 : 18,
                            marginBottom: 6,
                            fontWeight:   700,
                            fontSize:     "0.78rem",
                            letterSpacing:"0.08em",
                            color:        headerColors[line.trim()] || "#94a3b8",
                            borderBottom: `1px solid ${headerColors[line.trim()] || "#94a3b8"}33`,
                            paddingBottom:4,
                          }}>
                            {line.trim()}
                          </div>
                        );
                      }
                      // Empty lines become small spacers
                      if (!line.trim()) return <div key={li} style={{ height: 4 }} />;
                      // Numbered points
                      return (
                        <div key={li} style={{ marginBottom: 4, paddingLeft: 4 }}>
                          {line}
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Fallback when neither body nor otherKeys */}
                {!body && otherKeys.length === 0 && (
                  <div style={{ fontSize: "0.84rem", color: "#94a3b8" }}>
                    {Object.entries(item)
                      .filter(([k]) => k !== sectionKey)
                      .map(([k, v]) => (
                        <div key={k} style={{ marginBottom: 6 }}>
                          <strong style={{ color: "#cbd5e1" }}>{k.replace(/_/g, " ")}:</strong>{" "}
                          {safeStr(v)}
                        </div>
                      ))}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function SearchResults({ searchPayload, baseUrl, onBack }) {
  const BASE = (baseUrl || "").replace(/\/+$/, "");

  const [taskId,        setTaskId]        = useState(null);
  const [running,       setRunning]       = useState(false);
  const [progress,      setProgress]      = useState(0);
  const [statusMessage, setStatusMessage] = useState("Starting...");
  const [results,       setResults]       = useState([]);
  const [viewType,      setViewType]      = useState("table");
  const [currentBatch,  setCurrentBatch]  = useState(0);
  const [totalBatches,    setTotalBatches]    = useState(0);
  const [quadrantSummary, setQuadrantSummary] = useState({});
  const [error,         setError]         = useState(null);

  const intervalRef = useRef(null);
  const startedRef  = useRef(false);

  const { keyword, report_type, city, country, radius_km, place_name } = searchPayload || {};
  const columns = deriveColumns(results);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    startSearch();
    // eslint-disable-next-line
  }, []);

  async function startSearch() {
    setRunning(true);
    setError(null);
    setResults([]);
    setProgress(0);
    setViewType("table");
    setQuadrantSummary({});

    try {
      const resp = await axios.post(`${BASE}/search/`, {
        keyword,
        report_type,
        city,
        country,
        radius_km,
        place_name,
      });

      setTaskId(resp.data.task_id);

      intervalRef.current = setInterval(async () => {
        try {
          const poll = await axios.get(`${BASE}/search-progress/${resp.data.task_id}`);
          const d    = poll.data;

          setProgress(d.progress || 0);
          setStatusMessage(d.status_message || "");
          setCurrentBatch(d.current_batch || 0);
          setTotalBatches(d.total_batches || 0);
          if (d.quadrant_summary)    setQuadrantSummary(d.quadrant_summary);
          if (d.results?.length > 0) setResults(d.results);
          if (d.view_type)           setViewType(d.view_type);
          if (d.error)  { setError(d.error); setRunning(false); clearInterval(intervalRef.current); }
          if (!d.running) { setRunning(false); clearInterval(intervalRef.current); }

        } catch (pollErr) {
          setError("Lost connection to server.");
          clearInterval(intervalRef.current);
          setRunning(false);
        }
      }, 2500);

    } catch (startErr) {
      setError(startErr?.response?.data?.error || startErr.message);
      setRunning(false);
    }
  }

  useEffect(() => {
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  async function handleCancel() {
    if (!taskId) return;
    try { await axios.post(`${BASE}/cancel-search/${taskId}`); } catch {}
    clearInterval(intervalRef.current);
    setRunning(false);
  }

  function handleDownloadCsv() {
    if (!results.length || !columns.length) return;
    const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv    = [
      columns.join(","),
      ...results.map((r) => columns.map((c) => escape(r[c])).join(",")),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url;
    a.download = `${keyword}_${city}_results.csv`.replace(/\s+/g, "_").toLowerCase();
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  }

  return (
    <div style={S.page}>
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 28 }}>
          <button onClick={onBack} style={S.btnSecondary}>Back</button>
          <div>
            <h2 style={{ margin: 0, fontSize: "1.4rem", fontWeight: 700 }}>Search Results</h2>
            <p style={{ margin: 0, ...S.muted }}>
              {keyword} &middot; {city}, {country} &middot; {radius_km} km
            </p>
          </div>
        </div>

        {/* Progress */}
        {running && (
          <div style={S.card}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{statusMessage}</span>
              <span style={S.muted}>{progress.toFixed(0)}%</span>
            </div>
            <div style={{ background: "#1e293b", borderRadius: 99, height: 6, overflow: "hidden", marginBottom: 10 }}>
              <div style={{
                width: `${progress}%`, height: "100%",
                background: "linear-gradient(90deg, #0ea5e9, #6366f1)",
                borderRadius: 99, transition: "width 0.4s ease",
              }} />
            </div>
            {totalBatches > 0 && (
              <p style={{ ...S.muted, marginBottom: 8 }}>
                Quadrant {currentBatch} of {totalBatches}
                {results.length > 0 && ` — ${results.length} results so far`}
              </p>
            )}
            {/* Quadrant point distribution — shown once inscriber data arrives */}
            {Object.keys(quadrantSummary).length > 0 && (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
                {Object.entries(quadrantSummary).map(([name, count]) => (
                  <span key={name} style={{
                    background:   "#1e293b",
                    borderRadius: 6,
                    padding:      "3px 10px",
                    fontSize:     "0.75rem",
                    color:        count > 0 ? "#94a3b8" : "#334155",
                    fontWeight:   600,
                  }}>
                    {name} · {count} pts
                  </span>
                ))}
              </div>
            )}
            <button onClick={handleCancel} style={S.btnCancel}>Cancel</button>
          </div>
        )}

        {/* Error */}
        {error && <div style={S.error}>Error: {error}</div>}

        {/* Toolbar */}
        {results.length > 0 && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 16, flexWrap: "wrap", gap: 10,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <span style={S.muted}>
                <strong style={{ color: "#f1f5f9" }}>{results.length}</strong> results
              </span>
              {/* View type toggle — user can override Gemini's suggestion */}
              <div style={{ display: "flex", gap: 6 }}>
                {["table", "report"].map((v) => (
                  <button key={v} onClick={() => setViewType(v)} style={{
                    background:   viewType === v ? "#0ea5e9" : "none",
                    border:       `1px solid ${viewType === v ? "#0ea5e9" : "#1e293b"}`,
                    borderRadius: 6,
                    color:        viewType === v ? "#fff" : "#94a3b8",
                    padding:      "4px 12px",
                    fontSize:     "0.78rem",
                    fontWeight:   600,
                    cursor:       "pointer",
                    textTransform:"capitalize",
                  }}>
                    {v}
                  </button>
                ))}
              </div>
            </div>
            {!running && (
              <button onClick={handleDownloadCsv} style={S.btnSecondary}>
                Download CSV
              </button>
            )}
          </div>
        )}

        {/* Results */}
        {results.length > 0 && viewType === "table" && (
          <div style={S.card}>
            <DynamicTable results={results} columns={columns} city={city} />
          </div>
        )}

        {results.length > 0 && viewType === "report" && (
          <ReportView results={results} columns={columns} city={city} />
        )}

        {!running && results.length === 0 && !error && (
          <div style={{ textAlign: "center", padding: "60px 20px", ...S.muted }}>
            No results found. Try adjusting your search radius or prompt.
          </div>
        )}

      </div>
    </div>
  );
}