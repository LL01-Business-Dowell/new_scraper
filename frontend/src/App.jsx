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
  // // Business / Corporate
  // { group: "Corporate", value: "Vice Presidents of Operations" },
  // { group: "Corporate", value: "Chief Financial Officers" },
  // { group: "Corporate", value: "Managing Directors" },
  // { group: "Corporate", value: "Head of Business Development" },
  // Food & Beverage
  { group: "Food & Beverage", value: "Cafe" },
  { group: "Food & Beverage", value: "Restaurant" },
  { group: "Food & Beverage", value: "Bakery" },
  // // Real Estate
  // { group: "Real Estate", value: "Real Estate Agencies" },
  // { group: "Real Estate", value: "Property Developers" },
];

// ---------------------------------------------------------------------------
// Report type options.
// Each entry has a display label and a function that generates the full
// prompt string given (keyword, city, country).
// Add new report types here — the prompt preview updates automatically.
// ---------------------------------------------------------------------------
const REPORT_TYPES = [
  // {
  //   value: "swot",
  //   label: "SWOT Analysis",
  //   requiresPlace: true,   // shows the establishment name input field
  //   buildPrompt: (keyword, city, country) =>
  //     `SWOT Analysis for ${keyword} in ${city}, ${country} — ` +
  //     `split across geographic quadrants (North, South, East, West). ` +
  //     `If a specific establishment URL is provided, each quadrant card includes a comparison.`,
  // },
  {
    value: "competitive_swot",
    label: "Competitive SWOT Analysis",
    requiresPlace: true,   // establishment name is required
    buildPrompt: (keyword, city, country) =>
      `Competitive SWOT Analysis — benchmarks your specific ${keyword} ` +
      `against approximately 100 competitors within the selected radius in ${city}, ${country}.`,
  },
  // ── Add more report types below as needed ────────────────────────────────
  // { value: "...", label: "...", requiresPlace: false, buildPrompt: () => `...` },
];

