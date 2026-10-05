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

// -----------------------------------------------------------------------------
// Leaflet Marker Icons
// -----------------------------------------------------------------------------
delete L.Icon.Default.prototype._getIconUrl;

const defaultIcon = L.icon({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});

// Distinct Red Icon for Highlighted/Selected Pin
const selectedIcon = L.icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [30, 48],
  iconAnchor: [15, 48],
  popupAnchor: [1, -38],
});

// -----------------------------------------------------------------------------
// Helper Component: Handles smooth flying/zooming to selected pin
// -----------------------------------------------------------------------------
function MapController({ selectedScan }) {
  const map = useMap();

  useEffect(() => {
    if (selectedScan) {
      const lat = Number(selectedScan.latitude);
      const lng = Number(selectedScan.longitude);

      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        map.flyTo([lat, lng], 16, {
          duration: 1.5,
        });
      }
    }
  }, [selectedScan, map]);

  return null;
}

// -----------------------------------------------------------------------------
// Map Component
// -----------------------------------------------------------------------------
function ScanMap({ scans, selectedScan, onSelectScan, markerRefs }) {
  return (
    <MapContainer
      center={[20, 0]}
      zoom={2}
      style={{
        width: "100%",
        height: "100%",
      }}
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
              if (el) {
                markerRefs.current[key] = el;
              }
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

// -----------------------------------------------------------------------------
// Main Page Component
// -----------------------------------------------------------------------------
export default function ScanMapPage() {
  const [scans, setScans] = useState([]);
  const [selectedScan, setSelectedScan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isMobileCollapsed, setIsMobileCollapsed] = useState(false); // Default to open list on mobile
  const [isDesktopCollapsed, setIsDesktopCollapsed] = useState(false);

  const markerRefs = useRef({});
  const isFirstLoad = useRef(true);
  const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

  // Parse the 'type' query parameter from the URL
  const urlParams = new URLSearchParams(window.location.search);
  const typeParam = urlParams.get("type");

  // Format header title dynamically based on typeParam
  const headerTitle = typeParam
    ? `${typeParam.toUpperCase()} SCANS — LAST 24 HOURS`
    : "MEDSIGNQR SCANS — LAST 24 HOURS";

  useEffect(() => {
    let cancelled = false;

    async function fetchRecentScans(isInitialLoad = false) {
      if (isInitialLoad) {
        setLoading(true);
        setError(null); // Clear any old errors on load
      }

      try {
        let endpoint = `${baseUrl}/api/scans/last24hours`;
        if (typeParam) {
          endpoint += `?type=${encodeURIComponent(typeParam)}`;
        }

        const response = await fetch(endpoint);

        // If backend returns a non-OK status during initial load (warm-up), suppress showing error right away
        if (!response.ok) {
          if (!isInitialLoad) {
            setError("Failed to update scan coordinates.");
          }
          return;
        }

        const result = await response.json();

        if (cancelled) return;

        if (result.success) {
          const rawScans = Array.isArray(result.data) ? result.data : [];

          const sortedScans = [...rawScans].sort((a, b) => {
            const timeA = new Date(a.scanned_at || 0).getTime();
            const timeB = new Date(b.scanned_at || 0).getTime();
            return timeB - timeA;
          });

          setScans(sortedScans);
          setError(null); // Clear error on successful fetch

          if (isFirstLoad.current && sortedScans.length > 0) {
            setSelectedScan(sortedScans[0]);
            isFirstLoad.current = false;
          }
        } else {
          // Only set error if not in initial warm-up retry phase
          if (!isInitialLoad) {
            setError(result.detail || "Failed to load scan coordinates.");
          }
        }
      } catch (err) {
        if (cancelled) return;
        console.error("Map fetch error:", err);
        // Don't show critical network error banner immediately on first frame
        if (!isInitialLoad) {
          setError("Network error fetching scan locations.");
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
  }, [baseUrl, typeParam]);

  // Handle clicking an item in the sidebar/drawer menu
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
      {/* Dynamic CSS Rules for Responsive Behavior */}
      <style>{`
        /* Desktop Toggle Button Display */
        .mobile-toggle-btn {
          display: none !important;
        }
        .desktop-toggle-btn {
          display: flex !important;
        }

        /* Mobile Layout Modifications */
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
          .scan-drawer-header {
            position: sticky !important;
            top: 0 !important;
            z-index: 10 !important;
          }
          .scan-map-header h3 {
            font-size: 0.85rem !important;
          }
          .scan-map-header div {
            font-size: 0.75rem !important;
            padding: 3px 8px !important;
          }
        }
      `}</style>

      {/* Dynamic Header Title */}
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
          zIndex: 1000,
        }}
      >
        <h3 style={{ margin: 0, fontSize: "1.1rem" }}>{headerTitle}</h3>
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
      </header>

      {/* Main Container */}
      <div
        className="scan-map-content"
        style={{ display: "flex", flex: 1, minHeight: 0, position: "relative" }}
      >
        {/* Sidebar for Desktop / Drawer for Mobile */}
        <aside
          className="scan-map-sidebar"
          style={{
            width: isDesktopCollapsed ? "48px" : "320px",
            background: "#1e293b",
            color: "#f8fafc",
            display: "flex",
            flexDirection: "column",
            borderRight: "1px solid #334155",
            zIndex: 10,
            transition: "width 0.3s ease, height 0.3s ease",
            overflow: "hidden",
          }}
        >
          {/* Header Bar */}
          <div
            className="scan-drawer-header"
            onClick={toggleMobileDrawer}
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
            <span>Scanned Locations</span>

            {/* Desktop Only Toggle Button */}
            <button
              className="desktop-toggle-btn"
              onClick={(e) => {
                e.stopPropagation();
                setIsDesktopCollapsed(!isDesktopCollapsed);
              }}
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
                marginLeft: "auto",
              }}
            >
              {isDesktopCollapsed ? "▶" : "◀"}
            </button>

            {/* Mobile Only Toggle Button */}
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

          {/* Scanned Items List */}
          <div className="scan-list-container" style={{ flex: 1, overflowY: "auto" }}>
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
              const isSelected =
                selectedScan &&
                selectedScan.qr_id === scan.qr_id &&
                selectedScan.scanned_at === scan.scanned_at;

              return (
                <div
                  key={`${scan.qr_id}-${scan.scanned_at || idx}`}
                  onClick={() => handleItemClick(scan)}
                  style={{
                    padding: "12px 16px",
                    borderBottom: "1px solid #334155",
                    cursor: "pointer",
                    backgroundColor: isSelected ? "#3b82f6" : "transparent",
                    transition: "background-color 0.2s ease",
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = "#334155";
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = "transparent";
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

        {/* Map View */}
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