import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import API_BASE_URL from "./config";

const BASE = (API_BASE_URL || "").replace(/\/+$/, "");

const MicIcon = () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="23" />
        <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
);

const StopIcon = () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
        <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
);

const CheckIcon = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
    </svg>
);

const RefreshIcon = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23 4 23 10 17 10" />
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
);

const StarIcon = ({ filled, onClick, onMouseEnter, onMouseLeave }) => (
    <svg
        onClick={onClick}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        width="28"
        height="28"
        viewBox="0 0 24 24"
        fill={filled ? "#10b981" : "none"}
        stroke={filled ? "#10b981" : "#A8C4B4"}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ cursor: "pointer", transition: "transform 0.15s ease, fill 0.15s ease" }}
    >
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
);

const styles = {
    page: {
        minHeight: "100vh",
        background: "linear-gradient(135deg, #F4F7F5 0%, #E8EFEB 50%, #DDE7E1 100%)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-start",
        padding: "1.5rem 1rem",
        fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif",
    },
    card: {
        background: "rgba(255, 255, 255, 0.95)",
        backdropFilter: "blur(12px)",
        border: "1px solid #D1E0D7",
        borderRadius: 16,
        padding: "1.25rem 1.5rem 1.5rem",
        width: "100%",
        maxWidth: 440,
        boxShadow: "0 12px 32px rgba(27, 59, 43, 0.06)",
        position: "relative",
    },
    topBar: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "1rem",
        paddingBottom: "0.75rem",
        borderBottom: "1px solid #D1E0D7",
    },
    closeBtn: {
        backgroundColor: "#10b981",
        color: "#ffffff",
        border: "none",
        padding: "0.4rem 0.9rem",
        fontWeight: "700",
        borderRadius: "8px",
        cursor: "pointer",
        fontSize: "0.82rem",
        transition: "background-color 0.2s, transform 0.1s, opacity 0.2s",
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
    },
    title: {
        fontSize: "1.35rem",
        fontWeight: 700,
        color: "#1B3B2B",
        margin: 0,
        letterSpacing: "-0.01em",
    },
    subtitle: {
        fontSize: "0.78rem",
        color: "#527060",
        margin: 0,
    },
    label: {
        display: "block",
        fontSize: "0.72rem",
        fontWeight: 700,
        color: "#2E5A44",
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        marginBottom: 4,
    },
    batchDisplay: {
        fontSize: "0.78rem",
        fontWeight: 600,
        color: "#1B3B2B",
        background: "#EAF2EC",
        padding: "3px 8px",
        borderRadius: 4,
        border: "1px solid #C2D6CA",
        wordBreak: "break-all",
    },
    textarea: {
        width: "100%",
        padding: "8px 10px",
        borderRadius: 6,
        background: "#FAFCFA",
        border: "1px solid #C2D6CA",
        color: "#1B3B2B",
        fontSize: "0.85rem",
        outline: "none",
        boxSizing: "border-box",
        resize: "vertical",
        minHeight: 60,
    },
    ratingContainer: {
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "#F2F7F4",
        border: "1px solid #D1E0D7",
        borderRadius: 8,
        padding: "10px",
        marginBottom: "1rem",
    },
    starsWrapper: {
        display: "flex",
        gap: "6px",
        marginTop: "2px",
    },
    consentBox: {
        background: "#F2F7F4",
        border: "1px solid #D1E0D7",
        borderRadius: 12,
        padding: "14px",
        marginBottom: "1rem",
    },
    consentTitle: {
        fontSize: "0.78rem",
        fontWeight: 700,
        color: "#2E5A44",
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        marginBottom: 6,
    },
    consentText: {
        fontSize: "0.8rem",
        color: "#385445",
        lineHeight: 1.5,
        margin: 0,
    },
    consentCheck: {
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        marginTop: 10,
        cursor: "pointer",
    },
    checkbox: {
        width: 16,
        height: 16,
        borderRadius: 4,
        flexShrink: 0,
        border: "2px solid #2E5A44",
        marginTop: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
    },
    micBtn: (recording) => ({
        width: 64,
        height: 64,
        borderRadius: "50%",
        border: "none",
        background: recording
            ? "linear-gradient(135deg, #C93B3B, #A82E2E)"
            : "linear-gradient(135deg, #2E5A44, #1B3B2B)",
        color: "#FFF",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: recording
            ? "0 0 0 6px rgba(201, 59, 59, 0.15), 0 6px 18px rgba(201, 59, 59, 0.25)"
            : "0 6px 16px rgba(46, 90, 68, 0.25)",
        transition: "all 0.3s ease",
        transform: recording ? "scale(1.05)" : "scale(1)",
    }),
    pulseRing: {
        position: "absolute",
        width: 64,
        height: 64,
        borderRadius: "50%",
        border: "2px solid rgba(201, 59, 59, 0.4)",
        animation: "pulse 1.5s ease-out infinite",
    },
    timer: {
        fontSize: "0.8rem",
        color: "#C93B3B",
        fontWeight: 700,
        marginTop: 6,
        fontVariantNumeric: "tabular-nums",
    },
    primaryBtn: {
        width: "100%",
        padding: "12px",
        borderRadius: 8,
        border: "none",
        background: "linear-gradient(135deg, #2E5A44 0%, #1B3B2B 100%)",
        color: "#FFFFFF",
        fontSize: "0.88rem",
        fontWeight: 600,
        letterSpacing: "0.02em",
        cursor: "pointer",
        boxShadow: "0 4px 12px rgba(27, 59, 43, 0.18)",
        transition: "opacity 0.2s",
    },
    secondaryBtn: {
        width: "100%",
        padding: "10px",
        borderRadius: 8,
        border: "1px solid #A8C4B4",
        background: "transparent",
        color: "#2E5A44",
        fontSize: "0.82rem",
        fontWeight: 600,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
    },
    success: {
        textAlign: "center",
        padding: "0.5rem 0 0",
    },
    successIcon: {
        width: 48,
        height: 48,
        borderRadius: "50%",
        background: "linear-gradient(135deg, #2E5A44, #1B3B2B)",
        color: "#FFF",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        margin: "0 auto 10px",
        fontSize: 20,
        boxShadow: "0 4px 14px rgba(27, 59, 43, 0.2)",
    },
    errorBox: {
        background: "rgba(201, 59, 59, 0.08)",
        border: "1px solid rgba(201, 59, 59, 0.2)",
        borderRadius: 8,
        padding: "8px 12px",
        marginBottom: 10,
        color: "#C93B3B",
        fontSize: "0.8rem",
    },
};

