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
  const hasProps = Boolean(keywordProp && cityProp && countryProp);
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

  useEffect(() => {
    if (!searchTaskId) return;
    const pollProgress = async () => {
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
    pollProgress();
    pollIntervalRef.current = setInterval(pollProgress, 2000);
    return () => clearInterval(pollIntervalRef.current);
  }, [searchTaskId]);

  const startSearch = async (kw, ct, cntry, radius, estName) => {
    try {
      const resp = await axios.post(`${BASE}/api/competitors/search`, {
        keyword: kw, city: ct, country: cntry,
        establishment_name: estName, radius_km: radius, limit: 100,
      });
      setSearchTaskId(resp.data.task_id);
      setSearchPhase("searching");
      setProgress(0);
      setStatusMessage("Searching Google Maps...");
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
      await axios.post(`${BASE}/api/competitors/approve-and-analyze`, {
        task_id: searchTaskId, approved_places: approvedPlaces,
      });
      setSearchPhase("analyzing");
      setProgress(0);
      setStatusMessage("Running SWOT analysis...");
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
        <PageHeader title="Searching Google Maps..." />
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
            Scraping Google Maps for <strong style={{ color: "#a78bfa" }}>{keyword}</strong> in <strong style={{ color: "#a78bfa" }}>{city}</strong>
          </p>
          <p style={{ color: "#6b7280", margin: "6px 0 0", fontSize: "0.8rem" }}>
            This may take 1–2 minutes. Please wait.
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
        <PageHeader title="Running SWOT Analysis..." />
        <ProgressBar value={progress} color="linear-gradient(to right, #10b981, #059669)" />
        <div style={{
          background: "#1f2937", borderRadius: 12, padding: 20,
          border: "1px solid #374151", textAlign: "center",
        }}>
          <p style={{ color: "#d1d5db", margin: 0 }}>
            Analysing <strong style={{ color: "#10b981" }}>{selectedCount}</strong> places using NLTK sentiment analysis
          </p>
          <p style={{ color: "#6b7280", margin: "6px 0 0", fontSize: "0.8rem" }}>
            No API calls — running locally on server
          </p>
        </div>
      </Shell>
    );
  }

  // ── RENDER: Complete ──────────────────────────────────────────────────────
  if (searchPhase === "complete") {
    return (
      <div className="app-container">
        <div className="animated-background">
          <div className="gradient-overlay" />
          <div className="dot-pattern" />
        </div>
        <div className="content-container">
          <div className="main-content" style={{ maxWidth: 1200, width: "100%" }}>
            <div style={{ width: "100%", padding: "2.5rem 1.5rem" }}>

              {/* Back button */}
              <button
                onClick={onBack}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  background: "none", border: "none", color: "#a78bfa",
                  cursor: "pointer", fontSize: "0.85rem", fontWeight: 600,
                  marginBottom: 20, padding: 0,
                }}
              >
                <FaArrowLeft style={{ fontSize: 12 }} /> Back to Search
              </button>

              <h2 style={{
                margin: "0 0 24px", fontSize: "1.4rem", fontWeight: 700,
                background: "linear-gradient(to right, #a78bfa, #818cf8)",
                WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
              }}>
                SWOT Analysis Results
              </h2>

              {/* Market overview card */}
              {competitiveAnalysis && (
                <div style={{
                  background: "#1A1E2E", borderRadius: 16, padding: 24,
                  border: "1px solid #374151", marginBottom: 24,
                  boxShadow: "0 25px 50px -12px rgba(0,0,0,0.25)",
                }}>
                  <h3 style={{ margin: "0 0 16px", color: "#a78bfa", fontSize: "1rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Market Overview
                  </h3>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 16 }}>
                    {[
                      { label: "Analysed", value: competitiveAnalysis.total_competitors_analyzed, color: "#a78bfa" },
                      { label: "Avg Rating", value: `${competitiveAnalysis.average_rating} / 5`, color: "#f59e0b" },
                      { label: "Market Leader", value: competitiveAnalysis.market_leader, color: "#10b981", small: true },
                      { label: "Leader Rating", value: `★ ${competitiveAnalysis.market_leader_rating}`, color: "#10b981" },
                    ].map(({ label, value, color, small }) => (
                      <div key={label} style={{
                        background: "#1f2937", borderRadius: 10, padding: "14px 16px",
                        border: "1px solid #374151",
                      }}>
                        <div style={{ fontSize: "0.7rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>{label}</div>
                        <div style={{ fontSize: small ? "0.85rem" : "1.3rem", fontWeight: 700, color }}>{value}</div>
                      </div>
                    ))}
                  </div>
                  {competitiveAnalysis.market_insights?.length > 0 && (
                    <div style={{ background: "rgba(147,51,234,0.1)", borderRadius: 8, padding: "10px 14px", border: "1px solid rgba(147,51,234,0.2)" }}>
                      <p style={{ margin: 0, fontSize: "0.85rem", color: "#d1d5db" }}>
                        💡 {competitiveAnalysis.market_insights[0]}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* SWOT cards grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
                {swotResults.map((result, idx) => {
                  const isUser = result.name === (establishmentName || establishmentNameProp);
                  return (
                    <div key={idx} style={{
                      background: isUser ? "rgba(245,158,11,0.08)" : "#1A1E2E",
                      borderRadius: 14, padding: 18,
                      border: `1px solid ${isUser ? "#f59e0b" : "#374151"}`,
                      boxShadow: "0 4px 24px rgba(0,0,0,0.2)",
                    }}>
                      {/* Card header */}
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                          {isUser && (
                            <span style={{
                              fontSize: "0.65rem", background: "#f59e0b",
                              color: "#000", padding: "1px 6px", borderRadius: 4, fontWeight: 800,
                            }}>YOUR PLACE</span>
                          )}
                          <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700, color: isUser ? "#fbbf24" : "#f1f1f1" }}>
                            {result.name}
                          </h4>
                        </div>
                        <div style={{ display: "flex", gap: 12, fontSize: "0.75rem", color: "#6b7280" }}>
                          {result.rating && (
                            <span style={{ color: "#f59e0b", display: "flex", alignItems: "center", gap: 3 }}>
                              <FaStar style={{ fontSize: 10 }} /> {result.rating}
                            </span>
                          )}
                          {result.review_count > 0 && <span>{result.review_count.toLocaleString()} reviews</span>}
                          <span style={{ color: result.sentiment_score > 0 ? "#10b981" : "#ef4444" }}>
                            {result.sentiment_score > 0 ? "▲ Positive" : "▼ Neutral"}
                          </span>
                        </div>
                      </div>

                      {/* SWOT grid */}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                        {[
                          { key: "strengths",    label: "Strengths",    color: "#10b981", bg: "rgba(16,185,129,0.08)",  border: "rgba(16,185,129,0.2)"  },
                          { key: "weaknesses",   label: "Weaknesses",   color: "#ef4444", bg: "rgba(239,68,68,0.08)",   border: "rgba(239,68,68,0.2)"   },
                          { key: "opportunities",label: "Opportunities", color: "#3b82f6", bg: "rgba(59,130,246,0.08)",  border: "rgba(59,130,246,0.2)"  },
                          { key: "threats",      label: "Threats",      color: "#f59e0b", bg: "rgba(245,158,11,0.08)",  border: "rgba(245,158,11,0.2)"  },
                        ].map(({ key, label, color, bg, border }) => (
                          <div key={key} style={{ background: bg, borderRadius: 8, padding: "8px 10px", border: `1px solid ${border}` }}>
                            <div style={{ fontSize: "0.65rem", fontWeight: 700, color, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 5 }}>
                              {label}
                            </div>
                            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                              {(result.swot[key] || []).map((item, i) => (
                                <li key={i} style={{ fontSize: "0.72rem", color: "#d1d5db", marginBottom: 3, paddingLeft: 8, position: "relative" }}>
                                  <span style={{ position: "absolute", left: 0, color }}>·</span>
                                  {item}
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

            </div>
          </div>
        </div>
      </div>
    );
  }
}