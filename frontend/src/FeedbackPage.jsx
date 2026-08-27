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
        background: "linear-gradient(135deg, #FAF7F2 0%, #F3EDE2 50%, #EFE7D8 100%)",
        display: "flex", 
        flexDirection: "column", 
        alignItems: "center",
        justifyContent: "flex-start", 
        padding: "2.5rem 1rem", 
        fontFamily: "'Playfair Display', Georgia, 'Segoe UI', serif",
    },
    card: {
        background: "rgba(255, 255, 255, 0.88)",
        backdropFilter: "blur(16px)",
        border: "1px solid rgba(212, 175, 55, 0.3)",
        borderRadius: 16,
        padding: "2.5rem 2rem", 
        width: "100%", 
        maxWidth: 480,
        boxShadow: "0 20px 40px rgba(44, 36, 32, 0.08)",
        position: "relative",
    },
    logo: {
        textAlign: "center", 
        marginBottom: "1.75rem",
    },
    logoIcon: {
        width: 60, 
        height: 60, 
        borderRadius: "50%",
        background: "linear-gradient(135deg, #C5A059 0%, #9E7938 100%)",
        color: "#FFF",
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center",
        margin: "0 auto 14px", 
        fontSize: 26,
        boxShadow: "0 6px 16px rgba(197, 160, 89, 0.3)",
    },
    title: {
        fontSize: "1.55rem", 
        fontWeight: 700, 
        color: "#1A1A1A",
        margin: "0 0 4px", 
        textAlign: "center",
        letterSpacing: "0.02em",
    },
    subtitle: {
        fontSize: "0.85rem", 
        color: "#6B5E54", 
        textAlign: "center", 
        margin: 0,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        fontStyle: "italic",
    },
    label: {
        display: "block", 
        fontSize: "0.75rem", 
        fontWeight: 700,
        color: "#54463A", 
        textTransform: "uppercase", 
        letterSpacing: "0.08em",
        marginBottom: 8,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
    },
    input: {
        width: "100%", 
        padding: "12px 14px", 
        borderRadius: 8,
        background: "#FDFCFA",
        border: "1px solid #D6C7B2",
        color: "#1A1A1A", 
        fontSize: "0.95rem", 
        outline: "none",
        boxSizing: "border-box",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        transition: "border-color 0.2s, box-shadow 0.2s",
    },
    textarea: {
        width: "100%", 
        padding: "12px 14px", 
        borderRadius: 8,
        background: "#FDFCFA",
        border: "1px solid #D6C7B2",
        color: "#1A1A1A", 
        fontSize: "0.9rem", 
        outline: "none",
        boxSizing: "border-box", 
        resize: "vertical", 
        minHeight: 90,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        transition: "border-color 0.2s, box-shadow 0.2s",
    },
    consentBox: {
        background: "#FAF5ED",
        border: "1px solid #E2D2B8",
        borderRadius: 12, 
        padding: "18px", 
        marginBottom: "1.5rem",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
    },
    consentTitle: {
        fontSize: "0.82rem", 
        fontWeight: 700, 
        color: "#8C6D37",
        textTransform: "uppercase", 
        letterSpacing: "0.06em", 
        marginBottom: 10,
    },
    consentText: {
        fontSize: "0.83rem", 
        color: "#4A3E35", 
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
        border: "2px solid #C5A059", 
        marginTop: 1,
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center",
        transition: "all 0.2s",
    },
    micBtn: (recording) => ({
        width: 80, 
        height: 80, 
        borderRadius: "50%", 
        border: "none",
        background: recording
            ? "linear-gradient(135deg, #A83232, #852121)"
            : "linear-gradient(135deg, #C5A059, #9E7938)",
        color: "#FFF", 
        cursor: "pointer", 
        display: "flex",
        alignItems: "center", 
        justifyContent: "center",
        boxShadow: recording
            ? "0 0 0 8px rgba(168, 50, 50, 0.2), 0 8px 24px rgba(168, 50, 50, 0.3)"
            : "0 8px 24px rgba(197, 160, 89, 0.35)",
        transition: "all 0.3s", 
        transform: recording ? "scale(1.08)" : "scale(1)",
    }),
    pulseRing: {
        position: "absolute", 
        width: 80, 
        height: 80, 
        borderRadius: "50%",
        border: "2px solid rgba(168, 50, 50, 0.5)",
        animation: "pulse 1.5s ease-out infinite",
    },
    timer: {
        fontSize: "0.85rem", 
        color: "#A83232", 
        fontWeight: 700,
        marginTop: 8, 
        fontVariantNumeric: "tabular-nums",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
    },
    primaryBtn: {
        width: "100%", 
        padding: "14px", 
        borderRadius: 8, 
        border: "none",
        background: "linear-gradient(135deg, #C5A059 0%, #A37E3E 100%)",
        color: "#FFFFFF", 
        fontSize: "0.9rem", 
        fontWeight: 700, 
        letterSpacing: "0.04em",
        cursor: "pointer",
        boxShadow: "0 4px 14px rgba(163, 126, 62, 0.25)",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        transition: "opacity 0.2s, transform 0.1s",
    },
    secondaryBtn: {
        width: "100%", 
        padding: "12px", 
        borderRadius: 8,
        border: "1px solid #C5A059",
        background: "transparent", 
        color: "#8C6D37",
        fontSize: "0.85rem", 
        fontWeight: 600, 
        cursor: "pointer",
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center", 
        gap: 8,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        transition: "background 0.2s, color 0.2s",
    },
    transcriptBox: {
        background: "#FAF6F0",
        border: "1px solid #E8DCBE",
        borderRadius: 8, 
        padding: "14px 16px", 
        marginTop: 12, 
        textAlign: "left",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
    },
    transcriptText: {
        fontSize: "0.9rem", 
        color: "#2C2420", 
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
        background: "linear-gradient(135deg, #8C6D37, #C5A059)",
        color: "#FFF",
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center",
        margin: "0 auto 16px", 
        fontSize: 28,
        boxShadow: "0 6px 18px rgba(140, 109, 55, 0.25)",
    },
    errorBox: {
        background: "rgba(168, 50, 50, 0.08)", 
        border: "1px solid rgba(168, 50, 50, 0.25)",
        borderRadius: 8, 
        padding: "10px 14px", 
        marginBottom: 14,
        color: "#A83232", 
        fontSize: "0.82rem",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
    },
};

