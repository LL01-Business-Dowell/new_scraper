/**
 * App.jsx
 * -------
 * Main application shell — Location search form.
 * Keyword + Report Type + Country/City/Radius + optional Google Maps URL.
 * On submit, navigates to SearchResults page.
 * No email field. No Gemini references in UI text.
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
import ReviewAnalysis from "./ReviewAnalysis";
import Dashboard from "./Dashboard";
import SentimentApp from "./SentimentApp";
import FeedbackPage from "./FeedbackPage";
import SentimentTestPage from "./SentimentTestPage";
import FeedbackQrManager from "./FeedbackQrManager";
import "./App.css";

// Normalise base URL — strip trailing slash once
const BASE = API_BASE_URL.replace(/\/+$/, "");

// ---------------------------------------------------------------------------
// Keyword options — hardcoded list grouped by domain.
// Add new keywords here; they will appear in the dropdown automatically.
// ---------------------------------------------------------------------------
const KEYWORD_OPTIONS = [
  // Healthcare / Medical
  { group: "Healthcare", value: "Hospital" },
  { group: "Healthcare", value: "Pharmacy" },
  // Food & Beverage
  { group: "Food & Beverage", value: "Cafe" },
  { group: "Food & Beverage", value: "Restaurant" },
  { group: "Food & Beverage", value: "Bakery" },
  // Hospitality & Lodging
  { group: "Hospitality", value: "Hotel" },
  { group: "Hospitality", value: "Resort" },
  { group: "Hospitality", value: "Luxury Hotel" },
];

// ---------------------------------------------------------------------------
// Report type options.
// Each entry has a display label and a function that generates the full
// prompt string given (keyword, city, country).
// ---------------------------------------------------------------------------
const REPORT_TYPES = [
  {
    value: "competitive_swot",
    label: "Competitive SWOT Analysis",
    requiresPlace: true,   // establishment name is required
    buildPrompt: (keyword, city, country) =>
      `Competitive SWOT Analysis — benchmarks your specific ${keyword} ` +
      `against approximately 100 competitors within the selected radius in ${city}, ${country}.`,
  },
];

const App = () => {
  // ── Client-side Routing State ──────────────────────────────────────────────
  const [currentPath, setCurrentPath] = useState(window.location.pathname);

  useEffect(() => {
    const handlePopState = () => setCurrentPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // ── Form state ─────────────────────────────────────────────────────────────
  const [keyword, setKeyword] = useState("");
  const [selectedReportType, setSelectedReportType] = useState("");
  const [radiusKm, setRadiusKm] = useState(5);
  const [placeName, setPlaceName] = useState("");  // set by PlacePicker map component
  const [placeCity, setPlaceCity] = useState("");
  const [placeCountry, setPlaceCountry] = useState("");
  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedCity, setSelectedCity] = useState("");

  // ── CSV scraping task state ────────────────────────────────────────────────
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [searchComplete, setSearchComplete] = useState(false);

  // ── Navigation ─────────────────────────────────────────────────────────────
  const [searchPayload, setSearchPayload] = useState(null);
  const [showCsvProcessor, setShowCsvProcessor] = useState(false);
  const [showCompetitorAnalysis, setShowCompetitorAnalysis] = useState(false);

  const [placeLat, setPlaceLat] = useState(null);
  const [placeLng, setPlaceLng] = useState(null);

  const intervalRef = useRef(null);

  axios.defaults.baseURL = BASE;

  // ---------------------------------------------------------------------------
  // Poll CSV scraping progress (By CSV mode only)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!taskId || !isRunning) return;

    intervalRef.current = setInterval(async () => {
      try {
        const r = await axios.get(`/progress/${taskId}`);
        const d = r.data;

        if (d.progress !== undefined) setProgress(d.progress);
        if (d.results?.length > 0) setResults(d.results);

        if (d.error) {
          console.error("Scraping error:", d.error);
          setIsRunning(false);
          setSearchComplete(true);
          clearInterval(intervalRef.current);
        }
        if (!d.running) {
          setIsRunning(false);
          setSearchComplete(true);
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

  // ---------------------------------------------------------------------------
  // Form submit
  // ---------------------------------------------------------------------------
  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!keyword.trim()) {
      alert("Please enter a keyword.");
      return;
    }

    if (!selectedCountry || !selectedCity) {
      alert("Please select both a country and a city.");
      return;
    }

    const rt = REPORT_TYPES.find(r => r.value === selectedReportType);
    if (rt?.requiresPlace && selectedReportType === "competitive_swot" && !placeName.trim()) {
      alert("Please enter your establishment name for Competitive SWOT Analysis.");
      return;
    }

    setSearchPayload({
      keyword,
      report_type: selectedReportType,
      city: selectedCity,
      country: selectedCountry,
      radius_km: radiusKm,
      place_name: placeName.trim() || undefined,
    });
  };

  // ---------------------------------------------------------------------------
  // Cancel CSV scraping
  // ---------------------------------------------------------------------------
  const handleCancel = async () => {
    if (!taskId) return;
    try {
      await axios.post(`/cancel/${taskId}`);
    } catch (err) {
      console.error("Cancel failed:", err.message);
    }
    clearInterval(intervalRef.current);
    setTaskId(null);
    setIsRunning(false);
    setProgress(0);
    setSearchComplete(true);
  };

  // ---------------------------------------------------------------------------
  // Reset everything
  // ---------------------------------------------------------------------------
  const handleReset = () => {
    setKeyword("");
    setSelectedReportType(REPORT_TYPES[0].value);
    setPlaceName("");
    setPlaceCity("");
    setPlaceCountry("");
    setSelectedCountry("");
    setSelectedCity("");
    setTaskId(null);
    setProgress(0);
    setResults([]);
    setIsRunning(false);
    setSearchComplete(false);
    setSearchPayload(null);
    setShowCsvProcessor(false);
  };

  // ---------------------------------------------------------------------------
  // Route Guards based on currentPath
  // ---------------------------------------------------------------------------
  const sessionRouteMatch = currentPath.match(/^\/session\/([\w-]+)$/);
  if (sessionRouteMatch) {
    return (
      <SessionPage
        sessionId={sessionRouteMatch[1]}
        baseUrl={BASE}
      />
    );
  }

  if (currentPath === "/dashboard") {
    return <Dashboard />;
  }

  if (currentPath === "/review-analysis") {
    return <ReviewAnalysis />;
  }

  if (currentPath === "/sentiment") {
    return <SentimentApp />;
  }

  if (currentPath === "/feedback") {
    return <FeedbackPage />;
  }

  if (currentPath === "/test-sentiment") {
    return <SentimentTestPage />;
  }

  if (currentPath === "/feedback-qr" || currentPath === "/qr-manager") {
    return <FeedbackQrManager />;
  }

  if (showCsvProcessor) {
    return (
      <CsvProcessor
        baseUrl={BASE}
        onBack={() => setShowCsvProcessor(false)}
      />
    );
  }

  if (showCompetitorAnalysis) {
    return (
      <CompetitorAnalysis
        baseUrl={BASE}
        onBack={() => {
          setShowCompetitorAnalysis(false);
          setKeyword("");
          setSelectedReportType("");
          setPlaceName("");
          setPlaceCity("");
          setPlaceCountry("");
          setRadiusKm(5);
          setTaskId(null);
          setProgress(0);
          setResults([]);
          setIsRunning(false);
          setSearchComplete(false);
          setSearchPayload(null);
        }}
        keyword={keyword}
        city={placeCity}
        country={placeCountry}
        radiusKm={radiusKm}
        establishmentName={placeName}
        originLat={placeLat}
        originLng={placeLng}
      />
    );
  }

  if (searchPayload) {
    return (
      <SearchResults
        searchPayload={searchPayload}
        baseUrl={BASE}
        onBack={() => setSearchPayload(null)}
      />
    );
  }

  // ---------------------------------------------------------------------------
  // Main form render
  // ---------------------------------------------------------------------------
  return (
    <div className="app-container">
      <div className="animated-background">
        <div className="gradient-overlay" />
        <div className="dot-pattern" />
      </div>

      <div className="content-container">

        <div className="main-content">

          {/* Left: Form */}
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
                  <option value="" disabled>Select a Category</option>
                  {Array.from(new Set(KEYWORD_OPTIONS.map(k => k.group))).map(group => (
                    <optgroup key={group} label={group}>
                      {KEYWORD_OPTIONS
                        .filter(k => k.group === group)
                        .map(k => (
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
                  <option value="" disabled>Select Analysis Type</option>
                  {REPORT_TYPES.map(rt => (
                    <option key={rt.value} value={rt.value}>{rt.label}</option>
                  ))}
                </select>
              </div>

              {/* Establishment map picker */}
              <div style={{ width: "100%", marginBottom: 8 }}>
                <PlacePicker
                  keyword={keyword}
                  city={selectedCity}
                  country={selectedCountry}
                  onSelect={(place) => {
                    if (place) {
                      setPlaceName(place.name || "");
                      setPlaceLat(parseFloat(place.lat) || null);
                      setPlaceLng(parseFloat(place.lon) || null);
                      const parts = (place.display_name || "").split(",").map(s => s.trim());
                      const extractedCountry = parts[parts.length - 1] || "";

                      // Remove country and postcodes from consideration
                      const candidates = parts
                        .slice(1)                          // drop the establishment name itself
                        .filter(p =>
                          p &&
                          p !== extractedCountry &&
                          !/^\d[\d\s-]*$/.test(p)          // drop pure postcodes
                        );

                      const reversed = [...candidates].reverse();
                      const extractedCity =
                        reversed[1] ||   // [0] = state/province, [1] = city/district
                        reversed[0] ||
                        "";

                      setPlaceCity(extractedCity);
                      setPlaceCountry(extractedCountry);
                    } else {
                      setPlaceName("");
                      setPlaceLat(null);
                      setPlaceLng(null);
                      setPlaceCity("");
                      setPlaceCountry("");
                    }
                  }}
                  selectedName={placeName}
                  required={selectedReportType === "competitive_swot"}
                />

                {selectedReportType === "swot" && (
                  <p style={{ fontSize: "0.72rem", color: "#334155", marginTop: 4 }}>
                    adds a personal SWOT card for your establishment.
                  </p>
                )}

                {selectedReportType === "competitive_swot" && (
                  <p style={{ fontSize: "0.72rem", color: "#334155", marginTop: 4 }}>
                    select your establishment for competitor benchmarking.
                  </p>
                )}
              </div>

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

              {/* Competitor Analysis button */}
              <button
                type="button"
                onClick={() => setShowCompetitorAnalysis(true)}
                className="submit-button"
                style={{ background: "#f97316", marginTop: 8 }}
              >
                <FaSearch className="button-icon" />
                Competitor Analysis
              </button>

              {/* Reset */}
              {searchComplete && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="reset-button"
                >
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

export default App;