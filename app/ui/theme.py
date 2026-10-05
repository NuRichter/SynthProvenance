"""Dark scientific-instrument theme."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette

C = {"base": "#0E1318", "panel": "#141B22", "raised": "#1A232C", "field": "#10171D", "line": "#243140",
     "text": "#D5DEE7", "muted": "#7D8C9B", "cyan": "#4CC3D9", "blue": "#3D7FD9", "ok": "#46B37B",
     "warn": "#D9A441", "bad": "#E0605A", "unknown": "#8A96A3"}

STATE_COLORS = {
    "PRESENT": C["cyan"], "ABSENT": C["muted"], "UNKNOWN": C["unknown"], "INVALID": C["bad"], "REMOVED": C["warn"],
    "PRESERVED": C["ok"], "PIXEL-EXACT": C["ok"], "TRANSFORMATION DETECTED": C["warn"], "NOT COMPARABLE": C["unknown"],
    "OBSERVED": C["cyan"], "NOT OBSERVED": C["muted"], "DETECTED": C["cyan"], "NOT DETECTED": C["muted"],
    "PERSISTED": C["ok"], "ALTERED": C["warn"], "UNAVAILABLE": C["unknown"], "NOT TESTABLE": C["unknown"],
    "MATCH": C["ok"], "MISMATCH": C["bad"], "COMPLETE": C["ok"], "FAILED": C["bad"], "REFUSED": C["warn"],
    "NOT VALIDATED": C["unknown"], "NOT RUN": C["muted"], "RECORDED": C["cyan"], "READY": C["ok"],
    "AVAILABLE": C["ok"], "ACTIVE": C["ok"], "\u2713": C["ok"], "\u2715": C["bad"], "?": C["unknown"], "N/A": C["muted"],
    "\u2014": C["muted"], "YES": C["ok"], "NO": C["muted"], "WARNING": C["warn"], "ERROR": C["bad"], "INFO": C["muted"],
    "NOTICE": C["cyan"], "POSSIBLY DETECTED": C["warn"], "AUTHORITATIVE": C["ok"], "RESEARCH": C["cyan"],
    "EXPERIMENTAL": C["warn"], "UNVERIFIED": C["warn"], "VERIFIED": C["ok"], "NOT IMPLEMENTED": C["muted"],
    "NOT EVALUATED": C["muted"], "LOCAL MODE": C["ok"], "ONLINE MODE": C["warn"], "INSUFFICIENT DATA": C["warn"],
}


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


QSS = f"""
QWidget {{ background: {C['base']}; color: {C['text']}; font-size: 9.5pt; }}
QToolTip {{ background: {C['raised']}; color: {C['text']}; border: 1px solid {C['line']}; padding: 4px; }}
#TopBar, #FooterBar {{ background: {C['panel']}; }}
#TopBar {{ border-bottom: 1px solid {C['line']}; }}
#FooterBar {{ border-top: 1px solid {C['line']}; }}
#Nav {{ background: {C['panel']}; border: none; border-right: 1px solid {C['line']}; outline: 0; padding-top: 6px; }}
#Nav::item {{ padding: 9px 14px; color: {C['muted']}; border-left: 2px solid transparent; }}
#Nav::item:selected {{ color: {C['text']}; background: {C['raised']}; border-left: 2px solid {C['cyan']}; }}
#Nav::item:hover {{ color: {C['text']}; }}
QFrame#Panel {{ background: {C['panel']}; border: 1px solid {C['line']}; border-radius: 3px; }}
QFrame#Panel QLabel, QFrame#Readout QLabel {{ background: transparent; }}
QLabel#PanelTitle {{ color: {C['muted']}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#Brand {{ color: {C['muted']}; font-size: 8pt; font-weight: 600; letter-spacing: 2px; }}
QLabel#AppTitle {{ font-size: 15pt; font-weight: 600; }}
QLabel#Hero {{ font-size: 24pt; font-weight: 300; }}
QLabel#Muted, QLabel#Footer {{ color: {C['muted']}; }}
QLabel#Footer {{ font-size: 8pt; }}
QLabel#LayerTitle {{ color: {C['cyan']}; font-size: 11pt; font-weight: 600; letter-spacing: 1px; }}
QFrame#Readout {{ background: {C['field']}; border: 1px solid {C['line']}; border-radius: 2px; }}
QLabel#ReadoutCaption {{ color: {C['muted']}; font-size: 7.5pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#ReadoutValue {{ font-size: 13pt; font-weight: 600; }}
QLabel#ReadoutDetail {{ color: {C['muted']}; font-size: 8pt; }}
QLabel#Banner {{ background: #2A2213; border: 1px solid {C['warn']}; color: #F1D7A0; padding: 8px; }}
QLabel#InfoBanner {{ background: #10252C; border: 1px solid #1F5563; color: #BFE7F0; padding: 8px; }}
QLabel#Badge {{ border: 1px solid {C['line']}; border-radius: 2px; padding: 1px 6px; font-weight: 600; }}
QPushButton {{ background: {C['raised']}; border: 1px solid {C['line']}; padding: 6px 12px; border-radius: 2px; }}
QPushButton:hover {{ border-color: {C['cyan']}; }}
QPushButton:checked {{ border-color: {C['cyan']}; background: #16323B; }}
QPushButton:disabled {{ color: #4A5866; border-color: #1C2630; }}
QPushButton#Primary {{ background: #123845; border: 1px solid {C['cyan']}; color: #E8F8FB; font-weight: 600; padding: 8px 18px; }}
QPushButton#Primary:hover {{ background: #184A5A; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextBrowser, QTableWidget, QTreeWidget, QListWidget {{
  background: {C['field']}; border: 1px solid {C['line']}; selection-background-color: #1E4A57; selection-color: {C['text']}; }}
QComboBox QAbstractItemView {{ background: {C['raised']}; }}
QTableWidget, QTreeWidget {{ gridline-color: {C['line']}; alternate-background-color: #121A21; }}
QHeaderView::section {{ background: {C['panel']}; color: {C['muted']}; border: none; border-right: 1px solid {C['line']};
  border-bottom: 1px solid {C['line']}; padding: 4px 6px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {C['line']}; top: -1px; }}
QTabBar::tab {{ background: {C['panel']}; color: {C['muted']}; padding: 6px 14px; border: 1px solid {C['line']}; border-bottom: none; margin-right: 1px; }}
QTabBar::tab:selected {{ color: {C['text']}; border-top: 2px solid {C['cyan']}; background: {C['base']}; }}
QProgressBar {{ border: 1px solid {C['line']}; background: {C['field']}; max-height: 12px; text-align: center; font-size: 7pt; }}
QProgressBar::chunk {{ background: {C['cyan']}; }}
QStatusBar {{ background: {C['panel']}; border-top: 1px solid {C['line']}; color: {C['muted']}; }}
QStatusBar QLabel {{ background: transparent; color: {C['muted']}; padding: 0 8px; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {C['base']}; border: none; width: 10px; height: 10px; }}
QScrollBar::handle {{ background: {C['line']}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QDockWidget::title {{ background: {C['panel']}; padding: 4px; color: {C['muted']}; }}
QMenuBar {{ background: {C['panel']}; }} QMenuBar::item:selected, QMenu::item:selected {{ background: {C['raised']}; }}
QMenu {{ background: {C['panel']}; border: 1px solid {C['line']}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 13px; height: 13px; }}
QSplitter::handle {{ background: {C['line']}; }}
"""


def apply(app) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "base"), (QPalette.ColorRole.Base, "field"),
                      (QPalette.ColorRole.AlternateBase, "panel"), (QPalette.ColorRole.Button, "raised"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "blue"),
                      (QPalette.ColorRole.ToolTipBase, "raised"), (QPalette.ColorRole.ToolTipText, "text")):
        pal.setColor(role, QColor(C[key]))
    app.setPalette(pal)
    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "DejaVu Sans", "Arial"])
    font.setPointSizeF(9.5)
    app.setFont(font)
    app.setStyleSheet(QSS)
