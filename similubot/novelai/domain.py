"""Pure NovelAI settings and request construction."""

from __future__ import annotations

import re
import secrets
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from difflib import get_close_matches
from typing import Any

QUALITY_TAGS = "very aesthetic, masterpiece, no text"
UC_PRESETS = {
    "heavy": (
        "lowres, artistic error, film grain, scan artifacts, worst quality, "
        "bad quality, jpeg artifacts, very displeasing, chromatic aberration, "
        "dithering, halftone, screentone, multiple views, logo, too many "
        "watermarks, negative space, blank page"
    ),
    "light": (
        "lowres, bad hands, bad anatomy, artistic error, sepia, white haze, "
        "worst quality, very displeasing, jpeg artifacts, 0::ai-generated::"
    ),
    "furry": (
        "{worst quality}, distracting watermark, unfinished, bad quality, "
        "{widescreen}, upscale, {sequence}, {{grandfathered content}}, "
        "blurred foreground, chromatic aberration, sketch, everyone, "
        "[sketch background], simple, [flat colors], ych (character), outline, "
        "multiple scenes, [[horror (theme)]], comic"
    ),
    "human": (
        "lowres, artistic error, film grain, scan artifacts, worst quality, "
        "bad quality, jpeg artifacts, very displeasing, chromatic aberration, "
        "dithering, halftone, screentone, multiple views, logo, too many "
        "watermarks, negative space, blank page, @_@, mismatched pupils, "
        "glowing eyes, bad anatomy"
    ),
    "none": "",
}

# ucPreset is the legacy preset selector; tag_hint_uc_preset is V5's model hint.
UC_PRESET_IDS = {"heavy": 0, "light": 1, "furry": 2, "human": 3, "none": 4}
V5_UC_HINTS = {"none": 0, "furry": 1, "heavy": 2, "light": 3, "human": 4}

ORIENTATIONS = {
    "portrait": (832, 1216),
    "landscape": (1216, 832),
    "square": (1024, 1024),
}

SAMPLERS = {
    "k_euler_ancestral": "Euler Ancestral",
    "k_euler": "Euler",
    "k_dpmpp_2s_ancestral": "DPM++ 2S Ancestral",
    "k_dpmpp_2m": "DPM++ 2M",
    "k_dpmpp_sde": "DPM++ SDE",
}


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    label: str
    params_version: int
    default_guidance: float = 7.0
    default_steps: int = 23
    default_sampler: str = "k_euler_ancestral"
    default_uc_preset: str = "heavy"


MODEL_PROFILES = {
    profile.model_id: profile
    for profile in (
        ModelProfile("nai-diffusion-5-curated", "V5 Curated", 4),
        ModelProfile("nai-diffusion-5-full", "V5 Full", 4),
        ModelProfile("nai-diffusion-4-5-curated", "V4.5 Curated", 3, 5.0),
        ModelProfile("nai-diffusion-4-5-full", "V4.5 Full", 3, 5.0),
    )
}


@dataclass(frozen=True)
class UserSettings:
    user_id: str
    model: str | None = None
    orientation: str | None = None
    guidance: float | None = None
    steps: int | None = None
    uc_preset: str | None = None
    uc_text: str | None = None
    sampler: str | None = None


@dataclass(frozen=True)
class EffectiveSettings:
    model: str
    orientation: str
    guidance: float
    steps: int
    uc_preset: str
    uc_text: str
    sampler: str
    seed: int

    @property
    def profile(self) -> ModelProfile:
        return MODEL_PROFILES[self.model]

    @property
    def size(self) -> tuple[int, int]:
        return ORIENTATIONS[self.orientation]


@dataclass(frozen=True)
class CharacterPrompt:
    prompt: str
    x: float
    y: float = 0.5


@dataclass(frozen=True)
class PreparedGeneration:
    original_prompt: str
    settings: EffectiveSettings
    payload: dict[str, Any]


class UnknownMacros(ValueError):
    """Raised when a prompt references missing artist macros."""

    def __init__(self, names: list[str], suggestions: Mapping[str, str]):
        self.names = names
        self.suggestions = dict(suggestions)
        message = ", ".join(f"${name}$" for name in names)
        super().__init__(f"未找到画师串：{message}")


_MACRO_PATTERN = re.compile(r"\$(?P<name>[^$\s]{1,32})\$")
_CHARACTER_PATTERN = re.compile(
    r"char(?P<number>\d+):\[(?P<prompt>[^\]]+)\]", re.IGNORECASE
)
_LITERAL_DOLLAR = "\0SIMILUBOT_DOLLAR\0"


def normalize_macro_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name.strip().strip("$")).casefold()
    if (
        not normalized
        or len(normalized) > 32
        or any(char.isspace() or char == "$" for char in normalized)
    ):
        raise ValueError("画师串名称需为 1-32 个字符，且不能包含空白或 '$'")
    return normalized


