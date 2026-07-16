import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

// How many prompts to send per session — keep low to conserve quota
const DEFAULT_PROMPT_LIMIT = 6;

// ── Helpers ───────────────────────────────────────────────────────────────────
function StatusPill({ status }) {
  const map = {
    pending: { label: "Queued",     bg: "#1e293b", color: "#64748b" },
    done:    { label: "Done",       bg: "#14532d", color: "#4ade80" },
    error:   { label: "Error",      bg: "#450a0a", color: "#f87171" },
    mock:    { label: "Mock Data",  bg: "#1e1b4b", color: "#818cf8" },
  };
  const s = map[status] || map.pending;
  return (
    <span style={{
      fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.05em",
      padding: "3px 10px", borderRadius: 99,
      background: s.bg, color: s.color,
    }}>
      {s.label}
    </span>
  );
}

function PromptCard({ item, index }) {
  const [expanded, setExpanded] = useState(false);

  const lines = (item.raw_response || "").split("\n");

  return (
    <div style={{
      background: "#0d1117",
      border: `1px solid ${item.status === "error" ? "#450a0a" : "#1e293b"}`,
      borderRadius: 12,
      overflow: "hidden",
      transition: "box-shadow 0.2s",
    }}>
      {/* ── Card header ── */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          padding: "14px 18px",
          display: "flex", alignItems: "flex-start", gap: 14,
          cursor: "pointer",
          background: expanded ? "#0f172a" : "transparent",
          borderBottom: expanded ? "1px solid #1e293b" : "none",
        }}
      >
        {/* Prompt number badge */}
        <span style={{
          minWidth: 32, height: 32, borderRadius: 8,
          background: "#1e293b", color: "#94a3b8",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "0.8rem", fontWeight: 700, flexShrink: 0,
        }}>
          {index + 1}
        </span>

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Prompt text preview */}
          <p style={{
            margin: "0 0 6px", fontSize: "0.85rem",
            color: "#cbd5e1", lineHeight: 1.5,
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {item.prompt}
          </p>

          {/* Stats row */}
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
            <StatusPill status={item.status} />
            {item.status === "done" || item.status === "mock" ? (
              <>
                <span style={{ fontSize: "0.75rem", color: "#475569" }}>
                  {item.char_count?.toLocaleString()} chars
                </span>
                <span style={{ fontSize: "0.75rem", color: "#475569" }}>
                  {item.word_count?.toLocaleString()} words
                </span>
                <span style={{ fontSize: "0.75rem", color: "#475569" }}>
                  {lines.filter(l => l.trim()).length} lines
                </span>
              </>
            ) : item.status === "error" ? (
              <span style={{ fontSize: "0.75rem", color: "#f87171" }}>{item.error}</span>
            ) : (
              <span style={{ fontSize: "0.75rem", color: "#475569" }}>Waiting…</span>
            )}
          </div>
        </div>

        <span style={{ color: "#475569", fontSize: "0.8rem", flexShrink: 0 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {/* ── Expanded: full prompt + raw response ── */}
      {expanded && (
        <div style={{ padding: "16px 18px" }}>

          {/* Full prompt */}
          <div style={{ marginBottom: 16 }}>
            <p style={{
              margin: "0 0 6px", fontSize: "0.7rem", fontWeight: 700,
              color: "#475569", letterSpacing: "0.08em", textTransform: "uppercase",
            }}>
              Prompt sent to Gemini
            </p>
            <div style={{
              background: "#1e293b", borderRadius: 8,
              padding: "10px 14px", fontSize: "0.82rem",
              color: "#94a3b8", lineHeight: 1.6, fontFamily: "monospace",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {item.prompt}
            </div>
          </div>

          {/* Raw response */}
          {(item.raw_response || item.error) && (
            <div>
              <p style={{
                margin: "0 0 6px", fontSize: "0.7rem", fontWeight: 700,
                color: "#475569", letterSpacing: "0.08em", textTransform: "uppercase",
              }}>
                Raw Gemini Response
              </p>
              <div style={{
                background: "#020617",
                border: "1px solid #1e293b",
                borderRadius: 8,
                padding: "12px 16px",
                fontSize: "0.83rem",
                color: item.status === "error" ? "#f87171" : "#e2e8f0",
                lineHeight: 1.7,
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                maxHeight: 500,
                overflowY: "auto",
              }}>
                {item.raw_response || item.error}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function RawGeminiExplorer({ prompts, keyword, city, country, baseUrl, onBack }) {
  const BASE = (baseUrl || "").replace(/\/+$/, "");

  const [taskId,         setTaskId]         = useState(null);
  const [running,        setRunning]        = useState(false);
  const [progress,       setProgress]       = useState(0);
  const [results,        setResults]        = useState([]);
  const [error,          setError]          = useState(null);
  const [currentPrompt,  setCurrentPrompt]  = useState(0);
  const [totalPrompts,   setTotalPrompts]   = useState(0);
  const [currentText,    setCurrentText]    = useState("");
  const [promptLimit,    setPromptLimit]    = useState(DEFAULT_PROMPT_LIMIT);
  const [started,        setStarted]        = useState(false);

  const intervalRef  = useRef(null);
  const startedRef   = useRef(false);

  // Build the simple prompts from keyword/city/country
  // One simple prompt per run (not coordinate-based)
  function buildSimplePrompts(limit) {
    // Use the first `limit` of the existing coordinate prompts
    // but rewrite them in the simple format the user wants
    if (prompts && prompts.length > 0) {
      return prompts.slice(0, limit).map(() =>
        `find name, email, phone number, linkedin profile and hospital details of 100 "${keyword}" in ${city}, ${country}`
      );
    }
    return [
      `find name, email, phone number, linkedin profile and hospital details of 100 "${keyword}" in ${city}, ${country}`
    ];
  }

  async function handleStart() {
    if (startedRef.current) return;
    startedRef.current = true;
    setStarted(true);
    setRunning(true);
    setError(null);
    setResults([]);
    setProgress(0);

    const simplePrompts = buildSimplePrompts(promptLimit);

    try {
      const resp = await axios.post(`${BASE}/raw-gemini/`, {
        keyword,
        city,
        country,
        prompt_count: promptLimit,
        prompts: simplePrompts,
      });

      const { task_id, total_prompts } = resp.data;
      setTaskId(task_id);
      setTotalPrompts(total_prompts);

      intervalRef.current = setInterval(async () => {
        try {
          const poll = await axios.get(`${BASE}/raw-gemini-progress/${task_id}`);
          const d = poll.data;

          setProgress(d.progress || 0);
          setCurrentPrompt(d.current_prompt || 0);
          setCurrentText(d.current_prompt_text || "");

          if (d.results?.length > 0) setResults(d.results);
          if (d.error) { setError(d.error); setRunning(false); clearInterval(intervalRef.current); }
          if (!d.running) { setRunning(false); clearInterval(intervalRef.current); }

        } catch (e) {
          console.error("Poll error", e);
          clearInterval(intervalRef.current);
          setRunning(false);
        }
      }, 2500);

    } catch (e) {
      setError(e?.response?.data?.error || e.message);
      setRunning(false);
      startedRef.current = false;
    }
  }

  async function handleCancel() {
    if (taskId) {
      try { await axios.post(`${BASE}/cancel-raw-gemini/${taskId}`); } catch {}
    }
    clearInterval(intervalRef.current);
    setRunning(false);
  }

  useEffect(() => {
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  // ── CSV download of all raw responses ──────────────────────────────────────
  function handleDownloadCsv() {
    const escape = v => `"${String(v || "").replace(/"/g, '""')}"`;
    const headers = ["Prompt Number", "Prompt", "Status", "Raw Response", "Char Count", "Word Count"];
    const rows = results.map(r => [
      r.prompt_number, r.prompt, r.status, r.raw_response, r.char_count, r.word_count
    ].map(escape).join(","));
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `raw_responses_${keyword}_${city}.csv`.replace(/\s+/g, "_").toLowerCase();
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{
      "--accent":       "#f59e0b",
      "--border":       "#1e293b",
      "--text-primary": "#f1f5f9",
      "--text-muted":   "#475569",
      fontFamily:       "'DM Sans', 'Segoe UI', sans-serif",
      minHeight:        "100vh",
      background:       "#020617",
      color:            "var(--text-primary)",
      padding:          "32px 24px",
    }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>

        {/* ── Header ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 28 }}>
          <button onClick={onBack} style={{
            background: "none", border: "1px solid var(--border)",
            color: "#94a3b8", borderRadius: 8, padding: "6px 14px",
            cursor: "pointer", fontSize: "0.85rem",
          }}>← Back</button>
          <div>
            <h2 style={{ margin: 0, fontSize: "1.4rem", fontWeight: 700 }}>
              Raw Gemini Explorer
            </h2>
            <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "0.85rem" }}>
              {keyword} · {city}, {country} · No processing — raw responses only
            </p>
          </div>
        </div>

        {/* ── Config panel — only shown before starting ── */}
        {!started && (
          <div style={{
            background: "#0d1117", border: "1px solid var(--border)",
            borderRadius: 12, padding: "22px 24px", marginBottom: 24,
          }}>
            <p style={{ margin: "0 0 6px", fontWeight: 600, fontSize: "0.95rem" }}>
              Prompt that will be sent to Gemini:
            </p>
            <div style={{
              background: "#1e293b", borderRadius: 8, padding: "12px 16px",
              fontSize: "0.85rem", color: "#94a3b8", fontFamily: "monospace",
              lineHeight: 1.6, marginBottom: 20,
            }}>
              {`find name, email, phone number, linkedin profile and hospital details of 100 "${keyword}" in ${city}, ${country}`}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <label style={{ fontSize: "0.88rem", color: "#94a3b8" }}>
                  Number of API calls:
                </label>
                <select
                  value={promptLimit}
                  onChange={e => setPromptLimit(Number(e.target.value))}
                  style={{
                    background: "#1e293b", border: "1px solid var(--border)",
                    color: "var(--text-primary)", borderRadius: 6,
                    padding: "6px 10px", fontSize: "0.88rem", cursor: "pointer",
                  }}
                >
                  {[1, 2, 3, 4, 5, 6].map(n => (
                    <option key={n} value={n}>{n} call{n > 1 ? "s" : ""} ({n} prompt{n > 1 ? "s" : ""})</option>
                  ))}
                </select>
                <span style={{ fontSize: "0.78rem", color: "#475569" }}>
                  (daily quota: 20 calls)
                </span>
              </div>

              <button onClick={handleStart} style={{
                background: "linear-gradient(135deg, #f59e0b, #ef4444)",
                border: "none", borderRadius: 8, color: "#fff",
                padding: "10px 24px", fontWeight: 700, fontSize: "0.9rem",
                cursor: "pointer", letterSpacing: "0.02em",
              }}>
                Run Raw Exploration →
              </button>
            </div>
          </div>
        )}

        {/* ── Progress bar ── */}
        {running && (
          <div style={{
            background: "#0d1117", border: "1px solid var(--border)",
            borderRadius: 12, padding: "18px 22px", marginBottom: 20,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                Running prompt {currentPrompt} of {totalPrompts}…
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                {progress.toFixed(0)}%
              </span>
            </div>
            <div style={{ background: "#1e293b", borderRadius: 99, height: 5, overflow: "hidden", marginBottom: 10 }}>
              <div style={{
                width: `${progress}%`, height: "100%",
                background: "linear-gradient(90deg, #f59e0b, #ef4444)",
                borderRadius: 99, transition: "width 0.4s ease",
              }} />
            </div>
            {currentText && (
              <p style={{
                margin: 0, fontSize: "0.78rem", color: "var(--text-muted)",
                fontFamily: "monospace",
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>
                ↳ {currentText}
              </p>
            )}
            <button onClick={handleCancel} style={{
              marginTop: 12, background: "none",
              border: "1px solid #450a0a", color: "#f87171",
              borderRadius: 6, padding: "5px 14px",
              fontSize: "0.8rem", cursor: "pointer",
            }}>
              Cancel
            </button>
          </div>
        )}

        {error && (
          <div style={{
            background: "#450a0a22", border: "1px solid #450a0a",
            borderRadius: 10, padding: "14px 18px", marginBottom: 20, color: "#f87171",
          }}>
            ⚠ {error}
          </div>
        )}

        {/* ── Results header bar ── */}
        {results.length > 0 && (
          <div style={{
            display: "flex", justifyContent: "space-between",
            alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10,
          }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>
              <strong style={{ color: "var(--text-primary)" }}>{results.length}</strong> of{" "}
              <strong style={{ color: "var(--text-primary)" }}>{totalPrompts}</strong> prompts processed
              {!running && results.length === totalPrompts && (
                <span style={{ marginLeft: 10, color: "#4ade80" }}>✓ Complete</span>
              )}
            </span>
            {!running && results.length > 0 && (
              <button onClick={handleDownloadCsv} style={{
                background: "none", border: "1px solid var(--border)",
                color: "#94a3b8", borderRadius: 8,
                padding: "7px 16px", fontWeight: 600, fontSize: "0.85rem",
                cursor: "pointer",
              }}>
                ⬇ Download Raw CSV
              </button>
            )}
          </div>
        )}

        {/* ── Prompt cards ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {results.map((item, i) => (
            <PromptCard key={i} item={item} index={i} />
          ))}
        </div>

        {/* ── Empty state ── */}
        {!running && results.length === 0 && started && !error && (
          <div style={{
            textAlign: "center", padding: "60px 20px",
            color: "var(--text-muted)", fontSize: "0.95rem",
          }}>
            No responses received yet.
          </div>
        )}

      </div>
    </div>
  );
}