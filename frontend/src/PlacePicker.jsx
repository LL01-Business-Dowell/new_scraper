/**
 * PlacePicker.jsx
 * ---------------
 * Inline place search component that lives inside the main form.
 *
 * Default state: shows a search input + "View on Map" button.
 * Expanded state: the map appears below the search bar inside the form.
 *
 * Stack — all free, no API keys:
 *   Leaflet 1.9.4    — map rendering (cdnjs)
 *   OpenStreetMap    — tile layer
 *   Nominatim API    — geocoding / place search
 *
 * Props:
 *   keyword      string   — biases search (e.g. "Cafes")
 *   city         string   — biases search and flies map to city
 *   country      string   — biases search
 *   onSelect     fn       — called with { name, display_name, lat, lon } | null
 *   selectedName string   — currently selected place name
 *   required     bool     — show required asterisk
 */

import React, { useState, useEffect, useRef, useCallback } from "react";

// ── Nominatim search ─────────────────────────────────────────────────────────
async function nominatimSearch(query, city, country) {
    if (!query || query.trim().length < 2) return [];
    const bias = [city, country].filter(Boolean).join(", ");
    const q = bias ? `${query.trim()}, ${bias}` : query.trim();
    try {
        const resp = await fetch(
            `https://nominatim.openstreetmap.org/search` +
            `?q=${encodeURIComponent(q)}&format=json&limit=8&addressdetails=1`,
            { headers: { "Accept-Language": "en" } }
        );
        if (!resp.ok) return [];
        const data = await resp.json();
        return Array.isArray(data) ? data : [];
    } catch {
        return [];
    }
}

