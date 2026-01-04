import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, 
    QFormLayout, QFrame, QPushButton, QHBoxLayout,
    QCheckBox
)
from PySide6.QtCore import Signal, Qt

class ConfigWidget(QFrame):
    start_requested = Signal(dict)
    stop_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.inputs = {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("⚙️ Configuration")
        header.setObjectName("subheader")
        layout.addWidget(header)
        
        # Form
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignLeft)
        
        fields = [
            ("🔐 API Key", "POLY_API_KEY"),
            ("🔐 API Secret", "POLY_API_SECRET"),
            ("🔐 Passphrase", "POLY_API_PASSPHRASE"),
            ("🔑 Private Key", "PRIVATE_KEY"),
            ("💰 Capital ($)", "CAPITAL_PER_TRADE"),
            ("📈 Min Margin", "MIN_PROFIT_MARGIN"),
            ("📊 Min Volume", "MIN_MARKET_VOLUME"),
            ("🛡️ Stop Loss", "STOP_LOSS"),
            ("🎯 Take Profit", "TAKE_PROFIT"),
        ]

        # Keys that should be masked as passwords
        secret_keys = {"POLY_API_KEY", "POLY_API_SECRET", "POLY_API_PASSPHRASE", "PRIVATE_KEY"}

        for label_text, key in fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #94a3b8; font-weight: bold;")

            inp = QLineEdit()
            inp.setPlaceholderText("Required" if key in secret_keys or key in {"CAPITAL_PER_TRADE", "MIN_PROFIT_MARGIN", "MIN_MARKET_VOLUME"} else "Optional")
            if key in secret_keys:
                inp.setEchoMode(QLineEdit.Password)
            
            self.inputs[key] = inp
            form_layout.addRow(lbl, inp)
            
        layout.addLayout(form_layout)

        # Paper Trading Toggle
        self.paper_toggle = QCheckBox("🧪 Enable Paper Trading (Simulation)")
        self.paper_toggle.setStyleSheet("color: #38bdf8; font-weight: bold; margin: 10px 0;")
        self.paper_toggle.setToolTip("Run the bot without real money using simulated order fills.")
        layout.addWidget(self.paper_toggle)
        
        layout.addStretch()
        
        # Actions
        btn_layout = QHBoxLayout()
        
        self.btn_start = QPushButton("START ENGINE")
        self.btn_start.setFixedHeight(45)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.on_start)
        
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setFixedHeight(45)
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop)
        
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        
        layout.addLayout(btn_layout)

    def load_defaults(self):
        import os
        for key, inp in self.inputs.items():
            val = os.getenv(key)
            if val:
                inp.setText(val)
        
        # Load paper trading toggle
        paper_enabled = os.getenv("PAPER_TRADING_ENABLED", "false").lower() in ("true", "1", "yes")
        self.paper_toggle.setChecked(paper_enabled)

    def on_start(self):
        data = {k: v.text().strip() for k, v in self.inputs.items()}
        data["PAPER_TRADING_ENABLED"] = "true" if self.paper_toggle.isChecked() else "false"
        
        # Auto-save to .env
        self._save_to_env(data)
        
        self.start_requested.emit(data)
        self.btn_start.setEnabled(False)

    def _save_to_env(self, data: dict):
        """Persist settings to .env file."""
        try:
            from backend.logger import logger
            env_path = ".env"
            
            # Read existing lines or start empty
            lines = []
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()
            
            # Parse existing keys
            env_vars = {}
            for line in lines:
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = line # Keep original formatting
            
            # Update with new data
            new_lines = []
            keys_handled = set()
            
            for line in lines:
                if "=" in line and not line.startswith("#"):
                    k = line.split("=", 1)[0].strip()
                    if k in data:
                        new_lines.append(f"{k}={data[k]}\n")
                        keys_handled.add(k)
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            # Add new keys that weren't in the file
            for k, v in data.items():
                if k not in keys_handled and v:
                    new_lines.append(f"{k}={v}\n")
            
            with open(env_path, "w") as f:
                f.writelines(new_lines)
            
            logger.info("Configuration auto-saved to .env")
        except Exception as e:
            from backend.logger import logger
            logger.error(f"Failed to auto-save configuration: {e}")
        self.btn_stop.setEnabled(True)
        # Lock inputs
        for inp in self.inputs.values():
            inp.setEnabled(False)
        self.paper_toggle.setEnabled(False)

    def on_stop(self):
        self.stop_requested.emit()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        # Unlock inputs
        for inp in self.inputs.values():
            inp.setEnabled(True)
        self.paper_toggle.setEnabled(True)
