
# Premium Modern Dark Theme for PySide6

THEME_STYLES = """
/* Global Reset & Base */
QWidget {
    background-color: #0f1115; /* Très sombre, presque noir mais teinté bleu/gris */
    color: #e0e6ed;
    font-family: 'Inter', 'Segoe UI', 'Roboto', sans-serif;
    font-size: 14px;
    selection-background-color: #3d5afe;
    selection-color: #ffffff;
}

/* Headers & Titles */
QLabel#header {
    font-size: 24px;
    font-weight: 800; /* Extra Bold */
    color: #ffffff;
    padding: 15px 0;
    letter-spacing: 0.5px;
}

QLabel#subheader {
    font-size: 16px;
    font-weight: 600;
    color: #94a3b8; /* Slate scale */
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Cards / Containers */
QFrame#card {
    background-color: #1a1d24;
    border: 1px solid #2d3748;
    border-radius: 12px;
}

/* Inputs */
QLineEdit {
    background-color: #242936;
    border: 1px solid #2d3748;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 14px;
    color: #ffffff;
}
QLineEdit:focus {
    border: 1px solid #3d5afe;
    background-color: #2a303f;
}

/* Buttons */
QPushButton {
    background-color: #3d5afe; /* Vivid Blue */
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 0.5px;
}

QPushButton:hover {
    background-color: #536dfe;
    margin-top: -1px; /* Subtle lift effect */
}

QPushButton:pressed {
    background-color: #304ffe;
    margin-top: 1px;
}

QPushButton:disabled {
    background-color: #2d3748;
    color: #4a5568;
}

QPushButton#stop {
    background-color: #ef4444; /* Vivid Red */
}
QPushButton#stop:hover {
    background-color: #f87171;
}

/* Table Widget */
QTableWidget {
    background-color: #1a1d24;
    border: 1px solid #2d3748;
    border-radius: 10px;
    gridline-color: #2d3748;
    outline: none;
}
QTableWidget::item {
    padding: 10px;
    border-bottom: 1px solid #2d3748;
}
QTableWidget::item:selected {
    background-color: #2d3748;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #242936;
    padding: 12px;
    border: none;
    border-bottom: 2px solid #3d5afe;
    font-weight: bold;
    color: #94a3b8;
    text-transform: uppercase;
    font-size: 12px;
}
QScrollBar:vertical {
    border: none;
    background: #0f1115;
    width: 8px;
    margin: 0px; 
}
QScrollBar::handle:vertical {
    background: #4b5563;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Log Console */
QTextEdit {
    background-color: #0d0e12;
    color: #00e676; /* Hacker/Matrix Green for logs */
    border: 1px solid #2d3748;
    border-radius: 8px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
    padding: 10px;
    line-height: 1.5;
}

/* Status Indicators */
QLabel#status_badge {
    padding: 4px 8px;
    border-radius: 4px;
    font-weight: bold;
}
"""
