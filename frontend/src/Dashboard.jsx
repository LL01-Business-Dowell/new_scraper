/**
 * Dashboard.jsx
 * -------------
 * Analytics dashboard for competitor search data saved in Datacube.
 * Matches App.jsx / App.css dark theme exactly.
 * 
 * Features:
 * - Total searches, unique keywords, unique cities, avg radius
 * - Recent searches table
 * - Searches by keyword bar chart (pure CSS)
 * - Searches by city bar chart (pure CSS)
 * - Activity timeline (last 14 days)
 * - Auto-refreshes every 60 seconds
 */

import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { FaSearch, FaSync, FaMapMarkerAlt, FaChartBar, FaStore } from "react-icons/fa";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const BASE = API_BASE_URL.replace(/\/+$/, "");

export default function Dashboard() {
  // Standalone page — only renders at /dashboard
  useEffect(() => {
    if (window.location.pathname !== "/dashboard") {
      window.location.pathname = "/dashboard";
    }
  }, []);

  const [data,        setData]        = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [page,        setPage]        = useState(1);
  const PAGE_SIZE = 10;

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const resp = await axios.get(`${BASE}/api/competitors/dashboard`);
      setData(resp.data.searches || []);
      setLastUpdated(new Date());
    } catch (err) {
      setError("Failed to load dashboard data. " + err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // ── Derived stats ─────────────────────────────────────────────────────────
  const totalSearches   = data.length;
  const uniqueKeywords  = [...new Set(data.map(d => d.keyword).filter(Boolean))];
  const uniqueCities    = [...new Set(data.map(d => d.city).filter(Boolean))];
  const avgRadius       = data.length
    ? (data.reduce((s, d) => s + (d.radius_km || 0), 0) / data.length).toFixed(1)
    : 0;

  // Keyword frequency
  const keywordFreq = data.reduce((acc, d) => {
    if (d.keyword) acc[d.keyword] = (acc[d.keyword] || 0) + 1;
    return acc;
  }, {});
  const topKeywords = Object.entries(keywordFreq)
    .sort((a, b) => b[1] - a[1]).slice(0, 8);

  // City frequency
  const cityFreq = data.reduce((acc, d) => {
    if (d.city) acc[d.city] = (acc[d.city] || 0) + 1;
    return acc;
  }, {});
  const topCities = Object.entries(cityFreq)
    .sort((a, b) => b[1] - a[1]).slice(0, 8);

  // Activity last 14 days
  const today = new Date();
  const last14 = Array.from({ length: 14 }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (13 - i));
    return d.toISOString().split("T")[0];
  });
  const activityByDay = last14.map(day => ({
    day,
    label: new Date(day).toLocaleDateString("en", { weekday: "short", month: "short", day: "numeric" }),
    count: data.filter(d => d.created_at?.startsWith(day)).length,
  }));
  const maxActivity = Math.max(...activityByDay.map(d => d.count), 1);

  // Paginated recent searches
  const sorted  = [...data].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const pageData   = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // ── Styles ────────────────────────────────────────────────────────────────
  const card = {
    background: "#1A1E2E", borderRadius: 14,
    border: "1px solid #374151", padding: "20px 24px",
  };

  const label = {
    fontSize: "0.65rem", fontWeight: 700, color: "#6b7280",
    textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 6,
  };

  const gradientText = {
    background: "linear-gradient(to right, #a78bfa, #818cf8)",
    WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
  };

  // ── Loading / Error ───────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="app-container">
        <div className="animated-background">
          <div className="gradient-overlay" /><div className="dot-pattern" />
        </div>
        <div className="content-container" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ textAlign: "center", color: "#6b7280" }}>
            <div style={{
              width: 48, height: 48, borderRadius: "50%", margin: "0 auto 16px",
              background: "linear-gradient(to right, #9333ea, #4f46e5)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <FaChartBar style={{ color: "#fff", fontSize: 20 }} />
            </div>
            <p style={{ color: "#9ca3af" }}>Loading dashboard...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <div className="animated-background">
        <div className="gradient-overlay" /><div className="dot-pattern" />
      </div>
      <div className="content-container">
        <div style={{ maxWidth: 1600, margin: "0 auto", padding: "2.5rem 1.5rem" }}>

          {/* ── Header ─────────────────────────────────────────────────── */}
          <div style={{ marginBottom: 28 }}>
            {/* Logo bar matching App.jsx */}
            <div style={{
              display: "flex", alignItems: "center", gap: 12, marginBottom: 24,
              paddingBottom: 20, borderBottom: "1px solid rgba(31,41,55,0.5)",
            }}>
              <div style={{
                width: 42, height: 42, borderRadius: "50%",
                background: "linear-gradient(to bottom right, #9333ea, #4f46e5)",
                display: "flex", alignItems: "center", justifyContent: "center",
                overflow: "hidden",
              }}>
                <img
                  src="https://dowellfileuploader.uxlivinglab.online/hr/logo-2-min-min.png"
                  alt="DoWell logo"
                  style={{ maxWidth: "100%", maxHeight: "100%" }}
                />
              </div>
              <span style={{
                fontSize: "1.1rem", fontWeight: 700, letterSpacing: "-0.02em",
                background: "linear-gradient(to right, #a78bfa, #818cf8)",
                WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
              }}>
                DoWell Samanta AI
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
              <div>
                <h1 style={{ margin: 0, fontSize: "1.75rem", fontWeight: 800, ...gradientText }}>
                  Search Analytics
                </h1>
                {/* <p style={{ margin: "6px 0 0", fontSize: "0.85rem", color: "#6b7280" }}>
                  All competitor searches saved to Datacube
                </p> */}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {lastUpdated && (
                  <span style={{ fontSize: "0.72rem", color: "#4b5563" }}>
                    Updated {lastUpdated.toLocaleTimeString()}
                  </span>
                )}
                <button onClick={fetchData} style={{
                  display: "flex", alignItems: "center", gap: 6,
                  background: "#1f2937", border: "1px solid #374151",
                  color: "#9ca3af", borderRadius: 8, padding: "6px 14px",
                  fontSize: "0.78rem", cursor: "pointer", fontWeight: 600,
                }}>
                  <FaSync style={{ fontSize: 10 }} /> Refresh
                </button>
              </div>
            </div>
          </div>

          {error && (
            <div style={{
              background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
              borderRadius: 10, padding: "12px 16px", marginBottom: 20,
              color: "#ef4444", fontSize: "0.85rem",
            }}>
              {error}
            </div>
          )}

          {/* ── KPI tiles ──────────────────────────────────────────────── */}
          {/* <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14, marginBottom: 24 }}>
            {[
              { label: "Total Searches",    value: totalSearches,         color: "#a78bfa", icon: <FaSearch /> },
              { label: "Unique Keywords",   value: uniqueKeywords.length, color: "#3b82f6", icon: <FaChartBar /> },
              { label: "Unique Cities",     value: uniqueCities.length,   color: "#10b981", icon: <FaMapMarkerAlt /> },
              { label: "Avg Radius (km)",   value: avgRadius,             color: "#f59e0b", icon: <FaStore /> },
            ].map(({ label: lbl, value, color, icon }) => (
              <div key={lbl} style={{ ...card }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                  <span style={{ ...label, marginBottom: 0 }}>{lbl}</span>
                  <span style={{ color, fontSize: 14, opacity: 0.7 }}>{icon}</span>
                </div>
                <div style={{ fontSize: "2rem", fontWeight: 800, color, lineHeight: 1 }}>
                  {value}
                </div>
              </div>
            ))}
          </div> */}

          {/* ── Activity timeline ───────────────────────────────────────── */}
          <div style={{ ...card, marginBottom: 20 }}>
            <p style={{ ...label, marginBottom: 16 }}>Activity — Last 14 Days</p>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 100 }}>
              {activityByDay.map(({ day, label: dayLabel, count }) => (
                <div key={day} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                  <div style={{ position: "relative", width: "100%", display: "flex", justifyContent: "center" }}>
                    {count > 0 && (
                      <span style={{
                        position: "absolute", top: -18, fontSize: "0.6rem",
                        color: "#a78bfa", fontWeight: 700,
                      }}>{count}</span>
                    )}
                    <div style={{
                      width: "100%", maxWidth: 36,
                      height: Math.max((count / maxActivity) * 60, count > 0 ? 4 : 2),
                      background: count > 0
                        ? "linear-gradient(to top, #9333ea, #a78bfa)"
                        : "#1f2937",
                      borderRadius: "3px 3px 0 0",
                      transition: "height 0.3s",
                    }} />
                  </div>
                  <span style={{
                    fontSize: "0.55rem", color: "#4b5563",
                    writingMode: "vertical-rl", transform: "rotate(180deg)",
                    whiteSpace: "nowrap",
                  }}>
                    {dayLabel}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Charts row ──────────────────────────────────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>

            {/* Top Keywords */}
            {/* <div style={{ ...card }}>
              <p style={{ ...label, marginBottom: 16 }}>Top Keywords</p>
              {topKeywords.length === 0 ? (
                <p style={{ color: "#4b5563", fontSize: "0.82rem" }}>No data yet</p>
              ) : topKeywords.map(([kw, count]) => (
                <div key={kw} style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: "0.8rem", color: "#d1d5db" }}>{kw}</span>
                    <span style={{ fontSize: "0.72rem", color: "#a78bfa", fontWeight: 700 }}>{count}</span>
                  </div>
                  <div style={{ height: 4, background: "#1f2937", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 2,
                      width: `${(count / (topKeywords[0]?.[1] || 1)) * 100}%`,
                      background: "linear-gradient(to right, #9333ea, #a78bfa)",
                      transition: "width 0.5s",
                    }} />
                  </div>
                </div>
              ))}
            </div> */}

            {/* Top Cities */}
            {/* <div style={{ ...card }}>
              <p style={{ ...label, marginBottom: 16 }}>Top Cities</p>
              {topCities.length === 0 ? (
                <p style={{ color: "#4b5563", fontSize: "0.82rem" }}>No data yet</p>
              ) : topCities.map(([city, count]) => (
                <div key={city} style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: "0.8rem", color: "#d1d5db" }}>{city}</span>
                    <span style={{ fontSize: "0.72rem", color: "#10b981", fontWeight: 700 }}>{count}</span>
                  </div>
                  <div style={{ height: 4, background: "#1f2937", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 2,
                      width: `${(count / (topCities[0]?.[1] || 1)) * 100}%`,
                      background: "linear-gradient(to right, #059669, #10b981)",
                      transition: "width 0.5s",
                    }} />
                  </div>
                </div>
              ))}
            </div> */}
          </div>

          {/* ── Recent searches table ────────────────────────────────────── */}
          <div style={{ ...card }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <p style={{ ...label, marginBottom: 0 }}>Recent Searches</p>
              <span style={{ fontSize: "0.72rem", color: "#4b5563" }}>
                {totalSearches} total
              </span>
            </div>

            {/* Table header */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "2.5fr 1.5fr 1.5fr 90px 80px 140px",
              padding: "8px 12px",
              background: "#252B3E", borderRadius: "8px 8px 0 0",
              fontSize: "0.65rem", fontWeight: 700, color: "#6b7280",
              textTransform: "uppercase", letterSpacing: "0.06em",
              borderBottom: "1px solid #374151",
            }}>
              <span>Establishment</span>
              <span>Keyword</span>
              <span>City</span>
              <span style={{ textAlign: "center" }}>Radius</span>
              <span style={{ textAlign: "center" }}>Found</span>
              <span style={{ textAlign: "right" }}>Date</span>
            </div>

            {/* Table rows */}
            <div style={{ border: "1px solid #374151", borderTop: "none", borderRadius: "0 0 8px 8px", overflow: "hidden" }}>
              {pageData.length === 0 ? (
                <div style={{ padding: "32px 16px", textAlign: "center", color: "#4b5563", fontSize: "0.85rem" }}>
                  No searches recorded yet
                </div>
              ) : pageData.map((row, i) => (
                <div key={row.task_id || i} style={{
                  display: "grid",
                  gridTemplateColumns: "2.5fr 1.5fr 1.5fr 90px 80px 140px",
                  padding: "10px 12px",
                  borderBottom: i < pageData.length - 1 ? "1px solid #1f2937" : "none",
                  alignItems: "center",
                  transition: "background 0.15s",
                }}
                  onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.02)"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <span style={{
                    fontSize: "0.82rem", color: "#f1f1f1", fontWeight: 500,
                    lineHeight: 1.4, whiteSpace: "normal", wordBreak: "break-word"
                  }}>
                    {row.establishment_name || "—"}
                  </span>
                  <span style={{ fontSize: "0.78rem", color: "#a78bfa" }}>
                    {row.keyword || "—"}
                  </span>
                  <span style={{ fontSize: "0.78rem", color: "#9ca3af" }}>
                    {row.city || "—"}{row.country ? `, ${row.country}` : ""}
                  </span>
                  <span style={{ textAlign: "center", fontSize: "0.78rem", color: "#f59e0b" }}>
                    {row.radius_km ? `${row.radius_km} km` : "—"}
                  </span>
                  <span style={{ textAlign: "center", fontSize: "0.78rem", color: "#10b981", fontWeight: 700 }}>
                    {row.places_found ?? "—"}
                  </span>
                  <span style={{ textAlign: "right", fontSize: "0.72rem", color: "#4b5563" }}>
                    {row.created_at
                      ? new Date(row.created_at).toLocaleString("en", {
                          month: "short", day: "numeric",
                          hour: "2-digit", minute: "2-digit",
                        })
                      : "—"}
                  </span>
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 8, marginTop: 16 }}>
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  style={{
                    padding: "5px 14px", borderRadius: 6,
                    border: "1px solid #374151", background: "transparent",
                    color: page === 1 ? "#374151" : "#9ca3af",
                    cursor: page === 1 ? "not-allowed" : "pointer",
                    fontSize: "0.78rem",
                  }}
                >← Prev</button>

                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
                  .reduce((acc, p, idx, arr) => {
                    if (idx > 0 && p - arr[idx - 1] > 1) acc.push("...");
                    acc.push(p);
                    return acc;
                  }, [])
                  .map((p, i) => p === "..." ? (
                    <span key={`ellipsis-${i}`} style={{ color: "#4b5563", fontSize: "0.78rem" }}>…</span>
                  ) : (
                    <button key={p} onClick={() => setPage(p)} style={{
                      padding: "5px 10px", borderRadius: 6,
                      border: `1px solid ${page === p ? "#9333ea" : "#374151"}`,
                      background: page === p ? "linear-gradient(to right, #9333ea, #4f46e5)" : "transparent",
                      color: page === p ? "#fff" : "#9ca3af",
                      cursor: "pointer", fontSize: "0.78rem", fontWeight: page === p ? 700 : 400,
                    }}>{p}</button>
                  ))}

                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  style={{
                    padding: "5px 14px", borderRadius: 6,
                    border: "1px solid #374151", background: "transparent",
                    color: page === totalPages ? "#374151" : "#9ca3af",
                    cursor: page === totalPages ? "not-allowed" : "pointer",
                    fontSize: "0.78rem",
                  }}
                >Next →</button>
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}