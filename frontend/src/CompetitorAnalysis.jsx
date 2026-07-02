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
    originLat: originLatProp = null,
    originLng: originLngProp = null,
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

    const [originLat, setOriginLat] = useState(originLatProp);
    const [originLng, setOriginLng] = useState(originLngProp);

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
                    clearInterval(pollIntervalRef.current);
                    setStatusMessage(data.status_message || "Filtering results...");
                    await new Promise(res => setTimeout(res, 1500));
                    const allPlaces = data.places || [];
                    setPlaces(allPlaces);
                    const checked = {};
                    allPlaces.forEach((p, i) => { checked[i] = p.selected !== false; });
                    setCheckedPlaces(checked);
                    setSearchPhase("approving");
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
                origin_lat: originLat, origin_lng: originLng,
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
                        Searching for Competitors...
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
            <ApprovingPhase
                places={places}
                checkedPlaces={checkedPlaces}
                togglePlace={togglePlace}
                selectedCount={selectedCount}
                establishmentName={establishmentName}
                originLat={originLat}
                originLng={originLng}
                radiusKm={radiusKm}
                onApprove={handleApproveAndAnalyze}
                onBack={onBack}
            />
        );
    }

    // ── RENDER: Analyzing ─────────────────────────────────────────────────────
    if (searchPhase === "analyzing") {
        return (
            <Shell>
                <PageHeader title="Finding Reviews & Running SWOT..." />
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
                            { step: 2, label: "Running analysis on reviews", done: progress > 60 },
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

// ── Approving phase — split layout: list left, map right ─────────────────
function ApprovingPhase({ places, checkedPlaces, togglePlace, selectedCount, establishmentName, originLat, originLng, radiusKm, onApprove, onBack }) {
    const [hoveredIdx, setHoveredIdx] = React.useState(null);
    const mapRef = React.useRef(null);
    const leafletMapRef = React.useRef(null);
    const markersRef = React.useRef([]);
    const circleRef = React.useRef(null);
    const listRef = React.useRef(null);

    // ── Places with coords ────────────────────────────────────────────────
    const placesWithCoords = places.map((p, i) => ({
        ...p,
        _idx: i,
        _hasCoords: p.lat != null && p.lng != null,
    }));

    // ── Origin coords: use originLat/Lng if available, else first place with coords ──
    const mapCenter = React.useMemo(() => {
        if (originLat && originLng) return [originLat, originLng];
        const first = placesWithCoords.find(p => p._hasCoords);
        return first ? [first.lat, first.lng] : [20, 0];
    }, [originLat, originLng, places]);

    // ── Load Leaflet once ─────────────────────────────────────────────────
    React.useEffect(() => {
        if (!mapRef.current) return;
        if (leafletMapRef.current) return; // already initialized

        // Inject Leaflet CSS
        if (!document.getElementById('leaflet-css')) {
            const link = document.createElement('link');
            link.id = 'leaflet-css';
            link.rel = 'stylesheet';
            link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
            document.head.appendChild(link);
        }

        const loadLeaflet = () => {
            if (window.L) {
                initMap();
                return;
            }
            const script = document.createElement('script');
            script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
            script.onload = initMap;
            document.head.appendChild(script);
        };

        const initMap = () => {
            const L = window.L;
            const map = L.map(mapRef.current, {
                center: mapCenter,
                zoom: 13,
                zoomControl: true,
            });

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(map);

            leafletMapRef.current = map;
            renderMapFeatures();
        };

        loadLeaflet();

        return () => {
            if (leafletMapRef.current) {
                leafletMapRef.current.remove();
                leafletMapRef.current = null;
            }
        };
    }, []);

    // ── Re-render markers when places or hoveredIdx changes ──────────────
    React.useEffect(() => {
        if (!leafletMapRef.current || !window.L) return;
        renderMapFeatures();
    }, [places, checkedPlaces, hoveredIdx, originLat, originLng, radiusKm]);

    const renderMapFeatures = () => {
        const L = window.L;
        const map = leafletMapRef.current;
        if (!map || !L) return;

        // Clear old markers
        markersRef.current.forEach(m => m.remove());
        markersRef.current = [];
        if (circleRef.current) { circleRef.current.remove(); circleRef.current = null; }

        // Draw radius circle
        if (originLat && originLng && radiusKm) {
            circleRef.current = L.circle([originLat, originLng], {
                radius: radiusKm * 1000,
                color: '#9333ea',
                weight: 2,
                opacity: 0.7,
                fillColor: '#9333ea',
                fillOpacity: 0.06,
                dashArray: '6 4',
            }).addTo(map);
        }

        // Draw origin pin (user establishment)
        if (originLat && originLng) {
            const userIcon = L.divIcon({
                html: `<div style="
                    width: 32px; height: 32px; border-radius: 50% 50% 50% 0;
                    transform: rotate(-45deg);
                    background: linear-gradient(135deg, #f59e0b, #d97706);
                    border: 3px solid #fff;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
                    display: flex; align-items: center; justify-content: center;
                "><span style="transform: rotate(45deg); color:#fff; font-size:13px; font-weight:900; display:block; text-align:center; line-height:26px;">★</span></div>`,
                className: '',
                iconSize: [32, 32],
                iconAnchor: [16, 32],
                popupAnchor: [0, -34],
            });
            const userMarker = L.marker([originLat, originLng], { icon: userIcon, zIndexOffset: 1000 })
                .addTo(map)
                .bindPopup(`<div style="font-family:sans-serif;min-width:120px"><strong style="color:#d97706">YOUR PLACE</strong></div>`);
            markersRef.current.push(userMarker);
        }

        // Draw competitor pins
        placesWithCoords.forEach((place, i) => {
            if (!place._hasCoords || place.is_user_establishment) return;

            const idx = place._idx;
            const isExcluded = checkedPlaces[idx] === false;
            const isHovered = hoveredIdx === idx;
            const rating = place.rating;

            const color = isExcluded ? '#4b5563' : isHovered ? '#38bdf8' : '#818cf8';
            const borderColor = isHovered ? '#fff' : (isExcluded ? '#374151' : '#6366f1');
            const size = isHovered ? 36 : 28;
            const shadow = isHovered ? '0 4px 16px rgba(56,189,248,0.6)' : '0 2px 6px rgba(0,0,0,0.4)';
            const zOffset = isHovered ? 500 : 0;

            const icon = L.divIcon({
                html: `<div style="
                    width:${size}px; height:${size}px; border-radius:50% 50% 50% 0;
                    transform:rotate(-45deg);
                    background:${color};
                    border:2.5px solid ${borderColor};
                    box-shadow:${shadow};
                    display:flex; align-items:center; justify-content:center;
                    transition: all 0.15s;
                "><span style="transform:rotate(45deg);color:#fff;font-size:${isHovered ? 11 : 9}px;font-weight:700;display:block;text-align:center;line-height:${size - 6}px;">${rating ? rating : '?'}</span></div>`,
                className: '',
                iconSize: [size, size],
                iconAnchor: [size / 2, size],
                popupAnchor: [0, -(size + 4)],
            });

            const marker = L.marker([place.lat, place.lng], { icon, zIndexOffset: zOffset })
                .addTo(map)
                .bindPopup(`<div style="font-family:sans-serif;min-width:140px;max-width:200px">
                    <strong style="font-size:0.85rem;color:#1e293b">${place.name}</strong>
                    ${rating ? `<div style="color:#d97706;margin-top:2px;font-size:0.78rem">★ ${rating}</div>` : ''}
                    ${place.distance_km != null ? `<div style="color:#7c3aed;font-size:0.75rem;margin-top:2px">${place.distance_km} km away</div>` : ''}
                    ${place.address ? `<div style="color:#64748b;font-size:0.72rem;margin-top:2px">${place.address}</div>` : ''}
                    ${isExcluded ? '<div style="color:#ef4444;font-size:0.72rem;margin-top:4px">⊘ Excluded</div>' : ''}
                </div>`);

            // Clicking marker scrolls list to that item
            marker.on('click', () => {
                const el = document.getElementById(`place-row-${idx}`);
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });

            markersRef.current.push(marker);
        });

        // Fit bounds to all pins
        const allCoords = placesWithCoords
            .filter(p => p._hasCoords)
            .map(p => [p.lat, p.lng]);
        if (originLat && originLng) allCoords.push([originLat, originLng]);
        if (allCoords.length > 1) {
            map.fitBounds(allCoords, { padding: [40, 40] });
        }
    };

    return (
        <div className="app-container">
            <div className="animated-background">
                <div className="gradient-overlay" />
                <div className="dot-pattern" />
            </div>
            <div className="content-container">
                <div style={{ maxWidth: 1200, width: '100%', margin: '0 auto', padding: '1.5rem 1rem' }}>

                    {/* Header */}
                    <div style={{ marginBottom: 16 }}>
                        <button onClick={onBack} style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            background: 'none', border: 'none', color: '#a78bfa',
                            cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600, padding: 0, marginBottom: 10,
                        }}>
                            <FaArrowLeft style={{ fontSize: 11 }} /> Back
                        </button>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                            <div>
                                <h2 style={{
                                    margin: 0, fontSize: '1.3rem', fontWeight: 700,
                                    background: 'linear-gradient(to right, #a78bfa, #818cf8)',
                                    WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
                                }}>
                                    Found {places.length} Places
                                </h2>
                                <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#6b7280' }}>
                                    {selectedCount} selected · Uncheck to exclude · Hover a row to highlight its pin
                                </p>
                            </div>
                            {/* KPI chips */}
                            <div style={{ display: 'flex', gap: 8 }}>
                                {[
                                    { label: 'Found', value: places.length, color: '#a78bfa' },
                                    { label: 'Selected', value: selectedCount, color: '#10b981' },
                                    { label: 'Excluded', value: places.length - selectedCount, color: '#ef4444' },
                                ].map(({ label, value, color }) => (
                                    <div key={label} style={{
                                        background: '#1f2937', borderRadius: 8, padding: '6px 14px',
                                        border: '1px solid #374151', textAlign: 'center',
                                    }}>
                                        <div style={{ fontSize: '1.1rem', fontWeight: 700, color }}>{value}</div>
                                        <div style={{ fontSize: '0.65rem', color: '#6b7280' }}>{label}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Split layout */}
                    <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 16, alignItems: 'start' }}>

                        {/* ── Left: places list ─────────────────────────────── */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            <div
                                ref={listRef}
                                style={{
                                    maxHeight: 'calc(100vh - 260px)',
                                    overflowY: 'auto',
                                    border: '1px solid #374151',
                                    borderRadius: 12,
                                    background: '#1A1E2E',
                                }}
                            >
                                {placesWithCoords.map((place) => {
                                    const idx = place._idx;
                                    const isExcluded = checkedPlaces[idx] === false;
                                    const isHovered = hoveredIdx === idx;
                                    const isUser = place.is_user_establishment ||
                                        (establishmentName && place.name.toLowerCase() === establishmentName.trim().toLowerCase());

                                    return (
                                        <div
                                            id={`place-row-${idx}`}
                                            key={idx}
                                            onClick={() => togglePlace(idx)}
                                            onMouseEnter={() => setHoveredIdx(idx)}
                                            onMouseLeave={() => setHoveredIdx(null)}
                                            style={{
                                                padding: '11px 14px',
                                                borderBottom: idx < places.length - 1 ? '1px solid #1f2937' : 'none',
                                                display: 'flex', alignItems: 'center', gap: 10,
                                                cursor: 'pointer',
                                                background: isHovered
                                                    ? 'rgba(56,189,248,0.07)'
                                                    : isExcluded
                                                        ? 'rgba(239,68,68,0.04)'
                                                        : isUser
                                                            ? 'rgba(245,158,11,0.05)'
                                                            : 'transparent',
                                                borderLeft: isHovered
                                                    ? '3px solid #38bdf8'
                                                    : isUser
                                                        ? '3px solid #f59e0b'
                                                        : '3px solid transparent',
                                                transition: 'all 0.15s',
                                                opacity: isExcluded ? 0.5 : 1,
                                            }}
                                        >
                                            {/* Checkbox */}
                                            <div style={{
                                                width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                                                border: `2px solid ${isExcluded ? '#4b5563' : '#9333ea'}`,
                                                background: isExcluded ? 'transparent' : 'linear-gradient(to right, #9333ea, #4f46e5)',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            }}>
                                                {!isExcluded && (
                                                    <svg width="9" height="7" viewBox="0 0 10 8" fill="none">
                                                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                                    </svg>
                                                )}
                                            </div>

                                            {/* Info */}
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                                    {isUser && (
                                                        <span style={{
                                                            fontSize: '0.58rem', background: '#f59e0b', color: '#000',
                                                            padding: '1px 5px', borderRadius: 3, fontWeight: 800,
                                                        }}>YOU</span>
                                                    )}
                                                    <span style={{
                                                        fontWeight: 600, fontSize: '0.85rem',
                                                        color: isUser ? '#fbbf24' : isHovered ? '#38bdf8' : '#f1f1f1',
                                                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                                        maxWidth: 240,
                                                    }}>
                                                        {place.name}
                                                    </span>
                                                </div>
                                                <div style={{ display: 'flex', gap: 6, fontSize: '0.7rem', color: '#6b7280', marginTop: 3, flexWrap: 'wrap', alignItems: 'center' }}>
                                                    {place.rating && (
                                                        <span style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: 2 }}>
                                                            <FaStar style={{ fontSize: 8 }} /> {place.rating}
                                                        </span>
                                                    )}
                                                    {place.reviews > 0 && (
                                                        <span style={{ color: '#4b5563' }}>{place.reviews.toLocaleString()} reviews</span>
                                                    )}
                                                    {place.distance_km != null && (
                                                        <span style={{
                                                            background: 'rgba(147,51,234,0.15)',
                                                            color: '#c084fc',
                                                            padding: '1px 5px', borderRadius: 3,
                                                            fontSize: '0.68rem', fontWeight: 600,
                                                            border: '1px solid rgba(147,51,234,0.3)',
                                                        }}>
                                                            {place.distance_km} km
                                                        </span>
                                                    )}
                                                    {!place._hasCoords && (
                                                        <span style={{ color: '#4b5563', fontSize: '0.65rem' }}>no pin</span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {/* Action buttons */}
                            <div style={{ display: 'flex', gap: 8 }}>
                                <button onClick={onApprove} className="submit-button" style={{ flex: 1, margin: 0 }}>
                                    <FaChartBar className="button-icon" />
                                    Analyse {selectedCount} Places
                                </button>
                                <button onClick={onBack} className="reset-button" style={{ width: 'auto', marginTop: 0, padding: '0.75rem 1.2rem' }}>
                                    Cancel
                                </button>
                            </div>
                        </div>

                        {/* ── Right: map ───────────────────────────────────── */}
                        <div style={{
                            borderRadius: 12, overflow: 'hidden',
                            border: '1px solid #374151',
                            height: 'calc(100vh - 260px)',
                            minHeight: 500,
                            position: 'sticky', top: '1rem',
                        }}>
                            <div ref={mapRef} style={{ width: '100%', height: '100%' }} />

                            {/* Map legend */}
                            <div style={{
                                position: 'absolute', bottom: 24, left: 12, zIndex: 1000,
                                background: 'rgba(17,24,39,0.9)',
                                backdropFilter: 'blur(8px)',
                                borderRadius: 8, padding: '8px 12px',
                                border: '1px solid #374151',
                                fontSize: '0.7rem', color: '#9ca3af',
                                display: 'flex', flexDirection: 'column', gap: 5,
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#f59e0b' }} />
                                    <span>Your establishment</span>
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#818cf8' }} />
                                    <span>Competitor</span>
                                </div>
                                {/* <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#38bdf8' }} />
                                    <span>Hovered</span>
                                </div> */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ width: 20, height: 2, background: '#9333ea', borderTop: '2px dashed #9333ea' }} />
                                    <span>{radiusKm} km radius</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
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
            `Generated by DoWell Samanta Scraper`,
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
            `Generated by DoWell Samanta Scraper`,
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