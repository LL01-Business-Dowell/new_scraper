/**
 * FeedbackPage.jsx
 * ----------------
 * Guest voice feedback form at /feedback.
 * Accessible via QR code scan — standalone page, no nav links.
 */

import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import API_BASE_URL from "./config";

const BASE = (API_BASE_URL || "").replace(/\/+$/, "");

// ── Icons ────────────────────────────────────────────────────────────────────
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

const SunIcon = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.22" x2="5.64" y2="17.84"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
    </svg>
);

const MoonIcon = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
    </svg>
);

// ── Styles ────────────────────────────────────────────────────────────────────
const styles = {
    page: (isLight) => ({
        minHeight: "100vh",
        background: isLight
            ? "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #f8fafc 100%)"
            : "linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%)",
        display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "flex-start", padding: "2rem 1rem", fontFamily: "'Segoe UI', system-ui, sans-serif",
        transition: "background 0.3s ease",
    }),
    card: (isLight) => ({
        background: isLight ? "rgba(255, 255, 255, 0.7)" : "rgba(255,255,255,0.04)",
        backdropFilter: "blur(20px)",
        border: isLight ? "1px solid rgba(0, 0, 0, 0.06)" : "1px solid rgba(255,255,255,0.1)",
        borderRadius: 20,
        padding: "2rem 1.75rem", width: "100%", maxWidth: 480,
        boxShadow: isLight ? "0 25px 50px rgba(0,0,0,0.06)" : "0 25px 50px rgba(0,0,0,0.4)",
        position: "relative",
        transition: "background 0.3s ease, border 0.3s ease, box-shadow 0.3s ease",
    }),
    logo: {
        textAlign: "center", marginBottom: "1.75rem",
    },
    logoIcon: {
        width: 56, height: 56, borderRadius: "50%",
        background: "linear-gradient(135deg, #6d28d9, #4338ca)",
        display: "flex", alignItems: "center", justifyContent: "center",
        margin: "0 auto 12px", fontSize: 26,
    },
    title: (isLight) => ({
        fontSize: "1.4rem", fontWeight: 700, color: isLight ? "#0f172a" : "#f1f5f9",
        margin: "0 0 4px", textAlign: "center",
        transition: "color 0.3s ease",
    }),
    subtitle: (isLight) => ({
        fontSize: "0.82rem", color: isLight ? "#475569" : "#94a3b8", textAlign: "center", margin: 0,
        transition: "color 0.3s ease",
    }),
    label: (isLight) => ({
        display: "block", fontSize: "0.75rem", fontWeight: 600,
        color: isLight ? "#475569" : "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em",
        marginBottom: 6,
        transition: "color 0.3s ease",
    }),
    input: (isLight) => ({
        width: "100%", padding: "11px 14px", borderRadius: 10,
        background: isLight ? "rgba(0, 0, 0, 0.03)" : "rgba(255,255,255,0.06)",
        border: isLight ? "1px solid rgba(0, 0, 0, 0.12)" : "1px solid rgba(255,255,255,0.12)",
        color: isLight ? "#0f172a" : "#f1f5f9", fontSize: "0.9rem", outline: "none",
        boxSizing: "border-box", transition: "border-color 0.2s, background 0.3s, color 0.3s",
    }),
    textarea: (isLight) => ({
        width: "100%", padding: "11px 14px", borderRadius: 10,
        background: isLight ? "rgba(0, 0, 0, 0.03)" : "rgba(255,255,255,0.06)",
        border: isLight ? "1px solid rgba(0, 0, 0, 0.12)" : "1px solid rgba(255,255,255,0.12)",
        color: isLight ? "#0f172a" : "#f1f5f9", fontSize: "0.9rem", outline: "none",
        boxSizing: "border-box", resize: "vertical", minHeight: 90,
        fontFamily: "inherit", transition: "border-color 0.2s, background 0.3s, color 0.3s",
    }),
    consentBox: (isLight) => ({
        background: isLight ? "rgba(109,40,217,0.04)" : "rgba(109,40,217,0.1)",
        border: isLight ? "1px solid rgba(109,40,217,0.2)" : "1px solid rgba(109,40,217,0.3)",
        borderRadius: 10, padding: "14px 16px", marginBottom: "1.25rem",
        transition: "background 0.3s ease, border 0.3s ease",
    }),
    consentTitle: (isLight) => ({
        fontSize: "0.78rem", fontWeight: 700, color: isLight ? "#5b21b6" : "#a78bfa",
        textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8,
        transition: "color 0.3s ease",
    }),
    consentText: (isLight) => ({
        fontSize: "0.78rem", color: isLight ? "#334155" : "#94a3b8", lineHeight: 1.6, margin: 0,
        transition: "color 0.3s ease",
    }),
    consentCheck: {
        display: "flex", alignItems: "flex-start", gap: 10, marginTop: 12, cursor: "pointer",
    },
    checkbox: {
        width: 18, height: 18, borderRadius: 4, flexShrink: 0,
        border: "2px solid rgba(109,40,217,0.6)", marginTop: 1,
        display: "flex", alignItems: "center", justifyContent: "center",
        transition: "all 0.2s",
    },
    micBtn: (recording) => ({
        width: 80, height: 80, borderRadius: "50%", border: "none",
        background: recording
            ? "linear-gradient(135deg, #dc2626, #b91c1c)"
            : "linear-gradient(135deg, #6d28d9, #4338ca)",
        color: "#fff", cursor: "pointer", display: "flex",
        alignItems: "center", justifyContent: "center",
        boxShadow: recording
            ? "0 0 0 8px rgba(220,38,38,0.2), 0 8px 24px rgba(220,38,38,0.4)"
            : "0 8px 24px rgba(109,40,217,0.4)",
        transition: "all 0.3s", transform: recording ? "scale(1.08)" : "scale(1)",
    }),
    pulseRing: {
        position: "absolute", width: 80, height: 80, borderRadius: "50%",
        border: "2px solid rgba(220,38,38,0.5)",
        animation: "pulse 1.5s ease-out infinite",
    },
    timer: {
        fontSize: "0.85rem", color: "#ef4444", fontWeight: 700,
        marginTop: 8, fontVariantNumeric: "tabular-nums",
    },
    primaryBtn: {
        width: "100%", padding: "13px", borderRadius: 10, border: "none",
        background: "linear-gradient(to right, #6d28d9, #4338ca)",
        color: "#fff", fontSize: "0.9rem", fontWeight: 700, cursor: "pointer",
        transition: "opacity 0.2s",
    },
    secondaryBtn: (isLight) => ({
        width: "100%", padding: "11px", borderRadius: 10,
        border: isLight ? "1px solid rgba(0,0,0,0.12)" : "1px solid rgba(255,255,255,0.12)",
        background: "transparent", color: isLight ? "#475569" : "#94a3b8",
        fontSize: "0.85rem", fontWeight: 600, cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
        transition: "border-color 0.2s, color 0.3s",
    }),
    transcriptBox: (isLight) => ({
        background: isLight ? "rgba(0,0,0,0.02)" : "rgba(255,255,255,0.04)",
        border: isLight ? "1px solid rgba(0,0,0,0.08)" : "1px solid rgba(255,255,255,0.1)",
        borderRadius: 10, padding: "14px 16px",
        transition: "background 0.3s ease, border 0.3s ease",
    }),
    transcriptText: (isLight) => ({
        fontSize: "0.9rem", color: isLight ? "#1e293b" : "#e2e8f0", lineHeight: 1.7, margin: 0,
        fontStyle: "italic",
        transition: "color 0.3s ease",
    }),
    success: {
        textAlign: "center", padding: "1.5rem 0",
    },
    successIcon: {
        width: 64, height: 64, borderRadius: "50%",
        background: "linear-gradient(135deg, #059669, #10b981)",
        display: "flex", alignItems: "center", justifyContent: "center",
        margin: "0 auto 16px", fontSize: 28,
    },
    errorBox: {
        background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
        borderRadius: 8, padding: "10px 14px", marginBottom: 12,
        color: "#ef4444", fontSize: "0.82rem",
    },
    tag: {
        display: "inline-block", fontSize: "0.7rem", fontWeight: 600,
        padding: "3px 8px", borderRadius: 4,
        background: "rgba(109,40,217,0.2)", color: "#a78bfa",
        border: "1px solid rgba(109,40,217,0.3)",
    },
    themeToggle: (isLight) => ({
        position: "absolute",
        top: "1.25rem",
        right: "1.25rem",
        background: "none",
        border: "none",
        color: isLight ? "#64748b" : "#94a3b8",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "6px",
        borderRadius: "50%",
        transition: "color 0.2s ease, background-color 0.2s ease",
    }),
};

