"""Scientific-instrument theme engine (multi-theme, presentation only).

``C`` holds the active theme's colour tokens (mutated in place so importers keep a live
reference). ``state_color`` maps a state string to a token via ``STATE_ROLES``. ``apply``
selects a theme from :mod:`app.ui.themes`, rebuilds ``C`` and ``STATE_COLORS`` in place,
and sets the palette + stylesheet, so a theme can be switched live without restart.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette

from app.ui.themes import DEFAULT_THEME, resolve

# active theme tokens (start on the default; replaced in place by apply)
C: dict = dict(resolve(DEFAULT_THEME)["tokens"])
_current = DEFAULT_THEME

# state string -> role key in C (so every theme recolours states consistently)
STATE_ROLES: dict[str, str] = {
    "PRESENT": "cyan", "ABSENT": "muted", "UNKNOWN": "unknown", "INVALID": "bad", "REMOVED": "warn",
    "PRESERVED": "ok", "PIXEL-EXACT": "ok", "TRANSFORMATION DETECTED": "warn", "NOT COMPARABLE": "unknown",
    "OBSERVED": "cyan", "NOT OBSERVED": "muted", "DETECTED": "cyan", "NOT DETECTED": "muted", "PERSISTED": "ok",
    "ALTERED": "warn", "UNAVAILABLE": "unknown", "NOT TESTABLE": "unknown", "MATCH": "ok", "MISMATCH": "bad",
    "COMPLETE": "ok", "FAILED": "bad", "REFUSED": "warn", "NOT VALIDATED": "unknown", "NOT RUN": "muted",
    "RECORDED": "cyan", "READY": "ok", "AVAILABLE": "ok", "ACTIVE": "ok", "✓": "ok", "✕": "bad",
    "?": "unknown", "N/A": "muted", "—": "muted", "YES": "ok", "NO": "muted", "WARNING": "warn", "ERROR": "bad",
    "INFO": "muted", "NOTICE": "cyan", "POSSIBLY DETECTED": "warn", "AUTHORITATIVE": "ok", "RESEARCH": "cyan",
    "EXPERIMENTAL": "warn", "UNVERIFIED": "warn", "VERIFIED": "ok", "NOT IMPLEMENTED": "muted",
    "NOT EVALUATED": "muted", "LOCAL MODE": "ok", "ONLINE MODE": "warn", "INSUFFICIENT DATA": "warn",
    "AGREEMENT": "ok", "DISAGREEMENT": "warn", "PARTIAL AGREEMENT": "cyan", "INSUFFICIENT EVIDENCE": "unknown",
}
STATE_COLORS: dict[str, str] = {}


def _rebuild_state_colors() -> None:
    STATE_COLORS.clear()
    STATE_COLORS.update({state: C[role] for state, role in STATE_ROLES.items()})


_rebuild_state_colors()


def state_color(text: str) -> str:
    t = str(text or "").upper().strip()
    if t in STATE_COLORS:
        return STATE_COLORS[t]
    for key in sorted(STATE_COLORS, key=len, reverse=True):
        if len(key) > 2 and t.startswith(key):
            return STATE_COLORS[key]
    return C["text"]


def mono_font(size: float = 9.0) -> QFont:
    f = QFont()
    f.setFamilies(["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New"])
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSizeF(size)
    return f


def current_theme() -> str:
    return _current


def build_qss(c: dict) -> str:
    return f"""
