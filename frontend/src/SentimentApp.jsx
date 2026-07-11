/**
 * SentimentApp.jsx
 * ----------------
 * Standalone page at /sentiment — direct URL access only.
 * Exact copy of App.jsx with one addition:
 *   "Sentiment Analysis" added as a report type option.
 * When selected, routes to SentimentAnalysis.jsx.
 * Everything else is identical to App.jsx.
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import {
  FaUpload, FaFileDownload, FaTimes, FaSync,
  FaSearch, FaMapMarkerAlt, FaKeyboard,
} from "react-icons/fa";
import API_BASE_URL from "./config";
import SearchResults from "./SearchResults";
import CsvProcessor from "./CsvProcessor";
import SessionPage from "./SessionPage";
import PlacePicker from "./PlacePicker";
import CompetitorAnalysis from "./CompetitorAnalysis";
import SentimentAnalysis from "./SentimentAnalysis";
import "./App.css";

const BASE = API_BASE_URL.replace(/\/+$/, "");
axios.defaults.baseURL = BASE;

const KEYWORD_OPTIONS = [
  { group: "Healthcare",      value: "Hospital" },
  { group: "Healthcare",      value: "Pharmacy" },
  { group: "Food & Beverage", value: "Cafe" },
  { group: "Food & Beverage", value: "Restaurant" },
  { group: "Food & Beverage", value: "Bakery" },
];

const REPORT_TYPES = [
  {
    value:         "swot",
    label:         "SWOT Analysis",
    requiresPlace: true,
    buildPrompt:   (keyword, city, country) =>
      `SWOT Analysis for ${keyword} in ${city}, ${country} — ` +
      `split across geographic quadrants (North, South, East, West). ` +
      `If a specific establishment URL is provided, each quadrant card includes a comparison.`,
  },
  {
    value:         "competitive_swot",
    label:         "Competitive SWOT Analysis",
    requiresPlace: true,
    buildPrompt:   (keyword, city, country) =>
      `Competitive SWOT Analysis — benchmarks your specific ${keyword} ` +
      `against approximately 100 competitors within the selected radius in ${city}, ${country}.`,
  },
  {
    value:         "sentiment",
    label:         "Sentiment Analysis",
    requiresPlace: true,
    buildPrompt:   (keyword, city, country) =>
      `Sentiment Analysis for ${keyword} in ${city}, ${country}`,
  },
];

const SentimentApp = () => {

  // ── Route guard ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (window.location.pathname !== "/sentiment") {
      window.history.replaceState({}, "", "/sentiment");
    }
  }, []);

  // ── Form state ─────────────────────────────────────────────────────────────
  const [keyword,              setKeyword]              = useState("");
  const [selectedReportType,   setSelectedReportType]   = useState(REPORT_TYPES[0].value);
  const [radiusKm,             setRadiusKm]             = useState(5);
  const [placeName,            setPlaceName]            = useState("");
  const [placeCity,            setPlaceCity]            = useState("");
  const [placeCountry,         setPlaceCountry]         = useState("");
  const [placeLat,             setPlaceLat]             = useState(null);
  const [placeLng,             setPlaceLng]             = useState(null);
  const [file,                 setFile]                 = useState(null);

  // ── Task state ─────────────────────────────────────────────────────────────
  const [taskId,               setTaskId]               = useState(null);
  const [progress,             setProgress]             = useState(0);
  const [results,              setResults]              = useState([]);
  const [isRunning,            setIsRunning]            = useState(false);
  const [searchComplete,       setSearchComplete]       = useState(false);

  // ── Navigation ─────────────────────────────────────────────────────────────
  const [searchPayload,        setSearchPayload]        = useState(null);
  const [showCsvProcessor,     setShowCsvProcessor]     = useState(false);
  const [showCompetitorAnalysis, setShowCompetitorAnalysis] = useState(false);
  const [showSentimentAnalysis,  setShowSentimentAnalysis]  = useState(false);

  const intervalRef  = useRef(null);
  const fileInputRef = useRef(null);

  // ── Poll task progress ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!taskId || !isRunning) return;
    intervalRef.current = setInterval(async () => {
      try {
        const r = await axios.get(`/progress/${taskId}`);
        const d = r.data;
        if (d.progress !== undefined) setProgress(d.progress);
        if (d.results?.length > 0)    setResults(d.results);
        if (d.error) {
          setIsRunning(false); setSearchComplete(true);
          clearInterval(intervalRef.current);
        }
        if (!d.running) {
          setIsRunning(false); setSearchComplete(true);
          clearInterval(intervalRef.current);
        }
      } catch (err) {
        console.error("Poll error:", err.message);
        clearInterval(intervalRef.current);
        setIsRunning(false);
      }
    }, 2000);
    return () => clearInterval(intervalRef.current);
  }, [taskId, isRunning]);

  // ── PlacePicker handler — captures lat/lng and city/country ───────────────
  const handlePlaceSelect = (place) => {
    if (!place) {
      setPlaceName(""); setPlaceCity(""); setPlaceCountry("");
      setPlaceLat(null); setPlaceLng(null);
      return;
    }
    const addr = place.address || {};
    setPlaceName(place.name || place.display_name?.split(",")[0]?.trim() || "");
    setPlaceLat(parseFloat(place.lat) || null);
    setPlaceLng(parseFloat(place.lon) || null);
    setPlaceCity(
      addr.city || addr.town || addr.village || addr.county ||
      place.display_name?.split(",").slice(-3, -2)[0]?.trim() || ""
    );
    setPlaceCountry(
      addr.country || place.display_name?.split(",").slice(-1)[0]?.trim() || ""
    );
  };

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!keyword.trim()) {
      alert("Please select a keyword.");
      return;
    }

    const rt = REPORT_TYPES.find(r => r.value === selectedReportType);

    if (selectedReportType === "sentiment") {
      if (!placeName.trim()) {
        alert("Please select your establishment for Sentiment Analysis.");
        return;
      }
      if (!placeCity) {
        alert("Could not determine city from selected place. Please re-select your establishment.");
        return;
      }
      setShowSentimentAnalysis(true);
      return;
    }

    if (selectedReportType === "competitive_swot") {
      if (!placeName.trim()) {
        alert("Please select your establishment for Competitive SWOT Analysis.");
        return;
      }
      setShowCompetitorAnalysis(true);
      return;
    }

    setSearchPayload({
      keyword,
      report_type: selectedReportType,
      city:        placeCity,
      country:     placeCountry,
      radius_km:   radiusKm,
      place_name:  placeName.trim() || undefined,
    });
  };

  // ── Reset ──────────────────────────────────────────────────────────────────
  const handleReset = () => {
    setKeyword(""); setSelectedReportType(REPORT_TYPES[0].value);
    setPlaceName(""); setPlaceCity(""); setPlaceCountry("");
    setPlaceLat(null); setPlaceLng(null);
    setFile(null); setTaskId(null); setProgress(0);
    setResults([]); setIsRunning(false); setSearchComplete(false);
    setSearchPayload(null); setShowCsvProcessor(false);
    setShowCompetitorAnalysis(false); setShowSentimentAnalysis(false);
  };

  const handleCancel = async () => {
    if (!taskId) return;
    try { await axios.post(`/cancel/${taskId}`); } catch {}
    clearInterval(intervalRef.current);
    setTaskId(null); setIsRunning(false); setProgress(0); setSearchComplete(true);
  };

  const handleDownload = async () => {
    if (!taskId) return;
    try {
      const r = await axios.get(`/download/${taskId}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url; a.download = `results_${taskId}.csv`; a.style.display = "none";
      document.body.appendChild(a); a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) { alert("Download failed. Please try again."); }
  };

  // ── Routing ────────────────────────────────────────────────────────────────
  if (showSentimentAnalysis) {
    return (
      <SentimentAnalysis
        baseUrl={BASE}
        onBack={() => setShowSentimentAnalysis(false)}
        city={placeCity}
        country={placeCountry}
        establishmentName={placeName}
        originLat={placeLat}
        originLng={placeLng}
        radiusKm={radiusKm}
        daysBack={30}
      />
    );
  }

  if (showCompetitorAnalysis) {
    return (
      <CompetitorAnalysis
        baseUrl={BASE}
        onBack={() => setShowCompetitorAnalysis(false)}
        keyword={keyword}
        city={placeCity}
        country={placeCountry}
        radiusKm={radiusKm}
        establishmentName={placeName}
        originLat={placeLat}
        originLng={placeLng}
        daysBack={30}
      />
    );
  }

  if (showCsvProcessor) {
    return <CsvProcessor baseUrl={BASE} onBack={() => setShowCsvProcessor(false)} />;
  }

  if (searchPayload) {
    return <SearchResults searchPayload={searchPayload} baseUrl={BASE} onBack={() => setSearchPayload(null)} />;
  }

  // ── Form ──────────────────────────────────────────────────────────────────
  return (
    <div className="app-container">
      <div className="animated-background">
        <div className="gradient-overlay" />
        <div className="dot-pattern" />
      </div>

      <div className="content-container">

        <header className="app-header">
          <div className="header-container">
            <div className="logo-container">
              <div className="logo">
                <img
                  src="https://dowellfileuploader.uxlivinglab.online/hr/logo-2-min-min.png"
                  alt="DoWell logo"
                />
              </div>
              <h1 className="app-title">DoWell Samanta AI</h1>
            </div>
            <div className="app-badge">
              <span>Data Extraction Tool</span>
            </div>
          </div>
        </header>

        <div className="main-content">

          <div className="form-container">
            <div className="gradient-border" />

            <form onSubmit={handleSubmit} className="scraper-form">

              {/* Keyword dropdown */}
              <div className="input-container">
                <FaKeyboard className="input-icon" />
                <select
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  required
                  className="form-input"
                  style={{ cursor: "pointer" }}
                >
                  <option value="" disabled>Select a Keyword</option>
                  {Array.from(new Set(KEYWORD_OPTIONS.map(k => k.group))).map(group => (
                    <optgroup key={group} label={group}>
                      {KEYWORD_OPTIONS.filter(k => k.group === group).map(k => (
                        <option key={k.value} value={k.value}>{k.value}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              {/* Report Type dropdown */}
              <div className="input-container">
                <FaSearch className="input-icon" />
                <select
                  value={selectedReportType}
                  onChange={(e) => setSelectedReportType(e.target.value)}
                  required
                  className="form-input"
                  style={{ cursor: "pointer" }}
                >
                  {REPORT_TYPES.map(rt => (
                    <option key={rt.value} value={rt.value}>{rt.label}</option>
                  ))}
                </select>
              </div>

              {/* Establishment picker */}
              {REPORT_TYPES.find(r => r.value === selectedReportType)?.requiresPlace && (
                <div style={{ width: "100%", marginBottom: 8 }}>
                  <PlacePicker
                    keyword={keyword}
                    city={placeCity}
                    country={placeCountry}
                    onSelect={handlePlaceSelect}
                    selectedName={placeName}
                    required={selectedReportType === "competitive_swot" || selectedReportType === "sentiment"}
                  />
                </div>
              )}

              {/* Radius slider */}
              <div className="input-container">
                <label className="slider-label" style={{ width: "100%" }}>
                  Search radius: {radiusKm} km
                  <input
                    type="range"
                    min="5"
                    max="200"
                    step="5"
                    value={radiusKm}
                    onChange={(e) => setRadiusKm(Number(e.target.value))}
                    className="slider-input"
                    style={{ width: "100%" }}
                  />
                </label>
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={isRunning}
                className={`submit-button ${isRunning ? "disabled" : ""}`}
              >
                <FaSearch className="button-icon" />
                {isRunning ? "Processing..." : "Start Search"}
              </button>

              {searchComplete && (
                <button type="button" onClick={handleReset} className="reset-button">
                  <FaSync className="button-icon" /> Reset Form
                </button>
              )}
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SentimentApp;