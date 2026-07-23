/**
 * PlacePicker.jsx
 */

import React, { useState, useRef, useEffect } from "react";
import {
  APIProvider,
  Map,
  AdvancedMarker,
  Pin,
  useMap,
  useMapsLibrary,
} from "@vis.gl/react-google-maps";

const defaultCenter = {
  lat: 20.5937,
  lng: 78.9629,
};

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";

function AutocompleteInput({
  city,
  onSelect,
  setSelectedLocation,
  setMapCenter,
  setQuery,
  selectedName,
}) {
  const places = useMapsLibrary("places");
  const containerRef = useRef(null);
  const autocompleteRef = useRef(null);

  useEffect(() => {
    if (!places || !containerRef.current) return;

    containerRef.current.innerHTML = "";

    const autocomplete = new places.PlaceAutocompleteElement();
    autocomplete.style.width = "100%";
    autocomplete.style.display = "block";
    autocompleteRef.current = autocomplete;

    containerRef.current.appendChild(autocomplete);

    const handleSelect = async (event) => {
      try {
        let place = event.place;
        if (!place && event.placePrediction) {
          place = event.placePrediction.toPlace();
        }
        if (!place) return;

        await place.fetchFields({
          fields: [
            "id",
            "displayName",
            "formattedAddress",
            "location",
            "addressComponents",
            "googleMapsURI",
          ],
        });

        if (!place.location) {
          alert("No location details available for this selection.");
          return;
        }

        const lat = typeof place.location.lat === "function" ? place.location.lat() : place.location.lat;
        const lng = typeof place.location.lng === "function" ? place.location.lng() : place.location.lng;
        
        const cleanName =
          place.displayName ||
          place.formattedAddress?.split(",")[0]?.trim() ||
          "Selected Location";

        let extractedCity = "";
        let extractedCountry = "";

        if (place.addressComponents) {
          place.addressComponents.forEach((comp) => {
            const types = comp.types || [];
            if (types.includes("locality") || types.includes("postal_town")) {
              extractedCity = comp.longText || comp.shortText;
            } else if (!extractedCity && types.includes("administrative_area_level_2")) {
              extractedCity = comp.longText || comp.shortText;
            } else if (!extractedCity && types.includes("administrative_area_level_1")) {
              extractedCity = comp.longText || comp.shortText;
            }

            if (types.includes("country")) {
              extractedCountry = comp.longText || comp.shortText;
            }
          });
        }

        if (!extractedCity && place.formattedAddress) {
          const parts = place.formattedAddress.split(",");
          if (parts.length >= 2) {
            extractedCity = parts[parts.length - 2].trim();
          }
        }

        const locationData = { lat, lng };
        setSelectedLocation(locationData);
        setMapCenter(locationData);
        setQuery(cleanName);

        onSelect?.({
          name: cleanName,
          display_name: place.formattedAddress || cleanName,
          lat: lat,
          lon: lng,
          googleMapsUri: place.googleMapsURI || `https://www.google.com/maps/place/?q=place_id:${place.id}`,
          place_id: place.id,
          address: {
            city: extractedCity || city || "Selected Area",
            country: extractedCountry,
          },
        });
      } catch (err) {
        console.error("Error fetching place details:", err);
      }
    };

    autocomplete.addEventListener("gmp-select", handleSelect);

    return () => {
      autocomplete.removeEventListener("gmp-select", handleSelect);
    };
  }, [places, city, onSelect, setSelectedLocation, setMapCenter, setQuery]);

  // Clears the underlying Google Autocomplete input element when form resets
  useEffect(() => {
    if (!selectedName && autocompleteRef.current) {
      if ("value" in autocompleteRef.current) {
        autocompleteRef.current.value = "";
      }
    }
  }, [selectedName]);

  return <div ref={containerRef} style={{ width: "100%", display: "block" }} />;
}

function MapCameraUpdater({ location }) {
  const map = useMap();

  useEffect(() => {
    if (map && location) {
      map.panTo(location);
      map.setZoom(16);
    }
  }, [map, location]);

  return null;
}

