import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import API_BASE_URL from "./config";

const BASE = (API_BASE_URL || "").replace(/\/+$/, "");

const MicIcon = () => (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="23" />
        <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
);

const StopIcon = () => (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
        <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
);

const CheckIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
    </svg>
);

const RefreshIcon = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23 4 23 10 17 10" />
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
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
        padding: "2.5rem 1rem",
        fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif",
    },
    card: {
        background: "rgba(255, 255, 255, 0.95)",
        backdropFilter: "blur(12px)",
        border: "1px solid #D1E0D7",
        borderRadius: 16,
        padding: "2.5rem 2rem",
        width: "100%",
        maxWidth: 480,
        boxShadow: "0 12px 32px rgba(27, 59, 43, 0.06)",
        position: "relative",
    },
    logo: {
        textAlign: "center",
        marginBottom: "1.5rem",
    },
    title: {
        fontSize: "1.55rem",
        fontWeight: 700,
        color: "#1B3B2B",
        margin: "0 0 4px",
        textAlign: "center",
        letterSpacing: "-0.01em",
    },
    subtitle: {
        fontSize: "0.85rem",
        color: "#527060",
        textAlign: "center",
        margin: 0,
    },
    label: {
        display: "block",
        fontSize: "0.75rem",
        fontWeight: 700,
        color: "#2E5A44",
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        marginBottom: 8,
    },
    input: {
        width: "100%",
        padding: "12px 14px",
        borderRadius: 8,
        background: "#FAFCFA",
        border: "1px solid #C2D6CA",
        color: "#1B3B2B",
        fontSize: "0.95rem",
        outline: "none",
        boxSizing: "border-box",
        transition: "border-color 0.2s",
    },
    textarea: {
        width: "100%",
        padding: "12px 14px",
        borderRadius: 8,
        background: "#FAFCFA",
        border: "1px solid #C2D6CA",
        color: "#1B3B2B",
        fontSize: "0.9rem",
        outline: "none",
        boxSizing: "border-box",
        resize: "vertical",
        minHeight: 90,
    },
    consentBox: {
        background: "#F2F7F4",
        border: "1px solid #D1E0D7",
        borderRadius: 12,
        padding: "18px",
        marginBottom: "1.5rem",
    },
    consentTitle: {
        fontSize: "0.82rem",
        fontWeight: 700,
        color: "#2E5A44",
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        marginBottom: 10,
    },
    consentText: {
        fontSize: "0.83rem",
        color: "#385445",
        lineHeight: 1.6,
        margin: 0,
    },
    consentCheck: {
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        marginTop: 14,
        cursor: "pointer",
    },
    checkbox: {
        width: 18,
        height: 18,
        borderRadius: 4,
        flexShrink: 0,
        border: "2px solid #2E5A44",
        marginTop: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
    },
    micBtn: (recording) => ({
        width: 80,
        height: 80,
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
            ? "0 0 0 8px rgba(201, 59, 59, 0.15), 0 8px 24px rgba(201, 59, 59, 0.25)"
            : "0 8px 20px rgba(46, 90, 68, 0.25)",
        transition: "all 0.3s ease",
        transform: recording ? "scale(1.05)" : "scale(1)",
    }),
    pulseRing: {
        position: "absolute",
        width: 80,
        height: 80,
        borderRadius: "50%",
        border: "2px solid rgba(201, 59, 59, 0.4)",
        animation: "pulse 1.5s ease-out infinite",
    },
    timer: {
        fontSize: "0.85rem",
        color: "#C93B3B",
        fontWeight: 700,
        marginTop: 8,
        fontVariantNumeric: "tabular-nums",
    },
    primaryBtn: {
        width: "100%",
        padding: "14px",
        borderRadius: 8,
        border: "none",
        background: "linear-gradient(135deg, #2E5A44 0%, #1B3B2B 100%)",
        color: "#FFFFFF",
        fontSize: "0.9rem",
        fontWeight: 600,
        letterSpacing: "0.02em",
        cursor: "pointer",
        boxShadow: "0 4px 14px rgba(27, 59, 43, 0.18)",
        transition: "opacity 0.2s",
    },
    secondaryBtn: {
        width: "100%",
        padding: "12px",
        borderRadius: 8,
        border: "1px solid #A8C4B4",
        background: "transparent",
        color: "#2E5A44",
        fontSize: "0.85rem",
        fontWeight: 600,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
    },
    transcriptBox: {
        background: "#F2F7F4",
        border: "1px solid #D1E0D7",
        borderRadius: 8,
        padding: "14px 16px",
        marginTop: 12,
        textAlign: "left",
    },
    transcriptText: {
        fontSize: "0.9rem",
        color: "#1B3B2B",
        lineHeight: 1.7,
        margin: 0,
        fontStyle: "italic",
    },
    success: {
        textAlign: "center",
        padding: "1rem 0",
    },
    successIcon: {
        width: 64,
        height: 64,
        borderRadius: "50%",
        background: "linear-gradient(135deg, #2E5A44, #1B3B2B)",
        color: "#FFF",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        margin: "0 auto 16px",
        fontSize: 28,
        boxShadow: "0 6px 18px rgba(27, 59, 43, 0.2)",
    },
    errorBox: {
        background: "rgba(201, 59, 59, 0.08)",
        border: "1px solid rgba(201, 59, 59, 0.2)",
        borderRadius: 8,
        padding: "10px 14px",
        marginBottom: 14,
        color: "#C93B3B",
        fontSize: "0.82rem",
    },
};

