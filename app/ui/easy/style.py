"""Easy Mode look: a calm, light, high-contrast application distinct from the dark research console.

Colours meet WCAG AA contrast on their backgrounds (text #0F1A24 and muted #45525F on white;
accent #0B6E80 with white text). Focus is a 3 px blue ring on every control, and state is
never conveyed by colour alone (symbols and words accompany it).
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette

E = {"bg": "#F4F6F8", "surface": "#FFFFFF", "line": "#D3DAE1", "strong_line": "#A9B6C2", "text": "#0F1A24",
     "muted": "#45525F", "accent": "#0B6E80", "accent_hover": "#095C6A", "accent_soft": "#E2F1F4", "ok": "#1D7A4C",
     "ok_soft": "#E6F4EC", "warn": "#8A5A00", "warn_soft": "#FFF6E0", "bad": "#B42318", "bad_soft": "#FDECEA",
     "focus": "#1D4ED8", "pending": "#8C99A6"}

# dark-console state colours -> light-theme equivalents with adequate contrast on white
_STATE_REMAP = {"#4CC3D9": E["accent"], "#46B37B": E["ok"], "#D9A441": E["warn"], "#E0605A": E["bad"],
                "#7D8C9B": E["muted"], "#8A96A3": "#56626E", "#3D7FD9": E["focus"]}

QSS = f"""
QWidget {{ background: {E['bg']}; color: {E['text']}; font-size: 11pt; }}
QToolTip {{ background: {E['surface']}; color: {E['text']}; border: 1px solid {E['line']}; padding: 6px; }}
QScrollArea {{ border: none; }}
#EasyHeader {{ background: {E['surface']}; border-bottom: 1px solid {E['line']}; }}
#EasyHeader QLabel {{ background: transparent; }}
#EasyBrand {{ font-size: 17pt; font-weight: 700; }}
#EasyTag, #Help, #Footer, #Muted {{ color: {E['muted']}; }}
#EasyTag {{ font-size: 10pt; }}
#Help {{ font-size: 10pt; }}
#Footer {{ font-size: 9pt; }}
#StepTitle {{ font-size: 23pt; font-weight: 700; letter-spacing: 1px; }}
#ActionBar {{ background: {E['bg']}; border-top: 1px solid {E['line']}; }}
#StepSub {{ color: {E['muted']}; font-size: 13pt; }}
#StateTitle {{ font-size: 20pt; font-weight: 700; letter-spacing: 1px; }}
#SectionLabel {{ font-size: 10pt; font-weight: 700; letter-spacing: 1.5px; }}
#Card {{ background: {E['surface']}; border: 1px solid {E['line']}; border-radius: 12px; }}
#Card QLabel {{ background: transparent; }}
#CardTitle {{ color: {E['muted']}; font-size: 9.5pt; font-weight: 700; letter-spacing: 1.5px; }}
#CardValue {{ font-size: 11pt; }}
#DropZone {{ background: {E['surface']}; border: 2px dashed {E['strong_line']}; border-radius: 16px; }}
#DropZone[active="true"] {{ border: 2px solid {E['accent']}; background: {E['accent_soft']}; }}
#DropZone:focus {{ border: 3px solid {E['focus']}; }}
#DropZone QLabel {{ background: transparent; }}
#DropTitle {{ font-size: 16pt; font-weight: 700; letter-spacing: 1px; }}
#Preview {{ background: {E['surface']}; border: 1px solid {E['line']}; border-radius: 12px; }}
QPushButton {{ background: {E['surface']}; color: {E['text']}; border: 2px solid {E['strong_line']}; border-radius: 10px;
  padding: 10px 22px; min-height: 26px; font-weight: 600; }}
QPushButton:hover {{ border-color: {E['accent']}; }}
QPushButton:focus {{ border: 3px solid {E['focus']}; }}
QPushButton:disabled {{ color: #7E8A96; border-color: {E['line']}; background: #F0F3F5; }}
QPushButton#EasyPrimary {{ background: {E['accent']}; color: #FFFFFF; border: 2px solid {E['accent']}; font-size: 13pt;
  padding: 14px 40px; min-height: 34px; letter-spacing: 1px; }}
QPushButton#EasyPrimary:hover {{ background: {E['accent_hover']}; border-color: {E['accent_hover']}; }}
QPushButton#EasyPrimary:focus {{ border: 3px solid {E['text']}; }}
QPushButton#EasyPrimary:disabled {{ background: #A7C4CA; border-color: #A7C4CA; color: #FFFFFF; }}
QPushButton#EasyLink {{ background: transparent; border: 2px solid transparent; color: {E['accent']}; padding: 6px 10px;
  text-decoration: underline; }}
