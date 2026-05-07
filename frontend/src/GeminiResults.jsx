import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

// ─── Config ───────────────────────────────────────────────────────────────────
// Dummy QR API config — replace values with your real ones
const QR_DATABASE_ID = "YOUR_DATABASE_ID_HERE";
const QR_PROXY_BASE  = "https://your-qr-api.example.com";   // replace with real base URL

// ─── Dummy QR creator (mirrors your reference implementation) ─────────────────
async function createQrCode({ qrId, qrName, qrUrl, clientName, dbId, qrLogo, qrImage }) {
  const now   = new Date();
  const date  = now.toISOString().split("T")[0];
  const time  = now.toTimeString().split(" ")[0];

  const payload = {
    database_id:     QR_DATABASE_ID,
    collection_name: clientName,
    documents: [
      {
        qr_id:     qrId,
        db_id:     dbId,
        date,
        time,
        qr_name:   qrName,
        qr_url:    qrUrl,
        qr_logo:   qrLogo || null,
        qr_image:  qrImage || null,
        qr_status: 1,
      },
    ],
  };

  // TODO: replace with your real QR endpoint
  const response = await fetch(`${QR_PROXY_BASE}/crud`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });

  if (!response.ok) throw new Error(`QR API error: ${response.status}`);
  return response.json();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function genId() {
  return Math.random().toString(36).slice(2, 10).toUpperCase();
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    idle:    { label: "Pending",  color: "#64748b" },
    pending: { label: "Queued",   color: "#f59e0b" },
    done:    { label: "QR Done",  color: "#22c55e" },
    error:   { label: "Error",    color: "#ef4444" },
  };
  const s = map[status] || map.idle;
  return (
    <span style={{
      fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.06em",
      padding: "2px 8px", borderRadius: 99,
      background: s.color + "22", color: s.color, border: `1px solid ${s.color}55`,
    }}>
      {s.label}
    </span>
  );
}

