/**
 * SentimentApp.jsx
 */

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { FaSearch, FaSync, FaKeyboard } from "react-icons/fa";
import API_BASE_URL from "./config";
import SearchResults from "./SearchResults";
import CsvProcessor from "./CsvProcessor";
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
  { group: "Hospitality", value: "Hotel" },
  { group: "Hospitality", value: "Resort" },
  { group: "Hospitality", value: "Luxury Hotel" },
];

const REPORT_TYPES = [
  {
    value:         "swot",
    label:         "SWOT Analysis",
    requiresPlace: true,
  },
  {
    value:         "competitive_swot",
    label:         "Competitive SWOT Analysis",
    requiresPlace: true,
  },
  {
    value:         "sentiment",
    label:         "Sentiment Analysis",
    requiresPlace: true,
  },
];

const SentimentApp = () => {
  useEffect(() => {
    if (window.location.pathname !== "/sentiment") {
      window.history.replaceState({}, "", "/sentiment");
    }
  }, []);

  const [keyword,              setKeyword]              = useState("");
  const [selectedReportType,   setSelectedReportType]   = useState(REPORT_TYPES[0].value);
  const [radiusKm,             setRadiusKm]             = useState(5);
  const [placeName,            setPlaceName]            = useState("");
  const [placeCity,            setPlaceCity]            = useState("");
  const [placeCountry,         setPlaceCountry]         = useState("");
  const [placeLat,             setPlaceLat]             = useState(null);
  const [placeLng,             setPlaceLng]             = useState(null);
  const [placeGoogleUri,       setPlaceGoogleUri]       = useState("");
  const [placeId,              setPlaceId]              = useState("");

  const [taskId,               setTaskId]               = useState(null);
  const [progress,             setProgress]             = useState(0);
  const [results,              setResults]              = useState([]);
  const [isRunning,            setIsRunning]            = useState(false);
  const [searchComplete,       setSearchComplete]       = useState(false);

  const [searchPayload,        setSearchPayload]        = useState(null);
  const [showCsvProcessor,     setShowCsvProcessor]     = useState(false);
  const [showCompetitorAnalysis, setShowCompetitorAnalysis] = useState(false);
  const [showSentimentAnalysis,  setShowSentimentAnalysis]  = useState(false);

  const intervalRef  = useRef(null);

  useEffect(() => {
    if (!taskId || !isRunning) return;
    intervalRef.current = setInterval(async () => {
      try {
        const r = await axios.get(`/progress/${taskId}`);
        const d = r.data;
        if (d.progress !== undefined) setProgress(d.progress);
        if (d.results?.length > 0)    setResults(d.results);
        if (d.error || !d.running) {
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

  const handlePlaceSelect = (place) => {
    console.group("📍 Place Selection Callback");
    console.log("Raw Place Received:", place);

    if (!place) {
      console.warn("Place is null/empty. Resetting place state.");
      setPlaceName(""); setPlaceCity(""); setPlaceCountry("");
      setPlaceLat(null); setPlaceLng(null);
      setPlaceGoogleUri(""); setPlaceId("");
      console.groupEnd();
      return;
    }

    const addr = place.address || {};
    const nameVal = place.name || "";
    const latVal = parseFloat(place.lat) || null;
    const lngVal = parseFloat(place.lon) || null;
    const uriVal = place.googleMapsUri || "";
    const idVal = place.place_id || "";

    const extractedCity =
      addr.city ||
      addr.town ||
      addr.village ||
      addr.county ||
      addr.state ||
      "Selected Area";

    const extractedCountry = addr.country || "";

    console.log("Extracted Values:", {
      name: nameVal,
      city: extractedCity,
      country: extractedCountry,
      lat: latVal,
      lng: lngVal,
      googleMapsUri: uriVal,
      place_id: idVal,
    });

    setPlaceName(nameVal);
    setPlaceLat(latVal);
    setPlaceLng(lngVal);
    setPlaceGoogleUri(uriVal);
    setPlaceId(idVal);
    setPlaceCity(extractedCity);
    setPlaceCountry(extractedCountry);
    console.groupEnd();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    console.group("🚀 Start Search Button Clicked");
    console.log("Current Form State:", {
      keyword,
      selectedReportType,
      radiusKm,
      placeName,
      placeCity,
      placeCountry,
      placeLat,
      placeLng,
      placeGoogleUri,
      placeId,
      origin_lat:  placeLat,
      origin_lng:  placeLng,
    });

    if (!keyword.trim()) {
      console.warn("❌ Validation Failed: Keyword is missing.");
      alert("Please select a keyword.");
      console.groupEnd();
      return;
    }

    if (selectedReportType === "sentiment") {
      if (!placeName.trim()) {
        console.warn("❌ Validation Failed: Place Name missing for Sentiment Analysis.");
        alert("Please select your establishment for Sentiment Analysis.");
        console.groupEnd();
        return;
      }
      console.log("✅ Validation Passed: Navigating to <SentimentAnalysis />");
      setShowSentimentAnalysis(true);
      console.groupEnd();
      return;
    }

    if (selectedReportType === "competitive_swot") {
      if (!placeName.trim()) {
        console.warn("❌ Validation Failed: Place Name missing for Competitive SWOT.");
        alert("Please select your establishment for Competitive SWOT Analysis.");
        console.groupEnd();
        return;
      }
      console.log("✅ Validation Passed: Navigating to <CompetitorAnalysis />");
      setShowCompetitorAnalysis(true);
      console.groupEnd();
      return;
    }

    const payload = {
      keyword,
      report_type: selectedReportType,
      city:        placeCity,
      country:     placeCountry,
      radius_km:   radiusKm,
      place_name:  placeName.trim() || undefined,
      google_maps_uri: placeGoogleUri,
      place_id:    placeId,
    };

    console.log("✅ Validation Passed: Setting searchPayload and launching <SearchResults />:", payload);
    setSearchPayload(payload);
    console.groupEnd();
  };

  const handleReset = () => {
    console.log("🔄 Resetting form...");
    setKeyword(""); setSelectedReportType(REPORT_TYPES[0].value);
    setPlaceName(""); setPlaceCity(""); setPlaceCountry("");
    setPlaceLat(null); setPlaceLng(null);
    setPlaceGoogleUri(""); setPlaceId("");
    setTaskId(null); setProgress(0); setResults([]);
    setIsRunning(false); setSearchComplete(false);
    setSearchPayload(null); setShowCsvProcessor(false);
    setShowCompetitorAnalysis(false); setShowSentimentAnalysis(false);
  };

  if (showSentimentAnalysis) {
    return (
      <SentimentAnalysis
        baseUrl={BASE}
        onBack={() => {
          console.log("⬅️ Returning from Sentiment Analysis view.");
          handleReset();
        }}
        city={placeCity}
        country={placeCountry}
        establishmentName={placeName}
        originLat={placeLat}
        originLng={placeLng}
        googleMapsUri={placeGoogleUri}
        placeId={placeId}
        radiusKm={radiusKm}
        daysBack={30}
      />
    );
  }

  if (showCompetitorAnalysis) {
    return (
      <CompetitorAnalysis
        baseUrl={BASE}
        onBack={() => {
          console.log("⬅️ Returning from Competitor Analysis view.");
          handleReset();
        }}
        keyword={keyword}
        city={placeCity}
        country={placeCountry}
        radiusKm={radiusKm}
        establishmentName={placeName}
        originLat={placeLat}
        originLng={placeLng}
        googleMapsUri={placeGoogleUri}
        daysBack={30}
      />
    );
  }

  if (showCsvProcessor) {
    return <CsvProcessor baseUrl={BASE} onBack={handleReset} />;
  }

  if (searchPayload) {
    return <SearchResults searchPayload={searchPayload} baseUrl={BASE} onBack={handleReset} />;
  }

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