import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { FaArrowLeft, FaClock, FaInfoCircle } from "react-icons/fa";

// ── Helpers ──────────────────────────────────────────────────────────────────
const sentColor = (score) => {
    if (score == null) return "#6b7280";
    if (score > 0.25) return "#10b981";  // Positive
    if (score < -0.25) return "#ef4444"; // Negative
    return "#f59e0b";                    // Neutral/Mixed
};

const sentLabel = (score, explicitLabel = null) => {
    if (explicitLabel) return explicitLabel;
    if (score == null) return "No Data";
    if (score > 0.6) return "Very Positive";
    if (score > 0.2) return "Positive";
    if (score > -0.2) return "Mixed / Neutral";
    if (score > -0.6) return "Negative";
    return "Very Negative";
};

function Bar({ ratio, color, height = 8 }) {
    return (
        <div style={{ height, background: "#1f2937", borderRadius: 4, overflow: "hidden", flex: 1 }}>
            <div style={{ height: "100%", width: `${Math.min(100, Math.max(1, (ratio || 0) * 100))}%`, background: color, borderRadius: 4, transition: "width 0.5s ease-in-out" }} />
        </div>
    );
}

// ── Main Test Component ──────────────────────────────────────────────────────
export default function TestSentimentAnalysis({ baseUrl = "", onBack, daysBack = 30 }) {
    const cleanBaseUrl = (baseUrl || "").replace(/\/+$/, "");
    
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [taskId, setTaskId] = useState("instant-test-task");
    const [results, setResults] = useState([]);
    const [combined, setCombined] = useState(null);
    const [generatedAt, setGeneratedAt] = useState("");

    const [activeTab, setActiveTab] = useState("combined");
    const [expandedIdx, setExpandedIdx] = useState(null);
    const [rankingCollapsed, setRankingCollapsed] = useState(false);

    // Track fetch execution to prevent duplicate calls in React StrictMode
    const hasFetched = useRef(false);

    const createClientTimestamp = () => {
        return new Date().toLocaleString("en-US", {
            month: "long",
            day: "numeric",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit",
            hour12: true,
        });
    };

    // ── Fetch Mock Data on Component Mount ──────────────────────────────────
    useEffect(() => {
        let isMounted = true;

        const fetchTestData = async () => {
            // Prevent duplicate triggers if data was already fetched
            if (hasFetched.current) return;
            hasFetched.current = true;

            try {
                if (isMounted) {
                    setLoading(true);
                    setError(null);
                }

                const endpoint = `${cleanBaseUrl}/api/hotel-sentiment/test-instant`;
                const response = await axios.post(endpoint, {}, { timeout: 60000 });

                if (isMounted && response.data) {
                    setResults(response.data.results || []);
                    setCombined(response.data.combined_report || null);
                    if (response.data.task_id) setTaskId(response.data.task_id);
                    setGeneratedAt(createClientTimestamp());
                }
            } catch (err) {
                console.error("Failed to load test mock data:", err);
                if (isMounted) {
                    setError(err.response?.data?.detail || err.message || "Failed to load report data");
                }
            } finally {
                if (isMounted) {
                    setLoading(false); // Guarantees loading state clears on 200 OK or Error
                }
            }
        };

        fetchTestData();

        return () => {
            isMounted = false;
        };
    }, [cleanBaseUrl]);

    // ── PDF Download Handler ─────────────────────────────────────────────────
    const downloadPdf = async () => {
        try {
            const encodedTime = encodeURIComponent(generatedAt || "");
            const endpoint = `${cleanBaseUrl}/api/hotel-sentiment/report/pdf/${taskId}?client_time=${encodedTime}`;

            const response = await axios.get(endpoint, { responseType: "blob" });

            const blob = new Blob([response.data], { type: "application/pdf" });
            const downloadUrl = window.URL.createObjectURL(blob);

            const link = document.createElement("a");
            link.href = downloadUrl;
            link.setAttribute("download", `Sentiment_Report_${taskId}.pdf`);
            document.body.appendChild(link);
            link.click();

            link.remove();
            window.URL.revokeObjectURL(downloadUrl);
        } catch (err) {
            console.error("PDF download error:", err);
            alert("Failed to download PDF report. Ensure backend PDF endpoint is active.");
        }
    };

    const Shell = ({ children }) => (
        <div className="app-container">
            <div className="animated-background"><div className="gradient-overlay" /><div className="dot-pattern" /></div>
            <div className="content-container">
                <div style={{ maxWidth: 960, width: "100%", margin: "0 auto", padding: "2rem 1rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, flexWrap: "wrap", gap: 10 }}>
                        <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", color: "#a78bfa", cursor: "pointer", fontSize: "0.85rem", fontWeight: 600, padding: 0 }}>
                            <FaArrowLeft style={{ fontSize: 11 }} /> Back to Dashboard
                        </button>
                        <button onClick={downloadPdf} style={{ display: "flex", alignItems: "center", gap: 6, background: "linear-gradient(to right,#9333ea,#4f46e5)", border: "none", color: "#fff", borderRadius: 8, padding: "8px 18px", fontSize: "0.82rem", fontWeight: 700, cursor: "pointer" }}>
                            ↓ Download PDF Report
                        </button>
                    </div>
                    {children}
                </div>
            </div>
        </div>
    );

    if (loading) {
        return (
            <div className="app-container">
                <div className="animated-background"><div className="gradient-overlay" /><div className="dot-pattern" /></div>
                <div className="content-container">
                    <div style={{ maxWidth: 600, margin: "0 auto", padding: "4rem 1rem", textAlign: "center" }}>
                        <div style={{ width: 64, height: 64, borderRadius: "50%", margin: "0 auto 24px", background: "conic-gradient(#9333ea,#4f46e5,#9333ea 30%,#1f2937 30%)", animation: "spin 1.2s linear infinite" }} />
                        <style>{`@keyframes spin{to{transform:rotate(360deg);}}`}</style>
                        <h2 style={{ fontSize: "1.3rem", fontWeight: 700, marginBottom: 8, background: "linear-gradient(to right,#a78bfa,#818cf8)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                            Loading Test Report Data...
                        </h2>
                        <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Processing mock reviews directly from backend JSON...</p>
                    </div>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <Shell>
                <div style={{ padding: 20, background: "rgba(239, 68, 68, 0.1)", border: "1px solid #ef4444", borderRadius: 12, color: "#fca5a5" }}>
                    <h3 style={{ margin: "0 0 8px" }}>Error Loading Mock Report</h3>
                    <p style={{ margin: 0, fontSize: "0.85rem" }}>{error}</p>
                    <button onClick={onBack} style={{ marginTop: 12, background: "#ef4444", color: "#fff", border: "none", padding: "6px 12px", borderRadius: 6, cursor: "pointer" }}>Go Back</button>
                </div>
            </Shell>
        );
    }

    return (
        <Shell>
            <h2 style={{ margin: "0 0 4px", fontSize: "1.4rem", fontWeight: 800, background: "linear-gradient(to right,#a78bfa,#818cf8)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                Sentiment Analysis
            </h2>

            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", margin: "0 0 20px" }}>
                <p style={{ margin: 0, color: "#6b7280", fontSize: "0.82rem" }}>
                    {results.length} hotels analysed · Last {daysBack} days
                </p>

                {generatedAt && (
                    <div style={{ display: "flex", alignItems: "center", gap: 5, background: "rgba(147, 51, 234, 0.12)", border: "1px solid rgba(147, 51, 234, 0.3)", borderRadius: 6, padding: "2px 8px", fontSize: "0.75rem", color: "#c084fc" }}>
                        <FaClock style={{ fontSize: 10 }} />
                        <span>Generated: {generatedAt}</span>
                    </div>
                )}
            </div>

            <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
                {[{ key: "combined", label: "Combined Executive Report" }, { key: "individual", label: `Individual Hotels (${results.length})` }].map(t => (
                    <button key={t.key} onClick={() => setActiveTab(t.key)} style={{ padding: "7px 18px", borderRadius: 20, fontSize: "0.78rem", fontWeight: 600, border: `1px solid ${activeTab === t.key ? "#9333ea" : "#374151"}`, background: activeTab === t.key ? "linear-gradient(to right,#9333ea,#4f46e5)" : "transparent", color: activeTab === t.key ? "#fff" : "#6b7280", cursor: "pointer" }}>{t.label}</button>
                ))}
            </div>

            {/* COMBINED EXECUTIVE REPORT */}
            {activeTab === "combined" && combined && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12 }}>
                        {[
                            { label: "Hotels Analysed", value: combined.total_analysed, color: "#a78bfa" },
                            { label: "Market Sentiment", value: combined.market_label, color: sentColor(combined.avg_sentiment_score), small: true },
                            { label: "Avg Sentiment Index", value: combined.avg_sentiment_score != null ? `${combined.avg_sentiment_score > 0 ? "+" : ""}${combined.avg_sentiment_score}` : "—", color: sentColor(combined.avg_sentiment_score) },
                            { label: "Avg Rating", value: combined.avg_rating ? `★ ${combined.avg_rating}` : "—", color: "#f59e0b" },
                            { label: "Positive Reviews", value: `${combined.positive_pct || 0}%`, color: "#10b981" },
                            { label: "Negative Reviews", value: `${combined.negative_pct || 0}%`, color: "#ef4444" },
                        ].map(({ label, value, color, small }) => (
                            <div key={label} style={{ background: "#1A1E2E", borderRadius: 12, padding: "14px 16px", border: "1px solid #374151", textAlign: "center" }}>
                                <div style={{ fontSize: "0.62rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 6 }}>{label}</div>
                                <div style={{ fontSize: small ? "0.85rem" : "1.5rem", fontWeight: 800, color, lineHeight: 1.1 }}>{value}</div>
                            </div>
                        ))}
                    </div>

                    <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid #374151" }}>
                        <p style={{ margin: "0 0 14px", fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>Overall Sentiment Distribution</p>
                        {[{ label: "Positive", pct: combined.positive_pct || 0, color: "#10b981" }, { label: "Neutral", pct: combined.neutral_pct || 0, color: "#f59e0b" }, { label: "Negative", pct: combined.negative_pct || 0, color: "#ef4444" }].map(({ label, pct, color }) => (
                            <div key={label} style={{ marginBottom: 12 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                                    <span style={{ fontSize: "0.82rem", color: "#d1d5db", fontWeight: 600 }}>{label}</span>
                                    <span style={{ fontSize: "0.78rem", color, fontWeight: 700 }}>{pct}%</span>
                                </div>
                                <Bar ratio={pct / 100} color={color} height={10} />
                            </div>
                        ))}
                    </div>

                    {combined.sentiment_ranking?.length > 0 && (
                        <div style={{ background: "#1A1E2E", borderRadius: 12, border: "1px solid #374151", overflow: "hidden" }}>
                            <div
                                onClick={() => setRankingCollapsed(c => !c)}
                                style={{ padding: "14px 20px", background: "#252B3E", borderBottom: rankingCollapsed ? "none" : "1px solid #374151", display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}
                            >
                                <p style={{ margin: 0, fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                                    Sentiment Ranking ({combined.sentiment_ranking.length} hotels)
                                </p>
                                <span style={{ color: "#6b7280", fontSize: 13, transform: rankingCollapsed ? "rotate(0deg)" : "rotate(90deg)", transition: "transform 0.2s" }}>▶</span>
                            </div>
                            {!rankingCollapsed && combined.sentiment_ranking.map((r, i) => (
                                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 20px", borderBottom: i < combined.sentiment_ranking.length - 1 ? "1px solid #1f2937" : "none", background: r.isUser ? "rgba(245,158,11,0.05)" : "transparent", borderLeft: r.isUser ? "3px solid #f59e0b" : "3px solid transparent" }}>
                                    <div style={{ width: 28, height: 28, borderRadius: "50%", background: r.isUser ? "linear-gradient(to right,#f59e0b,#d97706)" : i === 0 ? "linear-gradient(to right,#f59e0b,#d97706)" : i === 1 ? "linear-gradient(to right,#9ca3af,#6b7280)" : i === 2 ? "linear-gradient(to right,#b45309,#92400e)" : "#1f2937", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.72rem", fontWeight: 800, color: i < 3 || r.isUser ? "#fff" : "#6b7280", flexShrink: 0 }}>
                                        {r.isUser ? "★" : i + 1}
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                            {r.isUser && <span style={{ fontSize: "0.6rem", background: "#f59e0b", color: "#000", padding: "1px 5px", borderRadius: 3, fontWeight: 800 }}>YOU</span>}
                                            <div style={{ fontSize: "0.85rem", fontWeight: 600, color: r.isUser ? "#fbbf24" : "#f1f1f1", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</div>
                                        </div>
                                        <div style={{ fontSize: "0.72rem", color: "#6b7280", marginTop: 2 }}>
                                            {r.score == null ? "No reviews in this period" : r.label}
                                        </div>
                                    </div>
                                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                                        <div style={{ fontSize: "0.9rem", fontWeight: 800, color: r.score == null ? "#4b5563" : sentColor(r.score) }}>
                                            {r.score != null ? `${r.score > 0 ? "+" : ""}${r.score}` : "—"}
                                        </div>
                                        {r.rating && <div style={{ fontSize: "0.7rem", color: "#f59e0b" }}>★ {r.rating}</div>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {combined.combined_journey && Object.keys(combined.combined_journey).length > 0 && (
                        <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid #374151" }}>
                            <p style={{ margin: "0 0 14px", fontSize: "0.72rem", color: "#a78bfa", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                                Customer Journey Touchpoint Analysis
                            </p>

                            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                                {Object.entries(combined.combined_journey).map(([phaseName, subDict]) => {
                                    const pos = Object.values(subDict).reduce((acc, curr) => acc + curr.pos, 0);
                                    const neu = Object.values(subDict).reduce((acc, curr) => acc + curr.neu, 0);
                                    const neg = Object.values(subDict).reduce((acc, curr) => acc + curr.neg, 0);
                                    const total = pos + neu + neg;

                                    if (total === 0) return null;

                                    return (
                                        <div key={phaseName} style={{ background: "#111827", padding: 14, borderRadius: 8, border: "1px solid #1f2937" }}>
                                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                                                <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#f3f4f6" }}>{phaseName}</span>
                                                <div style={{ display: "flex", gap: 10, fontSize: "0.75rem", fontWeight: 600 }}>
                                                    <span style={{ color: "#10b981" }}>+{pos}</span>
                                                    <span style={{ color: "#f59e0b" }}>~{neu}</span>
                                                    <span style={{ color: "#ef4444" }}>-{neg}</span>
                                                </div>
                                            </div>

                                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                {Object.entries(subDict).map(([subName, counts]) => {
                                                    const subTotal = counts.pos + counts.neu + counts.neg;
                                                    if (subTotal === 0) return null;

                                                    return (
                                                        <div key={subName} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#1A1E2E", padding: "6px 10px", borderRadius: 4, fontSize: "0.75rem" }}>
                                                            <span style={{ color: "#9ca3af" }}>• {subName}</span>
                                                            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                                                <span style={{ color: "#10b981" }}>{counts.pos}</span>
                                                                <span style={{ color: "#f59e0b" }}>{counts.neu}</span>
                                                                <span style={{ color: "#ef4444" }}>{counts.neg}</span>
                                                                <span style={{ color: "#6b7280", borderLeft: "1px solid #374151", paddingLeft: 6 }}>{subTotal}</span>
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* INDIVIDUAL HOTEL REPORTS */}
            {activeTab === "individual" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {results.map((r, idx) => {
                        const s = r.sentiment || {};
                        const score = s.overall_score;
                        const isUser = r.is_user_establishment;
                        const isExp = expandedIdx === idx;
                        const pos = s.positive_count || 0;
                        const neu = s.neutral_count || 0;
                        const neg = s.negative_count || 0;
                        const total = pos + neu + neg || 1;

                        return (
                            <div key={idx} style={{ background: "#1A1E2E", borderRadius: 12, border: `1px solid ${isUser ? "rgba(245,158,11,0.4)" : "#374151"}`, overflow: "hidden" }}>
                                <div onClick={() => setExpandedIdx(isExp ? null : idx)} style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 12, cursor: "pointer", background: isExp ? "rgba(147,51,234,0.06)" : "transparent", transition: "background 0.15s" }}>
                                    <div style={{ width: 32, height: 32, borderRadius: "50%", background: isUser ? "linear-gradient(to right,#f59e0b,#d97706)" : "linear-gradient(to right,#9333ea,#4f46e5)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.72rem", fontWeight: 800, color: "#fff", flexShrink: 0 }}>{idx + 1}</div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                            {isUser && <span style={{ fontSize: "0.6rem", background: "#f59e0b", color: "#000", padding: "1px 5px", borderRadius: 3, fontWeight: 800 }}>YOU</span>}
                                            <span style={{ fontWeight: 700, fontSize: "0.9rem", color: isUser ? "#fbbf24" : "#f1f1f1" }}>{r.name}</span>
                                        </div>
                                        <div style={{ display: "flex", gap: 8, marginTop: 3, flexWrap: "wrap", alignItems: "center" }}>
                                            {r.rating && <span style={{ fontSize: "0.72rem", color: "#f59e0b" }}>★ {r.rating}</span>}
                                            {r.scraped_review_count > 0 && <span style={{ fontSize: "0.72rem", color: "#6b7280" }}>{r.scraped_review_count} reviews evaluated</span>}
                                            {r.distance_km != null && <span style={{ fontSize: "0.7rem", color: "#c084fc", background: "rgba(147,51,234,0.15)", padding: "1px 6px", borderRadius: 3, border: "1px solid rgba(147,51,234,0.3)" }}>{r.distance_km} km</span>}
                                        </div>
                                    </div>
                                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                                        <div style={{ fontSize: "1rem", fontWeight: 800, color: sentColor(score) }}>{score != null ? `${score > 0 ? "+" : ""}${score}` : "—"}</div>
                                        <div style={{ fontSize: "0.7rem", color: sentColor(score), marginTop: 2 }}>{sentLabel(score, s.overall_label)}</div>
                                    </div>
                                    <div style={{ fontSize: 14, color: "#6b7280", transform: isExp ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s", flexShrink: 0 }}>▶</div>
                                </div>
                                {isExp && (
                                    <div style={{ padding: "16px 18px", borderTop: "1px solid #1f2937" }}>
                                        {r.scraped_review_count === 0 ? (
                                            <p style={{ color: "#4b5563", fontSize: "0.82rem", margin: 0 }}>No reviews found for this period.</p>
                                        ) : (
                                            <>
                                                {s.confidence_score && (
                                                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 14, background: "rgba(59, 130, 246, 0.1)", padding: "6px 10px", borderRadius: 6, fontSize: "0.72rem", color: "#60a5fa", border: "1px solid rgba(59, 130, 246, 0.2)" }}>
                                                        <FaInfoCircle />
                                                        <span>Model Confidence Score: <strong>{(s.confidence_score * 100).toFixed(1)}%</strong></span>
                                                    </div>
                                                )}

                                                <div style={{ marginBottom: 16 }}>
                                                    <p style={{ margin: "0 0 10px", fontSize: "0.7rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>Sentiment Distribution</p>
                                                    {[{ label: "Positive", count: pos, color: "#10b981" }, { label: "Neutral", count: neu, color: "#f59e0b" }, { label: "Negative", count: neg, color: "#ef4444" }].map(({ label, count, color }) => (
                                                        <div key={label} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                                                            <span style={{ fontSize: "0.75rem", color: "#9ca3af", width: 60, flexShrink: 0 }}>{label}</span>
                                                            <Bar ratio={count / total} color={color} height={8} />
                                                            <span style={{ fontSize: "0.72rem", color, fontWeight: 700, width: 70, textAlign: "right", flexShrink: 0 }}>{count} ({(count / total * 100).toFixed(0)}%)</span>
                                                        </div>
                                                    ))}
                                                </div>

                                                {s.journey_breakdown && (
                                                    <div style={{ marginBottom: 16 }}>
                                                        <p style={{ margin: "0 0 10px", fontSize: "0.7rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>
                                                            Touchpoint Mentions
                                                        </p>
                                                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                                                            {Object.entries(s.journey_breakdown).map(([phaseName, subDict]) => {
                                                                const totalMentions = Object.values(subDict).reduce((acc, c) => acc + c.pos + c.neu + c.neg, 0);
                                                                if (totalMentions === 0) return null;

                                                                return (
                                                                    <div key={phaseName} style={{ background: "#111827", padding: 8, borderRadius: 6, fontSize: "0.72rem" }}>
                                                                        <div style={{ fontWeight: 600, color: "#d1d5db", marginBottom: 4 }}>{phaseName}</div>
                                                                        <div style={{ color: "#a78bfa" }}>{totalMentions} mention{totalMentions > 1 ? "s" : ""}</div>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                )}

                                                {s.top_positive_phrases?.length > 0 && (
                                                    <div style={{ marginBottom: 12 }}>
                                                        <p style={{ margin: "0 0 8px", fontSize: "0.7rem", color: "#10b981", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>Most Positive Feedback</p>
                                                        {s.top_positive_phrases.slice(0, 2).map((p, i) => (
                                                            <div key={i} style={{ background: "rgba(16,185,129,0.05)", borderRadius: 6, padding: "8px 12px", marginBottom: 6, borderLeft: "2px solid #10b981" }}>
                                                                <div style={{ fontSize: "0.7rem", color: "#6b7280", marginBottom: 3 }}>{p.author} · {p.date}</div>
                                                                <p style={{ margin: 0, fontSize: "0.8rem", color: "#9ca3af", fontStyle: "italic" }}>"{p.text}…"</p>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}

                                                {s.top_negative_phrases?.length > 0 && (
                                                    <div>
                                                        <p style={{ margin: "0 0 8px", fontSize: "0.7rem", color: "#ef4444", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>Most Critical Feedback</p>
                                                        {s.top_negative_phrases.slice(0, 2).map((p, i) => (
                                                            <div key={i} style={{ background: "rgba(239,68,68,0.05)", borderRadius: 6, padding: "8px 12px", marginBottom: 6, borderLeft: "2px solid #ef4444" }}>
                                                                <div style={{ fontSize: "0.7rem", color: "#6b7280", marginBottom: 3 }}>{p.author} · {p.date}</div>
                                                                <p style={{ margin: 0, fontSize: "0.8rem", color: "#9ca3af", fontStyle: "italic" }}>"{p.text}…"</p>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </Shell>
    );
}