const PulseStyle = () => (
    <style>{`
    @keyframes pulse {
      0% { transform: scale(1); opacity: 1; }
      100% { transform: scale(1.8); opacity: 0; }
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
    const [consentGiven, setConsentGiven] = useState(false);

    const [phase, setPhase] = useState("privacy");
    const [recording, setRecording] = useState(false);
    const [audioBlob, setAudioBlob] = useState(null);
    const [audioUrl, setAudioUrl] = useState(null);
    const [errorMsg, setErrorMsg] = useState("");

    const [loadingTranscript, setLoadingTranscript] = useState(false);
    const [transcriptText, setTranscriptText] = useState("");
    const [transcribeChoiceMade, setTranscribeChoiceMade] = useState(false);
    const [tabClosed, setTabClosed] = useState(false);

    const mediaRecorderRef = useRef(null);
    const chunksRef = useRef([]);

    const { formatted: timer, isNearLimit } = useTimer(recording, 120, () => {
        stopRecording();
    });

    useEffect(() => {
        const searchParams = new URLSearchParams(window.location.search);
        const idParam = searchParams.get("id") || "";

        setQrId(idParam);

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

    const isBatchIdValid = batchId.trim() !== "";

    const startRecording = async () => {
        if (!isBatchIdValid) {
            setErrorMsg("Please enter the Batch ID before recording.");
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
            setErrorMsg("Please enter the Batch ID.");
            return;
        }

        setPhase("submitting");
        setErrorMsg("");
        setLoadingTranscript(true);

        try {
            const form = new FormData();
            form.append("audio", audioBlob, "recording.webm");
            form.append("batch_id", batchId);
            form.append("description", description);
            form.append("client", clientName);

            if (location.latitude !== null && location.longitude !== null) {
                form.append("latitude", location.latitude);
                form.append("longitude", location.longitude);
            }

            const resp = await axios.post(`${BASE}/api/product-feedback/submit${window.location.search}`, form, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 120000,
            });

            const docId = resp.data?.doc_id;
            const fileId = resp.data?.file_id;

            setPhase("done");
            runBackgroundTranscription(docId, fileId);

        } catch (err) {
            setErrorMsg("Submission failed. Please try again.");
            setPhase("recorded");
            setLoadingTranscript(false);
        }
    };

    const runBackgroundTranscription = async (docId, fileId) => {
        try {
            const form = new FormData();
            form.append("audio", audioBlob, "recording.webm");
            form.append("doc_id", docId || "");
            form.append("file_id", fileId || "");
            form.append("description", description);

            const resp = await axios.post(`${BASE}/api/product-feedback/transcribe-lazy${window.location.search}`, form, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 180000,
            });

            setTranscriptText(resp.data?.transcript || "No readable audio transcript available.");
        } catch (err) {
            setErrorMsg("Could not fetch transcript at this time.");
        } finally {
            setLoadingTranscript(false);
        }
    };

    const handleReRecord = () => {
        setAudioBlob(null);
        setAudioUrl(null);
        setErrorMsg("");
        setPhase("form");
    };

    const handleRequestTranscript = () => {
        setTranscribeChoiceMade(true);
    };

    const handleCloseTab = () => {
        window.close();
        setTabClosed(true);
    };

    if (phase === "done") {
        return (
            <div style={styles.page}>
                <PulseStyle />
                <div style={styles.card}>
                    <div style={styles.success}>
                        <div style={styles.successIcon}>✓</div>
                        <h2 style={{ ...styles.title, marginBottom: 8 }}>Thank You</h2>
                        <p style={{ color: "#527060", fontSize: "0.9rem", lineHeight: 1.6, marginBottom: 20 }}>
                            Your feedback has been submitted successfully.
                        </p>

                        <div style={{
                            background: "#F2F7F4",
                            border: "1px solid #D1E0D7",
                            borderRadius: 10,
                            padding: "14px 16px",
                            textAlign: "center",
                            marginBottom: 20,
                        }}>
                            <div style={{ fontSize: "0.85rem", color: "#1B3B2B", display: "flex", flexDirection: "column", gap: 4 }}>
                                <div><strong>Batch ID:</strong> {batchId}</div>
                                {clientName && <div><strong>Brand:</strong> {clientName}</div>}
                                <div style={{ fontSize: "0.78rem", color: "#527060", marginTop: 4 }}>
                                    <span>{new Date().toLocaleDateString("en-US", { dateStyle: "long" })}</span>
                                </div>
                            </div>
                        </div>

                        {!transcribeChoiceMade ? (
                            <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid #D1E0D7" }}>
                                <p style={{ fontSize: "0.88rem", fontWeight: 600, color: "#1B3B2B", marginBottom: 14 }}>
                                    Would you like to view the transcript of your voice feedback?
                                </p>
                                <div style={{ display: "flex", gap: 12 }}>
                                    <button onClick={handleRequestTranscript} style={styles.primaryBtn}>
                                        Yes, View Transcript
                                    </button>
                                    <button onClick={handleCloseTab} style={styles.secondaryBtn}>
                                        No, Close
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div style={{ marginTop: 16 }}>
                                {loadingTranscript && (
                                    <p style={{ fontSize: "0.85rem", color: "#527060" }}>
                                        Generating audio transcript...
                                    </p>
                                )}

                                {errorMsg && <div style={styles.errorBox}>{errorMsg}</div>}

                                {!loadingTranscript && transcriptText && (
                                    <div style={styles.transcriptBox}>
                                        <label style={styles.label}>Your Audio Transcript</label>
                                        <p style={styles.transcriptText}>"{transcriptText}"</p>
                                    </div>
                                )}

                                <div style={{ marginTop: 16 }}>
                                    <button onClick={handleCloseTab} style={styles.secondaryBtn}>
                                        Close Page
                                    </button>
                                </div>
                            </div>
                        )}

                        {tabClosed && (
                            <p style={{ fontSize: "0.8rem", color: "#C93B3B", marginTop: 12 }}>
                                Tab close requested. You may safely close this window.
                            </p>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div style={styles.page}>
            <PulseStyle />

            <div style={styles.card}>
                <div style={styles.logo}>
                    <h1 style={styles.title}>Product Feedback</h1>
                    <p style={styles.subtitle}>Help us improve product quality</p>
                </div>

                {errorMsg && <div style={styles.errorBox}>{errorMsg}</div>}

                {phase === "privacy" && (
                    <div>
                        <div style={styles.consentBox}>
                            <div style={styles.consentTitle}>🔒 Privacy Notice — Voice Recording</div>
                            <p style={styles.consentText}>
                                By proceeding, you consent to recording your voice to give product feedback:
                            </p>
                            <ul style={{ ...styles.consentText, paddingLeft: 16, margin: "8px 0 0" }}>
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
                                <span style={{ fontSize: "0.8rem", color: "#385445", lineHeight: 1.5 }}>
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
                        <div style={{
                            marginBottom: "1.5rem",
                            background: "#F2F7F4",
                            padding: "16px",
                            borderRadius: 10,
                            border: "1px solid #D1E0D7",
                        }}>
                            <label style={{ ...styles.label, marginBottom: 8 }}>
                                Batch ID *
                            </label>
                            <input
                                type="text"
                                value={batchId}
                                onChange={e => setBatchId(e.target.value)}
                                placeholder="e.g. BATCH-88402"
                                disabled={recording || phase === "submitting"}
                                style={{ ...styles.input, fontSize: "1.05rem", fontWeight: 600 }}
                                required
                            />
                        </div>

                        {phase === "form" && (
                            <div style={{ textAlign: "center", marginBottom: "1.5rem" }}>
                                <label style={{ ...styles.label, textAlign: "center", marginBottom: 6 }}>
                                    Record Voice Feedback
                                </label>
                                <p style={{ color: "#527060", fontSize: "0.8rem", marginBottom: 16 }}>
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
                            <div style={{ textAlign: "center", padding: "1rem 0", marginBottom: "1.5rem" }}>
                                <p style={{ color: "#C93B3B", fontSize: "0.85rem", marginBottom: 16, fontWeight: 600 }}>
                                    🔴 Recording...
                                </p>
                                <div style={{ position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: 20 }}>
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
                            <div style={{ marginBottom: "1.5rem", textAlign: "center" }}>
                                <label style={{ ...styles.label, marginBottom: 8 }}>Listen Back To Recording</label>
                                <audio src={audioUrl} controls style={{ width: "100%", borderRadius: 8, marginBottom: 12 }} />
                                <button onClick={handleReRecord} style={styles.secondaryBtn}>
                                    <RefreshIcon /> Re-record Audio
                                </button>
                            </div>
                        )}

                        <div style={{ marginBottom: "1.25rem" }}>
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

                        {phase === "recorded" && (
                            <button onClick={handleSubmit} style={styles.primaryBtn}>
                                ✓ Submit Product Feedback
                            </button>
                        )}
                    </>
                )}

                {phase === "submitting" && (
                    <div style={{ textAlign: "center", padding: "2rem 0" }}>
                        <p style={{ color: "#527060", fontSize: "0.88rem" }}>Submitting feedback...</p>
                    </div>
                )}

                <p style={{ textAlign: "center", color: "#527060", fontSize: "0.72rem", marginTop: "1.5rem", marginBottom: 0 }}>
                    Your privacy is protected · Data processed securely
                </p>

            </div>
        </div>
    );
}