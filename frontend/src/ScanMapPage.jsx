import React, { useEffect, useState } from "react";
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
// Leaflet default marker icons
// -----------------------------------------------------------------------------

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// -----------------------------------------------------------------------------
// Automatically fit the map to all valid scan coordinates
// -----------------------------------------------------------------------------

function AutoBounds({ markers }) {
  const map = useMap();

  useEffect(() => {
    const validMarkers = markers.filter(
      (marker) =>
        Number.isFinite(Number(marker.latitude)) &&
        Number.isFinite(Number(marker.longitude))
    );

    if (validMarkers.length === 0) {
      map.setView([20, 0], 2);
      return;
    }

    const bounds = validMarkers.map((marker) => [
      Number(marker.latitude),
      Number(marker.longitude),
    ]);

    if (bounds.length === 1) {
      map.setView(bounds[0], 13);
      return;
    }

    map.fitBounds(bounds, {
      padding: [50, 50],
      maxZoom: 15,
    });
  }, [markers, map]);

  return null;
}

// -----------------------------------------------------------------------------
// Map itself
// -----------------------------------------------------------------------------

function ScanMap({ scans }) {
  return (
    <MapContainer
      center={[20, 0]}
      zoom={2}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
      }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {scans.map((scan, idx) => {
        const latitude = Number(scan.latitude);
        const longitude = Number(scan.longitude);

        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
          return null;
        }

        return (
          <Marker
            key={`${scan.qr_id || "scan"}-${scan.scanned_at || idx}-${idx}`}
            position={[latitude, longitude]}
          >
            <Popup>
              <div
                style={{
                  fontSize: "13px",
                  lineHeight: "1.4",
                }}
              >
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

      <AutoBounds markers={scans} />
    </MapContainer>
  );
}

// -----------------------------------------------------------------------------
// Main page
// -----------------------------------------------------------------------------

export default function ScanMapPage() {
  const [scans, setScans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const baseUrl =
    import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

  useEffect(() => {
    let cancelled = false;

    async function fetchRecentScans() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `${baseUrl}/api/scans/last24hours`
        );

        const result = await response.json();

        if (cancelled) {
          return;
        }

        if (response.ok && result.success) {
          setScans(Array.isArray(result.data) ? result.data : []);
        } else {
          setError(
            result.detail || "Failed to load scan coordinates."
          );
        }
      } catch (err) {
        if (cancelled) {
          return;
        }

        console.error("Map fetch error:", err);
        setError("Network error fetching scan locations.");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchRecentScans();

    return () => {
      cancelled = true;
    };
  }, [baseUrl]);

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
          position: "relative",
          zIndex: 1000,
        }}
      >
        <h3
          style={{
            margin: 0,
            fontSize: "1.1rem",
          }}
        >
          Scan Activity — Last 24 Hours
        </h3>

        <div
          style={{
            background: "#3b82f6",
            padding: "4px 12px",
            borderRadius: "12px",
            fontSize: "0.9rem",
            fontWeight: "bold",
          }}
        >
          Total Pins: {scans.length}
        </div>
      </header>

      {/* Map area */}
      <div
        style={{
          position: "relative",
          flex: 1,
          minHeight: 0,
        }}
      >
        {/* Map is ALWAYS mounted */}
        <ScanMap scans={scans} />

        {/* Loading overlay */}
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
            Loading map pins...
          </div>
        )}

        {/* Error overlay */}
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
      </div>
    </div>
  );
}