QWidget {{ background: {c['base']}; color: {c['text']}; font-size: 9.5pt; }}
QToolTip {{ background: {c['raised']}; color: {c['text']}; border: 1px solid {c['line']}; padding: 4px; }}
#TopBar, #FooterBar {{ background: {c['panel']}; }}
#TopBar {{ border-bottom: 1px solid {c['line']}; }}
#FooterBar {{ border-top: 1px solid {c['line']}; }}
#Nav {{ background: {c['panel']}; border: none; border-right: 1px solid {c['line']}; outline: 0; padding-top: 6px; }}
#Nav::item {{ padding: 9px 14px; color: {c['muted']}; border-left: 2px solid transparent; }}
#Nav::item:selected {{ color: {c['text']}; background: {c['raised']}; border-left: 2px solid {c['cyan']}; }}
#Nav::item:hover {{ color: {c['text']}; }}
QFrame#Panel {{ background: {c['panel']}; border: 1px solid {c['line']}; border-radius: 3px; }}
QFrame#Panel QLabel, QFrame#Readout QLabel {{ background: transparent; }}
QLabel#PanelTitle {{ color: {c['muted']}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#Brand {{ color: {c['muted']}; font-size: 8pt; font-weight: 600; letter-spacing: 2px; }}
QLabel#AppTitle {{ font-size: 15pt; font-weight: 600; }}
QLabel#Hero {{ font-size: 24pt; font-weight: 300; }}
QLabel#Muted, QLabel#Footer {{ color: {c['muted']}; }}
QLabel#Footer {{ font-size: 8pt; }}
QLabel#LayerTitle {{ color: {c['cyan']}; font-size: 11pt; font-weight: 600; letter-spacing: 1px; }}
QFrame#Readout {{ background: {c['field']}; border: 1px solid {c['line']}; border-radius: 2px; }}
QLabel#ReadoutCaption {{ color: {c['muted']}; font-size: 7.5pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#ReadoutValue {{ font-size: 13pt; font-weight: 600; }}
QLabel#ReadoutDetail {{ color: {c['muted']}; font-size: 8pt; }}
QLabel#Banner {{ background: {c['panel']}; border: 1px solid {c['warn']}; color: {c['warn']}; padding: 8px; }}
QLabel#InfoBanner {{ background: {c['panel']}; border: 1px solid {c['cyan']}; color: {c['cyan']}; padding: 8px; }}
QLabel#Badge {{ border: 1px solid {c['line']}; border-radius: 2px; padding: 1px 6px; font-weight: 600; }}
QPushButton {{ background: {c['raised']}; border: 1px solid {c['line']}; padding: 6px 12px; border-radius: 2px; }}
QPushButton:hover {{ border-color: {c['cyan']}; }}
QPushButton:checked {{ border-color: {c['cyan']}; background: {c['field']}; }}
QPushButton:disabled {{ color: {c['muted']}; border-color: {c['line']}; }}
QPushButton#Primary {{ background: {c['cyan']}; border: 1px solid {c['cyan']}; color: {c['base']}; font-weight: 600; padding: 8px 18px; }}
QPushButton#Primary:hover {{ background: {c['blue']}; border-color: {c['blue']}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextBrowser, QTableWidget, QTreeWidget, QListWidget {{
  background: {c['field']}; border: 1px solid {c['line']}; selection-background-color: {c['blue']}; selection-color: {c['text']}; }}
QComboBox QAbstractItemView {{ background: {c['raised']}; }}
QTableWidget, QTreeWidget {{ gridline-color: {c['line']}; alternate-background-color: {c['panel']}; }}
QHeaderView::section {{ background: {c['panel']}; color: {c['muted']}; border: none; border-right: 1px solid {c['line']};
  border-bottom: 1px solid {c['line']}; padding: 4px 6px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {c['line']}; top: -1px; }}
QTabBar::tab {{ background: {c['panel']}; color: {c['muted']}; padding: 6px 14px; border: 1px solid {c['line']}; border-bottom: none; margin-right: 1px; }}
QTabBar::tab:selected {{ color: {c['text']}; border-top: 2px solid {c['cyan']}; background: {c['base']}; }}
QProgressBar {{ border: 1px solid {c['line']}; background: {c['field']}; max-height: 12px; text-align: center; font-size: 7pt; }}
QProgressBar::chunk {{ background: {c['cyan']}; }}
QStatusBar {{ background: {c['panel']}; border-top: 1px solid {c['line']}; color: {c['muted']}; }}
QStatusBar QLabel {{ background: transparent; color: {c['muted']}; padding: 0 8px; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {c['base']}; border: none; width: 10px; height: 10px; }}
QScrollBar::handle {{ background: {c['line']}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QDockWidget::title {{ background: {c['panel']}; padding: 4px; color: {c['muted']}; }}
QMenuBar {{ background: {c['panel']}; }} QMenuBar::item:selected, QMenu::item:selected {{ background: {c['raised']}; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['line']}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 13px; height: 13px; }}
QSplitter::handle {{ background: {c['line']}; }}
"""


def apply(app, theme: str | None = None) -> None:
    """Apply a theme by name (persisted elsewhere). Rebuilds C and STATE_COLORS in place and re-skins the app."""
    global _current
    spec = resolve(theme)
    _current = theme if theme in __import__("app.ui.themes", fromlist=["THEMES"]).THEMES else DEFAULT_THEME
    C.clear()
    C.update(spec["tokens"])
    _rebuild_state_colors()
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "base"), (QPalette.ColorRole.Base, "field"),
                      (QPalette.ColorRole.AlternateBase, "panel"), (QPalette.ColorRole.Button, "raised"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "blue"),
                      (QPalette.ColorRole.ToolTipBase, "raised"), (QPalette.ColorRole.ToolTipText, "text"),
                      (QPalette.ColorRole.PlaceholderText, "muted")):
        pal.setColor(role, QColor(C[key]))
    app.setPalette(pal)
    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "DejaVu Sans", "Arial"])
    font.setPointSizeF(9.5)
    app.setFont(font)
    app.setStyleSheet(build_qss(C))