// ── Main component ───────────────────────────────────────────────────────────
export default function PlacePicker({
    keyword = "",
    city = "",
    country = "",
    onSelect,
    selectedName = "",
    required = false,
}) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showMap, setShowMap] = useState(true);
    const [showDrop, setShowDrop] = useState(false);
    const [leafletOk, setLeafletOk] = useState(false);

    const mapDivRef = useRef(null);
    const mapRef = useRef(null);
    const markerRef = useRef(null);
    const debounceRef = useRef(null);
    const wrapperRef = useRef(null);

    // Ensure results is strictly an array at all times
    const safeResults = Array.isArray(results) ? results : [];

    // ── Load Leaflet from CDN ─────────────────────────────────────────────────
    useEffect(() => {
        if (!document.getElementById("leaflet-css")) {
            const link = document.createElement("link");
            link.id = "leaflet-css";
            link.rel = "stylesheet";
            link.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
            document.head.appendChild(link);
        }
        if (window.L) {
            setLeafletOk(true);
            return;
        }
        if (!document.getElementById("leaflet-js")) {
            const s = document.createElement("script");
            s.id = "leaflet-js";
            s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
            s.async = true;
            s.onload = () => setLeafletOk(true);
            document.head.appendChild(s);
        } else {
            setLeafletOk(true);
        }
        return () => {
            if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
        };
    }, []);

    // ── Init map once Leaflet is ready ────────────────────────────────────────
    useEffect(() => {
        if (!leafletOk || !mapDivRef.current || mapRef.current) return;

        const L = window.L;
        if (!L) return;

        const map = L.map(mapDivRef.current, {
            center: [20, 77],
            zoom: 5,
            zoomControl: true,
        });

        setTimeout(() => {
            map?.invalidateSize?.();
        }, 100);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 19,
        }).addTo(map);
        mapRef.current = map;
    }, [leafletOk]);

    // ── When map becomes visible, fix tile rendering ──────────────────────────
    useEffect(() => {
        if (!showMap || !mapRef.current) return;

        const resize = () => {
            mapRef.current?.invalidateSize?.();
        };

        setTimeout(resize, 50);
        setTimeout(resize, 150);
        setTimeout(resize, 300);
    }, [showMap, selectedName]);

    useEffect(() => {
        const onResize = () => {
            mapRef.current?.invalidateSize?.();
        };

        window.addEventListener("resize", onResize);

        return () => {
            window.removeEventListener("resize", onResize);
        };
    }, []);

    // ── Destroy map on unmount only ───────────────────────────────────────────
    useEffect(() => {
        return () => {
            if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
        };
    }, []);

    // ── Fly to city when city changes (map already open) ─────────────────────
    useEffect(() => {
        if (!mapRef.current || !city) return;
        nominatimSearch(city, country, "").then(res => {
            if (Array.isArray(res) && res.length > 0 && mapRef.current && res[0]?.lat && res[0]?.lon) {
                mapRef.current.flyTo(
                    [parseFloat(res[0].lat), parseFloat(res[0].lon)], 13, { duration: 1.2 }
                );
            }
        });
    }, [city, country]);

    // ── Debounced Nominatim search ────────────────────────────────────────────
    const handleQueryChange = useCallback((e) => {
        const val = e.target.value;
        setQuery(val);
        setShowDrop(false);
        setResults([]);
        if (debounceRef.current) clearTimeout(debounceRef.current);
        if (!val || !val.trim() || val.trim().length < 2) return;
        debounceRef.current = setTimeout(async () => {
            setLoading(true);
            const data = await nominatimSearch(val, city, country);
            const verifiedData = Array.isArray(data) ? data.filter(Boolean) : [];
            setResults(verifiedData);
            setShowDrop(verifiedData.length > 0);
            setLoading(false);
        }, 450);
    }, [city, country]);

    // ── Select a result ───────────────────────────────────────────────────────
    function handleSelect(place) {
        if (!place) return;
        const lat = parseFloat(place.lat);
        const lon = parseFloat(place.lon);
        const displayName = place.display_name || "";
        const nameParts = displayName ? displayName.split(",") : [];
        const cleanName = nameParts[0]?.trim() || "Selected Location";
        const L = window.L;
        const map = mapRef.current;

        if (map && L && !isNaN(lat) && !isNaN(lon)) {
            if (markerRef.current) map.removeLayer(markerRef.current);
            map.flyTo([lat, lon], 17, { duration: 1.2 });

            const icon = L.divIcon({
                className: "",
                html: `<div style="
          width:28px;height:28px;
          background:#f59e0b;border:3px solid #fff;
          border-radius:50% 50% 50% 0;transform:rotate(-45deg);
          box-shadow:0 2px 8px rgba(0,0,0,0.4);"></div>`,
                iconSize: [28, 28], iconAnchor: [14, 28],
            });

            markerRef.current = L.marker([lat, lon], { icon })
                .addTo(map)
                .bindPopup(`<strong>${cleanName}</strong>`)
                .openPopup();
        }

        onSelect?.({ name: cleanName, display_name: displayName, lat, lon });
        setQuery("");
        setShowDrop(false);
        setResults([]);
    }

    // ── Clear ─────────────────────────────────────────────────────────────────
    function handleClear() {
        if (markerRef.current && mapRef.current) {
            mapRef.current.removeLayer(markerRef.current);
            markerRef.current = null;
        }
        onSelect?.(null);
        setQuery("");
        setShowDrop(false);
        setResults([]);
    }

    // ── Close dropdown on outside click ──────────────────────────────────────
    useEffect(() => {
        function onOutside(e) {
            if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
                setShowDrop(false);
            }
        }
        document.addEventListener("mousedown", onOutside);
        return () => document.removeEventListener("mousedown", onOutside);
    }, []);

    // ── Render ────────────────────────────────────────────────────────────────
    return (
        <div ref={wrapperRef} style={{ width: "100%", marginBottom: 8 }}>

            {/* Label */}
            <p style={{
                fontSize: "0.72rem", fontWeight: 700, color: "#475569",
                letterSpacing: "0.07em", textTransform: "uppercase",
                margin: "0 0 8px 0",
            }}>
                Your {keyword || "establishment"}
                {required && <span style={{ color: "#ef4444", marginLeft: 4 }}>*required</span>}
                {!required && <span style={{ color: "#334155", marginLeft: 6, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}></span>}
            </p>

            {/* Search bar row */}
            <div style={{ display: "flex", gap: 8, position: "relative" }}>
                <input
                    type="text"
                    value={query}
                    onChange={handleQueryChange}
                    onFocus={() => safeResults.length > 0 && setShowDrop(true)}
                    placeholder={
                        city
                            ? `Search for a ${keyword || "place"} in ${city}...`
                            : `Search for your ${keyword || "establishment"}...`
                    }
                    className="form-input"
                    style={{ flex: 1 }}
                />

                {/* Clear button — only when something is selected */}
                {selectedName && (
                    <button
                        type="button"
                        onClick={handleClear}
                        style={{
                            background: "none", border: "1px solid #334155",
                            borderRadius: 8, color: "#94a3b8",
                            padding: "0 12px", fontSize: "0.8rem", cursor: "pointer",
                            flexShrink: 0,
                        }}
                    >
                        ✕
                    </button>
                )}

                {/* Dropdown results */}
                {showDrop && safeResults.length > 0 && (
                    <div style={{
                        position: "absolute",
                        top: "calc(100% + 4px)",
                        left: 0,
                        right: 0,
                        background: "#1e293b",
                        border: "1px solid #334155",
                        borderRadius: 8,
                        zIndex: 2000,
                        maxHeight: 240,
                        overflowY: "auto",
                        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
                    }}>
                        {loading && (
                            <div style={{ padding: "10px 14px", color: "#475569", fontSize: "0.83rem" }}>
                                Searching...
                            </div>
                        )}
                        {safeResults.map((place, i) => {
                            if (!place) return null;
                            const displayName = place?.display_name || "";
                            const parts = displayName ? displayName.split(",") : [];
                            const mainName = parts[0]?.trim() || "Location";
                            const subName = parts.slice(1, 4).join(",").trim();
                            return (
                                <div
                                    key={i}
                                    onMouseDown={() => handleSelect(place)}
                                    style={{
                                        padding: "10px 14px",
                                        cursor: "pointer",
                                        fontSize: "0.84rem",
                                        borderBottom: "1px solid #334155",
                                    }}
                                    onMouseEnter={e => e.currentTarget.style.background = "#334155"}
                                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                                >
                                    <div style={{ fontWeight: 600, color: "#f1f5f9", marginBottom: 2 }}>
                                        {mainName}
                                    </div>
                                    {subName && (
                                        <div style={{ fontSize: "0.73rem", color: "#64748b" }}>
                                            {subName}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Selected place badge */}
            {selectedName && (
                <div style={{
                    marginTop: 8,
                    background: "#0ea5e915",
                    border: "1px solid #0ea5e944",
                    borderRadius: 8,
                    padding: "9px 14px",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: "0.84rem",
                }}>
                    <span>📍</span>
                    <span style={{ fontWeight: 700, color: "#7dd3fc" }}>{selectedName}</span>
                    <span style={{ color: "#334155", fontSize: "0.73rem" }}>— selected</span>
                </div>
            )}

            {/* Collapsible map — always mounted, shown/hidden via display */}
            <div
                style={{
                    marginTop: 8,
                    borderRadius: 12,
                    overflow: "hidden",
                    border: showMap ? "1px solid #334155" : "none",
                    width: "100%",
                    position: "relative",

                    height: showMap ? "clamp(320px, 55vh, 500px)" : 0,
                    minHeight: showMap ? "clamp(320px, 55vh, 500px)" : 0,

                    transition: "all 0.25s ease",
                    background: "#0f172a",
                }}
            >
                {!leafletOk && showMap && (
                    <div
                        style={{
                            height: "100%",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            background: "#1e293b",
                            color: "#475569",
                            fontSize: "0.84rem",
                        }}
                    >
                        Loading map...
                    </div>
                )}

                <div
                    ref={mapDivRef}
                    style={{
                        width: "100%",
                        height: "100%",
                    }}
                />
            </div>

            {/* Hint */}
            {!selectedName && (
                <p style={{ fontSize: "0.72rem", color: "#334155", marginTop: 6 }}>
                    {showMap
                        ? "Search above and click a result — a pin will drop on the map."
                        : "Search for your establishment by name, then click a result to select it."}
                </p>
            )}
        </div>
    );
}