def expand_macros(prompt: str, macros: Mapping[str, str]) -> str:
    escaped = prompt.replace("$$", _LITERAL_DOLLAR)
    missing: list[str] = []

    def replace_macro(match: re.Match[str]) -> str:
        name = normalize_macro_name(match.group("name"))
        if name not in macros:
            missing.append(name)
            return match.group(0)
        return macros[name]

    expanded = _MACRO_PATTERN.sub(replace_macro, escaped)
    if missing:
        available = list(macros)
        suggestions = {
            name: matches[0]
            for name in dict.fromkeys(missing)
            if (matches := get_close_matches(name, available, n=1, cutoff=0.6))
        }
        raise UnknownMacros(list(dict.fromkeys(missing)), suggestions)
    return expanded.replace(_LITERAL_DOLLAR, "$")


def extract_character_prompts(prompt: str) -> tuple[str, tuple[CharacterPrompt, ...]]:
    matches = list(_CHARACTER_PATTERN.finditer(prompt))
    if not matches:
        return prompt.strip(), ()

    numbered = [
        (int(match.group("number")), match.group("prompt").strip()) for match in matches
    ]
    numbers = [number for number, _ in numbered]
    if any(number < 1 or number > 8 for number in numbers):
        raise ValueError("角色编号必须在 1 到 8 之间")
    if len(set(numbers)) != len(numbers):
        raise ValueError("角色编号不能重复")

    numbered.sort()
    count = len(numbered)
    characters = tuple(
        CharacterPrompt(character_prompt, (index + 1) / (count + 1))
        for index, (_, character_prompt) in enumerate(numbered)
    )
    base_prompt = re.sub(r"\s+", " ", _CHARACTER_PATTERN.sub(" ", prompt)).strip(" ,")
    if not base_prompt:
        raise ValueError("除角色提示词外，还需要填写基础提示词")
    return base_prompt, characters


def resolve_settings(
    saved: UserSettings,
    default_model: str,
    overrides: Mapping[str, Any] | None = None,
) -> EffectiveSettings:
    overrides = {
        key: value for key, value in (overrides or {}).items() if value is not None
    }
    model = overrides.get("model") or saved.model or default_model
    profile = get_profile(model)
    uc_text = overrides.get("uc_text", saved.uc_text)
    if "uc_preset" in overrides and "uc_text" not in overrides:
        uc_text = None

    values = {
        "model": model,
        "orientation": overrides.get("orientation") or saved.orientation or "portrait",
        "guidance": overrides.get("guidance")
        if "guidance" in overrides
        else saved.guidance,
        "steps": overrides.get("steps") if "steps" in overrides else saved.steps,
        "uc_preset": overrides.get("uc_preset")
        or saved.uc_preset
        or profile.default_uc_preset,
        "uc_text": uc_text,
        "sampler": overrides.get("sampler") or saved.sampler or profile.default_sampler,
        "seed": overrides.get("seed"),
    }
    values["guidance"] = (
        profile.default_guidance
        if values["guidance"] is None
        else float(values["guidance"])
    )
    values["steps"] = (
        profile.default_steps if values["steps"] is None else int(values["steps"])
    )
    values["uc_text"] = (
        UC_PRESETS[values["uc_preset"]]
        if values["uc_text"] is None
        else values["uc_text"].strip()
    )
    values["seed"] = (
        secrets.randbelow(2**32) if values["seed"] is None else int(values["seed"])
    )

    validate_effective_settings(values)
    return EffectiveSettings(**values)


def normalize_saved_settings(
    settings: UserSettings,
) -> tuple[UserSettings, tuple[str, ...]]:
    changed: list[str] = []
    updates: dict[str, Any] = {}
    profile = MODEL_PROFILES.get(settings.model) if settings.model else None
    if settings.model is not None and profile is None:
        updates["model"] = None
        changed.append("model")
    if settings.orientation is not None and settings.orientation not in ORIENTATIONS:
        updates["orientation"] = None
        changed.append("orientation")
    if settings.guidance is not None and not 0 <= settings.guidance <= 10:
        updates["guidance"] = None
        changed.append("guidance")
    if settings.steps is not None and not 1 <= settings.steps <= 50:
        updates["steps"] = None
        changed.append("steps")
    if settings.uc_preset is not None and settings.uc_preset not in UC_PRESETS:
        updates["uc_preset"] = None
        changed.append("uc_preset")
    if settings.sampler is not None and settings.sampler not in SAMPLERS:
        updates["sampler"] = profile.default_sampler if profile else None
        changed.append("sampler")
    return replace(settings, **updates), tuple(changed)