const PulseStyle = () => (
    <style>{`
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,400&display=swap');
    @keyframes pulse {
      0% { transform: scale(1); opacity: 1; }
      100% { transform: scale(1.8); opacity: 0; }
    }
    input:focus, textarea:focus {
      border-color: #C5A059 !important;
      box-shadow: 0 0 0 3px rgba(197, 160, 89, 0.18) !important;
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

export default function FeedbackPage() {
    const [clientName, setClientName] = useState("");
    const [qrId, setQrId] = useState("");
    const [qrName, setQrName] = useState("");

    useEffect(() => {
        const searchParams = new URLSearchParams(window.location.search);

        const paramClient = searchParams.get("client") || searchParams.get("client_name");
        const idParam = searchParams.get("id") || "";
        setQrId(idParam);

        const nameParam = searchParams.get("name") || searchParams.get("qr_name") || "";
        setQrName(nameParam);

        if (paramClient) {
            setClientName(paramClient);
        } else if (idParam.includes("-")) {
            setClientName(idParam.split("-")[0]);
        }
    }, []);

    const [roomNumber, setRoomNumber] = useState("");
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

    const isRoomNumberValid = roomNumber.trim() !== "";

    const startRecording = async () => {
        if (!isRoomNumberValid) {
            setErrorMsg("Please enter your room number before recording.");
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
            setErrorMsg("Microphone access denied. Please allow microphone access and try again.");
        }
    };

    const stopRecording = () => {
        mediaRecorderRef.current?.stop();
        setRecording(false);
    };

    const handleSubmit = async () => {
        if (!isRoomNumberValid) {
            setErrorMsg("Please enter your room number.");
            return;
        }

        setPhase("submitting");
        setErrorMsg("");
        setLoadingTranscript(true);

        try {
            const form = new FormData();
            form.append("audio", audioBlob, "recording.webm");
            form.append("room_number", roomNumber);
            form.append("description", description);
            form.append("client", clientName);

            const resp = await axios.post(`${BASE}/api/feedback/submit${window.location.search}`, form, {
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

            const resp = await axios.post(`${BASE}/api/feedback/transcribe-lazy${window.location.search}`, form, {
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
                        <p style={{ color: "#6B5E54", fontSize: "0.9rem", lineHeight: 1.6, marginBottom: 20, fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
                            Your feedback has been received. We appreciate you taking the time to share your experience with us.
                        </p>

                        <div style={{
                            background: "#FAF6F0",
                            border: "1px solid #E8DCBE",
                            borderRadius: 10, 
                            padding: "14px 16px", 
                            textAlign: "center", 
                            marginBottom: 20,
                            fontFamily: "'Segoe UI', system-ui, sans-serif"
                        }}>
                            <div style={{ fontSize: "0.85rem", color: "#1A1A1A", display: "flex", flexDirection: "column", gap: 4 }}>
                                <div>
                                    Room <strong>{roomNumber}</strong>
                                    {qrName && <span> · <strong>{qrName}</strong></span>}
                                </div>
                                <div style={{ fontSize: "0.78rem", color: "#6B5E54" }}>
                                    <span>{new Date().toLocaleDateString("en-US", { dateStyle: "long" })}</span>
                                </div>
                            </div>
                        </div>

                        {!transcribeChoiceMade ? (
                            <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid #E8DCBE", fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
                                <p style={{ fontSize: "0.88rem", fontWeight: 600, color: "#1A1A1A", marginBottom: 14 }}>
                                    Would you like to view the transcript of your voice feedback?
                                </p>
                                <div style={{ display: "flex", gap: 12 }}>
                                    <button
                                        onClick={handleRequestTranscript}
                                        style={styles.primaryBtn}
                                    >
                                        Yes, View Transcript
                                    </button>
                                    <button
                                        onClick={handleCloseTab}
                                        style={styles.secondaryBtn}
                                    >
                                        No, Close
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div style={{ marginTop: 16 }}>
                                {loadingTranscript && (
                                    <p style={{ fontSize: "0.85rem", color: "#6B5E54", fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
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
                            <p style={{ fontSize: "0.8rem", color: "#A83232", marginTop: 12, fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
                                Tab close requested. If the tab stays open, you may safely close it manually.
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
                    <div style={styles.logoIcon}>🏨</div>
                    <h1 style={styles.title}>Guest Feedback</h1>
                    <p style={styles.subtitle}>We value your experience</p>
                    
                    {(clientName || qrId || qrName) && (
                        <div style={{
                            background: "#FAF5ED",
                            border: "1px solid #E2D2B8",
                            borderRadius: 10,
                            padding: "10px 14px",
                            marginTop: 16,
                            marginBottom: 8,
                            fontSize: "0.8rem",
                            color: "#8C6D37",
                            display: "flex",
                            flexDirection: "column",
                            gap: 4,
                            textAlign: "center",
                            fontFamily: "'Segoe UI', system-ui, sans-serif"
                        }}>
                            <div style={{ fontWeight: 700, fontSize: "0.85rem" }}>
                                {qrName && <span>{qrName}</span>}
                            </div>
                            {qrId && (
                                <div style={{ fontSize: "0.75rem", color: "#6B5E54", fontFamily: "monospace" }}>
                                    ID: <strong>{qrId}</strong>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {errorMsg && <div style={styles.errorBox}>{errorMsg}</div>}

                {phase === "privacy" && (
                    <div>
                        <div style={styles.consentBox}>
                            <div style={styles.consentTitle}>🔒 Privacy Notice — Voice Recording</div>
                            <p style={styles.consentText}>
                                By proceeding, you consent to the recording of your voice for the
                                purpose of collecting guest feedback. Your voice recording will be:
                            </p>
                            <ul style={{ ...styles.consentText, paddingLeft: 16, margin: "8px 0 0" }}>
                                <li>Processed to collect guest feedback securely</li>
                                <li>Used solely to improve our services</li>
                                <li>Stored securely and handled confidentially</li>
                            </ul>
                            <label
                                style={styles.consentCheck}
                                onClick={() => setConsentGiven(v => !v)}
                            >
                                <div style={{
                                    ...styles.checkbox,
                                    background: consentGiven ? "linear-gradient(135deg, #C5A059, #9E7938)" : "transparent",
                                    borderColor: consentGiven ? "#C5A059" : "#C5A059",
                                    color: "#FFF"
                                }}>
                                    {consentGiven && <CheckIcon />}
                                </div>
                                <span style={{ fontSize: "0.8rem", color: "#4A3E35", lineHeight: 1.5 }}>
                                    I understand and consent to the voice recording and processing.
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
                            Accept & Continue to Feedback
                        </button>
                    </div>
                )}

                {phase !== "privacy" && (
                    <>
                        <div style={{
                            marginBottom: "1.5rem",
                            background: "#FAF6F0",
                            padding: "16px",
                            borderRadius: 10,
                            border: "1px solid #E8DCBE",
                        }}>
                            <label style={{
                                ...styles.label,
                                color: "#8C6D37",
                                marginBottom: 8
                            }}>
                                Room Number *
                            </label>
                            <input
                                type="text"
                                value={roomNumber}
                                onChange={e => setRoomNumber(e.target.value)}
                                placeholder="e.g. 412"
                                disabled={recording || phase === "submitting"}
                                style={{
                                    ...styles.input,
                                    fontSize: "1.05rem",
                                    fontWeight: 600,
                                }}
                                required
                            />
                        </div>

                        {phase === "form" && (
                            <div style={{ textAlign: "center", marginBottom: "1.5rem" }}>
                                <label style={{ ...styles.label, textAlign: "center", marginBottom: 6 }}>
                                    Record Voice Feedback
                                </label>
                                <p style={{ color: "#6B5E54", fontSize: "0.8rem", marginBottom: 16, fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
                                    Press the button below to start recording your feedback
                                </p>
                                <div style={{ position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                                    <button
                                        onClick={startRecording}
                                        style={styles.micBtn(false)}
                                    >
                                        <MicIcon />
                                    </button>
                                </div>
                            </div>
                        )}

                        {phase === "recording" && (
                            <div style={{ textAlign: "center", padding: "1rem 0", marginBottom: "1.5rem" }}>
                                <p style={{ color: "#A83232", fontSize: "0.85rem", marginBottom: 16, fontWeight: 600, fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
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
                                    color: isNearLimit ? "#C55900" : "#A83232",
                                }}>
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
                                Brief Description <span style={{ color: "#6B5E54", fontWeight: 400 }}>(optional)</span>
                            </label>
                            <textarea
                                value={description}
                                onChange={e => setDescription(e.target.value)}
                                placeholder="e.g. Feedback about housekeeping, restaurant, or facilities..."
                                disabled={recording || phase === "submitting"}
                                style={styles.textarea}
                            />
                        </div>

                        {phase === "recorded" && (
                            <button onClick={handleSubmit} style={styles.primaryBtn}>
                                ✓ Submit Feedback
                            </button>
                        )}
                    </>
                )}

                {phase === "submitting" && (
                    <div style={{ textAlign: "center", padding: "2rem 0" }}>
                        <p style={{ color: "#6B5E54", fontSize: "0.88rem", fontFamily: "'Segoe UI', system-ui, sans-serif" }}>Finalizing submission...</p>
                    </div>
                )}

                <p style={{ textAlign: "center", color: "#6B5E54", fontSize: "0.72rem", marginTop: "1.5rem", marginBottom: 0, fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
                    Your privacy is protected · Data processed securely
                </p>

            </div>
        </div>
    );
}