function ResultCard({ item, index }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{
      background: "var(--card-bg)",
      border: "1px solid var(--border)",
      borderRadius: 10,
      padding: "14px 16px",
      display: "flex", flexDirection: "column", gap: 6,
      transition: "box-shadow 0.2s",
      cursor: "pointer",
    }}
      onClick={() => setExpanded(e => !e)}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            width: 28, height: 28, borderRadius: "50%",
            background: "var(--accent)", color: "#fff",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "0.75rem", fontWeight: 700, flexShrink: 0,
          }}>{index + 1}</span>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontWeight: 600, fontSize: "0.95rem", color: "var(--text-primary)" }}>
              {item.name || "—"}
            </span>
            {(item.title || item.hospital) && (
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 1 }}>
                {[item.title, item.hospital].filter(Boolean).join(" · ")}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <StatusBadge status={item._qrStatus || "idle"} />
          <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {expanded && (
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px",
          marginTop: 8, fontSize: "0.82rem", color: "var(--text-secondary)",
        }}>
          {[
            ["🏥 Hospital",  item.hospital],
            ["💼 Title",     item.title],
            ["📍 Address",   item.address],
            ["📞 Phone",     item.phone],
            ["✉️ Email",     item.email],
            ["🌐 Website",   item.website],
            ["🔗 LinkedIn",  item.linkedin],
          ].map(([label, value]) => value ? (
            <div key={label}>
              <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>{label}: </span>
              {label.includes("Website") || label.includes("LinkedIn")
                ? <a href={value} target="_blank" rel="noopener noreferrer"
                    style={{ color: "var(--accent)" }}
                    onClick={e => e.stopPropagation()}>
                    {value.length > 35 ? value.slice(0, 35) + "…" : value}
                  </a>
                : value}
            </div>
          ) : null)}
        </div>
      )}

      {item._qrError && (
        <div style={{ color: "#ef4444", fontSize: "0.78rem", marginTop: 4 }}>
          ⚠ {item._qrError}
        </div>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function GeminiResults({ prompts, keyword, city, country, baseUrl, onBack }) {
  const BASE = (baseUrl || "").replace(/\/+$/, "");

  // Gemini task state
  const [taskId,    setTaskId]    = useState(null);
  const [running,   setRunning]   = useState(false);
  const [progress,  setProgress]  = useState(0);
  const [batchInfo, setBatchInfo] = useState("");
  const [results,   setResults]   = useState([]);
  const [error,     setError]     = useState(null);

  // QR state
  const [confirmed,    setConfirmed]    = useState(false);
  const [qrRunning,    setQrRunning]    = useState(false);
  const [qrDone,       setQrDone]       = useState(0);
  const [qrTotal,      setQrTotal]      = useState(0);
  const [qrError,      setQrError]      = useState(null);

  const intervalRef = useRef(null);

  // ── Start Gemini processing on mount ────────────────────────────────────────
  useEffect(() => {
    if (!prompts || prompts.length === 0) return;
    startGemini();
    // eslint-disable-next-line
  }, []);

  async function startGemini() {
    setRunning(true);
    setError(null);
    setResults([]);
    setProgress(0);

    try {
      const resp = await axios.post(`${BASE}/generate-from-prompts/`, {
        prompts,
        keyword,
        city,
        country,
        results_per_call: 100,
        batch_size: 5,
      });

      const { task_id } = resp.data;
      setTaskId(task_id);

      // Poll for progress
      intervalRef.current = setInterval(async () => {
        try {
          const poll = await axios.get(`${BASE}/gemini-progress/${task_id}`);
          const d = poll.data;

          setProgress(d.progress || 0);
          setBatchInfo(d.batch_info || "");

          if (d.results && d.results.length > 0) {
            // Add internal QR status fields
            setResults(d.results.map(r => ({ ...r, _qrStatus: "idle", _qrError: null })));
          }

          if (d.error) {
            setError(d.error);
            setRunning(false);
            clearInterval(intervalRef.current);
          }

          if (!d.running) {
            setRunning(false);
            clearInterval(intervalRef.current);
          }
        } catch (e) {
          console.error("Poll error", e);
          clearInterval(intervalRef.current);
          setRunning(false);
        }
      }, 2500);

    } catch (e) {
      setError(e?.response?.data?.error || e.message);
      setRunning(false);
    }
  }

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // ── CSV Download ─────────────────────────────────────────────────────────────
  function handleDownloadCsv() {
    const headers = ["Name", "Title", "Hospital", "Address", "Phone", "Email", "Website", "LinkedIn", "City", "Country"];
    const escape = (val) => `"${String(val || "").replace(/"/g, '""')}"`;
    const rows = results.map(r => [
      r.name, r.title, r.hospital, r.address,
      r.phone, r.email, r.website, r.linkedin,
      r.city, r.country,
    ].map(escape).join(","));

    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${keyword}_${city}_results.csv`.replace(/\s+/g, "_").toLowerCase();
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── QR Code creation ─────────────────────────────────────────────────────────
  async function handleConfirm() {
    setConfirmed(true);
    setQrRunning(true);
    setQrDone(0);
    setQrTotal(results.length);
    setQrError(null);

    const updated = [...results];
    let done = 0;

    for (let i = 0; i < updated.length; i++) {
      const item = updated[i];
      updated[i] = { ...item, _qrStatus: "pending" };
      setResults([...updated]);

      try {
        const qrUrl = item.website || item.linkedin || `https://maps.google.com/?q=${encodeURIComponent(item.name + " " + item.address)}`;

        await createQrCode({
          qrId:       genId(),
          qrName:     item.name,
          qrUrl,
          clientName: `${keyword}_${city}`.replace(/\s+/g, "_").toLowerCase(),
          dbId:       genId(),
          qrLogo:     null,
          qrImage:    null,
        });

        updated[i] = { ...updated[i], _qrStatus: "done" };
      } catch (e) {
        updated[i] = { ...updated[i], _qrStatus: "error", _qrError: e.message };
      }

      done++;
      setQrDone(done);
      setResults([...updated]);

      // Small delay to avoid hammering the QR API
      await new Promise(r => setTimeout(r, 200));
    }

    setQrRunning(false);
  }

  // ── Render ────────────────────────────────────────────────────────────────────
  const doneCount  = results.filter(r => r._qrStatus === "done").length;
  const errorCount = results.filter(r => r._qrStatus === "error").length;

  return (
    <div style={{
      "--accent":        "#0ea5e9",
      "--accent-dim":    "#0ea5e922",
      "--card-bg":       "#0f172a",
      "--border":        "#1e293b",
      "--text-primary":  "#f1f5f9",
      "--text-secondary":"#94a3b8",
      "--text-muted":    "#475569",
      fontFamily:        "'DM Sans', 'Segoe UI', sans-serif",
      minHeight:         "100vh",
      background:        "#020617",
      color:             "var(--text-primary)",
      padding:           "32px 24px",
    }}>

      {/* ── Header ── */}
      <div style={{ maxWidth: 860, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 28 }}>
          <button onClick={onBack} style={{
            background: "none", border: "1px solid var(--border)", color: "var(--text-secondary)",
            borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: "0.85rem",
          }}>← Back</button>
          <div>
            <h2 style={{ margin: 0, fontSize: "1.4rem", fontWeight: 700 }}>
              Results
            </h2>
            <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "0.85rem" }}>
              {keyword} · {city}, {country}
            </p>
          </div>
        </div>

        {/* ── Gemini progress ── */}
        {running && (
          <div style={{
            background: "var(--card-bg)", border: "1px solid var(--border)",
            borderRadius: 12, padding: "20px 24px", marginBottom: 24,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
              <span style={{ fontWeight: 600 }}>Processing prompts with Gemini…</span>
              <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{progress.toFixed(0)}%</span>
            </div>
            <div style={{ background: "#1e293b", borderRadius: 99, height: 6, overflow: "hidden" }}>
              <div style={{
                width: `${progress}%`, height: "100%",
                background: "linear-gradient(90deg, #0ea5e9, #6366f1)",
                borderRadius: 99, transition: "width 0.4s ease",
              }} />
            </div>
            <p style={{ margin: "10px 0 0", color: "var(--text-muted)", fontSize: "0.8rem" }}>
              {batchInfo}
            </p>
          </div>
        )}

        {error && (
          <div style={{
            background: "#ef444415", border: "1px solid #ef444440",
            borderRadius: 10, padding: "14px 18px", marginBottom: 20, color: "#fca5a5",
          }}>
            ⚠ Error: {error}
          </div>
        )}

        {/* ── Results summary bar ── */}
        {results.length > 0 && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 16, flexWrap: "wrap", gap: 10,
          }}>
            <div style={{ display: "flex", gap: 20, fontSize: "0.88rem" }}>
              <span style={{ color: "var(--text-muted)" }}>
                <strong style={{ color: "var(--text-primary)" }}>{results.length}</strong> results found
              </span>
              {confirmed && (
                <>
                  <span style={{ color: "#22c55e" }}>✓ {doneCount} QR created</span>
                  {errorCount > 0 && <span style={{ color: "#ef4444" }}>✗ {errorCount} failed</span>}
                </>
              )}
            </div>

            {/* ── Confirm / QR progress button ── */}
            {!confirmed && !running && results.length > 0 && (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button onClick={handleDownloadCsv} style={{
                  background: "none",
                  border: "1px solid var(--border)", borderRadius: 8,
                  color: "var(--text-secondary)",
                  padding: "9px 18px", fontWeight: 600, fontSize: "0.9rem",
                  cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                }}>
                  ⬇ Download CSV
                </button>
                <button onClick={handleConfirm} style={{
                  background: "linear-gradient(135deg, #0ea5e9, #6366f1)",
                  border: "none", borderRadius: 8, color: "#fff",
                  padding: "9px 22px", fontWeight: 700, fontSize: "0.9rem",
                  cursor: "pointer", letterSpacing: "0.02em",
                }}>
                  Confirm & Create {results.length} QR Codes →
                </button>
              </div>
            )}

            {qrRunning && (
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ background: "#1e293b", borderRadius: 99, height: 6, width: 160, overflow: "hidden" }}>
                  <div style={{
                    width: `${(qrDone / qrTotal) * 100}%`, height: "100%",
                    background: "linear-gradient(90deg, #22c55e, #0ea5e9)",
                    borderRadius: 99, transition: "width 0.3s",
                  }} />
                </div>
                <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                  {qrDone}/{qrTotal} QRs
                </span>
              </div>
            )}

            {confirmed && !qrRunning && (
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ color: "#22c55e", fontWeight: 600, fontSize: "0.88rem" }}>
                  ✓ All QR codes created
                </span>
                <button onClick={handleDownloadCsv} style={{
                  background: "none",
                  border: "1px solid var(--border)", borderRadius: 8,
                  color: "var(--text-secondary)",
                  padding: "6px 14px", fontWeight: 600, fontSize: "0.82rem",
                  cursor: "pointer",
                }}>
                  ⬇ Download CSV
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── Result cards ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {results.map((item, i) => (
            <ResultCard key={i} item={item} index={i} />
          ))}
        </div>

        {/* ── Empty state ── */}
        {!running && results.length === 0 && !error && (
          <div style={{
            textAlign: "center", padding: "60px 20px",
            color: "var(--text-muted)", fontSize: "0.95rem",
          }}>
            No results yet. Processing will start automatically.
          </div>
        )}
      </div>
    </div>
  );
}