def reset_settings(settings: UserSettings, field_name: str) -> UserSettings:
    setting_fields = {field.name for field in fields(UserSettings)} - {"user_id"}
    if field_name == "all":
        return UserSettings(settings.user_id)
    if field_name not in setting_fields:
        raise ValueError(f"未知设置项：{field_name}")
    return replace(settings, **{field_name: None})


def prepare_generation(
    original_prompt: str,
    settings: EffectiveSettings,
    macros: Mapping[str, str],
) -> PreparedGeneration:
    if not original_prompt.strip():
        raise ValueError("提示词不能为空")
    expanded = expand_macros(original_prompt.strip(), macros)
    prompt, characters = extract_character_prompts(expanded)
    processed_prompt = f"{prompt}, {QUALITY_TAGS}"
    payload = build_payload(processed_prompt, characters, settings)
    return PreparedGeneration(original_prompt.strip(), settings, payload)


def build_payload(
    prompt: str,
    characters: tuple[CharacterPrompt, ...],
    settings: EffectiveSettings,
) -> dict[str, Any]:
    profile = settings.profile
    width, height = settings.size
    use_coords = len(characters) > 1
    character_prompts = [
        {
            "prompt": character.prompt,
            "uc": "",
            "center": {"x": character.x, "y": character.y},
            "enabled": True,
        }
        for character in characters
    ]
    captions = [
        {
            "char_caption": character.prompt,
            "centers": [{"x": character.x, "y": character.y}],
        }
        for character in characters
    ]
    negative_captions = [
        {"char_caption": "", "centers": [{"x": character.x, "y": character.y}]}
        for character in characters
    ]
    parameters: dict[str, Any] = {
        "params_version": profile.params_version,
        "width": width,
        "height": height,
        "scale": settings.guidance,
        "sampler": settings.sampler,
        "steps": settings.steps,
        "n_samples": 1,
        "seed": settings.seed,
        "noise_schedule": "karras",
        "ucPreset": UC_PRESET_IDS[settings.uc_preset],
        "qualityToggle": True,
        "legacy": False,
        "legacy_v3_extend": False,
        "add_original_image": False,
        "cfg_rescale": 0,
        "dynamic_thresholding": False,
        "deliberate_euler_ancestral_bug": False,
        "prefer_brownian": True,
        "characterPrompts": character_prompts,
        "negative_prompt": settings.uc_text,
        "v4_prompt": {
            "caption": {"base_caption": prompt, "char_captions": captions},
            "use_coords": use_coords,
            "use_order": True,
        },
        "v4_negative_prompt": {
            "caption": {
                "base_caption": settings.uc_text,
                "char_captions": negative_captions,
            },
            "use_coords": False,
            "use_order": False,
            "legacy_uc": False,
        },
        "image_format": "png",
    }
    if profile.params_version == 4:
        parameters.update(
            straight_alpha=True,
            tag_hint_qt=1,
            tag_hint_uc_preset=V5_UC_HINTS[settings.uc_preset],
        )
    return {
        "input": prompt,
        "model": settings.model,
        "action": "generate",
        "parameters": parameters,
    }


def free_generation_reasons(
    settings: EffectiveSettings, tier: int, active: bool, usage_available: bool
) -> tuple[str, ...]:
    width, height = settings.size
    reasons: list[str] = []
    if not active or tier != 3:
        reasons.append("NovelAI 账户没有有效的 Opus 订阅")
    if width * height > 1_048_576:
        reasons.append("分辨率超过 1024×1024")
    if settings.steps > 28:
        reasons.append("采样步数超过 Opus 免费上限 28")
    if not usage_available:
        reasons.append("Opus 免费生成池当前不可用")
    return tuple(reasons)


def get_profile(model: str) -> ModelProfile:
    try:
        return MODEL_PROFILES[model]
    except KeyError as error:
        raise ValueError(f"不支持的 NovelAI 模型：{model}") from error


def validate_effective_settings(values: Mapping[str, Any]) -> None:
    get_profile(values["model"])
    if values["orientation"] not in ORIENTATIONS:
        raise ValueError(f"不支持的画布方向：{values['orientation']}")
    if not 0 <= values["guidance"] <= 10:
        raise ValueError("引导强度必须在 0 到 10 之间")
    if not 1 <= values["steps"] <= 50:
        raise ValueError("采样步数必须在 1 到 50 之间")
    if values["uc_preset"] not in UC_PRESETS:
        raise ValueError(f"不支持的负面提示词预设：{values['uc_preset']}")
    if values["sampler"] not in SAMPLERS:
        raise ValueError(f"不支持的采样器：{values['sampler']}")
    if not 0 <= values["seed"] < 2**32:
        raise ValueError("随机种子必须在 0 到 4294967295 之间")
