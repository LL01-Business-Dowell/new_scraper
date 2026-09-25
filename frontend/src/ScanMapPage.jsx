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

        const isSelected = selectedScan && selectedScan.qr_id === scan.qr_id && selectedScan.scanned_at === scan.scanned_at;

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

  const markerRefs = useRef({});
  const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

  useEffect(() => {
    let cancelled = false;

    async function fetchRecentScans() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(`${baseUrl}/api/scans/last24hours`);
        const result = await response.json();

        if (cancelled) return;

        if (response.ok && result.success) {
          setScans(Array.isArray(result.data) ? result.data : []);
        } else {
          setError(result.detail || "Failed to load scan coordinates.");
        }
      } catch (err) {
        if (cancelled) return;
        console.error("Map fetch error:", err);
        setError("Network error fetching scan locations.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchRecentScans();

    return () => {
      cancelled = true;
    };
  }, [baseUrl]);

  // Handle clicking an item in the sidebar menu
  const handleItemClick = (scan) => {
    setSelectedScan(scan);

    const key = `${scan.qr_id}-${scan.scanned_at}`;
    const markerInstance = markerRefs.current[key];

    if (markerInstance) {
      markerInstance.openPopup();
    }
  };

  return (
    <div style={{ width: "100%", height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Header */}
      <header
        style={{
          flexShrink: 0,
          padding: "14px 20px",
          background: "#0f172a",
          color: "#ffffff",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          zIndex: 1000,
        }}
      >
        <h3 style={{ margin: 0, fontSize: "1.1rem" }}>MedSignQR Scan — Last 24 Hours</h3>
        <div style={{ background: "#3b82f6", padding: "4px 12px", borderRadius: "12px", fontSize: "0.9rem", fontWeight: "bold" }}>
          Total Scans: {scans.length}
        </div>
      </header>

      {/* Content Wrapper */}
      <div style={{ display: "flex", flex: 1, minHeight: 0, position: "relative" }}>
        
        {/* Sidebar Menu */}
        <aside
          style={{
            width: "320px",
            background: "#1e293b",
            color: "#f8fafc",
            display: "flex",
            flexDirection: "column",
            borderRight: "1px solid #334155",
            zIndex: 10,
          }}
        >
          <div style={{ padding: "12px 16px", background: "#0f172a", borderBottom: "1px solid #334155", fontSize: "0.85rem", fontWeight: "bold", textTransform: "uppercase", color: "#94a3b8" }}>
            Scanned IDs
          </div>

          <div style={{ flex: 1, overflowY: "auto" }}>
            {scans.length === 0 && !loading && (
              <div style={{ padding: "16px", color: "#94a3b8", fontSize: "0.9rem", textAlign: "center" }}>
                No scans recorded.
              </div>
            )}

            {scans.map((scan, idx) => {
              const isSelected = selectedScan && selectedScan.qr_id === scan.qr_id && selectedScan.scanned_at === scan.scanned_at;

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
                  <div style={{ fontWeight: "bold", fontSize: "0.95rem", color: isSelected ? "#ffffff" : "#38bdf8" }}>
                    ID: {scan.qr_id}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: isSelected ? "#e2e8f0" : "#94a3b8", marginTop: "4px" }}>
                    {scan.scanned_at ? new Date(scan.scanned_at).toLocaleString() : "N/A"}
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Main Map Container */}
        <main style={{ flex: 1, position: "relative" }}>
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