// ── Pulse animation ───────────────────────────────────────────────────────────
const PulseStyle = () => (
    <style>{`
    @keyframes pulse {
      0% { transform: scale(1); opacity: 1; }
      100% { transform: scale(1.8); opacity: 0; }
    }
    input:focus, textarea:focus {
      border-color: rgba(109,40,217,0.6) !important;
      box-shadow: 0 0 0 3px rgba(109,40,217,0.15);
    }
  `}</style>
);

// ── Timer hook ────────────────────────────────────────────────────────────────
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

// ── Main component ────────────────────────────────────────────────────────────
export default function FeedbackPage() {

    useEffect(() => {
        if (window.location.pathname !== "/feedback") {
            window.history.replaceState({}, "", "/feedback");
        }
    }, []);

    // Theme configuration state
    const [theme, setTheme] = useState("dark");
    const isLight = theme === "light";

    const toggleTheme = () => {
        setTheme(prev => prev === "dark" ? "light" : "dark");
    };

    // Form state
    const [roomNumber, setRoomNumber] = useState("");
    const [description, setDescription] = useState("");
    const [consentGiven, setConsentGiven] = useState(false);

    // Recording state
    const [phase, setPhase] = useState("form");
    const [recording, setRecording] = useState(false);
    const [audioBlob, setAudioBlob] = useState(null);
    const [audioUrl, setAudioUrl] = useState(null);
    const [transcript, setTranscript] = useState("");
    const [fileId, setFileId] = useState("");
    const [errorMsg, setErrorMsg] = useState("");

    const mediaRecorderRef = useRef(null);
    const chunksRef = useRef([]);
    
    const { formatted: timer, isNearLimit } = useTimer(recording, 120, () => {
        stopRecording();
    });

    const canRecord = roomNumber.trim() && consentGiven;

    // ── Start recording ───────────────────────────────────────────────────────
    const startRecording = async () => {
        setErrorMsg("");
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
            chunksRef.current = [];
            mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
            mr.onstop = async () => {
                const blob = new Blob(chunksRef.current, { type: "audio/webm" });
                setAudioBlob(blob);
                setAudioUrl(URL.createObjectURL(blob));
                stream.getTracks().forEach(t => t.stop());
                
                await handleTranscribe(blob);
            };
            mediaRecorderRef.current = mr;
            mr.start(250);
            setRecording(true);
            setPhase("recording");
        } catch (err) {
            setErrorMsg("Microphone access denied. Please allow microphone access and try again.");
        }
    };

    // ── Stop recording ────────────────────────────────────────────────────────
    const stopRecording = () => {
        mediaRecorderRef.current?.stop();
        setRecording(false);
    };

    // ── Automated transcription call ──────────────────────────────────────────
    const handleTranscribe = async (blobToUpload) => {
        if (!blobToUpload) return;
        setPhase("transcribing");
        setErrorMsg("");
        try {
            const form = new FormData();
            form.append("audio", blobToUpload, "recording.webm");
            form.append("room_number", roomNumber);
            form.append("description", description);

            const resp = await axios.post(`${BASE}/api/feedback/transcribe`, form, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 180000,
            });

            setTranscript(resp.data.transcript || "");
            setFileId(resp.data.file_id || "");
            setPhase("confirm");
        } catch (err) {
            setErrorMsg("Transcription failed automatically. Please try re-recording.");
            setPhase("form");
        }
    };

    // ── Submit feedback via FastAPI ────────────────────────────────────────────
    const handleSubmit = async () => {
        setPhase("submitting");
        setErrorMsg("");
        try {
            const form = new FormData();
            form.append("audio", audioBlob, "recording.webm");
            form.append("room_number", roomNumber);
            form.append("description", description);
            form.append("transcript", transcript);
            form.append("file_id", fileId);

            await axios.post(`${BASE}/api/feedback/submit`, form, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 120000,
            });

            setPhase("done");
        } catch (err) {
            setErrorMsg("Submission failed. Please try again.");
            setPhase("confirm");
        }
    };

    // ── Reset entire form for new submission ───────────────────────────────────
    const handleResetAll = () => {
        setRoomNumber("");
        setDescription("");
        setConsentGiven(false);
        setAudioBlob(null);
        setAudioUrl(null);
        setTranscript("");
        setFileId("");
        setErrorMsg("");
        setPhase("form");
    };

    // ── Re-record (Keep existing input details) ─────────────────────────────
    const handleReRecord = () => {
        setAudioBlob(null);
        setAudioUrl(null);
        setTranscript("");
        setFileId("");
        setErrorMsg("");
        setPhase("form");
    };

    // ── Done screen ───────────────────────────────────────────────────────────
    if (phase === "done") {
        return (
            <div style={styles.page(isLight)}>
                <PulseStyle />
                <div style={styles.card(isLight)}>
                    <button
                        type="button"
                        onClick={toggleTheme}
                        style={styles.themeToggle(isLight)}
                        aria-label="Toggle visual theme style"
                    >
                        {isLight ? <MoonIcon /> : <SunIcon />}
                    </button>

                    <div style={styles.success}>
                        <div style={styles.successIcon}>✓</div>
                        <h2 style={{ ...styles.title(isLight), marginBottom: 8 }}>Thank You!</h2>
                        <p style={{ color: isLight ? "#475569" : "#94a3b8", fontSize: "0.9rem", lineHeight: 1.6, marginBottom: 20 }}>
                            Your feedback has been received. We appreciate you taking the time to share your experience with us!
                        </p>

                        <div style={{
                            background: isLight ? "rgba(0,0,0,0.03)" : "rgba(255,255,255,0.04)",
                            border: isLight ? "1px solid rgba(0,0,0,0.08)" : "1px solid rgba(255,255,255,0.1)",
                            borderRadius: 12,
                            padding: "14px 16px",
                            textAlign: "center",
                            marginBottom: 20
                        }}>
                            <div style={{ fontSize: "0.85rem", color: isLight ? "#0f172a" : "#f1f5f9" }}>
                                Room <strong>{roomNumber}</strong> · {new Date().toLocaleDateString("en-US", { dateStyle: "long" })}
                            </div>
                        </div>

                        <button onClick={handleResetAll} style={styles.secondaryBtn(isLight)}>
                            Submit Additional Feedback
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // ── Main UI Card ──────────────────────────────────────────────────────────
    return (
        <div style={styles.page(isLight)}>
            <PulseStyle />

            <div style={styles.card(isLight)}>

                <button
                    type="button"
                    onClick={toggleTheme}
                    style={styles.themeToggle(isLight)}
                    aria-label="Toggle visual theme style"
                >
                    {isLight ? <MoonIcon /> : <SunIcon />}
                </button>

                <div style={styles.logo}>
                    <div style={styles.logoIcon}>🏨</div>
                    <h1 style={styles.title(isLight)}>Guest Feedback</h1>
                    <p style={styles.subtitle(isLight)}>We value your experience</p>
                </div>

                {errorMsg && <div style={styles.errorBox}>{errorMsg}</div>}

                {/* ── ALWAYS VISIBLE INITIAL FORM ENTRY ────────────────────────── */}
                <div style={{ marginBottom: "1rem" }}>
                    <label style={styles.label(isLight)}>Room Number *</label>
                    <input
                        type="text"
                        value={roomNumber}
                        onChange={e => setRoomNumber(e.target.value)}
                        placeholder="e.g. 412"
                        disabled={recording || phase === "submitting"}
                        style={styles.input(isLight)}
                    />
                </div>

                <div style={{ marginBottom: "1.25rem" }}>
                    <label style={styles.label(isLight)}>Brief Description <span style={{ color: "#475569", fontWeight: 400 }}>(optional)</span></label>
                    <textarea
                        value={description}
                        onChange={e => setDescription(e.target.value)}
                        placeholder="e.g. Feedback about housekeeping, restaurant, or facilities..."
                        disabled={recording || phase === "submitting"}
                        style={styles.textarea(isLight)}
                    />
                </div>

                <div style={styles.consentBox(isLight)}>
                    <div style={styles.consentTitle(isLight)}>🔒 Privacy Notice — Voice Recording</div>
                    <p style={styles.consentText(isLight)}>
                        By proceeding, you consent to the recording of your voice for the
                        purpose of collecting guest feedback. Your voice recording will be:
                    </p>
                    <ul style={{ ...styles.consentText(isLight), paddingLeft: 16, margin: "8px 0 0" }}>
                        <li>Processed to generate a text transcription instantly</li>
                        <li>Used solely to improve our services</li>
                        <li>Stored securely and handled confidentially</li>
                    </ul>
                    <label 
                        style={{
                            ...styles.consentCheck,
                            pointerEvents: (recording || phase === "submitting") ? "none" : "auto",
                        }} 
                        onClick={() => !(recording || phase === "submitting") && setConsentGiven(v => !v)}
                    >
                        <div style={{
                            ...styles.checkbox,
                            background: consentGiven ? "linear-gradient(to right, #6d28d9, #4338ca)" : "transparent",
                            borderColor: consentGiven ? "#6d28d9" : "rgba(109,40,217,0.6)",
                        }}>
                            {consentGiven && <CheckIcon />}
                        </div>
                        <span style={{ fontSize: "0.8rem", color: isLight ? "#4c1d95" : "#c4b5fd", lineHeight: 1.5 }}>
                            I understand and consent to the voice recording and processing.
                        </span>
                    </label>
                </div>

                {/* ── PHASE: INITIAL RECORDING BUTTON ────────────────────────────── */}
                {phase === "form" && (
                    <div style={{ textAlign: "center", marginBottom: "1.25rem" }}>
                        <p style={{ color: "#64748b", fontSize: "0.8rem", marginBottom: 16 }}>
                            Press the button below to start recording your feedback
                        </p>
                        <div style={{ position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                            <button
                                onClick={startRecording}
                                disabled={!canRecord}
                                style={{
                                    ...styles.micBtn(false),
                                    opacity: canRecord ? 1 : 0.4,
                                    cursor: canRecord ? "pointer" : "not-allowed",
                                }}
                            >
                                <MicIcon />
                            </button>
                        </div>
                    </div>
                )}

                {/* ── PHASE: LIVE RECORDING ────────────────────────────────────── */}
                {phase === "recording" && (
                    <div style={{ textAlign: "center", padding: "1rem 0" }}>
                        <p style={{ color: "#ef4444", fontSize: "0.85rem", marginBottom: 16, fontWeight: 600 }}>
                            🔴 Recording in progress — speak clearly
                        </p>
                        <div style={{ position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: 20 }}>
                            <div style={styles.pulseRing} />
                            <button onClick={stopRecording} style={styles.micBtn(true)}>
                                <StopIcon />
                            </button>
                        </div>
                        <div style={{
                            ...styles.timer,
                            color: isNearLimit ? "#f97316" : "#ef4444",
                            fontSize: isNearLimit ? "0.95rem" : "0.85rem",
                            fontWeight: 800,
                        }}>
                            Time Left: {timer}
                        </div>
                    </div>
                )}

                {/* ── PHASE: AUTOMATIC LOADING TRANSCRIBE ──────────────────────── */}
                {phase === "transcribing" && (
                    <div style={{ textAlign: "center", padding: "2rem 0" }}>
                        <div style={{
                            width: 48, height: 48, borderRadius: "50%", margin: "0 auto 20px",
                            background: "conic-gradient(#6d28d9, #4338ca, #6d28d9 30%, rgba(255,255,255,0.1) 30%)",
                            animation: "pulse-spin 1.2s linear infinite",
                        }} />
                        <style>{`@keyframes pulse-spin { to { transform: rotate(360deg); } }`}</style>
                        <p style={{ color: isLight ? "#475569" : "#94a3b8", fontSize: "0.88rem", fontWeight: 600 }}>
                            Processing and transcribing audio...
                        </p>
                    </div>
                )}

                {/* ── PHASE: INLINE CONFIRMATION AND REVIEW ─────────────────────── */}
                {phase === "confirm" && (
                    <>
                        <div style={{ marginBottom: "1.25rem" }}>
                            <label style={styles.label(isLight)}>
                                Transcription Result{" "}
                                <span style={styles.tag}>Please review</span>
                            </label>
                            {transcript ? (
                                <div style={styles.transcriptBox(isLight)}>
                                    <p style={styles.transcriptText(isLight)}>"{transcript}"</p>
                                </div>
                            ) : (
                                <div style={{ ...styles.transcriptBox(isLight), borderColor: "rgba(245,158,11,0.3)", background: "rgba(245,158,11,0.05)" }}>
                                    <p style={{ ...styles.transcriptText(isLight), color: "#f59e0b", fontStyle: "normal" }}>
                                        Could not extract text. You can submit your voice file raw or try re-recording.
                                    </p>
                                </div>
                            )}
                        </div>

                        {audioUrl && (
                            <div style={{ marginBottom: "1.25rem" }}>
                                <label style={styles.label(isLight)}>Listen Back</label>
                                <audio src={audioUrl} controls style={{ width: "100%", borderRadius: 8 }} />
                            </div>
                        )}

                        <button onClick={handleSubmit} style={styles.primaryBtn}>
                            ✓ Confirm & Submit Feedback
                        </button>
                        <div style={{ height: 10 }} />
                        <button onClick={handleReRecord} style={styles.secondaryBtn(isLight)}>
                            <RefreshIcon /> Delete & Re-record
                        </button>
                    </>
                )}

                {/* ── PHASE: SUBMITTING BLOCKER ────────────────────────────────── */}
                {phase === "submitting" && (
                    <div style={{ textAlign: "center", padding: "2rem 0" }}>
                        <p style={{ color: isLight ? "#475569" : "#94a3b8", fontSize: "0.88rem" }}> Finalizing submission...</p>
                    </div>
                )}

                {/* Footer */}
                <p style={{ textAlign: "center", color: "#334155", fontSize: "0.7rem", marginTop: "1.5rem", marginBottom: 0 }}>
                    Your privacy is protected · Data processed securely
                </p>

            </div>
        </div>
    );
}