const PulseStyle = () => (
    <style>{`
    @keyframes pulse {
      0% { transform: scale(1); opacity: 1; }
      100% { transform: scale(1.8); opacity: 0; }
    }
    .btn-close-action:hover:not(:disabled) {
      background-color: #059669 !important;
    }
  `}</style>
);

function useTimer(running, maxSeconds, onLimitReached) {
    const [secondsLeft, setSecondsLeft] = useState(maxSeconds);

    useEffect(() => {
        if (!running) {
            setSecondsLeft(maxSeconds);
            return;
        }

        const id = setInterval(() => {
            setSecondsLeft(s => {
                if (s <= 1) {
                    clearInterval(id);
                    setTimeout(() => onLimitReached(), 50);
                    return 0;
                }
                return s - 1;
            });
        }, 1000);

        return () => clearInterval(id);
    }, [running, maxSeconds]);

    const m = String(Math.floor(secondsLeft / 60)).padStart(2, "0");
    const s = String(secondsLeft % 60).padStart(2, "0");
    return {
        formatted: `${m}:${s}`,
        isNearLimit: secondsLeft <= 15
    };
}

export default function ProductFeedbackPage() {
    const [clientName, setClientName] = useState("");
    const [qrId, setQrId] = useState("");
    const [location, setLocation] = useState({ latitude: null, longitude: null });

    const [batchId, setBatchId] = useState("");
    const [description, setDescription] = useState("");
    const [rating, setRating] = useState(0);
    const [hoverRating, setHoverRating] = useState(0);
    const [consentGiven, setConsentGiven] = useState(false);

    const [phase, setPhase] = useState("privacy");
    const [recording, setRecording] = useState(false);
    const [audioBlob, setAudioBlob] = useState(null);
    const [audioUrl, setAudioUrl] = useState(null);
    const [errorMsg, setErrorMsg] = useState("");

    const mediaRecorderRef = useRef(null);
    const chunksRef = useRef([]);

    const { formatted: timer, isNearLimit } = useTimer(recording, 120, () => {
        stopRecording();
    });

    // Auto-fade error messages after 3 seconds
    useEffect(() => {
        if (errorMsg) {
            const timer = setTimeout(() => {
                setErrorMsg("");
            }, 3000);
            return () => clearTimeout(timer);
        }
    }, [errorMsg]);

    useEffect(() => {
        const searchParams = new URLSearchParams(window.location.search);
        const idParam = searchParams.get("id") || "";
        const batchParam = searchParams.get("batch_id") || "";

        setQrId(idParam);
        setBatchId(batchParam);

        if (idParam.includes("-")) {
            setClientName(idParam.split("-")[0]);
        }

        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    setLocation({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                    });
                },
                (error) => {
                    console.warn("Location permission denied or unavailable:", error.message);
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        }
    }, []);

    const handleReturnToSplash = () => {
        if (phase === "submitting") return;
        
        // Dynamic link target with URL query ID
        const redirectUrl = `https://location-map-1.onrender.com/puretrace.html?id=${encodeURIComponent(qrId)}`;
        window.location.href = redirectUrl;
    };

    const isBatchIdValid = batchId.trim() !== "";

    const startRecording = async () => {
        if (!isBatchIdValid) {
            setErrorMsg("Batch ID is missing in the URL parameter.");
            return;
        }

        setErrorMsg("");
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
            chunksRef.current = [];
            mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
            mr.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: "audio/webm" });
                setAudioBlob(blob);
                setAudioUrl(URL.createObjectURL(blob));
                stream.getTracks().forEach(t => t.stop());
                setPhase("recorded");
            };
            mediaRecorderRef.current = mr;
            mr.start(250);
            setRecording(true);
            setPhase("recording");
        } catch (err) {
            setErrorMsg("Microphone access denied. Please grant microphone access.");
        }
    };

    const stopRecording = () => {
        mediaRecorderRef.current?.stop();
        setRecording(false);
    };

    const handleSubmit = async () => {
        if (!isBatchIdValid) {
            setErrorMsg("Batch ID is missing.");
            return;
        }

        setPhase("submitting");
        setErrorMsg("");

        try {
            const form = new FormData();
            form.append("audio", audioBlob, "recording.webm");
            form.append("batch_id", batchId);
            form.append("description", description);
            form.append("rating", rating);
            form.append("client", clientName);

            if (location.latitude !== null && location.longitude !== null) {
                form.append("latitude", location.latitude);
                form.append("longitude", location.longitude);
            }

            await axios.post(`${BASE}/product-feedback/submit${window.location.search}`, form, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 120000,
            });

            setPhase("done");
        } catch (err) {
            setErrorMsg("Submission failed. Please try again.");
            setPhase("recorded");
        }
    };

    const handleReRecord = () => {
        setAudioBlob(null);
        setAudioUrl(null);
        setErrorMsg("");
        setPhase("form");
    };

    if (phase === "done") {
        return (
            <div style={styles.page}>
                <PulseStyle />
                <div style={styles.card}>
                    {/* Header Top Bar with Close Button */}
                    <div style={styles.topBar}>
                        <div>
                            <h1 style={styles.title}>Product Feedback</h1>
                            <p style={styles.subtitle}>Help us improve product quality</p>
                        </div>
                        <button
                            className="btn-close-action"
                            style={styles.closeBtn}
                            onClick={handleReturnToSplash}
                        >
                            Close
                        </button>
                    </div>

                    <div style={styles.success}>
                        <div style={styles.successIcon}>✓</div>
                        <h2 style={{ ...styles.title, textAlign: "center", marginBottom: 6 }}>Thank You</h2>
                        <p style={{ color: "#527060", fontSize: "0.85rem", lineHeight: 1.5, marginBottom: 14, textAlign: "center" }}>
                            Your feedback and rating have been submitted successfully.
                        </p>

                        <div style={{
                            background: "#F2F7F4",
                            border: "1px solid #D1E0D7",
                            borderRadius: 8,
                            padding: "10px 12px",
                            textAlign: "center",
                            marginBottom: 16,
                        }}>
                            <div style={{ fontSize: "0.82rem", color: "#1B3B2B", display: "flex", flexDirection: "column", gap: 4 }}>
                                <div><strong>Batch ID:</strong> {batchId || "N/A"}</div>
                                {rating > 0 && <div><strong>Rating Given:</strong> {rating} / 5 Stars</div>}
                                {clientName && <div><strong>Brand:</strong> {clientName}</div>}
                                <div style={{ fontSize: "0.75rem", color: "#527060", marginTop: 2 }}>
                                    <span>{new Date().toLocaleDateString("en-US", { dateStyle: "long" })}</span>
                                </div>
                            </div>
                        </div>

                        <div style={{ marginTop: 12 }}>
                            <button onClick={handleReturnToSplash} style={styles.secondaryBtn}>
                                Close Screen
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div style={styles.page}>
            <PulseStyle />

            <div style={styles.card}>
                {/* Header Top Bar with Close Button */}
                <div style={styles.topBar}>
                    <div>
                        <h1 style={styles.title}>Product Feedback</h1>
                        <p style={styles.subtitle}>Help us improve product quality</p>
                    </div>
                    <button
                        className="btn-close-action"
                        style={{
                            ...styles.closeBtn,
                            opacity: phase === "submitting" ? 0.5 : 1,
                            cursor: phase === "submitting" ? "not-allowed" : "pointer",
                        }}
                        disabled={phase === "submitting"}
                        onClick={handleReturnToSplash}
                    >
                        Close
                    </button>
                </div>

                {errorMsg && <div style={styles.errorBox}>{errorMsg}</div>}

                {phase === "privacy" && (
                    <div>
                        <div style={styles.consentBox}>
                            <div style={styles.consentTitle}>🔒 Privacy Notice — Voice Recording</div>
                            <p style={styles.consentText}>
                                By proceeding, you consent to recording your voice to give product feedback:
                            </p>
                            <ul style={{ ...styles.consentText, paddingLeft: 14, margin: "6px 0 0" }}>
                                <li>Processed for quality control and feedback analysis</li>
                                <li>Stored securely and handled confidentially</li>
                            </ul>
                            <label
                                style={styles.consentCheck}
                                onClick={() => setConsentGiven(v => !v)}
                            >
                                <div style={{
                                    ...styles.checkbox,
                                    background: consentGiven ? "#2E5A44" : "transparent",
                                    color: "#FFF"
                                }}>
                                    {consentGiven && <CheckIcon />}
                                </div>
                                <span style={{ fontSize: "0.78rem", color: "#385445", lineHeight: 1.4 }}>
                                    I consent to voice recording for product evaluation.
                                </span>
                            </label>
                        </div>

                        <button
                            disabled={!consentGiven}
                            onClick={() => setPhase("form")}
                            style={{
                                ...styles.primaryBtn,
                                opacity: consentGiven ? 1 : 0.45,
                                cursor: consentGiven ? "pointer" : "not-allowed"
                            }}
                        >
                            Accept & Continue
                        </button>
                    </div>
                )}

                {phase !== "privacy" && (
                    <>
                        {/* Compact Batch ID Section */}
                        <div style={{
                            marginBottom: "0.5rem",
                            background: "#F2F7F4",
                            padding: "4px 8px",
                            borderRadius: 6,
                            border: "1px solid #D1E0D7",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "6px"
                        }}>
                            <label style={{ ...styles.label, marginBottom: 0, minWidth: "fit-content" }}>
                                Batch ID:
                            </label>
                            <div style={styles.batchDisplay}>
                                {batchId ? batchId : <span style={{ color: "#C93B3B", fontWeight: 400 }}>No Batch ID Provided</span>}
                            </div>
                        </div>

                        {phase === "form" && (
                            <div style={{ textAlign: "center", marginBottom: "0.85rem" }}>
                                <label style={{ ...styles.label, textAlign: "center", marginBottom: 4 }}>
                                    Record Voice Feedback
                                </label>
                                <p style={{ color: "#527060", fontSize: "0.78rem", marginBottom: 10 }}>
                                    Tap the mic to record your experience with this batch
                                </p>
                                <div style={{ position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                                    <button onClick={startRecording} style={styles.micBtn(false)}>
                                        <MicIcon />
                                    </button>
                                </div>
                            </div>
                        )}

                        {phase === "recording" && (
                            <div style={{ textAlign: "center", padding: "0.25rem 0", marginBottom: "0.85rem" }}>
                                <p style={{ color: "#C93B3B", fontSize: "0.8rem", marginBottom: 10, fontWeight: 600 }}>
                                    🔴 Recording...
                                </p>
                                <div style={{ position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: 12 }}>
                                    <div style={styles.pulseRing} />
                                    <button onClick={stopRecording} style={styles.micBtn(true)}>
                                        <StopIcon />
                                    </button>
                                </div>
                                <div style={{ ...styles.timer, color: isNearLimit ? "#D97706" : "#C93B3B" }}>
                                    Time Left: {timer}
                                </div>
                            </div>
                        )}

                        {phase === "recorded" && audioUrl && (
                            <div style={{ marginBottom: "0.85rem", textAlign: "center" }}>
                                <label style={{ ...styles.label, marginBottom: 6 }}>Listen Back To Recording</label>
                                <audio src={audioUrl} controls style={{ width: "100%", borderRadius: 6, marginBottom: 8, height: "36px" }} />
                                <button onClick={handleReRecord} style={styles.secondaryBtn}>
                                    <RefreshIcon /> Re-record Audio
                                </button>
                            </div>
                        )}

                        {/* Additional Notes */}
                        <div style={{ marginBottom: "0.85rem" }}>
                            <label style={styles.label}>
                                Additional Notes <span style={{ color: "#527060", fontWeight: 400 }}>(optional)</span>
                            </label>
                            <textarea
                                value={description}
                                onChange={e => setDescription(e.target.value)}
                                placeholder="Details about product quality, packaging, or issues..."
                                disabled={recording || phase === "submitting"}
                                style={styles.textarea}
                            />
                        </div>

                        {/* 5-Star Rating Section */}
                        <div style={styles.ratingContainer}>
                            <label style={{ ...styles.label, marginBottom: 2 }}>
                                Rate Product Experience
                            </label>
                            <div style={styles.starsWrapper}>
                                {[1, 2, 3, 4, 5].map((starIndex) => (
                                    <StarIcon
                                        key={starIndex}
                                        filled={starIndex <= (hoverRating || rating)}
                                        onClick={() => setRating(starIndex)}
                                        onMouseEnter={() => setHoverRating(starIndex)}
                                        onMouseLeave={() => setHoverRating(0)}
                                    />
                                ))}
                            </div>
                            <span style={{ fontSize: "0.75rem", color: "#527060", marginTop: 4, fontWeight: 600 }}>
                                {hoverRating || rating ? `${hoverRating || rating} out of 5 Stars` : "Tap stars to rate"}
                            </span>
                        </div>

                        {phase === "recorded" && (
                            <button onClick={handleSubmit} style={styles.primaryBtn}>
                                ✓ Submit Product Feedback
                            </button>
                        )}
                    </>
                )}

                {phase === "submitting" && (
                    <div style={{ textAlign: "center", padding: "1rem 0" }}>
                        <p style={{ color: "#527060", fontSize: "0.85rem" }}>Submitting feedback...</p>
                    </div>
                )}

                <p style={{ textAlign: "center", color: "#527060", fontSize: "0.7rem", marginTop: "0.85rem", marginBottom: 0 }}>
                    Your privacy is protected · Data processed securely
                </p>

            </div>
        </div>
    );
}