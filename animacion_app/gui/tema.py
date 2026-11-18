"""Tema oscuro profesional."""
from PySide6.QtGui import QColor, QPalette

BG, PANEL, BORDE = "#111318", "#1a1d24", "#2a2f3a"
TEXTO, TEXTO2 = "#e8eaee", "#9aa3b2"
ACENTO, ACENTO2 = "#4f8cff", "#6ea0ff"
PELIGRO, AVISO, OK = "#ef5a5a", "#f0b34a", "#46c28a"

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; font-size: 13px; color: {TEXTO}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#panel {{ background: {PANEL}; }}
QMenuBar {{ background: {PANEL}; border-bottom: 1px solid {BORDE}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {ACENTO}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDE}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QLabel#titulo {{ font-size: 11px; font-weight: 600; color: {TEXTO2}; letter-spacing: 1px; }}
QLabel#aviso {{ background: #3a2f17; color: {AVISO}; border: 1px solid #5c4720; border-radius: 6px; padding: 6px 8px; }}
QLabel#info {{ color: {TEXTO2}; }}
QPushButton {{ background: #242934; border: 1px solid {BORDE}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ background: #2d3340; border-color: #3b4252; }}
QPushButton:pressed {{ background: #20242d; }}
QPushButton:disabled {{ color: #5d6472; }}
QPushButton:checked {{ background: {ACENTO}; border-color: {ACENTO}; }}
QPushButton#primario {{ background: {ACENTO}; border: none; font-weight: 700; font-size: 14px; padding: 11px; }}
QPushButton#primario:hover {{ background: {ACENTO2}; }}
QPushButton#primario:disabled {{ background: #2b3344; color: #6c7586; }}
QPushButton#peligro {{ color: {PELIGRO}; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px 8px; }}
QToolButton:hover {{ background: #2a2f3a; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #12151b; border: 1px solid {BORDE}; border-radius: 6px; padding: 5px 8px; selection-background-color: {ACENTO}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDE}; selection-background-color: {ACENTO}; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid #4a5263; background: #12151b; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked {{ background: {ACENTO}; border-color: {ACENTO}; }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:.5, cy:.5, radius:.5, fx:.5, fy:.5, stop:0 #fff, stop:.45 #fff, stop:.5 {ACENTO}, stop:1 {ACENTO}); border-color: {ACENTO}; }}
QGroupBox {{ border: 1px solid {BORDE}; border-radius: 8px; margin-top: 14px; padding: 12px 8px 8px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 6px; color: {TEXTO2}; }}
QListWidget, QTableWidget {{ background: #12151b; border: 1px solid {BORDE}; border-radius: 8px; outline: 0; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: #243456; border-radius: 6px; }}
QHeaderView::section {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDE}; padding: 5px; color: {TEXTO2}; }}
QSlider::groove:horizontal {{ height: 4px; background: #2a2f3a; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACENTO}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {ACENTO}; border-radius: 2px; }}
QProgressBar {{ background: #12151b; border: 1px solid {BORDE}; border-radius: 5px; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {ACENTO}; border-radius: 4px; }}
QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:horizontal {{ width: 5px; }}
QSplitter::handle:vertical {{ height: 5px; }}
QScrollArea {{ border: none; background: transparent; }}
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDE}; }}
QToolTip {{ background: {PANEL}; color: {TEXTO}; border: 1px solid {BORDE}; }}
"""


def aplicar(app):
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.Window, QColor(BG))
    p.setColor(QPalette.WindowText, QColor(TEXTO))
    p.setColor(QPalette.Base, QColor("#12151b"))
    p.setColor(QPalette.AlternateBase, QColor(PANEL))
    p.setColor(QPalette.Text, QColor(TEXTO))
    p.setColor(QPalette.Button, QColor("#242934"))
    p.setColor(QPalette.ButtonText, QColor(TEXTO))
    p.setColor(QPalette.Highlight, QColor(ACENTO))
    p.setColor(QPalette.HighlightedText, QColor("white"))
    p.setColor(QPalette.ToolTipBase, QColor(PANEL))
    p.setColor(QPalette.ToolTipText, QColor(TEXTO))
    app.setPalette(p)
    app.setStyleSheet(QSS)