const App = () => {

  // ── Form state ─────────────────────────────────────────────────────────────
  const [searchType, setSearchType] = useState("location");
  // Keyword and report type are now dropdowns — not free-form inputs
  const [keyword, setKeyword] = useState("");
  const [selectedReportType, setSelectedReportType] = useState("");
  const [radiusKm, setRadiusKm] = useState(5);
  const [placeName, setPlaceName] = useState("");  // set by PlacePicker map component
  const [placeCity, setPlaceCity] = useState("");
  const [placeCountry, setPlaceCountry] = useState("");
  const [file, setFile] = useState(null);

  // ── Dropdowns ──────────────────────────────────────────────────────────────
  const [countries, setCountries] = useState([]);
  const [selectedCountry, setSelectedCountry] = useState("");
  const [cities, setCities] = useState([]);
  const [selectedCity, setSelectedCity] = useState("");
  const [countrySearch, setCountrySearch] = useState("");
  const [citySearch, setCitySearch] = useState("");

  // ── CSV scraping task state ────────────────────────────────────────────────
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [searchComplete, setSearchComplete] = useState(false);

  // ── Navigation: when set, renders SearchResults instead of this page ───────
  const [searchPayload, setSearchPayload] = useState(null);
  const [showCsvProcessor, setShowCsvProcessor] = useState(false);

  const [showCompetitorAnalysis, setShowCompetitorAnalysis] = useState(false);

  const intervalRef = useRef(null);
  const fileInputRef = useRef(null);

  axios.defaults.baseURL = BASE;

  // ---------------------------------------------------------------------------
  // Fetch countries on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    axios
      .get("/countries")
      .then((r) => setCountries(r.data?.countries || []))
      .catch((err) => {
        console.error("Failed to load countries:", err.message);
        setCountries([]);
      });
  }, []);

  // ---------------------------------------------------------------------------
  // Load cities when country selection changes
  // ---------------------------------------------------------------------------
  const handleCountryChange = async (country) => {
    setSelectedCountry(country);
    setSelectedCity("");
    setCities([]);
    if (!country) return;
    try {
      const r = await axios.get(`/cities/${encodeURIComponent(country)}`);
      setCities(r.data?.cities || []);
    } catch (err) {
      console.error("Failed to load cities:", err.message);
      setCities([]);
    }
  };

  // ---------------------------------------------------------------------------
  // Close custom dropdowns on outside click
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const handleOutside = (e) => {
      if (!e.target.closest(".custom-select")) {
        document.getElementById("countryDropdown")?.classList.remove("show");
        document.getElementById("cityDropdown")?.classList.remove("show");
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

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
    // Navigate to SearchResults — backend handles everything from here
    // report_type drives the prompt on the backend; no user_prompt needed
    // Validate that place URL is provided when required
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
  // Download CSV scraping results
  // ---------------------------------------------------------------------------
  const handleDownload = async () => {
    if (!taskId) return;
    try {
      const r = await axios.get(`/download/${taskId}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(
        new Blob([r.data], { type: "text/csv" })
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `results_${taskId}.csv`;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed:", err.message);
      alert("Download failed. Please try again.");
    }
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
    setFile(null);
    setTaskId(null);
    setProgress(0);
    setResults([]);
    setIsRunning(false);
    setSearchComplete(false);
    setSearchPayload(null);
    setShowCsvProcessor(false);
  };

  // ---------------------------------------------------------------------------
  // Page switch — By Location goes to SearchResults
  // ---------------------------------------------------------------------------
  // ---------------------------------------------------------------------------
  // Session route — /session/{sessionId} opens SessionPage in a new tab.
  // We detect this from the URL path so no React Router is needed.
  // ---------------------------------------------------------------------------
  const sessionRouteMatch = window.location.pathname.match(/^\/session\/([\w-]+)$/);
  if (sessionRouteMatch) {
    return (
      <SessionPage
        sessionId={sessionRouteMatch[1]}
        baseUrl={BASE}
      />
    );
  }

  // Navigate to CsvProcessor page for By CSV mode
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
        onBack={() => setShowCompetitorAnalysis(false)}
        keyword={keyword}
        city={placeCity}
        country={placeCountry}
        radiusKm={radiusKm}
        establishmentName={placeName}
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

              {/* Establishment map picker — always visible */}
              <div style={{ width: "100%", marginBottom: 8 }}>
                <PlacePicker
                  keyword={keyword}
                  city={selectedCity}
                  country={selectedCountry}
                  // onSelect={(place) => setPlaceName(place ? place.name : "")}
                  onSelect={(place) => {
                    if (place) {
                      setPlaceName(place.name || "");

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

                      // Pick the part closest to the end that isn't a very short abbreviation
                      // — this tends to be the district/city rather than the suburb.
                      // We reverse and skip 1 (state) to land on city/district level.
                      const reversed = [...candidates].reverse();
                      const extractedCity =
                        reversed[1] ||   // [0] = state/province, [1] = city/district
                        reversed[0] ||
                        "";

                      setPlaceCity(extractedCity);
                      setPlaceCountry(extractedCountry);
                    } else {
                      setPlaceName("");
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

              {/* Country dropdown — removed, location inferred from PlacePicker
              <div className="input-container">
                <FaMapMarkerAlt className="input-icon" />
                <div className="custom-select">
                  <div
                    className="select-selected"
                    onClick={() =>
                      document.getElementById("countryDropdown").classList.toggle("show")
                    }
                  >
                    {selectedCountry || "Select a Country to Analyse"}
                  </div>
                  <div id="countryDropdown" className="select-items">
                    <div className="search-container">
                      <input
                        type="text"
                        placeholder="Search country..."
                        value={countrySearch}
                        onChange={(e) => setCountrySearch(e.target.value)}
                        className="dropdown-search"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                    {countries
                      .filter((c) => c.toLowerCase().includes(countrySearch.toLowerCase()))
                      .map((country, i) => (
                        <div
                          key={i}
                          className={`select-option ${selectedCountry === country ? "selected" : ""}`}
                          onClick={() => {
                            handleCountryChange(country);
                            document.getElementById("countryDropdown").classList.remove("show");
                          }}
                        >
                          {country}
                        </div>
                      ))}
                  </div>
                  <select
                    value={selectedCountry}
                    onChange={(e) => handleCountryChange(e.target.value)}
                    required
                    className="hidden-select"
                  >
                    <option value="" disabled>Select a Country to Analyse</option>
                    {countries.map((c, i) => (
                      <option key={i} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
              </div>
              */}

              {/* City dropdown — shown after country is picked
              {selectedCountry && (
                <div className="input-container">
                  <FaMapMarkerAlt className="input-icon" />
                  <div className="custom-select">
                    <div
                      className="select-selected"
                      onClick={() =>
                        document.getElementById("cityDropdown").classList.toggle("show")
                      }
                    >
                      {selectedCity || "Select a City to Analyse"}
                    </div>
                    <div id="cityDropdown" className="select-items">
                      <div className="search-container">
                        <input
                          type="text"
                          placeholder="Search city..."
                          value={citySearch}
                          onChange={(e) => setCitySearch(e.target.value)}
                          className="dropdown-search"
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                      {cities
                        .filter((c) => c.toLowerCase().includes(citySearch.toLowerCase()))
                        .map((city, i) => (
                          <div
                            key={i}
                            className={`select-option ${selectedCity === city ? "selected" : ""}`}
                            onClick={() => {
                              setSelectedCity(city);
                              document.getElementById("cityDropdown").classList.remove("show");
                            }}
                          >
                            {city}
                          </div>
                        ))}
                    </div>
                    <select
                      value={selectedCity}
                      onChange={(e) => setSelectedCity(e.target.value)}
                      required
                      className="hidden-select"
                    >
                      <option value="" disabled>Select a City to Analyse</option>
                      {cities.map((c, i) => (
                        <option key={i} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
                */}

              {/* Submit
              <button
                type="submit"
                disabled={isRunning}
                className={`submit-button ${isRunning ? "disabled" : ""}`}
              >
                <FaSearch className="button-icon" />
                {isRunning ? "Processing..." : "Analyse"}
              </button>
              */}

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

              {/* Progress bar for CSV scraping */}
              {isRunning && false && (
                <div className="progress-container">
                  <div className="progress-bar-container">
                    <div
                      className="progress-bar"
                      style={{ width: `${Math.min(progress, 100)}%` }}
                    />
                  </div>
                  <div className="progress-info">
                    <p className="progress-text">
                      Found: {progress} businesses
                    </p>
                    <button
                      type="button"
                      onClick={handleCancel}
                      disabled={!isRunning}
                      className="cancel-button"
                    >
                      <FaTimes className="button-icon-small" /> Cancel
                    </button>
                  </div>
                </div>
              )}

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