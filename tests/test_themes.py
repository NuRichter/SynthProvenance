"""Theme engine: every theme applies (presentation only), state colours resolve, setting persists."""
from __future__ import annotations



def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_all_themes_apply_and_resolve_states():
    from app.ui import theme
    from app.ui.themes import DEFAULT_THEME, THEME_NAMES, THEMES, is_dark
    app = _app()
    assert len(THEME_NAMES) >= 15 and DEFAULT_THEME in THEMES
    required = {"Dark Laboratory", "Light Laboratory", "Neon Blue", "Neon Yellow", "Arctic Cyan", "Aurora",
                "Graphite", "Ivory", "Ocean", "Forest", "Sunset", "Violet", "Rose", "Solar", "Paper"}
    assert required <= set(THEME_NAMES)
    for name in THEME_NAMES:
        theme.apply(app, name)
        assert theme.current_theme() == name
        # tokens are valid hex and states resolve to a colour
        for key in ("base", "panel", "text", "cyan", "ok", "warn", "bad"):
            assert theme.C[key].startswith("#") and len(theme.C[key]) == 7
        for state in ("COMPLETE", "FAILED", "WARNING", "DISAGREEMENT", "AGREEMENT", "READY", "UNAVAILABLE"):
            assert theme.state_color(state).startswith("#")
        assert is_dark(name) in (True, False)
    theme.apply(app, "does-not-exist")
    assert theme.current_theme() == DEFAULT_THEME      # unknown -> default, never a crash


def test_theme_setting_default(tmp_path):
    from app.utils.config import Settings
    st = Settings(tmp_path / "s.json")
    assert st.get("theme") == "Dark Laboratory"
    st.set("theme", "Neon Blue")
    st.save()
    assert Settings(tmp_path / "s.json").get("theme") == "Neon Blue"


def test_easy_mode_uses_a_light_look():
    from app.ui import theme
    from app.ui.easy.style import apply_easy
    app = _app()
    apply_easy(app)
    # Easy Mode forces the light palette regardless of the saved Expert theme
    assert theme.C["text"] == "#0F1A24"
    assert theme.state_color("COMPLETE").startswith("#")