function MapContent({
  defaultMapCenter,
  selectedLocation,
  selectedName,
  setSelectedLocation,
  setMapCenter,
  setQuery,
  onSelect,
  city,
  country,
  handleClear,
}) {
  const geocodingLib = useMapsLibrary("geocoding");

  const handleMapClick = async (e) => {
    if (!e.detail?.latLng) return;
    const lat = e.detail.latLng.lat;
    const lng = e.detail.latLng.lng;
    const locationData = { lat, lng };

    setSelectedLocation(locationData);
    setMapCenter(locationData);

    if (geocodingLib) {
      const geocoder = new geocodingLib.Geocoder();
      try {
        const response = await geocoder.geocode({ location: locationData });
        if (response.results?.[0]) {
          const result = response.results[0];
          const cleanName = result.formatted_address.split(",")[0] || "Pinned Location";

          let extractedCity = "";
          let extractedCountry = "";

          result.address_components.forEach((comp) => {
            if (comp.types.includes("locality") || comp.types.includes("postal_town")) {
              extractedCity = comp.long_name;
            } else if (!extractedCity && comp.types.includes("administrative_area_level_2")) {
              extractedCity = comp.long_name;
            }
            if (comp.types.includes("country")) {
              extractedCountry = comp.long_name;
            }
          });

          setQuery(cleanName);
          onSelect?.({
            name: cleanName,
            display_name: result.formatted_address,
            lat,
            lon: lng,
            googleMapsUri: `https://www.google.com/maps/place/?q=${lat},${lng}`,
            place_id: result.place_id,
            address: {
              city: extractedCity || city || "Pinned Area",
              country: extractedCountry || country,
            },
          });
          return;
        }
      } catch (err) {
        console.warn("Geocoding failed on click:", err);
      }
    }

    const fallbackName = `Pinned Location (${lat.toFixed(4)}, ${lng.toFixed(4)})`;
    setQuery(fallbackName);
    onSelect?.({
      name: fallbackName,
      display_name: fallbackName,
      lat,
      lon: lng,
      googleMapsUri: `https://www.google.com/maps/place/?q=${lat},${lng}`,
      address: { city: city || "Pinned Area", country },
    });
  };

  return (
    <div
      style={{
        marginTop: 8,
        borderRadius: 12,
        overflow: "hidden",
        border: "1px solid #334155",
        width: "100%",
        position: "relative",
        height: "clamp(320px, 55vh, 500px)",
        background: "#0f172a",
      }}
    >
      <Map
        style={{ width: "100%", height: "100%" }}
        defaultCenter={defaultMapCenter}
        defaultZoom={6}
        mapId="DEMO_MAP_ID"
        gestureHandling={"greedy"}
        disableDefaultUI={false}
        onClick={handleMapClick}
      >
        <MapCameraUpdater location={selectedLocation} />

        {selectedLocation && (
          <AdvancedMarker position={selectedLocation} title={selectedName}>
            <Pin background={"#0ea5e9"} glyphColor={"#ffffff"} borderColor={"#0284c7"} />
          </AdvancedMarker>
        )}
      </Map>

      {selectedLocation && (
        <button
          type="button"
          onClick={handleClear}
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            background: "rgba(15, 23, 42, 0.9)",
            border: "1px solid #ef4444",
            color: "#fca5a5",
            borderRadius: 8,
            padding: "8px 14px",
            fontSize: "0.8rem",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.3)",
            zIndex: 10,
          }}
        >
          🗑️ Remove Pin
        </button>
      )}
    </div>
  );
}

export default function PlacePicker({
  keyword = "",
  city = "",
  country = "",
  onSelect,
  selectedName = "",
  required = false,
}) {
  const [mapCenter, setMapCenter] = useState(defaultCenter);
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [query, setQuery] = useState(selectedName || "");

  useEffect(() => {
    if (selectedName) {
      setQuery(selectedName);
    } else {
      setSelectedLocation(null);
      setQuery("");
      setMapCenter(defaultCenter);
    }
  }, [selectedName]);

  const handleClear = () => {
    setSelectedLocation(null);
    setQuery("");
    setMapCenter(defaultCenter);
    onSelect?.(null);
  };

  return (
    <APIProvider apiKey={API_KEY}>
      <div style={{ width: "100%", marginBottom: 8 }}>
        <p
          style={{
            fontSize: "0.72rem",
            fontWeight: 700,
            color: "#475569",
            letterSpacing: "0.07em",
            textTransform: "uppercase",
            margin: "0 0 8px 0",
          }}
        >
          Your {keyword || "establishment"}
          {required && <span style={{ color: "#ef4444", marginLeft: 4 }}>*required</span>}
        </p>

        <div style={{ display: "flex", gap: 8, width: "100%", alignItems: "center" }}>
          <div style={{ flex: 1, minWidth: 0, width: "100%" }}>
            <AutocompleteInput
              city={city}
              onSelect={onSelect}
              setSelectedLocation={setSelectedLocation}
              setMapCenter={setMapCenter}
              setQuery={setQuery}
              selectedName={selectedName}
            />
          </div>

          {selectedName && (
            <button
              type="button"
              onClick={handleClear}
              style={{
                background: "none",
                border: "1px solid #334155",
                borderRadius: 8,
                color: "#94a3b8",
                padding: "0 12px",
                height: "42px",
                fontSize: "0.8rem",
                cursor: "pointer",
                flexShrink: 0,
              }}
            >
              ✕
            </button>
          )}
        </div>

        {selectedName && (
          <div
            style={{
              marginTop: 8,
              background: "#0ea5e915",
              border: "1px solid #0ea5e944",
              borderRadius: 8,
              padding: "9px 14px",
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: "0.84rem",
            }}
          >
            <span>📍</span>
            <span style={{ fontWeight: 700, color: "#7dd3fc" }}>{selectedName}</span>
            <span style={{ color: "#334155", fontSize: "0.73rem" }}>— selected</span>
          </div>
        )}

        <MapContent
          defaultMapCenter={mapCenter}
          selectedLocation={selectedLocation}
          selectedName={selectedName}
          setSelectedLocation={setSelectedLocation}
          setMapCenter={setMapCenter}
          setQuery={setQuery}
          onSelect={onSelect}
          city={city}
          country={country}
          handleClear={handleClear}
        />

        {!selectedName && (
          <p style={{ fontSize: "0.72rem", color: "#334155", marginTop: 6 }}>
            Search above or click anywhere on the map to pin your establishment.
          </p>
        )}
      </div>
    </APIProvider>
  );
}