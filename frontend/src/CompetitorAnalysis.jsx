/**
 * CompetitorAnalysis.jsx
 * ----------------------
 * Two-view component:
 * 1. Search for competitors + approve/edit list
 * 2. View SWOT analysis results with competitive summary
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { FaSearch, FaTimes, FaCheckCircle } from "react-icons/fa";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const BASE = API_BASE_URL.replace(/\/+$/, "");

export default function CompetitorAnalysis({ baseUrl = BASE, onBack }) {
  // Search phase
  const [searchPhase, setSearchPhase] = useState("input"); // "input" | "approving" | "analyzing" | "complete"
  const [keyword, setKeyword] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [establishmentName, setEstablishmentName] = useState("");
  const [radiusKm, setRadiusKm] = useState(5);
  const [searchTaskId, setSearchTaskId] = useState(null);
  
  // Approval phase
  const [places, setPlaces] = useState([]);
  const [checkedPlaces, setCheckedPlaces] = useState({});
  
  // Results phase
  const [swotResults, setSwotResults] = useState([]);
  const [competitiveAnalysis, setCompetitiveAnalysis] = useState(null);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  
  const pollIntervalRef = useRef(null);

  // Poll task progress
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
          (data.places || []).forEach((p, i) => {
            checked[i] = p.selected !== false;
          });
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

  // Start search
  const handleStartSearch = async (e) => {
    e.preventDefault();
    if (!keyword || !city || !country || !establishmentName) {
      alert("Please fill in all fields");
      return;
    }

    try {
      const resp = await axios.post(`${BASE}/api/competitors/search`, {
        keyword,
        city,
        country,
        establishment_name: establishmentName,
        radius_km: radiusKm,
        limit: 100,
      });

      setSearchTaskId(resp.data.task_id);
      setSearchPhase("searching");
      setProgress(0);
      setStatusMessage("Starting search...");
    } catch (err) {
      alert(`Search failed: ${err.message}`);
    }
  };

  // Approve and analyze
  const handleApproveAndAnalyze = async () => {
    const approvedPlaces = places.map((place, i) => ({
      ...place,
      selected: checkedPlaces[i] !== false,
    }));

    try {
      const resp = await axios.post(`${BASE}/api/competitors/approve-and-analyze`, {
        task_id: searchTaskId,
        approved_places: approvedPlaces,
      });

      setSearchPhase("analyzing");
      setProgress(0);
      setStatusMessage("Analyzing SWOT...");
    } catch (err) {
      alert(`Analysis failed: ${err.message}`);
    }
  };

  // Toggle place selection
  const togglePlace = (index) => {
    setCheckedPlaces((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER: Input phase
  // ─────────────────────────────────────────────────────────────────────────
  if (searchPhase === "input") {
    return (
      <div style={{ maxWidth: 600, margin: "0 auto", padding: 20 }}>
        <h2>Competitor Analysis</h2>
        <p style={{ color: "#666", marginBottom: 20 }}>
          Search for competitors, review the list, then run SWOT analysis on all of them.
        </p>

        <form onSubmit={handleStartSearch} style={{ display: "flex", flexDirection: "column", gap: 15 }}>
          <div>
            <label style={{ display: "block", marginBottom: 5, fontWeight: 600 }}>
              Your Establishment Name
            </label>
            <input
              type="text"
              value={establishmentName}
              onChange={(e) => setEstablishmentName(e.target.value)}
              placeholder="e.g. Blue Tokai Coffee"
              style={{
                width: "100%",
                padding: 10,
                borderRadius: 8,
                border: "1px solid #ddd",
                fontSize: 14,
                boxSizing: "border-box",
              }}
              required
            />
          </div>

          <div>
            <label style={{ display: "block", marginBottom: 5, fontWeight: 600 }}>
              Keyword / Category
            </label>
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="e.g. Cafe, Restaurant"
              style={{
                width: "100%",
                padding: 10,
                borderRadius: 8,
                border: "1px solid #ddd",
                fontSize: 14,
                boxSizing: "border-box",
              }}
              required
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ display: "block", marginBottom: 5, fontWeight: 600 }}>
                City
              </label>
              <input
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="e.g. Delhi"
                style={{
                  width: "100%",
                  padding: 10,
                  borderRadius: 8,
                  border: "1px solid #ddd",
                  fontSize: 14,
                  boxSizing: "border-box",
                }}
                required
              />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 5, fontWeight: 600 }}>
                Country
              </label>
              <input
                type="text"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="e.g. India"
                style={{
                  width: "100%",
                  padding: 10,
                  borderRadius: 8,
                  border: "1px solid #ddd",
                  fontSize: 14,
                  boxSizing: "border-box",
                }}
                required
              />
            </div>
          </div>

          <div>
            <label style={{ display: "block", marginBottom: 5, fontWeight: 600 }}>
              Search Radius (km)
            </label>
            <input
              type="number"
              min="1"
              max="50"
              value={radiusKm}
              onChange={(e) => setRadiusKm(Number(e.target.value))}
              style={{
                width: "100%",
                padding: 10,
                borderRadius: 8,
                border: "1px solid #ddd",
                fontSize: 14,
                boxSizing: "border-box",
              }}
            />
          </div>

          <button
            type="submit"
            style={{
              padding: "10px 20px",
              background: "#0ea5e9",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <FaSearch style={{ marginRight: 8 }} />
            Search Competitors
          </button>

          <button
            type="button"
            onClick={onBack}
            style={{
              padding: "10px 20px",
              background: "transparent",
              color: "#0ea5e9",
              border: "1px solid #0ea5e9",
              borderRadius: 8,
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Back
          </button>
        </form>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER: Searching / Approving phase
  // ─────────────────────────────────────────────────────────────────────────
  if (searchPhase === "searching" || searchPhase === "approving") {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: 20 }}>
        <h2>Competitor Search</h2>
        
        {searchPhase === "searching" && (
          <div style={{ marginBottom: 20 }}>
            <p>{statusMessage}</p>
            <div style={{
              width: "100%",
              height: 20,
              background: "#e5e7eb",
              borderRadius: 10,
              overflow: "hidden",
            }}>
              <div style={{
                width: `${progress}%`,
                height: "100%",
                background: "#0ea5e9",
                transition: "width 0.3s",
              }} />
            </div>
          </div>
        )}

        {searchPhase === "approving" && places.length > 0 && (
          <div>
            <p style={{ marginBottom: 15, color: "#666" }}>
              Found {places.length} places. Uncheck any you want to exclude, then click "Analyze".
            </p>

            <div style={{
              maxHeight: 500,
              overflowY: "auto",
              border: "1px solid #ddd",
              borderRadius: 8,
              marginBottom: 20,
            }}>
              {places.map((place, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: 12,
                    borderBottom: idx < places.length - 1 ? "1px solid #eee" : "none",
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checkedPlaces[idx] !== false}
                    onChange={() => togglePlace(idx)}
                    style={{ width: 18, height: 18, cursor: "pointer" }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600 }}>{place.name}</div>
                    <div style={{ fontSize: 12, color: "#666" }}>
                      {place.address}
                      {place.rating && ` • ★${place.rating}`}
                      {place.reviews > 0 && ` • ${place.reviews} reviews`}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={handleApproveAndAnalyze}
                style={{
                  flex: 1,
                  padding: "10px 20px",
                  background: "#10b981",
                  color: "#fff",
                  border: "none",
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                <FaCheckCircle style={{ marginRight: 8 }} />
                Analyze Selected Places
              </button>
              <button
                onClick={onBack}
                style={{
                  padding: "10px 20px",
                  background: "transparent",
                  border: "1px solid #ddd",
                  borderRadius: 8,
                  fontSize: 14,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER: Analyzing / Complete phase
  // ─────────────────────────────────────────────────────────────────────────
  if (searchPhase === "analyzing" || searchPhase === "complete") {
    return (
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: 20 }}>
        <h2>SWOT Analysis Results</h2>

        {searchPhase === "analyzing" && (
          <div style={{ marginBottom: 20 }}>
            <p>{statusMessage}</p>
            <div style={{
              width: "100%",
              height: 20,
              background: "#e5e7eb",
              borderRadius: 10,
              overflow: "hidden",
            }}>
              <div style={{
                width: `${progress}%`,
                height: "100%",
                background: "#10b981",
                transition: "width 0.3s",
              }} />
            </div>
          </div>
        )}

        {searchPhase === "complete" && (
          <div>
            {/* Competitive Analysis Summary */}
            {competitiveAnalysis && (
              <div style={{
                background: "#f0f9ff",
                border: "1px solid #0ea5e9",
                borderRadius: 8,
                padding: 15,
                marginBottom: 20,
              }}>
                <h3 style={{ marginTop: 0 }}>Market Overview</h3>
                <p><strong>Total Analyzed:</strong> {competitiveAnalysis.total_competitors_analyzed}</p>
                <p><strong>Average Rating:</strong> {competitiveAnalysis.average_rating}/5</p>
                <p><strong>Market Leader:</strong> {competitiveAnalysis.market_leader} ({competitiveAnalysis.market_leader_rating}★)</p>
                <p><strong>Key Insight:</strong> {competitiveAnalysis.market_insights?.[0]}</p>
              </div>
            )}

            {/* Individual SWOT Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(350px, 1fr))", gap: 15 }}>
              {swotResults.map((result, idx) => (
                <div
                  key={idx}
                  style={{
                    border: "1px solid #ddd",
                    borderRadius: 8,
                    padding: 15,
                    background: result.name === establishmentName ? "#fef3c7" : "#fff",
                  }}
                >
                  <h4 style={{ margin: "0 0 10px 0" }}>
                    {result.name}
                    {result.rating && ` (★${result.rating})`}
                  </h4>

                  <div style={{ fontSize: 12, marginBottom: 10 }}>
                    <div>📊 Sentiment: <strong>{result.sentiment_score > 0 ? "Positive" : "Neutral"}</strong></div>
                  </div>

                  <div style={{ fontSize: 12 }}>
                    <div style={{ marginBottom: 8 }}>
                      <strong style={{ color: "#10b981" }}>Strengths:</strong>
                      <ul style={{ margin: "4px 0", paddingLeft: 16 }}>
                        {result.swot.strengths.map((s, i) => (
                          <li key={i} style={{ fontSize: 11 }}>{s}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <strong style={{ color: "#ef4444" }}>Weaknesses:</strong>
                      <ul style={{ margin: "4px 0", paddingLeft: 16 }}>
                        {result.swot.weaknesses.map((w, i) => (
                          <li key={i} style={{ fontSize: 11 }}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
              <button
                onClick={onBack}
                style={{
                  padding: "10px 20px",
                  background: "#0ea5e9",
                  color: "#fff",
                  border: "none",
                  borderRadius: 8,
                  cursor: "pointer",
                }}
              >
                Back
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }
}