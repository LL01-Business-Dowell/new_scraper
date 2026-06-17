/**
 * CompetitorAnalysis.jsx
 * ----------------------
 * Styled to match App.jsx / App.css dark theme exactly.
 * Uses same background, form-container, gradient-border, input-container,
 * form-input, submit-button, progress-bar, and table classes.
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { FaSearch, FaCheckCircle, FaArrowLeft, FaStore, FaStar, FaChartBar } from "react-icons/fa";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const BASE = API_BASE_URL.replace(/\/+$/, "");

export default function CompetitorAnalysis({
    baseUrl = BASE,
    onBack,
    keyword: keywordProp = "",
    city: cityProp = "",
    country: countryProp = "",
    radiusKm: radiusKmProp = 5,
    establishmentName: establishmentNameProp = "",
}) {
    const hasProps = Boolean(keywordProp && establishmentNameProp);
    const [searchPhase, setSearchPhase] = useState(hasProps ? "searching" : "input");
    const [keyword, setKeyword] = useState(keywordProp);
    const [city, setCity] = useState(cityProp);
    const [country, setCountry] = useState(countryProp);
    const [establishmentName, setEstablishmentName] = useState(establishmentNameProp);
    const [radiusKm, setRadiusKm] = useState(radiusKmProp);
    const [searchTaskId, setSearchTaskId] = useState(null);

    const [places, setPlaces] = useState([]);
    const [checkedPlaces, setCheckedPlaces] = useState({});

    const [swotResults, setSwotResults] = useState([]);
    const [competitiveAnalysis, setCompetitiveAnalysis] = useState(null);
    const [progress, setProgress] = useState(0);
    const [statusMessage, setStatusMessage] = useState("");

    const pollIntervalRef = useRef(null);

    useEffect(() => {
        if (hasProps) {
            startSearch(keywordProp, cityProp, countryProp, radiusKmProp, establishmentNameProp);
        }
    }, []);

    const pollProgress = async () => {
        if (!searchTaskId) return;
        try {
            const resp = await axios.get(`${BASE}/api/competitors/progress/${searchTaskId}`);
            const data = resp.data;
            setProgress(data.progress);
            setStatusMessage(data.status_message);
            if (data.status === "ready_for_approval") {
                setPlaces(data.places || []);
                const checked = {};
                (data.places || []).forEach((p, i) => { checked[i] = p.selected !== false; });
                setCheckedPlaces(checked);
                setSearchPhase("approving");
                clearInterval(pollIntervalRef.current);
            } else if (data.status === "complete") {
                setSwotResults(data.swot_results || []);
                setCompetitiveAnalysis(data.competitive_analysis);
                setSearchPhase("complete");
                clearInterval(pollIntervalRef.current);
            } else if (data.status === "error") {
                alert(`Error: ${data.error}`);
                setSearchPhase("input");
                clearInterval(pollIntervalRef.current);
            }
        } catch (err) {
            console.error("Poll error:", err.message);
        }
    };

    const startPolling = () => {
        clearInterval(pollIntervalRef.current);
        pollProgress();
        pollIntervalRef.current = setInterval(pollProgress, 2000);
    };

    useEffect(() => {
        if (!searchTaskId) return;
        startPolling();
        return () => clearInterval(pollIntervalRef.current);
    }, [searchTaskId]);

    const startSearch = async (kw, ct, cntry, radius, estName) => {
        try {
            const resp = await axios.post(`${BASE}/api/competitors/search`, {
            keyword: kw,
            city: ct,
            country: cntry,
            establishment_name: estName,
            radius_km: radius,
            limit: 100,
            location_hint: ct && cntry ? `${ct}, ${cntry}` : ct || cntry || "",
            });
            setSearchTaskId(resp.data.task_id);
            setSearchPhase("searching");
            setProgress(0);
            setStatusMessage("Searching...");
        } catch (err) {
            alert(`Search failed: ${err.message}`);
        }
    };

    const handleStartSearch = async (e) => {
        e.preventDefault();
        if (!keyword || !city || !country) { alert("Please fill in all fields"); return; }
        await startSearch(keyword, city, country, radiusKm, establishmentName);
    };

    const handleApproveAndAnalyze = async () => {
        const approvedPlaces = places.map((place, i) => ({ ...place, selected: checkedPlaces[i] !== false }));
        try {
            await axios.post(`${BASE}/api/competitors/scrape-and-analyze`, {
                task_id: searchTaskId, approved_places: approvedPlaces,
            });
            setSearchPhase("analyzing");
            setProgress(0);
            setStatusMessage("Running SWOT analysis...");
            startPolling();   // ← restart polling for the analyze phase
        } catch (err) {
            alert(`Analysis failed: ${err.message}`);
        }
    };

    const togglePlace = (index) => {
        setCheckedPlaces((prev) => ({ ...prev, [index]: !prev[index] }));
    };

    const selectedCount = Object.values(checkedPlaces).filter(Boolean).length;

    // ── Shared page shell ─────────────────────────────────────────────────────
    const Shell = ({ children }) => (
        <div className="app-container">
            <div className="animated-background">
                <div className="gradient-overlay" />
                <div className="dot-pattern" />
            </div>
            <div className="content-container">
                <div className="main-content">
                    <div className="form-container" style={{ maxWidth: 900 }}>
                        <div className="gradient-border" />
                        {children}
                    </div>
                </div>
            </div>
        </div>
    );

    // ── Page header ───────────────────────────────────────────────────────────
    const PageHeader = ({ title, subtitle }) => (
        <div style={{ marginBottom: 24 }}>
            <button
                onClick={onBack}
                style={{
                    display: "flex", alignItems: "center", gap: 6,
                    background: "none", border: "none", color: "#a78bfa",
                    cursor: "pointer", fontSize: "0.85rem", fontWeight: 600,
                    marginBottom: 16, padding: 0,
                }}
            >
                <FaArrowLeft style={{ fontSize: 12 }} /> Back
            </button>
            <h2 style={{
                margin: 0, fontSize: "1.4rem", fontWeight: 700,
                background: "linear-gradient(to right, #a78bfa, #818cf8)",
                WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
            }}>
                {title}
            </h2>
            {subtitle && (
                <p style={{ margin: "6px 0 0", fontSize: "0.85rem", color: "#6b7280" }}>{subtitle}</p>
            )}
        </div>
    );

    // ── Progress bar ──────────────────────────────────────────────────────────
    const ProgressBar = ({ value, color = "linear-gradient(to right, #9333ea, #4f46e5)" }) => (
        <div style={{ marginBottom: 20 }}>
            <p style={{ fontSize: "0.875rem", color: "#9ca3af", marginBottom: 8 }}>{statusMessage}</p>
            <div className="progress-bar-container">
                <div className="progress-bar" style={{ width: `${value}%`, background: color }} />
            </div>
            <p style={{ fontSize: "0.75rem", color: "#4b5563", marginTop: 6, textAlign: "right" }}>{value}%</p>
        </div>
    );

    // ── RENDER: Input phase ───────────────────────────────────────────────────
    if (searchPhase === "input") {
        return (
            <Shell>
                <PageHeader
                    title="Competitor Analysis"
                    subtitle="Find and analyse competitors from Google Maps in your area"
                />
                <form onSubmit={handleStartSearch} className="scraper-form">
                    <div className="input-container">
                        <FaStore className="input-icon" />
                        <input
                            type="text" value={establishmentName}
                            onChange={(e) => setEstablishmentName(e.target.value)}
                            placeholder="Your establishment name (e.g. Blue Tokai Coffee)"
                            className="form-input"
                        />
                    </div>
                    <div className="input-container">
                        <FaSearch className="input-icon" />
                        <input
                            type="text" value={keyword}
                            onChange={(e) => setKeyword(e.target.value)}
                            placeholder="Category (e.g. Cafe, Restaurant)"
                            className="form-input" required
                        />
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                        <div className="input-container">
                            <input
                                type="text" value={city}
                                onChange={(e) => setCity(e.target.value)}
                                placeholder="City"
                                className="form-input" style={{ paddingLeft: "0.75rem" }} required
                            />
                        </div>
                        <div className="input-container">
                            <input
                                type="text" value={country}
                                onChange={(e) => setCountry(e.target.value)}
                                placeholder="Country"
                                className="form-input" style={{ paddingLeft: "0.75rem" }} required
                            />
                        </div>
                    </div>
                    <div className="input-container">
                        <label className="slider-label" style={{ width: "100%", color: "#9ca3af", fontSize: "0.875rem" }}>
                            Search radius: {radiusKm} km
                            <input
                                type="range" min="1" max="50" step="1" value={radiusKm}
                                onChange={(e) => setRadiusKm(Number(e.target.value))}
                                className="slider-input" style={{ width: "100%" }}
                            />
                        </label>
                    </div>
                    <button type="submit" className="submit-button">
                        <FaSearch className="button-icon" /> Search Competitors
                    </button>
                </form>
            </Shell>
        );
    }

    // ── RENDER: Searching ─────────────────────────────────────────────────────
    if (searchPhase === "searching") {
        return (
            <Shell>
                <PageHeader title="Searching..." />
                <ProgressBar value={progress} />
                <div style={{
                    background: "#1f2937", borderRadius: 12, padding: 20,
                    border: "1px solid #374151", textAlign: "center",
                }}>
                    <div style={{
                        width: 48, height: 48, borderRadius: "50%", margin: "0 auto 12px",
                        background: "linear-gradient(to right, #9333ea, #4f46e5)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                        <FaSearch style={{ color: "#fff", fontSize: 18 }} />
                    </div>
                    <p style={{ color: "#d1d5db", margin: 0, fontSize: "0.95rem" }}>
                        Searching for <strong style={{ color: "#a78bfa" }}>{keyword}</strong> in <strong style={{ color: "#a78bfa" }}>{city}</strong>
                    </p>
                    <p style={{ color: "#6b7280", margin: "6px 0 0", fontSize: "0.8rem" }}>
                        This may take a while. Please wait.
                    </p>
                </div>
            </Shell>
        );
    }

    // ── RENDER: Approving ─────────────────────────────────────────────────────
    if (searchPhase === "approving") {
        return (
            <Shell>
                <PageHeader
                    title={`Found ${places.length} Places`}
                    subtitle={`${selectedCount} selected — uncheck any to exclude before running SWOT analysis`}
                />

                {/* Stats bar */}
                <div style={{
                    display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
                    gap: 12, marginBottom: 20,
                }}>
                    {[
                        { label: "Total Found", value: places.length, color: "#a78bfa" },
                        { label: "Selected", value: selectedCount, color: "#10b981" },
                        { label: "Excluded", value: places.length - selectedCount, color: "#ef4444" },
                    ].map(({ label, value, color }) => (
                        <div key={label} style={{
                            background: "#1f2937", borderRadius: 10, padding: "12px 16px",
                            border: "1px solid #374151", textAlign: "center",
                        }}>
                            <div style={{ fontSize: "1.5rem", fontWeight: 700, color }}>{value}</div>
                            <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: 2 }}>{label}</div>
                        </div>
                    ))}
                </div>

                {/* Places list */}
                <div style={{
                    maxHeight: 420, overflowY: "auto",
                    border: "1px solid #374151", borderRadius: 12,
                    marginBottom: 20, background: "#1A1E2E",
                }}>
                    {places.map((place, idx) => (
                        <div
                            key={idx}
                            onClick={() => togglePlace(idx)}
                            style={{
                                padding: "12px 16px",
                                borderBottom: idx < places.length - 1 ? "1px solid #1f2937" : "none",
                                display: "flex", alignItems: "center", gap: 12,
                                cursor: "pointer",
                                background: checkedPlaces[idx] === false ? "rgba(239,68,68,0.05)" : "transparent",
                                transition: "background 0.2s",
                            }}
                        >
                            {/* Checkbox */}
                            <div style={{
                                width: 20, height: 20, borderRadius: 4, flexShrink: 0,
                                border: `2px solid ${checkedPlaces[idx] === false ? "#4b5563" : "#9333ea"}`,
                                background: checkedPlaces[idx] === false ? "transparent" : "linear-gradient(to right, #9333ea, #4f46e5)",
                                display: "flex", alignItems: "center", justifyContent: "center",
                            }}>
                                {checkedPlaces[idx] !== false && (
                                    <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                    </svg>
                                )}
                            </div>

                            {/* Place info */}
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{
                                    fontWeight: 600, fontSize: "0.9rem", color: "#f1f1f1",
                                    display: "flex", alignItems: "center", gap: 8,
                                }}>
                                    {place.is_user_establishment && (
                                        <span style={{
                                            fontSize: "0.65rem", background: "linear-gradient(to right, #9333ea, #4f46e5)",
                                            color: "#fff", padding: "1px 6px", borderRadius: 4, fontWeight: 700,
                                        }}>YOU</span>
                                    )}
                                    {place.name}
                                </div>
                                <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: 2, display: "flex", gap: 10 }}>
                                    {place.address && <span>{place.address}</span>}
                                    {place.rating && (
                                        <span style={{ color: "#f59e0b", display: "flex", alignItems: "center", gap: 3 }}>
                                            <FaStar style={{ fontSize: 10 }} /> {place.rating}
                                        </span>
                                    )}
                                    {place.reviews > 0 && (
                                        <span style={{ color: "#4b5563" }}>{place.reviews.toLocaleString()} reviews</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                <div style={{ display: "flex", gap: 10 }}>
                    <button
                        onClick={handleApproveAndAnalyze}
                        className="submit-button"
                        style={{ flex: 1 }}
                    >
                        <FaChartBar className="button-icon" />
                        Analyse {selectedCount} Places
                    </button>
                    <button
                        onClick={onBack}
                        className="reset-button"
                        style={{ width: "auto", marginTop: 0, padding: "0.75rem 1.5rem" }}
                    >
                        Cancel
                    </button>
                </div>
            </Shell>
        );
    }

    // ── RENDER: Analyzing ─────────────────────────────────────────────────────
    if (searchPhase === "analyzing") {
        return (
            <Shell>
                <PageHeader title="Scraping Reviews & Running SWOT..." />
                <ProgressBar value={progress} color="linear-gradient(to right, #10b981, #059669)" />
                <div style={{
                    background: "#1f2937", borderRadius: 12, padding: 20,
                    border: "1px solid #374151",
                }}>
                    <p style={{ color: "#d1d5db", margin: "0 0 10px", fontWeight: 600 }}>
                        {statusMessage || "Processing..."}
                    </p>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {[
                            { step: 1, label: "Finding reviews for each place", done: progress > 10 },
                            { step: 2, label: "Running sentiment analysis on reviews", done: progress > 60 },
                            { step: 3, label: "Generating individual SWOT reports", done: progress > 80 },
                            { step: 4, label: "Building combined competitive analysis", done: progress >= 100 },
                        ].map(({ step, label, done }) => (
                            <div key={step} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <div style={{
                                    width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                                    background: done ? "linear-gradient(to right, #10b981, #059669)" : "#374151",
                                    display: "flex", alignItems: "center", justifyContent: "center",
                                    fontSize: 11, color: "#fff", fontWeight: 700,
                                }}>
                                    {done ? "✓" : step}
                                </div>
                                <span style={{ fontSize: "0.82rem", color: done ? "#10b981" : "#6b7280" }}>
                                    {label}
                                </span>
                            </div>
                        ))}
                    </div>
                    <p style={{ color: "#4b5563", margin: "12px 0 0", fontSize: "0.75rem" }}>
                        This takes a while depending on the number of places. Please keep this tab open.
                    </p>
                </div>
            </Shell>
        );
    }

    // ── RENDER: Complete ──────────────────────────────────────────────────────
    if (searchPhase === "complete") {
        return <ResultsScreen
            swotResults={swotResults}
            competitiveAnalysis={competitiveAnalysis}
            establishmentName={establishmentName || establishmentNameProp}
            keyword={keyword || keywordProp}
            city={city || cityProp}
            onBack={onBack}
        />;
    }
}

