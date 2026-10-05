"""Internationalisation for SynthProvenance (v4 Section 29).

A tiny, dependency-free gettext-style translator. UI code calls ``tr("key")`` (or the
module-level ``t``); strings are looked up in the selected locale's JSON catalogue, with
English as the always-present fallback, so a missing or untranslated key never breaks the
UI — it shows the English text.

Scientific and method names stay in English on purpose (the canonical term is preserved);
locale files translate the surrounding UI chrome (navigation, buttons, modes, research
goals, common labels). Each locale declares its completeness and text direction.

Locale files live in ``app/i18n/locales/<code>.json`` with shape::

    {"_meta": {"name": "...", "english_name": "...", "rtl": false, "complete": 0.6}, "<key>": "<text>", ...}
"""
from __future__ import annotations

import json
from pathlib import Path

from app.utils.paths import resource_path

# code -> (native name, English name, rtl)
LANGUAGES: list[tuple[str, str, str, bool]] = [
    ("en", "English", "English", False), ("id", "Bahasa Indonesia", "Indonesian", False),
    ("zh", "中文", "Mandarin Chinese", False), ("es", "Español", "Spanish", False), ("hi", "हिन्दी", "Hindi", False),
    ("ar", "العربية", "Arabic", True), ("pt", "Português", "Portuguese", False), ("bn", "বাংলা", "Bengali", False),
    ("ru", "Русский", "Russian", False), ("ja", "日本語", "Japanese", False), ("pa", "ਪੰਜਾਬੀ", "Punjabi", False),
    ("de", "Deutsch", "German", False), ("jv", "Basa Jawa", "Javanese", False), ("ko", "한국어", "Korean", False),
    ("fr", "Français", "French", False), ("vi", "Tiếng Việt", "Vietnamese", False), ("ta", "தமிழ்", "Tamil", False),
    ("ur", "اردو", "Urdu", True), ("tr", "Türkçe", "Turkish", False), ("it", "Italiano", "Italian", False),
    ("th", "ไทย", "Thai", False), ("gu", "ગુજરાતી", "Gujarati", False), ("fa", "فارسی", "Persian", True),
    ("pl", "Polski", "Polish", False), ("uk", "Українська", "Ukrainian", False), ("ms", "Bahasa Melayu", "Malay", False),
    ("ro", "Română", "Romanian", False), ("nl", "Nederlands", "Dutch", False), ("el", "Ελληνικά", "Greek", False),
    ("cs", "Čeština", "Czech", False),
]
LANG_CODES = [c for c, *_ in LANGUAGES]
LANG_INFO = {c: {"native": n, "english": e, "rtl": r} for c, n, e, r in LANGUAGES}


def locales_dir() -> Path:
    return resource_path("app", "i18n", "locales")


class Translator:
    def __init__(self, code: str = "en") -> None:
        self._base = self._load("en")
        self.code = "en"
        self.catalog = dict(self._base)
        self.set_language(code)

    def _load(self, code: str) -> dict:
        p = locales_dir() / f"{code}.json"
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return {k: v for k, v in data.items() if not k.startswith("_")} | ({"_meta": data["_meta"]} if "_meta" in data else {})
        except Exception:  # noqa: BLE001 - a missing/broken locale falls back to English
            return {}

    def set_language(self, code: str) -> bool:
        if code not in LANG_CODES:
            return False
        loc = self._load(code) if code != "en" else dict(self._base)
        merged = dict(self._base)
        merged.update({k: v for k, v in loc.items() if not k.startswith("_") and v})
        self.catalog = merged
        self.meta = loc.get("_meta", {})
        self.code = code
        return True

    def t(self, key: str, **fmt) -> str:
        text = self.catalog.get(key) or self._base.get(key) or key
        if fmt:
            try:
                return text.format(**fmt)
            except (KeyError, IndexError, ValueError):
                return text
        return text

    @property
    def rtl(self) -> bool:
        return LANG_INFO.get(self.code, {}).get("rtl", False)

    def completeness(self) -> float:
        if self.code == "en":
            return 1.0
        return float(self.meta.get("complete", 0.0)) if isinstance(self.meta, dict) else 0.0


# a process-wide default translator; the GUI installs its own and calls tr()
_ACTIVE = Translator("en")


def set_active(code: str) -> bool:
    return _ACTIVE.set_language(code)


def active() -> Translator:
    return _ACTIVE


def tr(key: str, **fmt) -> str:
    return _ACTIVE.t(key, **fmt)


t = tr
