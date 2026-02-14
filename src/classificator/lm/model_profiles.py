from __future__ import annotations

from dataclasses import replace

from ..constants import (
    MODEL_EUROLLM_22B,
    MODEL_EUROLLM_22B_MLX_4BIT,
    MODEL_GLM_47_FLASH,
    MODEL_GPT_OSS_20B,
    MODEL_MINISTRAL_3_8B,
)
from ..models import LmModelConfig


DEFAULT_FALLBACK = LmModelConfig(model_id="fallback", temperature=0.0, top_k=40, top_p=1.0)

DEFAULTS = {
    MODEL_GPT_OSS_20B.lower(): LmModelConfig(
        model_id=MODEL_GPT_OSS_20B,
        temperature=0.0,
        top_k=40,
        top_p=1.0,
        max_tokens_cap=4096,
        reasoning_effort="low",
    ),
    MODEL_GLM_47_FLASH.lower(): LmModelConfig(
        model_id=MODEL_GLM_47_FLASH,
        temperature=0.0,
        top_k=40,
        top_p=1.0,
        max_tokens_cap=2048,
        reasoning_effort="low",
        enable_thinking=False,
        thinking_type="disabled",
    ),
    MODEL_MINISTRAL_3_8B.lower(): LmModelConfig(
        model_id=MODEL_MINISTRAL_3_8B,
        temperature=0.0,
        top_k=40,
        top_p=1.0,
        max_tokens_cap=3072,
    ),
    MODEL_EUROLLM_22B_MLX_4BIT.lower(): LmModelConfig(
        model_id=MODEL_EUROLLM_22B_MLX_4BIT,
        temperature=0.0,
        top_k=40,
        top_p=1.0,
        max_tokens_cap=3072,
    ),
    MODEL_EUROLLM_22B.lower(): LmModelConfig(
        model_id=MODEL_EUROLLM_22B,
        temperature=0.0,
        top_k=40,
        top_p=1.0,
        max_tokens_cap=3072,
    ),
}


def resolve_model_config(model: str) -> LmModelConfig:
    cfg = DEFAULTS.get(model.strip().lower(), DEFAULT_FALLBACK)
    return replace(cfg, model_id=model)
