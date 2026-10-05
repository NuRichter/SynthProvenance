"""Theme registry (presentation only).

Each theme is a set of colour tokens with the same keys the QSS and ``state_color`` use:
base, panel, raised, field, line, text, muted, accent (cyan), blue, ok, warn, bad, unknown.
Themes change colours only; layout, behaviour and the research engine are unaffected. Light
themes set ``dark=False`` so shells can adapt (focus ring, scrollbar).
"""
from __future__ import annotations

# shared accent-state colours tuned for dark vs light backgrounds (WCAG-reasonable contrast)
_DARK_STATE = {"ok": "#46B37B", "warn": "#D9A441", "bad": "#E0605A", "unknown": "#8A96A3"}
_LIGHT_STATE = {"ok": "#1D7A4C", "warn": "#8A5A00", "bad": "#B42318", "unknown": "#56626E"}


def _dark(base, panel, raised, field, line, text, muted, accent, blue, **extra):
    t = {"base": base, "panel": panel, "raised": raised, "field": field, "line": line, "text": text,
         "muted": muted, "cyan": accent, "blue": blue, **_DARK_STATE}
    t.update(extra)
    return {"dark": True, "tokens": t}


def _light(base, panel, raised, field, line, text, muted, accent, blue, **extra):
    t = {"base": base, "panel": panel, "raised": raised, "field": field, "line": line, "text": text,
         "muted": muted, "cyan": accent, "blue": blue, **_LIGHT_STATE}
    t.update(extra)
    return {"dark": False, "tokens": t}


THEMES: dict[str, dict] = {
    # --- dark
    "Dark Laboratory": _dark("#0E1318", "#141B22", "#1A232C", "#10171D", "#243140", "#D5DEE7", "#7D8C9B", "#4CC3D9", "#3D7FD9"),
    "Graphite": _dark("#17181A", "#1E2022", "#272A2D", "#141517", "#33373B", "#D7DADE", "#8A9199", "#9AA7B2", "#6E7E8C"),
    "Neon Blue": _dark("#0A0F1F", "#101936", "#16224A", "#0B1430", "#213061", "#DCE6FF", "#8597C6", "#2F7BFF", "#5A9BFF"),
    "Neon Yellow": _dark("#13130A", "#1D1C0E", "#272512", "#121106", "#3A371C", "#F2EED2", "#B7B07C", "#E8C534", "#C9A832"),
    "Ocean": _dark("#071A1F", "#0C2730", "#113641", "#061A20", "#1C4553", "#D6EEF2", "#7FA6B0", "#2FB7C9", "#2E8FBF"),
    "Forest": _dark("#0C140E", "#121E15", "#19291D", "#0A130C", "#213A28", "#DAE8DD", "#8AA291", "#4FB06A", "#3E9BD0"),
    "Sunset": _dark("#1A0F12", "#26151A", "#331D24", "#170C0F", "#4A2A33", "#F3DEDF", "#C59AA0", "#E8734E", "#D9594E"),
    "Violet": _dark("#120E1C", "#1B1430", "#261A43", "#0F0B1A", "#342A55", "#E5DEF5", "#9A8FC0", "#9B6CF0", "#6C7BF0"),
    "Rose": _dark("#190E14", "#27141D", "#341C28", "#160A10", "#4A2A38", "#F4DEE8", "#C498AC", "#E85C93", "#D95EB0"),
    "Solar": _dark("#161008", "#21180B", "#2D2110", "#140E06", "#43321A", "#F3E6CF", "#C3A97E", "#E39A2A", "#CFA23A"),
    "Aurora": _dark("#0A1518", "#102227", "#163036", "#09171A", "#1E444C", "#DCF0EC", "#86A8A6", "#43E0B0", "#5AC8E0"),
    # --- light
    "Light Laboratory": _light("#F4F6F8", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#D3DAE1", "#0F1A24", "#45525F", "#0B6E80", "#1D4ED8"),
    "Arctic Cyan": _light("#EEF6F8", "#FFFFFF", "#F4FBFC", "#FFFFFF", "#C4DBE1", "#0C2026", "#3C5861", "#0A7C90", "#1763B8"),
    "Ivory": _light("#FAF7F0", "#FFFFFF", "#FFFDF8", "#FFFFFF", "#DED7C7", "#211D14", "#5A5340", "#8A6A1F", "#1D4ED8"),
    "Paper": _light("#F6F5F2", "#FFFFFF", "#FBFAF8", "#FFFFFF", "#D9D5CC", "#1A1A18", "#55534C", "#4A5A66", "#2B5AA8"),
}

DEFAULT_THEME = "Dark Laboratory"
THEME_NAMES = tuple(THEMES)


def resolve(name: str | None) -> dict:
    return THEMES.get(name or "", THEMES[DEFAULT_THEME])


def is_dark(name: str | None) -> bool:
    return bool(resolve(name)["dark"])
