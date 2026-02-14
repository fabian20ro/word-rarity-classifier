from __future__ import annotations

from pathlib import Path

DEFAULT_LMSTUDIO_BASE_URL = "http://127.0.0.1:1234"
OPENAI_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
OPENAI_MODELS_PATH = "/v1/models"
LMSTUDIO_CHAT_PATH = "/api/v1/chat"
LMSTUDIO_MODELS_PATH = "/api/v1/models"

MODEL_GPT_OSS_20B = "openai/gpt-oss-20b"
MODEL_GLM_47_FLASH = "zai-org/glm-4.7-flash"
MODEL_MINISTRAL_3_8B = "ministral-3-8b-instruct-2512-mixed-8-6-bit"
MODEL_EUROLLM_22B_MLX_4BIT = "mlx-community/EuroLLM-22B-Instruct-2512-mlx-4bit"
MODEL_EUROLLM_22B = "eurollm-22b-instruct-2512-mlx"

DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_PREFLIGHT_TIMEOUT_SECONDS = 5
DEFAULT_MAX_TOKENS = 8000
MODEL_CRASH_BACKOFF_SECONDS = 10

DEFAULT_OUTLIER_THRESHOLD = 2
DEFAULT_CONFIDENCE_THRESHOLD = 0.55
FALLBACK_RARITY_LEVEL = 4

DEFAULT_REBALANCE_BATCH_SIZE = 600
DEFAULT_REBALANCE_LOWER_RATIO = 1.0 / 3.0
DEFAULT_REBALANCE_TRANSITIONS = "2:1,3:2,4:3"

REBALANCE_FROM_LEVEL_PLACEHOLDER = "{{FROM_LEVEL}}"
REBALANCE_TO_LEVEL_PLACEHOLDER = "{{TO_LEVEL}}"
REBALANCE_OTHER_LEVEL_PLACEHOLDER = "{{OTHER_LEVEL}}"
REBALANCE_TARGET_COUNT_PLACEHOLDER = "{{TARGET_COUNT}}"
REBALANCE_COMMON_LEVEL_PLACEHOLDER = "{{COMMON_LEVEL}}"
REBALANCE_COMMON_COUNT_PLACEHOLDER = "{{COMMON_COUNT}}"
USER_INPUT_PLACEHOLDER = "{{INPUT_JSON}}"

BASE_CSV_HEADERS = ["word_id", "word", "type"]
RUN_CSV_HEADERS = [
    "word_id",
    "word",
    "type",
    "rarity_level",
    "tag",
    "confidence",
    "scored_at",
    "model",
    "run_slug",
]
COMPARISON_CSV_HEADERS = [
    "word_id",
    "word",
    "type",
    "run_a_level",
    "run_a_confidence",
    "run_b_level",
    "run_b_confidence",
    "run_c_level",
    "run_c_confidence",
    "median_level",
    "spread",
    "is_outlier",
    "reason",
    "merge_strategy",
    "merge_rule",
    "final_level",
]
OUTLIERS_CSV_HEADERS = [
    "word_id",
    "word",
    "type",
    "run_a_level",
    "run_b_level",
    "run_c_level",
    "spread",
    "reason",
]
UPLOAD_REPORT_HEADERS = ["word_id", "previous_level", "new_level", "source"]
UPLOAD_MARKER_HEADERS = ["uploaded_at", "uploaded_level", "upload_status", "upload_batch_id"]


def ensure_output_dir(root: Path | None = None) -> Path:
    out = (root or Path("build") / "rarity").resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out
