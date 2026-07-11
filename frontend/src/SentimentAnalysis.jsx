/**
 * SentimentAnalysis.jsx
 * ---------------------
 * Full search → approve → analyse → sentiment report flow.
 * Used by SentimentApp.jsx at /sentiment route.
 *
 * Key behaviours:
 * - Search: calls /api/hotel-sentiment/search — backend uses "Luxury Hotels near {city}"
 * - Approve: same map + list UI (reuses ApprovingPhase from HotelSentimentAnalysis)
 * - Analyse: calls /api/hotel-sentiment/analyse — VADER per hotel, combined report
 * - Results: individual sentiment cards + combined report + PDF download
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { FaArrowLeft, FaStar, FaChartBar } from "react-icons/fa";

// ── Helpers ───────────────────────────────────────────────────────────────────
const sentColor = (score) =>
    score == null ? "#6b7280"
        : score > 0.2 ? "#10b981"
            : score < -0.2 ? "#ef4444"
                : "#f59e0b";

const sentLabel = (score) =>
    score == null ? "No Data"
        : score > 0.5 ? "Very Positive"
            : score > 0.2 ? "Positive"
                : score > -0.2 ? "Mixed / Neutral"
                    : score > -0.5 ? "Negative"
                        : "Very Negative";

function Bar({ ratio, color, height = 8 }) {
    return (
        <div style={{ height, background: "#1f2937", borderRadius: 4, overflow: "hidden", flex: 1 }}>
            <div style={{ height: "100%", width: `${Math.max(1, (ratio || 0) * 100)}%`, background: color, borderRadius: 4, transition: "width 0.5s" }} />
        </div>
    );
}

// ── Approving phase ───────────────────────────────────────────────────────────
function ApprovingPhase({ places, checkedPlaces, togglePlace, selectedCount, establishmentName, originLat, originLng, radiusKm, city, onApprove, onBack }) {
    const [hoveredIdx, setHoveredIdx] = React.useState(null);
    const mapRef = React.useRef(null);
    const leafletMapRef = React.useRef(null);
    const markersRef = React.useRef([]);
    const circleRef = React.useRef(null);

    const mapCenter = React.useMemo(() => {
        if (originLat && originLng) return [originLat, originLng];
        const f = places.find(p => p.lat != null);
        return f ? [f.lat, f.lng] : [20, 0];
    }, [originLat, originLng, places]);

    React.useEffect(() => {
        if (!mapRef.current || leafletMapRef.current) return;
        if (!document.getElementById("leaflet-css")) {
            const l = document.createElement("link"); l.id = "leaflet-css"; l.rel = "stylesheet";
            l.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"; document.head.appendChild(l);
        }
        const load = () => { if (window.L) { init(); return; } const s = document.createElement("script"); s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"; s.onload = init; document.head.appendChild(s); };
        const init = () => {
            const L = window.L;
            const map = L.map(mapRef.current, { center: mapCenter, zoom: 13 });
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap contributors", maxZoom: 19 }).addTo(map);
            leafletMapRef.current = map; renderMap();
        };
        load();
        return () => { if (leafletMapRef.current) { leafletMapRef.current.remove(); leafletMapRef.current = null; } };
    }, []);

    React.useEffect(() => { if (leafletMapRef.current && window.L) renderMap(); }, [places, checkedPlaces, hoveredIdx]);

    const renderMap = () => {
        const L = window.L; const map = leafletMapRef.current; if (!map || !L) return;
        markersRef.current.forEach(m => m.remove()); markersRef.current = [];
        if (circleRef.current) { circleRef.current.remove(); circleRef.current = null; }
        if (originLat && originLng && radiusKm) {
            circleRef.current = L.circle([originLat, originLng], { radius: radiusKm * 1000, color: "#9333ea", weight: 2, opacity: 0.7, fillColor: "#9333ea", fillOpacity: 0.06, dashArray: "6 4" }).addTo(map);
        }
        if (originLat && originLng) {
            const icon = L.divIcon({ html: `<div style="width:32px;height:32px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:linear-gradient(135deg,#f59e0b,#d97706);border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;"><span style="transform:rotate(45deg);color:#fff;font-size:13px;font-weight:900;display:block;text-align:center;line-height:26px;">★</span></div>`, className: "", iconSize: [32, 32], iconAnchor: [16, 32], popupAnchor: [0, -34] });
            markersRef.current.push(L.marker([originLat, originLng], { icon, zIndexOffset: 1000 }).addTo(map).bindPopup("<strong>Your establishment</strong>"));
        }
        places.forEach((place, idx) => {
            if (!place.lat || !place.lng || place.is_user_establishment) return;
            const excl = checkedPlaces[idx] === false; const hov = hoveredIdx === idx;
            const color = excl ? "#4b5563" : "#818cf8"; const size = hov ? 36 : 28;
            const shadow = hov ? "0 4px 16px rgba(56,189,248,0.6)" : "0 2px 6px rgba(0,0,0,0.4)";
            const icon = L.divIcon({ html: `<div style="width:${size}px;height:${size}px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2.5px solid ${hov ? "#38bdf8" : "#6366f1"};box-shadow:${shadow};display:flex;align-items:center;justify-content:center;"><span style="transform:rotate(45deg);color:#fff;font-size:${hov ? 11 : 9}px;font-weight:700;display:block;text-align:center;line-height:${size - 6}px;">${place.rating || "?"}</span></div>`, className: "", iconSize: [size, size], iconAnchor: [size / 2, size], popupAnchor: [0, -(size + 4)] });
            const marker = L.marker([place.lat, place.lng], { icon, zIndexOffset: hov ? 500 : 0 }).addTo(map).bindPopup(`<div style="font-family:sans-serif;min-width:140px"><strong>${place.name}</strong>${place.rating ? `<div style="color:#d97706">★ ${place.rating}</div>` : ""}${place.distance_km != null ? `<div style="color:#7c3aed;font-size:0.75rem">${place.distance_km} km</div>` : ""}</div>`);
            marker.on("click", () => { const el = document.getElementById(`sa-row-${idx}`); if (el) el.scrollIntoView({ behavior: "smooth", block: "center" }); });
            markersRef.current.push(marker);
        });
        const allCoords = places.filter(p => p.lat && p.lng).map(p => [p.lat, p.lng]);
        if (originLat && originLng) allCoords.push([originLat, originLng]);
        if (allCoords.length > 1) map.fitBounds(allCoords, { padding: [40, 40] });
    };

    return (
        <div className="app-container">
            <div className="animated-background"><div className="gradient-overlay" /><div className="dot-pattern" /></div>
            <div className="content-container">
                <div style={{ maxWidth: 1200, width: "100%", margin: "0 auto", padding: "1.5rem 1rem" }}>
                    <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", color: "#a78bfa", cursor: "pointer", fontSize: "0.85rem", fontWeight: 600, padding: 0, marginBottom: 14 }}>
                        <FaArrowLeft style={{ fontSize: 11 }} /> Back
                    </button>
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
                        <div>
                            <h2 style={{ margin: 0, fontSize: "1.3rem", fontWeight: 700, background: "linear-gradient(to right,#a78bfa,#818cf8)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                                Luxury Hotels near {city}
                            </h2>
                            <p style={{ margin: "4px 0 0", fontSize: "0.82rem", color: "#6b7280" }}>{selectedCount} selected · Hover a row to highlight its pin</p>
                        </div>
                        <div style={{ display: "flex", gap: 8 }}>
                            {[{ label: "Found", value: places.length, color: "#a78bfa" }, { label: "Selected", value: selectedCount, color: "#10b981" }, { label: "Excluded", value: places.length - selectedCount, color: "#ef4444" }].map(({ label, value, color }) => (
                                <div key={label} style={{ background: "#1f2937", borderRadius: 8, padding: "6px 14px", border: "1px solid #374151", textAlign: "center" }}>
                                    <div style={{ fontSize: "1.1rem", fontWeight: 700, color }}>{value}</div>
                                    <div style={{ fontSize: "0.65rem", color: "#6b7280" }}>{label}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: 16, alignItems: "start" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            <div style={{ maxHeight: "calc(100vh - 260px)", overflowY: "auto", border: "1px solid #374151", borderRadius: 12, background: "#1A1E2E" }}>
                                {places.map((place, idx) => {
                                    const excl = checkedPlaces[idx] === false; const hov = hoveredIdx === idx;
                                    const isUser = place.is_user_establishment || (establishmentName && place.name?.toLowerCase() === establishmentName.trim().toLowerCase());
                                    return (
                                        <div id={`sa-row-${idx}`} key={idx} onClick={() => togglePlace(idx)} onMouseEnter={() => setHoveredIdx(idx)} onMouseLeave={() => setHoveredIdx(null)}
                                            style={{
                                                padding: "11px 14px", borderBottom: idx < places.length - 1 ? "1px solid #1f2937" : "none", display: "flex", alignItems: "center", gap: 10, cursor: "pointer",
                                                background: hov ? "rgba(56,189,248,0.07)" : excl ? "rgba(239,68,68,0.04)" : isUser ? "rgba(245,158,11,0.05)" : "transparent",
                                                borderLeft: hov ? "3px solid #38bdf8" : isUser ? "3px solid #f59e0b" : "3px solid transparent", transition: "all 0.15s", opacity: excl ? 0.5 : 1
                                            }}>
                                            <div style={{ width: 18, height: 18, borderRadius: 4, flexShrink: 0, border: `2px solid ${excl ? "#4b5563" : "#9333ea"}`, background: excl ? "transparent" : "linear-gradient(to right,#9333ea,#4f46e5)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                                {!excl && <svg width="9" height="7" viewBox="0 0 10 8" fill="none"><path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>}
                                            </div>
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                                    {isUser && <span style={{ fontSize: "0.58rem", background: "#f59e0b", color: "#000", padding: "1px 5px", borderRadius: 3, fontWeight: 800 }}>YOU</span>}
                                                    <span style={{ fontWeight: 600, fontSize: "0.85rem", color: isUser ? "#fbbf24" : hov ? "#38bdf8" : "#f1f1f1", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 240 }}>{place.name}</span>
                                                </div>
                                                <div style={{ display: "flex", gap: 6, fontSize: "0.7rem", color: "#6b7280", marginTop: 3, flexWrap: "wrap", alignItems: "center" }}>
                                                    {place.rating && <span style={{ color: "#f59e0b", display: "flex", alignItems: "center", gap: 2 }}><FaStar style={{ fontSize: 8 }} /> {place.rating}</span>}
                                                    {place.reviews > 0 && <span>{place.reviews.toLocaleString()} reviews</span>}
                                                    {place.distance_km != null && <span style={{ background: "rgba(147,51,234,0.15)", color: "#c084fc", padding: "1px 5px", borderRadius: 3, fontSize: "0.68rem", fontWeight: 600, border: "1px solid rgba(147,51,234,0.3)" }}>{place.distance_km} km</span>}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                            <div style={{ display: "flex", gap: 8 }}>
                                <button onClick={onApprove} className="submit-button" style={{ flex: 1, margin: 0 }}><FaChartBar className="button-icon" /> Analyse {selectedCount} Hotels</button>
                                <button onClick={onBack} className="reset-button" style={{ width: "auto", marginTop: 0, padding: "0.75rem 1.2rem" }}>Cancel</button>
                            </div>
                        </div>
                        <div style={{ borderRadius: 12, overflow: "hidden", border: "1px solid #374151", height: "calc(100vh - 260px)", minHeight: 500, position: "sticky", top: "1rem" }}>
                            <div ref={mapRef} style={{ width: "100%", height: "100%" }} />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ── Results ───────────────────────────────────────────────────────────────────
function Results({ results, combined, city, daysBack, onBack, taskId, baseUrl }) {
    const [activeTab, setActiveTab] = useState("combined");
    const [expandedIdx, setExpandedIdx] = useState(null);

    const downloadPdf = () => window.open(`${baseUrl}/api/hotel-sentiment/report/pdf/${taskId}`, "_blank");

    const Shell = ({ children }) => (
        <div className="app-container">
            <div className="animated-background"><div className="gradient-overlay" /><div className="dot-pattern" /></div>
            <div className="content-container">
                <div style={{ maxWidth: 960, width: "100%", margin: "0 auto", padding: "2rem 1rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, flexWrap: "wrap", gap: 10 }}>
                        <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", color: "#a78bfa", cursor: "pointer", fontSize: "0.85rem", fontWeight: 600, padding: 0 }}>
                            <FaArrowLeft style={{ fontSize: 11 }} /> New Search
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

    const pos = combined.total_positive || 0;
    const neu = combined.total_neutral || 0;
    const neg = combined.total_negative || 0;

    return (
        <Shell>
            <h2 style={{ margin: "0 0 4px", fontSize: "1.4rem", fontWeight: 800, background: "linear-gradient(to right,#a78bfa,#818cf8)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                Luxury Hotel Sentiment — {city}
            </h2>
            <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: "0.82rem" }}>
                {results.length} hotels analysed · Last {daysBack} days · VADER sentiment
            </p>

            {/* Tabs */}
            <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
                {[{ key: "combined", label: "Combined Report" }, { key: "individual", label: `Individual (${results.length})` }].map(t => (
                    <button key={t.key} onClick={() => setActiveTab(t.key)} style={{ padding: "7px 18px", borderRadius: 20, fontSize: "0.78rem", fontWeight: 600, border: `1px solid ${activeTab === t.key ? "#9333ea" : "#374151"}`, background: activeTab === t.key ? "linear-gradient(to right,#9333ea,#4f46e5)" : "transparent", color: activeTab === t.key ? "#fff" : "#6b7280", cursor: "pointer" }}>{t.label}</button>
                ))}
            </div>

            {/* ── COMBINED ──────────────────────────────────────────────────────── */}
            {activeTab === "combined" && combined && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {/* KPI tiles */}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12 }}>
                        {[
                            { label: "Hotels Analysed", value: combined.total_analysed, color: "#a78bfa" },
                            { label: "Market Sentiment", value: combined.market_label, color: sentColor(combined.avg_sentiment_score), small: true },
                            { label: "Avg Score", value: combined.avg_sentiment_score != null ? `${combined.avg_sentiment_score > 0 ? "+" : ""}${combined.avg_sentiment_score}` : "—", color: sentColor(combined.avg_sentiment_score) },
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

                    {/* Sentiment breakdown */}
                    <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid #374151" }}>
                        <p style={{ margin: "0 0 14px", fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>Overall Sentiment Breakdown</p>
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

                    {/* Sentiment ranking */}
                    {combined.sentiment_ranking?.length > 0 && (
                        <div style={{ background: "#1A1E2E", borderRadius: 12, border: "1px solid #374151", overflow: "hidden" }}>
                            <div style={{ padding: "14px 20px", background: "#252B3E", borderBottom: "1px solid #374151" }}>
                                <p style={{ margin: 0, fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>Sentiment Ranking</p>
                            </div>
                            {combined.sentiment_ranking.map((r, i) => (
                                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 20px", borderBottom: i < combined.sentiment_ranking.length - 1 ? "1px solid #1f2937" : "none" }}>
                                    <div style={{ width: 28, height: 28, borderRadius: "50%", background: i === 0 ? "linear-gradient(to right,#f59e0b,#d97706)" : i === 1 ? "linear-gradient(to right,#9ca3af,#6b7280)" : i === 2 ? "linear-gradient(to right,#b45309,#92400e)" : "#1f2937", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.72rem", fontWeight: 800, color: i < 3 ? "#fff" : "#6b7280", flexShrink: 0 }}>
                                        {i + 1}
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#f1f1f1", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</div>
                                        <div style={{ fontSize: "0.72rem", color: "#6b7280", marginTop: 2 }}>{r.label}</div>
                                    </div>
                                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                                        <div style={{ fontSize: "0.9rem", fontWeight: 800, color: sentColor(r.score) }}>{r.score != null ? `${r.score > 0 ? "+" : ""}${r.score}` : "—"}</div>
                                        {r.rating && <div style={{ fontSize: "0.7rem", color: "#f59e0b" }}>★ {r.rating}</div>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Topic frequency */}
                    {combined.combined_themes && Object.keys(combined.combined_themes).length > 0 && (
                        <div style={{ background: "#1A1E2E", borderRadius: 12, padding: 20, border: "1px solid #374151" }}>
                            <p style={{ margin: "0 0 14px", fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>Topic Frequency Across All Hotels</p>
                            {Object.entries(combined.combined_themes).map(([topic, count]) => {
                                const maxC = Math.max(...Object.values(combined.combined_themes), 1);
                                return (
                                    <div key={topic} style={{ marginBottom: 12 }}>
                                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                                            <span style={{ fontSize: "0.82rem", color: "#d1d5db", fontWeight: 600 }}>{topic}</span>
                                            <span style={{ fontSize: "0.78rem", color: "#a78bfa", fontWeight: 700 }}>{count}</span>
                                        </div>
                                        <Bar ratio={count / maxC} color="#818cf8" height={10} />
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    {/* Insights */}
                    {combined.insights?.length > 0 && (
                        <div style={{ background: "rgba(147,51,234,0.06)", borderRadius: 12, padding: 18, border: "1px solid rgba(147,51,234,0.2)" }}>
                            <p style={{ margin: "0 0 14px", fontSize: "0.72rem", color: "#a78bfa", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>Market Insights</p>
                            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                {combined.insights.map((insight, i) => (
                                    <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                                        <div style={{ width: 20, height: 20, borderRadius: "50%", flexShrink: 0, background: "linear-gradient(to right,#9333ea,#4f46e5)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.62rem", fontWeight: 800, color: "#fff" }}>{i + 1}</div>
                                        <p style={{ margin: 0, fontSize: "0.83rem", color: "#d1d5db", lineHeight: 1.6 }}>{insight}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ── INDIVIDUAL ────────────────────────────────────────────────────── */}
            {activeTab === "individual" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {results.map((r, idx) => {
                        const s = r.sentiment || {}; const score = s.overall_score;
                        const isUser = r.is_user_establishment;
                        const isExp = expandedIdx === idx;
                        const pos = s.positive_count || 0; const neu = s.neutral_count || 0; const neg = s.negative_count || 0; const total = pos + neu + neg || 1;
                        return (
                            <div key={idx} style={{ background: "#1A1E2E", borderRadius: 12, border: `1px solid ${isUser ? "rgba(245,158,11,0.4)" : "#374151"}`, overflow: "hidden" }}>
                                <div onClick={() => setExpandedIdx(isExp ? null : idx)} style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 12, cursor: "pointer", background: isExp ? "rgba(147,51,234,0.06)" : "transparent", transition: "background 0.15s" }}
                                    onMouseEnter={e => { if (!isExp) e.currentTarget.style.background = "rgba(255,255,255,0.02)"; }}
                                    onMouseLeave={e => { if (!isExp) e.currentTarget.style.background = "transparent"; }}>
                                    <div style={{ width: 32, height: 32, borderRadius: "50%", background: isUser ? "linear-gradient(to right,#f59e0b,#d97706)" : "linear-gradient(to right,#9333ea,#4f46e5)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.72rem", fontWeight: 800, color: "#fff", flexShrink: 0 }}>{idx + 1}</div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                            {isUser && <span style={{ fontSize: "0.6rem", background: "#f59e0b", color: "#000", padding: "1px 5px", borderRadius: 3, fontWeight: 800 }}>YOU</span>}
                                            <span style={{ fontWeight: 700, fontSize: "0.9rem", color: isUser ? "#fbbf24" : "#f1f1f1" }}>{r.name}</span>
                                        </div>
                                        <div style={{ display: "flex", gap: 8, marginTop: 3, flexWrap: "wrap", alignItems: "center" }}>
                                            {r.rating && <span style={{ fontSize: "0.72rem", color: "#f59e0b" }}>★ {r.rating}</span>}
                                            {r.scraped_review_count > 0 && <span style={{ fontSize: "0.72rem", color: "#6b7280" }}>{r.scraped_review_count} reviews scraped</span>}
                                            {r.distance_km != null && <span style={{ fontSize: "0.7rem", color: "#c084fc", background: "rgba(147,51,234,0.15)", padding: "1px 6px", borderRadius: 3, border: "1px solid rgba(147,51,234,0.3)" }}>{r.distance_km} km</span>}
                                        </div>
                                    </div>
                                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                                        <div style={{ fontSize: "1rem", fontWeight: 800, color: sentColor(score) }}>{score != null ? `${score > 0 ? "+" : ""}${score}` : "—"}</div>
                                        <div style={{ fontSize: "0.7rem", color: sentColor(score), marginTop: 2 }}>{sentLabel(score)}</div>
                                    </div>
                                    <div style={{ fontSize: 14, color: "#6b7280", transform: isExp ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s", flexShrink: 0 }}>▶</div>
                                </div>
                                {isExp && (
                                    <div style={{ padding: "16px 18px", borderTop: "1px solid #1f2937" }}>
                                        {r.scraped_review_count === 0 ? (
                                            <p style={{ color: "#4b5563", fontSize: "0.82rem", margin: 0 }}>No reviews found for this period.</p>
                                        ) : (
                                            <>
                                                <div style={{ marginBottom: 16 }}>
                                                    <p style={{ margin: "0 0 10px", fontSize: "0.7rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>Sentiment Breakdown</p>
                                                    {[{ label: "Positive", count: pos, color: "#10b981" }, { label: "Neutral", count: neu, color: "#f59e0b" }, { label: "Negative", count: neg, color: "#ef4444" }].map(({ label, count, color }) => (
                                                        <div key={label} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                                                            <span style={{ fontSize: "0.75rem", color: "#9ca3af", width: 60, flexShrink: 0 }}>{label}</span>
                                                            <Bar ratio={count / total} color={color} height={8} />
                                                            <span style={{ fontSize: "0.72rem", color, fontWeight: 700, width: 70, textAlign: "right", flexShrink: 0 }}>{count} ({(count / total * 100).toFixed(0)}%)</span>
                                                        </div>
                                                    ))}
                                                </div>
                                                {s.keyword_themes && (
                                                    <div style={{ marginBottom: 16 }}>
                                                        <p style={{ margin: "0 0 10px", fontSize: "0.7rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>Topics Mentioned</p>
                                                        {Object.entries(s.keyword_themes).sort((a, b) => b[1] - a[1]).map(([topic, count]) => {
                                                            const maxC = Math.max(...Object.values(s.keyword_themes), 1);
                                                            return (
                                                                <div key={topic} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                                                                    <span style={{ fontSize: "0.72rem", color: "#9ca3af", width: 120, flexShrink: 0 }}>{topic}</span>
                                                                    <Bar ratio={count / maxC} color="#818cf8" height={7} />
                                                                    <span style={{ fontSize: "0.7rem", color: "#a78bfa", fontWeight: 600, width: 40, textAlign: "right", flexShrink: 0 }}>{count}</span>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                )}
                                                {s.top_positive_phrases?.length > 0 && (
                                                    <div style={{ marginBottom: 12 }}>
                                                        <p style={{ margin: "0 0 8px", fontSize: "0.7rem", color: "#10b981", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>Most Positive</p>
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
                                                        <p style={{ margin: "0 0 8px", fontSize: "0.7rem", color: "#ef4444", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>Most Critical</p>
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

// ── Main component ────────────────────────────────────────────────────────────
export default function SentimentAnalysis({ baseUrl, onBack, city, country, establishmentName, originLat, originLng, radiusKm, daysBack = 30 }) {
    const BASE = (baseUrl || "").replace(/\/+$/, "");
    const [phase, setPhase] = useState("searching");
    const [taskId, setTaskId] = useState(null);
    const [progress, setProgress] = useState(0);
    const [statusMessage, setStatusMessage] = useState("Starting search...");
    const [places, setPlaces] = useState([]);
    const [checkedPlaces, setCheckedPlaces] = useState({});
    const [results, setResults] = useState([]);
    const [combined, setCombined] = useState(null);
    const pollRef = useRef(null);

    useEffect(() => { startSearch(); }, []);

    const startSearch = async () => {
        try {
            const resp = await axios.post(`${BASE}/api/hotel-sentiment/search`, {
                city, country, establishment_name: establishmentName,
                radius_km: radiusKm, limit: 100,
                origin_lat: originLat, origin_lng: originLng,
            });
            setTaskId(resp.data.task_id);
        } catch (err) { alert(`Search failed: ${err.message}`); onBack(); }
    };

    useEffect(() => {
        if (!taskId) return;
        const poll = async () => {
            try {
                const resp = await axios.get(`${BASE}/api/hotel-sentiment/progress/${taskId}`);
                const data = resp.data;
                setProgress(data.progress || 0);
                setStatusMessage(data.status_message || "");
                if (data.status === "ready_for_approval") {
                    clearInterval(pollRef.current);
                    setStatusMessage(data.status_message);
                    await new Promise(r => setTimeout(r, 1200));
                    const all = data.places || [];
                    setPlaces(all);
                    const checked = {}; all.forEach((p, i) => { checked[i] = p.selected !== false; }); setCheckedPlaces(checked);
                    setPhase("approving");
                } else if (data.status === "complete") {
                    clearInterval(pollRef.current);
                    setResults(data.results || []); setCombined(data.combined_report || {}); setPhase("complete");
                } else if (data.status === "error") {
                    clearInterval(pollRef.current); alert(`Error: ${data.error}`); onBack();
                }
            } catch (err) { console.error("Poll error:", err.message); }
        };
        poll(); pollRef.current = setInterval(poll, 2000);
        return () => clearInterval(pollRef.current);
    }, [taskId]);

    const togglePlace = (i) => setCheckedPlaces(prev => ({ ...prev, [i]: !prev[i] }));
    const selectedCount = Object.values(checkedPlaces).filter(Boolean).length;

    const handleApprove = async () => {
        const approved = places.map((p, i) => ({ ...p, selected: checkedPlaces[i] !== false }));
        setPhase("analysing"); setProgress(0); setStatusMessage("Starting sentiment analysis...");
        try {
            const resp = await axios.post(`${BASE}/api/hotel-sentiment/analyse`, {
                task_id: taskId, approved_places: approved,
                establishment_name: establishmentName, days_back: daysBack,
            });
            clearInterval(pollRef.current);
            pollRef.current = setInterval(async () => {
                try {
                    const poll = await axios.get(`${BASE}/api/hotel-sentiment/progress/${resp.data.task_id}`);
                    const data = poll.data;
                    setProgress(data.progress || 0); setStatusMessage(data.status_message || "");
                    if (data.status === "complete") { clearInterval(pollRef.current); setResults(data.results || []); setCombined(data.combined_report || {}); setPhase("complete"); }
                    else if (data.status === "error") { clearInterval(pollRef.current); alert(`Error: ${data.error}`); setPhase("approving"); }
                } catch (err) { console.error("Poll error:", err.message); }
            }, 2000);
        } catch (err) { alert(`Failed: ${err.message}`); setPhase("approving"); }
    };

    // Searching / Analysing spinner
    if (phase === "searching" || phase === "analysing") {
        return (
            <div className="app-container">
                <div className="animated-background"><div className="gradient-overlay" /><div className="dot-pattern" /></div>
                <div className="content-container">
                    <div style={{ maxWidth: 600, margin: "0 auto", padding: "4rem 1rem", textAlign: "center" }}>
                        <div style={{ width: 64, height: 64, borderRadius: "50%", margin: "0 auto 24px", background: "conic-gradient(#9333ea,#4f46e5,#9333ea 30%,#1f2937 30%)", animation: "spin 1.2s linear infinite" }} />
                        <style>{`@keyframes spin{to{transform:rotate(360deg);}}`}</style>
                        <h2 style={{ fontSize: "1.3rem", fontWeight: 700, marginBottom: 8, background: "linear-gradient(to right,#a78bfa,#818cf8)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                            {phase === "analysing" ? "Running Analysis" : `Finding Your Competitors`}
                        </h2>
                        <p style={{ color: "#9ca3af", fontSize: "0.85rem", marginBottom: 20 }}>{statusMessage || "Please wait..."}</p>
                        <div style={{ height: 6, background: "#1f2937", borderRadius: 3, overflow: "hidden", maxWidth: 400, margin: "0 auto 8px" }}>
                            <div style={{ height: "100%", width: `${progress}%`, background: "linear-gradient(to right,#9333ea,#4f46e5)", borderRadius: 3, transition: "width 0.5s" }} />
                        </div>
                        <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>{progress}%</span>
                        {phase === "analysing" && <p style={{ fontSize: "0.75rem", color: "#4b5563", marginTop: 16 }}>Finding reviews for each hotel. Keep this tab open.</p>}
                    </div>
                </div>
            </div>
        );
    }

    if (phase === "approving") {
        return <ApprovingPhase places={places} checkedPlaces={checkedPlaces} togglePlace={togglePlace} selectedCount={selectedCount} establishmentName={establishmentName} originLat={originLat} originLng={originLng} radiusKm={radiusKm} city={city} onApprove={handleApprove} onBack={onBack} />;
    }

    if (phase === "complete") {
        return <Results results={results} combined={combined} city={city} daysBack={daysBack} onBack={onBack} taskId={taskId} baseUrl={BASE} />;
    }

    return null;
}