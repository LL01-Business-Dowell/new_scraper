import os
import time
import threading
import logging
import requests

logger = logging.getLogger(__name__)

MODEL_PRIORITY_ORDER = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-1.5-flash",
]

# URL template — {model} and {api_key} are interpolated at call time
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={api_key}"
)

# Max 503 retries before treating the model as temporarily blocked
MAX_503_RETRIES = 2

# Seconds to wait between 503 retries on the same model/key
RETRY_503_SLEEP = 4

# Seconds before an exhausted key auto-recovers (24 hours = daily quota reset)
KEY_QUOTA_RESET_SECONDS = 86_400

# Seconds before a blocked model is tried again (1 hour)
MODEL_BLOCK_RESET_SECONDS = 3_600


class GeminiKeyRotator:
    def __init__(self) -> None:
        self._lock = threading.Lock()

        # API key strings loaded from GEMINI_KEY_N env vars
        self._keys: list[str] = []

        # key_index -> unix timestamp when exhausted.
        # Auto-cleared after KEY_QUOTA_RESET_SECONDS.
        self._exhausted_keys: dict[int, float] = {}

        # model_name -> unix timestamp when blocked.
        # Auto-cleared after MODEL_BLOCK_RESET_SECONDS.
        self._blocked_models: dict[str, float] = {}

        # Current key index within self._keys
        self._key_index: int = 0

        self._load_keys()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _load_keys(self) -> None:
        index = 1
        while True:
            key = os.environ.get(f"GEMINI_KEY_{index}", "").strip()
            if not key:
                break
            self._keys.append(key)
            logger.info(f"[GeminiRotator] Loaded key slot {index}")
            index += 1

        if not self._keys:
            logger.warning(
                "[GeminiRotator] No GEMINI_KEY_N environment variables found. "
                "All Gemini calls will fail until at least one key is set."
            )

    # ── State helpers (must be called with self._lock held) ──────────────────

    def _available_keys(self) -> list[int]:
        now = time.time()
        recovered = [
            i for i, ts in self._exhausted_keys.items()
            if now - ts >= KEY_QUOTA_RESET_SECONDS
        ]
        for i in recovered:
            del self._exhausted_keys[i]
            logger.info(f"[GeminiRotator] Key slot {i + 1} auto-recovered after 24 h")
        return [i for i in range(len(self._keys)) if i not in self._exhausted_keys]

    def _available_models(self) -> list[str]:
        now = time.time()
        recovered = [
            m for m, ts in self._blocked_models.items()
            if now - ts >= MODEL_BLOCK_RESET_SECONDS
        ]
        for m in recovered:
            del self._blocked_models[m]
            logger.info(f"[GeminiRotator] Model '{m}' auto-recovered after 1 h")
        return [m for m in MODEL_PRIORITY_ORDER if m not in self._blocked_models]

    def _pick_next_key(self, tried: set[int]) -> int | None:
        available = [i for i in self._available_keys() if i not in tried]
        return available[0] if available else None

    # ── Public API ────────────────────────────────────────────────────────────

    def call(self, prompt: str, temperature: float = 0.0) -> str:
        with self._lock:
            if not self._keys:
                raise RuntimeError(
                    "No Gemini API keys configured. "
                    "Set GEMINI_KEY_1, GEMINI_KEY_2, … in the environment."
                )

        # Track which models we have already attempted in this call
        tried_models: set[str] = set()

        # Outer loop: try each model in priority order
        while True:
            with self._lock:
                available_models = self._available_models()
                remaining_models = [m for m in available_models if m not in tried_models]

            if not remaining_models:
                raise RuntimeError(
                    "All Gemini models are currently unavailable "
                    "(quota exhausted or overloaded). "
                    "Models auto-recover within 1-24 hours. "
                    "Add more API keys via GEMINI_KEY_N env vars to increase capacity."
                )

            current_model = remaining_models[0]
            tried_models.add(current_model)
            tried_keys_this_model: set[int] = set()

            logger.info(f"[GeminiRotator] Attempting model: {current_model}")

            # Inner loop: try each key for the current model
            while True:
                with self._lock:
                    key_idx = self._pick_next_key(tried_keys_this_model)

                if key_idx is None:
                    # All keys exhausted for this model — block it and try next
                    with self._lock:
                        self._blocked_models[current_model] = time.time()
                    logger.warning(
                        f"[GeminiRotator] All keys exhausted for model "
                        f"'{current_model}'. Blocking model, trying next."
                    )
                    break  # break key loop -> outer model loop

                with self._lock:
                    self._key_index = key_idx
                    api_key = self._keys[key_idx]

                tried_keys_this_model.add(key_idx)

                url     = GEMINI_URL_TEMPLATE.format(model=current_model, api_key=api_key)
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature},
                }

                logger.info(
                    f"[GeminiRotator] Sending request: "
                    f"model={current_model} key_slot={key_idx + 1}"
                )

                # 503 retry loop — handles temporary model overload
                retries_503 = 0
                resp = None
                model_blocked_by_503 = False

                while retries_503 <= MAX_503_RETRIES:
                    try:
                        resp = requests.post(url, json=payload, timeout=120)
                    except requests.RequestException as exc:
                        logger.error(f"[GeminiRotator] Network error: {exc}")
                        raise RuntimeError(f"Gemini network error: {exc}") from exc

                    if resp.status_code != 503:
                        break  # not overloaded — handle below

                    retries_503 += 1
                    if retries_503 <= MAX_503_RETRIES:
                        logger.warning(
                            f"[GeminiRotator] 503 (overloaded): "
                            f"model={current_model} key_slot={key_idx + 1}. "
                            f"Retry {retries_503}/{MAX_503_RETRIES} "
                            f"in {RETRY_503_SLEEP}s..."
                        )
                        time.sleep(RETRY_503_SLEEP)
                    else:
                        # Max 503 retries reached — block the model
                        with self._lock:
                            self._blocked_models[current_model] = time.time()
                        logger.warning(
                            f"[GeminiRotator] Model '{current_model}' blocked "
                            f"after {MAX_503_RETRIES} x 503. Trying next model."
                        )
                        model_blocked_by_503 = True
                        break

                # If model was blocked by 503 retries, move to next model
                if model_blocked_by_503:
                    break  # break key loop -> outer model loop

                # Handle the final response status
                if resp.status_code == 200:
                    data = resp.json()
                    try:
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        logger.info(
                            f"[GeminiRotator] Success: "
                            f"model={current_model} key_slot={key_idx + 1} "
                            f"response_len={len(text)}"
                        )
                        return text
                    except (KeyError, IndexError) as exc:
                        logger.error(
                            f"[GeminiRotator] Unexpected response shape: {data}"
                        )
                        raise RuntimeError(
                            f"Gemini returned unexpected response shape: {data}"
                        ) from exc

                elif resp.status_code == 429:
                    logger.warning(
                        f"[GeminiRotator] 429 (quota): "
                        f"model={current_model} key_slot={key_idx + 1}. "
                        "Key marked exhausted (auto-recovers in 24 h)."
                    )
                    with self._lock:
                        self._exhausted_keys[key_idx] = time.time()
                    # Continue inner key loop with the next key

                else:
                    # All other status codes are hard failures — do not retry
                    logger.error(
                        f"[GeminiRotator] Non-retryable {resp.status_code}: "
                        f"model={current_model} — {resp.text[:300]}"
                    )
                    raise RuntimeError(
                        f"Gemini API error {resp.status_code}: {resp.text[:300]}"
                    )

gemini_rotator = GeminiKeyRotator()