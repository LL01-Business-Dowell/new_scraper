/**
 * ReviewAnalysis.jsx
 * ------------------
 * Standalone page at /review-analysis
 * Scrapes all reviews for a single establishment (last 12 months)
 * and shows a comprehensive sentiment report with PDF download.
 *
 * Not linked from any other page — direct URL access only.
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");

// ── Nominatim place search (same as PlacePicker) ──────────────────────────────
// function PlaceSearch({ onSelect }) {
//   const [query, setQuery]       = useState("");
//   const [results, setResults]   = useState([]);
//   const [loading, setLoading]   = useState(false);
//   const [selected, setSelected] = useState(null);
//   const debounceRef = useRef(null);

//   const search = useCallback(async (q) => {
//     if (!q || q.length < 3) { setResults([]); return; }
//     setLoading(true);
//     try {
//       const resp = await axios.get("https://nominatim.openstreetmap.org/search", {
//         params: { q, format: "json", addressdetails: 1, limit: 6, "accept-language": "en" },
//         headers: { "Accept-Language": "en" },
//       });
//       setResults(resp.data || []);
//     } catch { setResults([]); }
//     finally { setLoading(false); }
//   }, []);

//   useEffect(() => {
//     if (selected) return;
//     clearTimeout(debounceRef.current);
//     debounceRef.current = setTimeout(() => search(query), 400);
//     return () => clearTimeout(debounceRef.current);
//   }, [query, search, selected]);

//   const pick = (place) => {
//     setSelected(place);
//     setQuery(place.display_name);
//     setResults([]);
//     onSelect(place);
//   };

//   const clear = () => {
//     setSelected(null);
//     setQuery("");
//     setResults([]);
//     onSelect(null);
//   };

//   return (
//     <div style={{ position: "relative" }}>
//       <div style={{ position: "relative" }}>
//         <input
//           value={query}
//           onChange={e => { setQuery(e.target.value); setSelected(null); }}
//           placeholder="Search for a café, restaurant, hotel…"
//           style={{
//             width: "100%", padding: "12px 44px 12px 16px",
//             background: "#1f2937", border: "1px solid #374151",
//             borderRadius: 10, color: "#f1f1f1", fontSize: "0.9rem",
//             outline: "none", boxSizing: "border-box",
//           }}
//           onFocus={e => e.target.style.borderColor = "#9333ea"}
//           onBlur={e  => e.target.style.borderColor = "#374151"}
//         />
//         {query && (
//           <button onClick={clear} style={{
//             position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)",
//             background: "none", border: "none", color: "#6b7280", cursor: "pointer", fontSize: 16,
//           }}>✕</button>
//         )}
//       </div>

//       {loading && (
//         <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50,
//           background: "#1A1E2E", border: "1px solid #374151", borderRadius: 8,
//           padding: "10px 14px", color: "#6b7280", fontSize: "0.82rem" }}>
//           Searching…
//         </div>
//       )}

//       {results.length > 0 && !selected && (
//         <div style={{
//           position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50,
//           background: "#1A1E2E", border: "1px solid #374151", borderRadius: 8,
//           overflow: "hidden", boxShadow: "0 8px 24px rgba(0,0,0,0.4)", marginTop: 4,
//         }}>
//           {results.map((r, i) => (
//             <div key={i} onClick={() => pick(r)}
//               style={{
//                 padding: "10px 14px", cursor: "pointer", fontSize: "0.82rem",
//                 borderBottom: i < results.length - 1 ? "1px solid #1f2937" : "none",
//               }}
//               onMouseEnter={e => e.currentTarget.style.background = "rgba(147,51,234,0.15)"}
//               onMouseLeave={e => e.currentTarget.style.background = "transparent"}
//             >
//               <div style={{ color: "#f1f1f1", fontWeight: 500 }}>
//                 {r.display_name.split(",")[0]}
//               </div>
//               <div style={{ color: "#6b7280", fontSize: "0.73rem", marginTop: 2 }}>
//                 {r.display_name.split(",").slice(1, 4).join(",")}
//               </div>
//             </div>
//           ))}
//         </div>
//       )}
//     </div>
//   );
// }

// ── Stat tile ─────────────────────────────────────────────────────────────────
function Tile({ label, value, color = "#a78bfa", small = false }) {
    return (
        <div style={{
            background: "#1A1E2E", borderRadius: 12, padding: "16px 18px",
            border: "1px solid #374151", textAlign: "center",
        }}>
            <div style={{ fontSize: "0.62rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 6 }}>
                {label}
            </div>
            <div style={{ fontSize: small ? "0.9rem" : "1.6rem", fontWeight: 800, color, lineHeight: 1.1 }}>
                {value}
            </div>
        </div>
    );
}

// ── Bar ───────────────────────────────────────────────────────────────────────
function Bar({ ratio, color, height = 8 }) {
    return (
        <div style={{ height, background: "#1f2937", borderRadius: 4, overflow: "hidden", flex: 1 }}>
            <div style={{
                height: "100%", width: `${Math.max(1, ratio * 100)}%`,
                background: color, borderRadius: 4, transition: "width 0.6s ease",
            }} />
        </div>
    );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ReviewAnalysis() {
    const [phase, setPhase] = useState("input");   // input | running | complete
    //   const [selectedPlace, setSelectedPlace]   = useState(null);
    const [mapsUrl, setMapsUrl] = useState("");
    //   const [useDirectUrl, setUseDirectUrl]     = useState(false);
    const [daysBack, setDaysBack] = useState(365);
    //   const [maxReviews, setMaxReviews]         = useState(500);
    const [taskId, setTaskId] = useState(null);
    const [progress, setProgress] = useState(0);
    const [statusMessage, setStatusMessage] = useState("");
    const [result, setResult] = useState(null);
    const [reviews, setReviews] = useState([]);
    const [error, setError] = useState(null);
    const [reviewsExpanded, setReviewsExpanded] = useState(false);
    const [activeTab, setActiveTab] = useState("sentiment");
    const pollRef = useRef(null);

    // Redirect if not at /review-analysis
    useEffect(() => {
        if (window.location.pathname !== "/review-analysis") {
            window.history.replaceState({}, "", "/review-analysis");
        }
    }, []);

    const handleStart = async () => {
        const url = mapsUrl.trim();

        if (!url) {
            alert("Please enter a Google Maps URL.");
            return;
        }

        // Basic validation
        if (
            !url.includes("google.com/maps") &&
            !url.includes("maps.app.goo.gl")
        ) {
            alert("Please enter a valid Google Maps URL.");
            return;
        }

        setError(null);
        setPhase("running");
        setProgress(0);
        setStatusMessage("Starting...");

        try {
            const resp = await axios.post(
                `${BASE}/api/review-analysis/start`,
                {
                    url,
                    days_back: daysBack,
                    max_reviews: maxReviews,
                }
            );

            setTaskId(resp.data.task_id);
        } catch (err) {
            setError(
                err.response?.data?.detail ||
                err.message ||
                "Failed to start review analysis."
            );
            setPhase("input");
        }
    };

    // Poll progress
    useEffect(() => {
        if (!taskId) return;
        const poll = async () => {
            try {
                const resp = await axios.get(`${BASE}/api/review-analysis/progress/${taskId}`);
                const data = resp.data;
                setProgress(data.progress || 0);
                setStatusMessage(data.status_message || "");

                if (data.status === "complete") {
                    clearInterval(pollRef.current);
                    setResult(data);
                    // Fetch full reviews list separately
                    try {
                        const rr = await axios.get(`${BASE}/api/review-analysis/reviews/${taskId}`);
                        setReviews(rr.data.reviews || []);
                    } catch { /* non-fatal */ }
                    setPhase("complete");
                } else if (data.status === "error") {
                    clearInterval(pollRef.current);
                    setError(data.error || "Unknown error");
                    setPhase("input");
                }
            } catch (err) {
                console.error("Poll error:", err.message);
            }
        };
        poll();
        pollRef.current = setInterval(poll, 2000);
        return () => clearInterval(pollRef.current);
    }, [taskId]);

    const handleReset = () => {
        setPhase("input"); setResult(null); setReviews([]);
        setTaskId(null); setProgress(0); setError(null);
    };

    const downloadPdf = () => {
        window.open(`${BASE}/api/review-analysis/report/pdf/${taskId}`, "_blank");
    };

    // ── Shared shell ──────────────────────────────────────────────────────────
    const Shell = ({ children }) => (
        <div className="app-container">
            <div className="animated-background">
                <div className="gradient-overlay" /><div className="dot-pattern" />
            </div>
            <div className="content-container">
                <div style={{ maxWidth: 900, width: "100%", margin: "0 auto", padding: "2rem 1rem" }}>
                    {/* Header */}
                    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 28, paddingBottom: 20, borderBottom: "1px solid rgba(55,65,81,0.5)" }}>
                        <div style={{
                            width: 40, height: 40, borderRadius: "50%",
                            background: "linear-gradient(135deg, #9333ea, #4f46e5)",
                            display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden",
                        }}>
                            <img src="https://dowellfileuploader.uxlivinglab.online/hr/logo-2-min-min.png"
                                alt="DoWell" style={{ maxWidth: "100%", maxHeight: "100%" }} />
                        </div>
                        <span style={{
                            fontSize: "1rem", fontWeight: 700, letterSpacing: "-0.02em",
                            background: "linear-gradient(to right, #a78bfa, #818cf8)",
                            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                        }}>DoWell Samanta — Review Analysis</span>
                    </div>
                    {children}
                </div>
            </div>
        </div>
    );

    // ── INPUT PHASE ───────────────────────────────────────────────────────────
    if (phase === "input") {
        return (
            <Shell>
                <h1 style={{
                    margin: "0 0 6px", fontSize: "1.6rem", fontWeight: 800,
                    background: "linear-gradient(to right, #a78bfa, #818cf8)",
                    WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                }}>
                    Single Establishment Review Analysis
                </h1>
                <p style={{ margin: "0 0 28px", color: "#6b7280", fontSize: "0.85rem" }}>
                    Scrape and analyse all Google Maps reviews for one business over the last 12 months.
                </p>

                {error && (
                    <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 10, padding: "12px 16px", marginBottom: 20, color: "#ef4444", fontSize: "0.85rem" }}>
                        {error}
                    </div>
                )}

                <div style={{ background: "#1A1E2E", borderRadius: 14, padding: 24, border: "1px solid #374151", marginBottom: 16 }}>

                    <div>
                        <label
                            style={{
                                fontSize: "0.75rem",
                                color: "#9ca3af",
                                display: "block",
                                marginBottom: 6,
                            }}
                        >
                            Google Maps URL
                        </label>

                        <input
                            value={mapsUrl}
                            onChange={(e) => setMapsUrl(e.target.value)}
                            placeholder="https://www.google.com/maps/place/..."
                            style={{
                                width: "100%",
                                padding: "12px 16px",
                                background: "#111827",
                                border: "1px solid #374151",
                                borderRadius: 10,
                                color: "#f1f1f1",
                                fontSize: "0.85rem",
                                outline: "none",
                                boxSizing: "border-box",
                            }}
                        />

                        <p
                            style={{
                                fontSize: "0.72rem",
                                color: "#6b7280",
                                marginTop: 8,
                            }}
                        >
                            Paste the Google Maps URL of the establishment you want to analyse.
                        </p>
                    </div>

                    {/* Toggle
                    <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
                        {[
                            { key: false, label: "Search for a place" },
                            { key: true, label: "Paste a Google Maps URL" },
                        ].map(({ key, label }) => (
                            <button key={String(key)} onClick={() => setUseDirectUrl(key)} style={{
                                padding: "6px 16px", borderRadius: 20, fontSize: "0.78rem", fontWeight: 600,
                                border: `1px solid ${useDirectUrl === key ? "#9333ea" : "#374151"}`,
                                background: useDirectUrl === key ? "rgba(147,51,234,0.2)" : "transparent",
                                color: useDirectUrl === key ? "#a78bfa" : "#6b7280", cursor: "pointer",
                            }}>{label}</button>
                        ))}
                    </div>

                    {useDirectUrl ? (
                        <div>
                            <label style={{ fontSize: "0.75rem", color: "#9ca3af", display: "block", marginBottom: 6 }}>
                                Google Maps Place URL
                            </label>
                            <input
                                value={mapsUrl}
                                onChange={e => setMapsUrl(e.target.value)}
                                placeholder="https://www.google.com/maps/place/..."
                                style={{
                                    width: "100%", padding: "12px 16px",
                                    background: "#111827", border: "1px solid #374151",
                                    borderRadius: 10, color: "#f1f1f1", fontSize: "0.85rem",
                                    outline: "none", boxSizing: "border-box",
                                }}
                            />
                        </div>
                    ) : (
                        <div>
                            <label style={{ fontSize: "0.75rem", color: "#9ca3af", display: "block", marginBottom: 6 }}>
                                Search for an establishment
                            </label>
                            <PlaceSearch onSelect={place => {
                                setSelectedPlace(place ? { ...place, url: place.url || "" } : null);
                                // Nominatim doesn't give Maps URL — user will need direct URL mode for now
                                if (place && !place.url) {
                                    setUseDirectUrl(true);
                                    setMapsUrl("");
                                }
                            }} />
                            <p style={{ fontSize: "0.72rem", color: "#4b5563", marginTop: 8 }}>
                                ℹ️ After selecting a place, copy its Google Maps URL and switch to "Paste a Google Maps URL" above.
                            </p>
                        </div>
                    )} */}

                    {/* Options */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16, marginTop: 20 }}>
                        <div>
                            <label style={{ fontSize: "0.75rem", color: "#9ca3af", display: "block", marginBottom: 6 }}>
                                Analysis period
                            </label>
                            <select value={daysBack} onChange={e => setDaysBack(Number(e.target.value))} style={{
                                width: "100%", padding: "10px 14px", background: "#111827",
                                border: "1px solid #374151", borderRadius: 10, color: "#f1f1f1",
                                fontSize: "0.85rem", outline: "none",
                            }}>
                                <option value={90}>Last 3 months</option>
                                <option value={180}>Last 6 months</option>
                                <option value={365}>Last 12 months</option>
                                <option value={730}>Last 24 months</option>
                            </select>
                        </div>
                        {/* <div>
                            <label style={{ fontSize: "0.75rem", color: "#9ca3af", display: "block", marginBottom: 6 }}>
                                Max reviews to scrape
                            </label>
                            <select value={maxReviews} onChange={e => setMaxReviews(Number(e.target.value))} style={{
                                width: "100%", padding: "10px 14px", background: "#111827",
                                border: "1px solid #374151", borderRadius: 10, color: "#f1f1f1",
                                fontSize: "0.85rem", outline: "none",
                            }}>
                                <option value={100}>Up to 100</option>
                                <option value={250}>Up to 250</option>
                                <option value={500}>Up to 500</option>
                                <option value={1000}>Up to 1,000</option>
                            </select>
                        </div> */}
                    </div>
                </div>

                <button onClick={handleStart} className="submit-button">
                    Start Review Analysis
                </button>
            </Shell>
        );
    }

    // ── RUNNING PHASE ─────────────────────────────────────────────────────────
    if (phase === "running") {
        return (
            <Shell>
                <div style={{ textAlign: "center", padding: "3rem 0" }}>
                    {/* Spinner */}
                    <div style={{
                        width: 64, height: 64, borderRadius: "50%", margin: "0 auto 24px",
                        background: "conic-gradient(#9333ea, #4f46e5, #9333ea 30%, #1f2937 30%)",
                        animation: "spin 1.2s linear infinite",
                    }} />
                    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

                    <h2 style={{
                        fontSize: "1.3rem", fontWeight: 700, marginBottom: 8,
                        background: "linear-gradient(to right, #a78bfa, #818cf8)",
                        WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                    }}>
                        Analysing Reviews
                    </h2>
                    <p style={{ color: "#9ca3af", fontSize: "0.85rem", marginBottom: 24 }}>
                        {statusMessage || "Please wait — this takes a few minutes..."}
                    </p>

                    {/* Progress bar */}
                    <div style={{
                        height: 6, background: "#1f2937", borderRadius: 3,
                        overflow: "hidden", maxWidth: 400, margin: "0 auto 8px",
                    }}>
                        <div style={{
                            height: "100%", width: `${progress}%`,
                            background: "linear-gradient(to right, #9333ea, #4f46e5)",
                            borderRadius: 3, transition: "width 0.5s",
                        }} />
                    </div>
                    <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>{progress}%</span>

                    <p style={{ fontSize: "0.75rem", color: "#4b5563", marginTop: 20 }}>
                        Keep this tab open.
                        Businesses with thousands of reviews may take several minutes.
                    </p>
                </div>
            </Shell>
        );
    }

    // ── COMPLETE PHASE ────────────────────────────────────────────────────────
    const s = result?.sentiment || {};
    const bd = result?.business_details || {};
    const pos = s.positive_count || 0;
    const neu = s.neutral_count || 0;
    const neg = s.negative_count || 0;
    const totalSent = pos + neu + neg || 1;
    const rd = s.rating_distribution || {};
    const totalRated = Object.values(rd).reduce((a, b) => a + b, 0) || 1;

    const sentColor = (score) =>
        score > 0.2 ? "#10b981" : score < -0.2 ? "#ef4444" : "#f59e0b";

    const tabs = [
        { key: "sentiment", label: "Sentiment" },
        { key: "ratings", label: "Ratings" },
        { key: "themes", label: "Topics" },
        { key: "monthly", label: "Monthly" },
        { key: "reviews", label: `Reviews (${reviews.length})` },
    ];

    return (
        <Shell>
            {/* Top bar */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 24 }}>
                <div>
                    <h2 style={{
                        margin: "0 0 4px", fontSize: "1.4rem", fontWeight: 800,
                        background: "linear-gradient(to right, #a78bfa, #818cf8)",
                        WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                    }}>
                        {bd.name || "Review Analysis"}
                    </h2>
                    <p style={{ margin: 0, color: "#6b7280", fontSize: "0.8rem" }}>
                        {bd.address}  ·  ★ {bd.rating ?? "-"}  ·  {(bd.total_reviews || 0).toLocaleString()} total reviews on Maps
                        ·  {result?.review_count || reviews.length} scraped from last {result?.days_back || daysBack} days
                    </p>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={downloadPdf} style={{
                        display: "flex", alignItems: "center", gap: 6,
                        background: "linear-gradient(to right, #9333ea, #4f46e5)",
                        border: "none", color: "#fff", borderRadius: 8, padding: "8px 18px",
                        fontSize: "0.82rem", fontWeight: 700, cursor: "pointer",
                    }}>
                        ↓ Download PDF Report
                    </button>
                    <button onClick={handleReset} style={{
                        background: "#1f2937", border: "1px solid #374151", color: "#9ca3af",
                        borderRadius: 8, padding: "8px 14px", fontSize: "0.78rem", cursor: "pointer",
                    }}>
                        New Analysis
                    </button>
                </div>
            </div>

            {/* KPI row */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 12, marginBottom: 24 }}>
                <Tile label="Reviews Scraped" value={(result?.review_count || reviews.length).toLocaleString()} color="#a78bfa" />
                <Tile label="Avg Review Rating" value={s.avg_rating ? `★ ${s.avg_rating}` : "—"} color="#f59e0b" />
                <Tile label="Overall Sentiment" value={s.overall_label || "—"} color={sentColor(s.overall_score || 0)} small />
                <Tile label="Sentiment Score" value={s.overall_score !== undefined ? `${s.overall_score > 0 ? "+" : ""}${s.overall_score}` : "—"} color={sentColor(s.overall_score || 0)} />
                <Tile label="Positive Reviews" value={pos.toLocaleString()} color="#10b981" />
                <Tile label="Negative Reviews" value={neg.toLocaleString()} color="#ef4444" />
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", gap: 4, marginBottom: 20, overflowX: "auto" }}>
                {tabs.map(t => (
                    <button key={t.key} onClick={() => setActiveTab(t.key)} style={{
                        padding: "7px 16px", borderRadius: 20, fontSize: "0.78rem", fontWeight: 600,
                        border: `1px solid ${activeTab === t.key ? "#9333ea" : "#374151"}`,
                        background: activeTab === t.key ? "linear-gradient(to right, #9333ea, #4f46e5)" : "transparent",
                        color: activeTab === t.key ? "#fff" : "#6b7280",
                        cursor: "pointer", whiteSpace: "nowrap",
                    }}>{t.label}</button>
                ))}
            </div>

            {/* ── SENTIMENT TAB ────────────────────────────────────────────────── */}
            {activeTab === "sentiment" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {/* Breakdown bars */}
                    <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid #374151" }}>
                        <p style={{ margin: "0 0 16px", fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                            Sentiment Breakdown
                        </p>
                        {[
                            { label: "Positive", count: pos, color: "#10b981" },
                            { label: "Neutral", count: neu, color: "#f59e0b" },
                            { label: "Negative", count: neg, color: "#ef4444" },
                        ].map(({ label, count, color }) => (
                            <div key={label} style={{ marginBottom: 14 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                                    <span style={{ fontSize: "0.82rem", color: "#d1d5db", fontWeight: 600 }}>{label}</span>
                                    <span style={{ fontSize: "0.78rem", color, fontWeight: 700 }}>
                                        {count} ({(count / totalSent * 100).toFixed(1)}%)
                                    </span>
                                </div>
                                <Bar ratio={count / totalSent} color={color} height={10} />
                            </div>
                        ))}
                    </div>

                    {/* Top positive */}
                    {s.top_positive_phrases?.length > 0 && (
                        <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid rgba(16,185,129,0.2)" }}>
                            <p style={{ margin: "0 0 14px", fontSize: "0.72rem", color: "#10b981", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                                Most Positive Reviews
                            </p>
                            {s.top_positive_phrases.map((r, i) => (
                                <div key={i} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: i < s.top_positive_phrases.length - 1 ? "1px solid #1f2937" : "none" }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                        <span style={{ fontSize: "0.78rem", color: "#f1f1f1", fontWeight: 600 }}>{r.author}</span>
                                        <span style={{ fontSize: "0.72rem", color: "#6b7280" }}>{r.date}</span>
                                    </div>
                                    <p style={{ margin: 0, fontSize: "0.82rem", color: "#9ca3af", lineHeight: 1.5, fontStyle: "italic" }}>
                                        "{r.text}…"
                                    </p>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Top negative */}
                    {s.top_negative_phrases?.length > 0 && (
                        <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid rgba(239,68,68,0.2)" }}>
                            <p style={{ margin: "0 0 14px", fontSize: "0.72rem", color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                                Most Critical Reviews
                            </p>
                            {s.top_negative_phrases.map((r, i) => (
                                <div key={i} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: i < s.top_negative_phrases.length - 1 ? "1px solid #1f2937" : "none" }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                        <span style={{ fontSize: "0.78rem", color: "#f1f1f1", fontWeight: 600 }}>{r.author}</span>
                                        <span style={{ fontSize: "0.72rem", color: "#6b7280" }}>{r.date}</span>
                                    </div>
                                    <p style={{ margin: 0, fontSize: "0.82rem", color: "#9ca3af", lineHeight: 1.5, fontStyle: "italic" }}>
                                        "{r.text}…"
                                    </p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* ── RATINGS TAB ──────────────────────────────────────────────────── */}
            {activeTab === "ratings" && (
                <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid #374151" }}>
                    <p style={{ margin: "0 0 16px", fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                        Rating Distribution
                    </p>
                    {["5", "4", "3", "2", "1"].map(star => {
                        const count = rd[star] || 0;
                        const color = star >= "4" ? "#10b981" : star === "3" ? "#f59e0b" : "#ef4444";
                        return (
                            <div key={star} style={{ marginBottom: 14 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                    <span style={{ fontSize: "0.82rem", color: "#f59e0b", width: 60, flexShrink: 0 }}>
                                        {"★".repeat(parseInt(star))}{"☆".repeat(5 - parseInt(star))}
                                    </span>
                                    <Bar ratio={count / totalRated} color={color} height={10} />
                                    <span style={{ fontSize: "0.78rem", color, fontWeight: 700, width: 70, textAlign: "right", flexShrink: 0 }}>
                                        {count} ({(count / totalRated * 100).toFixed(1)}%)
                                    </span>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ── TOPICS TAB ───────────────────────────────────────────────────── */}
            {activeTab === "themes" && (
                <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid #374151" }}>
                    <p style={{ margin: "0 0 16px", fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                        Topic Frequency in Reviews
                    </p>
                    {Object.entries(s.keyword_themes || {})
                        .sort((a, b) => b[1] - a[1])
                        .map(([topic, count], i) => {
                            const maxCount = Math.max(...Object.values(s.keyword_themes || {}), 1);
                            return (
                                <div key={topic} style={{ marginBottom: 14 }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                                        <span style={{ fontSize: "0.82rem", color: "#d1d5db", fontWeight: 600 }}>{topic}</span>
                                        <span style={{ fontSize: "0.78rem", color: "#a78bfa", fontWeight: 700 }}>{count} mentions</span>
                                    </div>
                                    <Bar ratio={count / maxCount} color="#818cf8" height={10} />
                                </div>
                            );
                        })
                    }
                </div>
            )}

            {/* ── MONTHLY TAB ──────────────────────────────────────────────────── */}
            {activeTab === "monthly" && (
                <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid #374151" }}>
                    <p style={{ margin: "0 0 16px", fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                        Monthly Breakdown
                    </p>
                    <div style={{ overflowX: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                            <thead>
                                <tr style={{ background: "#252B3E" }}>
                                    {["Month", "Reviews", "Avg Sentiment", "Avg Rating"].map(h => (
                                        <th key={h} style={{ padding: "10px 14px", textAlign: "left", color: "#6b7280", fontWeight: 700, fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {Object.entries(s.monthly_breakdown || {})
                                    .sort((a, b) => b[0].localeCompare(a[0]))
                                    .map(([month, data], i) => {
                                        const sc = data.avg_sentiment || 0;
                                        return (
                                            <tr key={month} style={{ background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)", borderBottom: "1px solid #1f2937" }}>
                                                <td style={{ padding: "10px 14px", color: "#d1d5db" }}>
                                                    {new Date(month + "-01").toLocaleDateString("en", { month: "long", year: "numeric" })}
                                                </td>
                                                <td style={{ padding: "10px 14px", color: "#a78bfa", fontWeight: 700 }}>{data.count}</td>
                                                <td style={{ padding: "10px 14px", color: sentColor(sc), fontWeight: 600 }}>
                                                    {sc > 0 ? "+" : ""}{sc.toFixed(3)}
                                                </td>
                                                <td style={{ padding: "10px 14px", color: "#f59e0b" }}>
                                                    {data.avg_rating ? `★ ${data.avg_rating}` : "—"}
                                                </td>
                                            </tr>
                                        );
                                    })
                                }
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ── REVIEWS TAB ──────────────────────────────────────────────────── */}
            {activeTab === "reviews" && (
                <div style={{ background: "#1A1E2E", borderRadius: 12, border: "1px solid #374151", overflow: "hidden" }}>
                    <div style={{ padding: "14px 20px", background: "#252B3E", borderBottom: "1px solid #374151", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                            {reviews.length} Reviews
                        </span>
                    </div>
                    <div style={{ maxHeight: 600, overflowY: "auto" }}>
                        {reviews.slice(0, reviewsExpanded ? undefined : 50).map((r, i) => {
                            const sc = (sia && r.text && r.text !== "[Rating Only]") ? null : null;
                            return (
                                <div key={i} style={{
                                    padding: "14px 20px",
                                    borderBottom: i < reviews.length - 1 ? "1px solid #1f2937" : "none",
                                }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                            <span style={{ fontSize: "0.82rem", color: "#f1f1f1", fontWeight: 600 }}>{r.author}</span>
                                            {r.rating && (
                                                <span style={{ fontSize: "0.72rem", color: "#f59e0b" }}>
                                                    {"★".repeat(r.rating)}{"☆".repeat(5 - r.rating)}
                                                </span>
                                            )}
                                        </div>
                                        <span style={{ fontSize: "0.72rem", color: "#6b7280" }}>{r.date}</span>
                                    </div>
                                    <p style={{ margin: 0, fontSize: "0.82rem", color: "#9ca3af", lineHeight: 1.6 }}>
                                        {r.text === "[Rating Only]"
                                            ? <em style={{ color: "#4b5563" }}>No text — rating only</em>
                                            : r.text
                                        }
                                    </p>
                                </div>
                            );
                        })}
                        {reviews.length > 50 && !reviewsExpanded && (
                            <div style={{ padding: "14px 20px", textAlign: "center" }}>
                                <button onClick={() => setReviewsExpanded(true)} style={{
                                    background: "rgba(147,51,234,0.15)", border: "1px solid rgba(147,51,234,0.3)",
                                    color: "#a78bfa", borderRadius: 8, padding: "8px 20px",
                                    fontSize: "0.78rem", cursor: "pointer", fontWeight: 600,
                                }}>
                                    Show all {reviews.length} reviews
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </Shell>
    );
}