QPushButton#EasyLink:focus {{ border: 2px solid {E['focus']}; }}
QPushButton#HeaderButton {{ padding: 6px 16px; min-height: 22px; font-size: 10pt; }}
QComboBox {{ background: {E['surface']}; border: 2px solid {E['strong_line']}; border-radius: 8px; padding: 6px 12px;
  min-height: 28px; font-size: 12pt; }}
QComboBox:focus {{ border: 3px solid {E['focus']}; }}
QComboBox QAbstractItemView {{ background: {E['surface']}; selection-background-color: {E['accent_soft']};
  selection-color: {E['text']}; border: 1px solid {E['line']}; }}
QLineEdit {{ background: {E['surface']}; border: 2px solid {E['strong_line']}; border-radius: 8px; padding: 6px 10px; }}
QLineEdit:focus {{ border: 3px solid {E['focus']}; }}
QCheckBox, QRadioButton {{ spacing: 10px; font-size: 11.5pt; padding: 4px; border: 2px solid transparent; border-radius: 6px; }}
QCheckBox:focus, QRadioButton:focus {{ border: 2px solid {E['focus']}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 22px; height: 22px; }}
QProgressBar {{ border: none; background: #E1E7EC; border-radius: 8px; min-height: 16px; max-height: 16px;
  text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {E['accent']}; border-radius: 8px; }}
#Notice {{ background: {E['warn_soft']}; border: 1px solid #E3C27A; border-radius: 10px; color: #4D3300; padding: 12px; }}
#Success {{ background: {E['ok_soft']}; border: 1px solid #9CCFB3; border-radius: 10px; color: #12482D; padding: 10px; }}
#ErrorBox {{ background: {E['bad_soft']}; border: 1px solid #EDA49B; border-radius: 12px; }}
#ErrorBox QLabel {{ background: transparent; }}
#ErrorTitle {{ color: {E['bad']}; font-size: 15pt; font-weight: 700; }}
#InlineError {{ color: {E['bad']}; font-weight: 600; }}
QPlainTextEdit, QTableWidget, QTreeWidget {{ background: {E['surface']}; border: 1px solid {E['line']};
  selection-background-color: {E['accent_soft']}; selection-color: {E['text']}; }}
QTableWidget {{ gridline-color: {E['line']}; alternate-background-color: #F6F8FA; }}
QHeaderView::section {{ background: #EDF1F4; color: {E['muted']}; border: none; border-right: 1px solid {E['line']};
  border-bottom: 1px solid {E['line']}; padding: 4px 6px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {E['line']}; top: -1px; background: {E['surface']}; }}
QTabBar::tab {{ background: #EDF1F4; color: {E['muted']}; padding: 8px 16px; border: 1px solid {E['line']};
  border-bottom: none; margin-right: 2px; }}
QTabBar::tab:selected {{ color: {E['text']}; background: {E['surface']}; border-top: 3px solid {E['accent']}; }}
QTabBar::tab:focus {{ border: 2px solid {E['focus']}; }}
QGroupBox {{ border: 1px solid {E['line']}; border-radius: 10px; margin-top: 14px; padding: 12px; background: {E['surface']}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; font-weight: 700; letter-spacing: 1px; }}
QLabel#PanelTitle, QLabel#ReadoutCaption {{ color: {E['muted']}; font-weight: 600; }}
QMessageBox QLabel {{ font-size: 11pt; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle {{ background: #C3CDD6; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {E['strong_line']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


def apply_easy(app) -> None:
    """Apply the Easy Mode theme to the whole application (one theme per process; modes switch by restart)."""
    from app.ui import theme
    from app.ui.themes import THEMES

    theme.C.clear()
    theme.C.update(THEMES["Light Laboratory"]["tokens"])
    theme.C["cyan"] = E["accent"]
    theme._rebuild_state_colors()
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.Base, "surface"),
                      (QPalette.ColorRole.AlternateBase, "bg"), (QPalette.ColorRole.Button, "surface"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.ToolTipBase, "surface"), (QPalette.ColorRole.ToolTipText, "text"),
                      (QPalette.ColorRole.PlaceholderText, "muted")):
        pal.setColor(role, QColor(E[key]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(pal)
    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "DejaVu Sans", "Arial"])
    font.setPointSizeF(11)
    app.setFont(font)
    app.setStyleSheet(QSS)