// ── Results screen (separate component to keep it clean) ──────────────────
function ResultsScreen({ swotResults, competitiveAnalysis, establishmentName, keyword, city, onBack }) {
    const [expandedIdx, setExpandedIdx] = useState(null);
    const [activeTab, setActiveTab] = useState("individual"); // "individual" | "combined"

    // ── Download individual report as text file ───────────────────────────
    const downloadIndividual = (result) => {
        const isUser = result.name === establishmentName;
        const lines = [
            `SWOT ANALYSIS REPORT`,
            `${"=".repeat(60)}`,
            ``,
            `${isUser ? "YOUR ESTABLISHMENT: " : ""}${result.name}`,
            result.rating ? `Rating:          ★ ${result.rating}` : "",
            result.review_count > 0 ? `Reviews:         ${result.review_count.toLocaleString()}` : "",
            result.scraped_count > 0 ? `Reviews Scraped: ${result.scraped_count}` : "",
            `Sentiment Score: ${result.sentiment_score > 0 ? "+" : ""}${result.sentiment_score} (${result.sentiment_score > 0.2 ? "Positive" : result.sentiment_score < -0.1 ? "Negative" : "Neutral"})`,
            ``,
            `STRENGTHS`,
            `${"-".repeat(40)}`,
            ...(result.swot?.strengths || []).map(s => `  • ${s}`),
            ``,
            `WEAKNESSES`,
            `${"-".repeat(40)}`,
            ...(result.swot?.weaknesses || []).map(w => `  • ${w}`),
            ``,
            `OPPORTUNITIES`,
            `${"-".repeat(40)}`,
            ...(result.swot?.opportunities || []).map(o => `  • ${o}`),
            ``,
            `THREATS`,
            `${"-".repeat(40)}`,
            ...(result.swot?.threats || []).map(t => `  • ${t}`),
            ``,
            `Generated by DoWell Samanta AI`,
        ].filter(l => l !== undefined);

        const blob = new Blob([lines.join("\n")], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `swot_${result.name.replace(/[^a-z0-9]/gi, "_").toLowerCase()}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    };

    // ── Download combined report ──────────────────────────────────────────
    const downloadCombined = () => {
        if (!competitiveAnalysis) return;
        const ca = competitiveAnalysis;
        const lines = [
            `COMPETITIVE ANALYSIS REPORT`,
            `${"=".repeat(60)}`,
            `Keyword:  ${keyword}`,
            `Location: ${city}`,
            ``,
            `MARKET OVERVIEW`,
            `${"-".repeat(40)}`,
            `Total Analysed:    ${ca.total_analyzed}`,
            `Average Rating:    ★ ${ca.average_rating}`,
            `Average Sentiment: ${ca.average_sentiment}`,
            `Market Leader:     ${ca.market_leader} (★${ca.market_leader_rating})`,
            `Lowest Rated:      ${ca.lowest_rated} (★${ca.lowest_rated_rating})`,
            ``,
            `MARKET INSIGHTS`,
            `${"-".repeat(40)}`,
            ...(ca.market_insights || []).map(i => `  • ${i}`),
            ``,
            `COMMON STRENGTHS ACROSS MARKET`,
            `${"-".repeat(40)}`,
            ...(ca.common_strengths || []).map(([s, c]) => `  • ${s} (${c} places)`),
            ``,
            `COMMON WEAKNESSES ACROSS MARKET`,
            `${"-".repeat(40)}`,
            ...(ca.common_weaknesses || []).map(([w, c]) => `  • ${w} (${c} places)`),
            ``,
            `INDIVIDUAL RESULTS SUMMARY`,
            `${"-".repeat(40)}`,
            ...(swotResults || []).map((r, i) =>
                `  ${i + 1}. ${r.name}${r.name === establishmentName ? " [YOUR PLACE]" : ""} — ★${r.rating || "N/A"} — Sentiment: ${r.sentiment_score}`
            ),
            ``,
            `Generated by DoWell Samanta AI`,
        ];

        const blob = new Blob([lines.join("\n")], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `competitive_analysis_${city.replace(/[^a-z0-9]/gi, "_").toLowerCase()}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const swotColors = [
        { key: "strengths", label: "Strengths", color: "#10b981", bg: "rgba(16,185,129,0.08)", border: "rgba(16,185,129,0.2)" },
        { key: "weaknesses", label: "Weaknesses", color: "#ef4444", bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.2)" },
        { key: "opportunities", label: "Opportunities", color: "#3b82f6", bg: "rgba(59,130,246,0.08)", border: "rgba(59,130,246,0.2)" },
        { key: "threats", label: "Threats", color: "#f59e0b", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.2)" },
    ];

    // Sort: user's place first, then by rating desc
    const sorted = [...(swotResults || [])].sort((a, b) => {
        if (a.name === establishmentName) return -1;
        if (b.name === establishmentName) return 1;
        return (b.rating || 0) - (a.rating || 0);
    });

    return (
        <div className="app-container">
            <div className="animated-background">
                <div className="gradient-overlay" />
                <div className="dot-pattern" />
            </div>
            <div className="content-container">
                <div style={{ width: "100%", maxWidth: 1000, margin: "0 auto", padding: "2.5rem 1.5rem" }}>

                    {/* Back */}
                    <button onClick={onBack} style={{
                        display: "flex", alignItems: "center", gap: 6,
                        background: "none", border: "none", color: "#a78bfa",
                        cursor: "pointer", fontSize: "0.85rem", fontWeight: 600,
                        marginBottom: 20, padding: 0,
                    }}>
                        <FaArrowLeft style={{ fontSize: 12 }} /> Back to Search
                    </button>

                    {/* Title */}
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
                        <h2 style={{
                            margin: 0, fontSize: "1.4rem", fontWeight: 700,
                            background: "linear-gradient(to right, #a78bfa, #818cf8)",
                            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                        }}>
                            Analysis Results — {sorted.length} Places
                        </h2>
                    </div>

                    {/* Tab switcher */}
                    <div style={{ display: "flex", gap: 4, marginBottom: 20, background: "#1f2937", borderRadius: 10, padding: 4 }}>
                        {[
                            { id: "individual", label: `Individual Reports (${sorted.length})` },
                            { id: "combined", label: "Combined Competitive Analysis" },
                        ].map(tab => (
                            <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
                                flex: 1, padding: "8px 12px", borderRadius: 8, border: "none",
                                cursor: "pointer", fontSize: "0.85rem", fontWeight: 600, transition: "all 0.2s",
                                background: activeTab === tab.id ? "linear-gradient(to right, #9333ea, #4f46e5)" : "transparent",
                                color: activeTab === tab.id ? "#fff" : "#6b7280",
                            }}>
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    {/* ── Individual reports tab ──────────────────────────────── */}
                    {activeTab === "individual" && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {sorted.map((result, idx) => {
                                const isUser = result.name === establishmentName;
                                const isExpanded = expandedIdx === idx;
                                const sentPos = result.sentiment_score > 0.2;
                                const sentNeg = result.sentiment_score < -0.1;

                                return (
                                    <div key={idx} style={{
                                        background: isUser ? "rgba(245,158,11,0.06)" : "#1A1E2E",
                                        borderRadius: 12,
                                        border: `1px solid ${isUser ? "#f59e0b" : isExpanded ? "#9333ea" : "#374151"}`,
                                        overflow: "hidden",
                                        transition: "border-color 0.2s",
                                    }}>
                                        {/* Row header — always visible, click to expand */}
                                        <div
                                            onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                                            style={{
                                                padding: "14px 18px",
                                                display: "flex", alignItems: "center", gap: 12,
                                                cursor: "pointer",
                                            }}
                                        >
                                            {/* Expand chevron */}
                                            <span style={{
                                                fontSize: 12, color: "#6b7280", flexShrink: 0,
                                                transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)",
                                                transition: "transform 0.2s", display: "inline-block",
                                            }}>▶</span>

                                            {/* Rank number */}
                                            <span style={{
                                                width: 26, height: 26, borderRadius: "50%", flexShrink: 0,
                                                background: isUser ? "#f59e0b" : "#1f2937",
                                                border: `1px solid ${isUser ? "#f59e0b" : "#374151"}`,
                                                display: "flex", alignItems: "center", justifyContent: "center",
                                                fontSize: "0.72rem", fontWeight: 700,
                                                color: isUser ? "#000" : "#9ca3af",
                                            }}>
                                                {isUser ? "★" : idx + 1}
                                            </span>

                                            {/* Name + badges */}
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                                    {isUser && (
                                                        <span style={{
                                                            fontSize: "0.6rem", background: "#f59e0b", color: "#000",
                                                            padding: "1px 5px", borderRadius: 3, fontWeight: 800,
                                                        }}>YOUR PLACE</span>
                                                    )}
                                                    <span style={{
                                                        fontWeight: 700, fontSize: "0.92rem",
                                                        color: isUser ? "#fbbf24" : "#f1f1f1",
                                                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                                                    }}>
                                                        {result.name}
                                                    </span>
                                                </div>
                                                <div style={{ display: "flex", gap: 10, fontSize: "0.72rem", color: "#6b7280", marginTop: 2, flexWrap: "wrap" }}>
                                                    {result.rating && (
                                                        <span style={{ color: "#f59e0b", display: "flex", alignItems: "center", gap: 2 }}>
                                                            <FaStar style={{ fontSize: 9 }} /> {result.rating}
                                                        </span>
                                                    )}
                                                    {result.review_count > 0 && <span>{result.review_count.toLocaleString()} reviews</span>}
                                                    {result.scraped_count > 0 && <span style={{ color: "#4b5563" }}>{result.scraped_count} scraped</span>}
                                                    <span style={{ color: sentPos ? "#10b981" : sentNeg ? "#ef4444" : "#6b7280" }}>
                                                        {sentPos ? "▲ Positive" : sentNeg ? "▼ Negative" : "→ Neutral"}
                                                    </span>
                                                </div>
                                            </div>

                                            {/* Download button */}
                                            <button
                                                onClick={(e) => { e.stopPropagation(); downloadIndividual(result); }}
                                                style={{
                                                    padding: "5px 12px", borderRadius: 6, border: "1px solid #374151",
                                                    background: "transparent", color: "#9ca3af", fontSize: "0.75rem",
                                                    cursor: "pointer", flexShrink: 0, whiteSpace: "nowrap",
                                                    transition: "all 0.2s",
                                                }}
                                                title="Download this report as .txt"
                                            >
                                                ↓ Download
                                            </button>
                                        </div>

                                        {/* Expanded SWOT content */}
                                        {isExpanded && (
                                            <div style={{ padding: "0 18px 18px", borderTop: "1px solid #1f2937" }}>
                                                <div style={{ paddingTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                                                    {swotColors.map(({ key, label, color, bg, border }) => (
                                                        <div key={key} style={{ background: bg, borderRadius: 10, padding: "10px 12px", border: `1px solid ${border}` }}>
                                                            <div style={{
                                                                fontSize: "0.65rem", fontWeight: 700, color,
                                                                textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 7,
                                                            }}>
                                                                {label}
                                                            </div>
                                                            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                                                                {(result.swot?.[key] || []).map((item, i) => (
                                                                    <li key={i} style={{
                                                                        fontSize: "0.78rem", color: "#d1d5db",
                                                                        marginBottom: 5, paddingLeft: 10, position: "relative",
                                                                        lineHeight: 1.4,
                                                                    }}>
                                                                        <span style={{ position: "absolute", left: 0, color }}>·</span>
                                                                        {item}
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    {/* ── Combined analysis tab ───────────────────────────────── */}
                    {activeTab === "combined" && competitiveAnalysis && (
                        <div>
                            {/* Download combined */}
                            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
                                <button
                                    onClick={downloadCombined}
                                    style={{
                                        padding: "8px 18px", borderRadius: 8,
                                        background: "linear-gradient(to right, #9333ea, #4f46e5)",
                                        border: "none", color: "#fff", fontSize: "0.82rem",
                                        fontWeight: 600, cursor: "pointer",
                                    }}
                                >
                                    ↓ Download Full Report
                                </button>
                            </div>

                            {/* Stats tiles */}
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12, marginBottom: 20 }}>
                                {[
                                    { label: "Total Analysed", value: competitiveAnalysis.total_analyzed, color: "#a78bfa" },
                                    { label: "Average Rating", value: `★ ${competitiveAnalysis.average_rating}`, color: "#f59e0b" },
                                    { label: "Avg Sentiment", value: competitiveAnalysis.average_sentiment, color: competitiveAnalysis.average_sentiment > 0 ? "#10b981" : "#ef4444" },
                                    { label: "Market Leader", value: competitiveAnalysis.market_leader, color: "#10b981", small: true },
                                    { label: "Leader Rating", value: `★ ${competitiveAnalysis.market_leader_rating}`, color: "#10b981" },
                                    { label: "Lowest Rated", value: competitiveAnalysis.lowest_rated, color: "#ef4444", small: true },
                                ].map(({ label, value, color, small }) => (
                                    <div key={label} style={{
                                        background: "#1A1E2E", borderRadius: 10, padding: "14px 16px",
                                        border: "1px solid #374151",
                                    }}>
                                        <div style={{ fontSize: "0.65rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>{label}</div>
                                        <div style={{ fontSize: small ? "0.82rem" : "1.25rem", fontWeight: 700, color, lineHeight: 1.2 }}>{value}</div>
                                    </div>
                                ))}
                            </div>

                            {/* Insights */}
                            {competitiveAnalysis.market_insights?.length > 0 && (
                                <div style={{
                                    background: "#1A1E2E", borderRadius: 12, padding: 18,
                                    border: "1px solid #374151", marginBottom: 20,
                                }}>
                                    <h4 style={{ margin: "0 0 12px", color: "#a78bfa", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                                        Market Insights
                                    </h4>
                                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                        {competitiveAnalysis.market_insights.map((insight, i) => (
                                            <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                                                <span style={{ color: "#9333ea", fontSize: "1rem", lineHeight: 1, flexShrink: 0 }}>💡</span>
                                                <p style={{ margin: 0, fontSize: "0.85rem", color: "#d1d5db", lineHeight: 1.5 }}>{insight}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Common themes side by side */}
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 20 }}>
                                {[
                                    { label: "Common Strengths Across Market", data: competitiveAnalysis.common_strengths, color: "#10b981", bg: "rgba(16,185,129,0.06)", border: "rgba(16,185,129,0.2)" },
                                    { label: "Common Weaknesses Across Market", data: competitiveAnalysis.common_weaknesses, color: "#ef4444", bg: "rgba(239,68,68,0.06)", border: "rgba(239,68,68,0.2)" },
                                ].map(({ label, data, color, bg, border }) => (
                                    <div key={label} style={{ background: bg, borderRadius: 12, padding: 16, border: `1px solid ${border}` }}>
                                        <h4 style={{ margin: "0 0 12px", color, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                                            {label}
                                        </h4>
                                        {(data || []).map(([item, count], i) => (
                                            <div key={i} style={{ marginBottom: 8 }}>
                                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                                                    <span style={{ fontSize: "0.78rem", color: "#d1d5db" }}>{item}</span>
                                                    <span style={{ fontSize: "0.7rem", color, fontWeight: 700 }}>{count}</span>
                                                </div>
                                                <div style={{ height: 3, background: "#1f2937", borderRadius: 2, overflow: "hidden" }}>
                                                    <div style={{
                                                        height: "100%", borderRadius: 2,
                                                        width: `${(count / (swotResults.length || 1)) * 100}%`,
                                                        background: color, transition: "width 0.5s",
                                                    }} />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ))}
                            </div>

                            {/* Summary table of all places */}
                            <div style={{
                                background: "#1A1E2E", borderRadius: 12,
                                border: "1px solid #374151", overflow: "hidden",
                            }}>
                                <div style={{
                                    padding: "12px 16px", background: "#252B3E",
                                    borderBottom: "1px solid #374151",
                                    display: "grid", gridTemplateColumns: "1fr 80px 80px 100px",
                                    fontSize: "0.7rem", fontWeight: 700, color: "#6b7280",
                                    textTransform: "uppercase", letterSpacing: "0.05em",
                                }}>
                                    <span>Establishment</span>
                                    <span style={{ textAlign: "center" }}>Rating</span>
                                    <span style={{ textAlign: "center" }}>Sentiment</span>
                                    <span style={{ textAlign: "center" }}>Reviews</span>
                                </div>
                                {sorted.map((r, i) => {
                                    const isUser = r.name === establishmentName;
                                    return (
                                        <div key={i} style={{
                                            padding: "10px 16px",
                                            borderBottom: i < sorted.length - 1 ? "1px solid #1f2937" : "none",
                                            display: "grid", gridTemplateColumns: "1fr 80px 80px 100px",
                                            alignItems: "center",
                                            background: isUser ? "rgba(245,158,11,0.05)" : "transparent",
                                        }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                                {isUser && (
                                                    <span style={{
                                                        fontSize: "0.55rem", background: "#f59e0b", color: "#000",
                                                        padding: "1px 4px", borderRadius: 3, fontWeight: 800,
                                                    }}>YOU</span>
                                                )}
                                                <span style={{ fontSize: "0.82rem", color: isUser ? "#fbbf24" : "#d1d5db", fontWeight: isUser ? 700 : 400 }}>
                                                    {r.name}
                                                </span>
                                            </div>
                                            <span style={{ textAlign: "center", color: "#f59e0b", fontSize: "0.82rem" }}>
                                                {r.rating ? `★ ${r.rating}` : "—"}
                                            </span>
                                            <span style={{
                                                textAlign: "center", fontSize: "0.78rem",
                                                color: r.sentiment_score > 0.2 ? "#10b981" : r.sentiment_score < -0.1 ? "#ef4444" : "#6b7280",
                                            }}>
                                                {r.sentiment_score > 0.2 ? "▲ Pos" : r.sentiment_score < -0.1 ? "▼ Neg" : "→ Neu"}
                                            </span>
                                            <span style={{ textAlign: "center", fontSize: "0.78rem", color: "#6b7280" }}>
                                                {r.review_count ? r.review_count.toLocaleString() : "—"}
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
}