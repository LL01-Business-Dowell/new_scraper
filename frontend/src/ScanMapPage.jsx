import React, { useEffect, useState, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

delete L.Icon.Default.prototype._getIconUrl;

const defaultIcon = L.icon({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});

const selectedIcon = L.icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [30, 48],
  iconAnchor: [15, 48],
  popupAnchor: [1, -38],
});

function MapController({ selectedScan }) {
  const map = useMap();

  useEffect(() => {
    if (selectedScan) {
      const lat = Number(selectedScan.latitude);
      const lng = Number(selectedScan.longitude);

      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        map.flyTo([lat, lng], 16, { duration: 1.5 });
      }
    }
  }, [selectedScan, map]);

  return null;
}

function ScanMap({ scans, selectedScan, onSelectScan, markerRefs }) {
  return (
    <MapContainer
      center={[20, 0]}
      zoom={2}
      style={{ width: "100%", height: "100%" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <MapController selectedScan={selectedScan} />

      {scans.map((scan, idx) => {
        const latitude = Number(scan.latitude);
        const longitude = Number(scan.longitude);

        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
          return null;
        }

        const isSelected =
          selectedScan &&
          selectedScan.qr_id === scan.qr_id &&
          selectedScan.scanned_at === scan.scanned_at;

        return (
          <Marker
            key={`${scan.qr_id || "scan"}-${scan.scanned_at || idx}-${idx}`}
            position={[latitude, longitude]}
            icon={isSelected ? selectedIcon : defaultIcon}
            ref={(el) => {
              const key = `${scan.qr_id}-${scan.scanned_at}`;
              if (el) markerRefs.current[key] = el;
            }}
            eventHandlers={{
              click: () => onSelectScan(scan),
            }}
          >
            <Popup>
              <div style={{ fontSize: "13px", lineHeight: "1.4" }}>
                <strong>QR ID:</strong> {scan.qr_id || "N/A"}
                <br />
                <strong>Time:</strong>{" "}
                {scan.scanned_at
                  ? new Date(scan.scanned_at).toLocaleString()
                  : "N/A"}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}

export default function ScanMapPage() {
  const [scans, setScans] = useState([]);
  const [selectedScan, setSelectedScan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Both collapsed by default
  const [isMobileCollapsed, setIsMobileCollapsed] = useState(true);
  const [isDesktopCollapsed, setIsDesktopCollapsed] = useState(true);

  // Highlighting new scans state
  const [highlightedScanKeys, setHighlightedScanKeys] = useState(new Set());
  const previousScanKeysRef = useRef(new Set());

  const markerRefs = useRef({});

  // Clean raw environment variable to eliminate literal quotes
  const rawBaseUrl = import.meta.env.VITE_API_URL || "";
  const baseUrl = rawBaseUrl.replace(/['"]/g, "").trim();

  // Parse URL parameters
  const urlParams = new URLSearchParams(window.location.search);
  const typeParam = urlParams.get("type");
  const timeParam = urlParams.get("time");

  const getInitialTime = () => {
    if (timeParam === "7" || timeParam === "7d") return "168";
    if (timeParam === "15" || timeParam === "15d") return "360";
    if (timeParam === "30" || timeParam === "30d") return "720";
    return "24";
  };

  const [timeRangeHours, setTimeRangeHours] = useState(getInitialTime);

  const handleTimeChange = (e) => {
    const selectedHours = e.target.value;
    setTimeRangeHours(selectedHours);

    let timeUrlValue = "24";
    if (selectedHours === "168") timeUrlValue = "7";
    if (selectedHours === "360") timeUrlValue = "15";
    if (selectedHours === "720") timeUrlValue = "30";

    const newSearchParams = new URLSearchParams(window.location.search);
    newSearchParams.set("time", timeUrlValue);
    window.history.replaceState(
      {},
      "",
      `${window.location.pathname}?${newSearchParams.toString()}`
    );
  };

  const timeLabelMap = {
    "24": "LAST 24 HOURS",
    "168": "LAST 7 DAYS",
    "360": "LAST 15 DAYS",
    "720": "LAST 30 DAYS",
  };

  const headerTitle = typeParam
    ? `${typeParam.toUpperCase()} SCANS — ${timeLabelMap[timeRangeHours]}`
    : `MEDSIGNQR SCANS — ${timeLabelMap[timeRangeHours]}`;

  useEffect(() => {
    let cancelled = false;

    async function fetchRecentScans(isInitialLoad = false) {
      if (isInitialLoad) {
        setLoading(true);
        setError(null);
      }

      try {
        let endpoint = `/api/scans/last24hours?hours=${timeRangeHours}`;
        if (typeParam) {
          endpoint += `&type=${encodeURIComponent(typeParam)}`;
        }

        if (baseUrl) {
          endpoint = `${baseUrl.replace(/\/$/, "")}${endpoint}`;
        }

        const response = await fetch(endpoint);
        const rawText = await response.text();

        if (!response.ok) {
          console.warn(`[Background Refresh Warning] Server returned HTTP ${response.status}`);
          if (isInitialLoad) {
            setError("Unable to load scan locations right now. Please try again later.");
          }
          return;
        }

        let result;
        try {
          result = JSON.parse(rawText);
        } catch (jsonErr) {
          console.error("[Parse Error] Non-JSON response received:", rawText.slice(0, 300));
          if (isInitialLoad) {
            setError("Unable to load scan locations right now. Please try again later.");
          }
          return;
        }

        if (cancelled) return;

        if (result.success) {
          const rawScans = Array.isArray(result.data) ? result.data : [];

          const sortedScans = [...rawScans].sort((a, b) => {
            const timeA = new Date(a.scanned_at || 0).getTime();
            const timeB = new Date(b.scanned_at || 0).getTime();
            return timeB - timeA;
          });

          const currentKeys = new Set(
            sortedScans.map((s) => `${s.qr_id}-${s.scanned_at}`)
          );

          if (previousScanKeysRef.current.size > 0) {
            const newlyAddedKeys = new Set();
            currentKeys.forEach((key) => {
              if (!previousScanKeysRef.current.has(key)) {
                newlyAddedKeys.add(key);
              }
            });

            if (newlyAddedKeys.size > 0) {
              setHighlightedScanKeys(newlyAddedKeys);
              
              if (sortedScans.length > 0) {
                setSelectedScan(sortedScans[0]);
              }

              setTimeout(() => {
                setHighlightedScanKeys(new Set());
              }, 2000);
            }
          }

          previousScanKeysRef.current = currentKeys;
          setScans(sortedScans);
          setError(null);

          if (isInitialLoad && sortedScans.length > 0) {
            setSelectedScan(sortedScans[0]);
          }
        } else {
          if (isInitialLoad) {
            setError("No scan data available.");
          }
        }
      } catch (err) {
        if (cancelled) return;
        console.error("Map fetch network exception:", err);
        if (isInitialLoad) {
          setError("Unable to connect to service. Please check your network connection.");
        }
      } finally {
        if (!cancelled && isInitialLoad) {
          setLoading(false);
        }
      }
    }

    fetchRecentScans(true);

    const intervalId = setInterval(() => {
      fetchRecentScans(false);
    }, 3000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [baseUrl, typeParam, timeRangeHours]);

  const handleItemClick = (scan) => {
    setSelectedScan(scan);

    const key = `${scan.qr_id}-${scan.scanned_at}`;
    const markerInstance = markerRefs.current[key];

    if (markerInstance) {
      markerInstance.openPopup();
    }
  };

  const toggleMobileDrawer = () => {
    setIsMobileCollapsed((prev) => !prev);
  };

  const toggleDesktopDrawer = (e) => {
    e.stopPropagation();
    setIsDesktopCollapsed((prev) => !prev);
  };

  return (
    <div
      style={{
        width: "100%",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <style>{`
        .mobile-toggle-btn {
          display: none !important;
        }
        .desktop-toggle-btn {
          display: flex !important;
        }

        @keyframes highlightPulse {
          0% { background-color: #f59e0b; }
          100% { background-color: transparent; }
        }

        .new-scan-highlight {
          animation: highlightPulse 2s ease-out;
        }

        /* Desktop View Styling */
        @media (min-width: 769px) {
          .scan-map-sidebar {
            position: absolute !important;
            top: 0 !important;
            left: 0 !important;
            bottom: 0 !important;
            height: 100% !important;
            z-index: 2000 !important;
            box-shadow: 4px 0 20px rgba(0,0,0,0.4);
          }
          .scan-list-container {
            display: ${isDesktopCollapsed ? "none" : "block"} !important;
          }
          .drawer-title-text {
            display: ${isDesktopCollapsed ? "none" : "inline"} !important;
          }
        }

        /* Mobile View Styling */
        @media (max-width: 768px) {
          .mobile-toggle-btn {
            display: flex !important;
          }
          .desktop-toggle-btn {
            display: none !important;
          }
          .scan-map-sidebar {
            width: 100% !important;
            height: ${isMobileCollapsed ? "48px" : "45vh"} !important;
            position: absolute !important;
            bottom: 0 !important;
            left: 0 !important;
            right: 0 !important;
            z-index: 2000 !important;
            border-right: none !important;
            border-top: 2px solid #334155 !important;
            box-shadow: 0 -4px 20px rgba(0,0,0,0.5);
          }
          .scan-list-container {
            display: ${isMobileCollapsed ? "none" : "block"} !important;
          }
          .drawer-title-text {
            display: inline !important;
          }
        }
      `}</style>

      {/* Header */}
      <header
        className="scan-map-header"
        style={{
          flexShrink: 0,
          padding: "12px 16px",
          background: "#0f172a",
          color: "#ffffff",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          zIndex: 2001,
        }}
      >
        <h3 style={{ margin: 0, fontSize: "1.1rem" }}>{headerTitle}</h3>

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <select
            value={timeRangeHours}
            onChange={handleTimeChange}
            style={{
              background: "#1e293b",
              color: "#38bdf8",
              border: "1px solid #334155",
              borderRadius: "6px",
              padding: "4px 8px",
              fontSize: "0.85rem",
              fontWeight: "bold",
              cursor: "pointer",
            }}
          >
            <option value="24">24 Hours</option>
            <option value="168">7 Days</option>
            <option value="360">15 Days</option>
            <option value="720">30 Days</option>
          </select>

          <div
            style={{
              background: "#3b82f6",
              padding: "4px 12px",
              borderRadius: "12px",
              fontSize: "0.9rem",
              fontWeight: "bold",
              whiteSpace: "nowrap",
            }}
          >
            Total Scans: {scans.length}
          </div>
        </div>
      </header>

      {/* Content Area */}
      <div
        className="scan-map-content"
        style={{ display: "flex", flex: 1, minHeight: 0, position: "relative" }}
      >
        {/* Sidebar / Mobile Bottom Drawer */}
        <aside
          className="scan-map-sidebar"
          style={{
            width: isDesktopCollapsed ? "48px" : "320px",
            background: "#1e293b",
            color: "#f8fafc",
            display: "flex",
            flexDirection: "column",
            borderRight: "1px solid #334155",
            transition: "width 0.3s ease, height 0.3s ease",
            overflow: "hidden",
          }}
        >
          <div
            className="scan-drawer-header"
            onClick={(e) => {
              if (window.innerWidth <= 768) {
                toggleMobileDrawer();
              } else {
                toggleDesktopDrawer(e);
              }
            }}
            style={{
              padding: "12px 16px",
              background: "#0f172a",
              borderBottom: "1px solid #334155",
              fontSize: "0.85rem",
              fontWeight: "bold",
              textTransform: "uppercase",
              color: "#94a3b8",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              cursor: "pointer",
              userSelect: "none",
              flexShrink: 0,
            }}
          >
            <span className="drawer-title-text">Scanned Locations</span>

            <button
              className="desktop-toggle-btn"
              onClick={toggleDesktopDrawer}
              aria-label="Toggle sidebar width"
              style={{
                background: "#334155",
                border: "none",
                borderRadius: "4px",
                color: "#38bdf8",
                cursor: "pointer",
                padding: "4px 8px",
                fontSize: "0.75rem",
                alignItems: "center",
                fontWeight: "bold",
                marginLeft: isDesktopCollapsed ? "auto" : "0",
              }}
            >
              {isDesktopCollapsed ? "▶" : "◀ HIDE"}
            </button>

            <button
              className="mobile-toggle-btn"
              onClick={(e) => {
                e.stopPropagation();
                toggleMobileDrawer();
              }}
              aria-label="Toggle scan list view"
              style={{
                background: "#334155",
                border: "none",
                borderRadius: "4px",
                color: "#38bdf8",
                cursor: "pointer",
                padding: "4px 8px",
                fontSize: "0.75rem",
                alignItems: "center",
                fontWeight: "bold",
              }}
            >
              {isMobileCollapsed ? "▲ SHOW LIST" : "▼ HIDE"}
            </button>
          </div>

          <div
            className="scan-list-container"
            style={{
              flex: 1,
              overflowY: "auto",
            }}
          >
            {scans.length === 0 && !loading && (
              <div
                style={{
                  padding: "16px",
                  color: "#94a3b8",
                  fontSize: "0.9rem",
                  textAlign: "center",
                }}
              >
                No scans recorded.
              </div>
            )}

            {scans.map((scan, idx) => {
              const itemKey = `${scan.qr_id}-${scan.scanned_at}`;
              const isSelected =
                selectedScan &&
                selectedScan.qr_id === scan.qr_id &&
                selectedScan.scanned_at === scan.scanned_at;

              const isHighlighted = highlightedScanKeys.has(itemKey);

              return (
                <div
                  key={`${scan.qr_id}-${scan.scanned_at || idx}`}
                  onClick={() => handleItemClick(scan)}
                  className={isHighlighted ? "new-scan-highlight" : ""}
                  style={{
                    padding: "12px 16px",
                    borderBottom: "1px solid #334155",
                    cursor: "pointer",
                    backgroundColor: isSelected
                      ? "#3b82f6"
                      : isHighlighted
                      ? "#f59e0b"
                      : "transparent",
                    transition: "background-color 0.2s ease",
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected && !isHighlighted)
                      e.currentTarget.style.backgroundColor = "#334155";
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected && !isHighlighted)
                      e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  <div
                    style={{
                      fontWeight: "bold",
                      fontSize: "0.95rem",
                      color: isSelected ? "#ffffff" : "#38bdf8",
                    }}
                  >
                    ID: {scan.qr_id}
                  </div>
                  <div
                    style={{
                      fontSize: "0.75rem",
                      color: isSelected ? "#e2e8f0" : "#94a3b8",
                      marginTop: "4px",
                    }}
                  >
                    {scan.scanned_at
                      ? new Date(scan.scanned_at).toLocaleString()
                      : "N/A"}
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Map */}
        <main style={{ flex: 1, position: "relative", width: "100%", height: "100%" }}>
          <ScanMap
            scans={scans}
            selectedScan={selectedScan}
            onSelectScan={handleItemClick}
            markerRefs={markerRefs}
          />

          {loading && (
            <div
              style={{
                position: "absolute",
                top: 20,
                left: "50%",
                transform: "translateX(-50%)",
                zIndex: 1000,
                background: "#ffffff",
                padding: "10px 18px",
                borderRadius: "8px",
                boxShadow: "0 2px 10px rgba(0, 0, 0, 0.15)",
                color: "#64748b",
                fontSize: "14px",
              }}
            >
              Loading scan locations...
            </div>
          )}

          {error && (
            <div
              style={{
                position: "absolute",
                top: 20,
                left: "50%",
                transform: "translateX(-50%)",
                zIndex: 1000,
                background: "#ffffff",
                padding: "10px 18px",
                borderRadius: "8px",
                boxShadow: "0 2px 10px rgba(0, 0, 0, 0.15)",
                color: "#ef4444",
                fontSize: "14px",
                maxWidth: "90%",
                textAlign: "center",
              }}
            >
              {error}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}