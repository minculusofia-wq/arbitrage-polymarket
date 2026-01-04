"""
Credentials Panel - Multi-platform credentials management UI.

Provides a tabbed interface for managing API credentials for multiple
prediction market platforms (Polymarket, Kalshi).
"""

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFormLayout, QFrame, QPushButton, QTabWidget, QCheckBox,
    QGroupBox, QMessageBox
)
from PySide6.QtCore import Signal, Qt

from backend.interfaces.credentials import (
    PolymarketCredentials,
    KalshiCredentials,
    CredentialsManager
)


class PolymarketCredentialsTab(QFrame):
    """Tab for Polymarket credentials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("credentialsTab")
        self._setup_ui()
        self.load_from_env()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Enable checkbox
        self.enabled_cb = QCheckBox("Enable Polymarket")
        self.enabled_cb.setStyleSheet("font-weight: bold; color: #10b981;")
        self.enabled_cb.setChecked(True)
        self.enabled_cb.stateChanged.connect(self._on_enabled_changed)
        layout.addWidget(self.enabled_cb)

        # Form layout
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignLeft)

        # API Key
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("Enter API Key")
        form_layout.addRow(self._make_label("API Key"), self.api_key)

        # API Secret
        self.api_secret = QLineEdit()
        self.api_secret.setPlaceholderText("Enter API Secret")
        self.api_secret.setEchoMode(QLineEdit.Password)
        form_layout.addRow(self._make_label("API Secret"), self.api_secret)

        # Passphrase
        self.passphrase = QLineEdit()
        self.passphrase.setPlaceholderText("Enter Passphrase")
        self.passphrase.setEchoMode(QLineEdit.Password)
        form_layout.addRow(self._make_label("Passphrase"), self.passphrase)

        # Private Key
        self.private_key = QLineEdit()
        self.private_key.setPlaceholderText("Enter Private Key (0x...)")
        self.private_key.setEchoMode(QLineEdit.Password)
        form_layout.addRow(self._make_label("Private Key"), self.private_key)

        layout.addLayout(form_layout)
        layout.addStretch()

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #94a3b8; font-weight: bold;")
        return lbl

    def _on_enabled_changed(self, state):
        enabled = state == Qt.Checked
        self.api_key.setEnabled(enabled)
        self.api_secret.setEnabled(enabled)
        self.passphrase.setEnabled(enabled)
        self.private_key.setEnabled(enabled)

    def load_from_env(self):
        """Load credentials from environment variables."""
        self.api_key.setText(os.getenv("POLY_API_KEY", ""))
        self.api_secret.setText(os.getenv("POLY_API_SECRET", ""))
        self.passphrase.setText(os.getenv("POLY_API_PASSPHRASE", ""))
        self.private_key.setText(os.getenv("PRIVATE_KEY", ""))

        # Check if polymarket is in enabled platforms
        enabled_platforms = os.getenv("ENABLED_PLATFORMS", "polymarket").lower()
        self.enabled_cb.setChecked("polymarket" in enabled_platforms)

    def get_credentials(self):
        """Get PolymarketCredentials object."""
        if not self.enabled_cb.isChecked():
            return None
        return PolymarketCredentials(
            api_key=self.api_key.text().strip(),
            api_secret=self.api_secret.text().strip(),
            passphrase=self.passphrase.text().strip(),
            private_key=self.private_key.text().strip()
        )

    def is_enabled(self) -> bool:
        return self.enabled_cb.isChecked()

    def validate(self):
        """Validate the credentials."""
        creds = self.get_credentials()
        if creds is None:
            return True, ""  # Not enabled, so valid
        return creds.validate()


class KalshiCredentialsTab(QFrame):
    """Tab for Kalshi credentials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("credentialsTab")
        self._setup_ui()
        self.load_from_env()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Enable checkbox
        self.enabled_cb = QCheckBox("Enable Kalshi")
        self.enabled_cb.setStyleSheet("font-weight: bold; color: #f59e0b;")
        self.enabled_cb.setChecked(False)
        self.enabled_cb.stateChanged.connect(self._on_enabled_changed)
        layout.addWidget(self.enabled_cb)

        # Form layout
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignLeft)

        # Email
        self.email = QLineEdit()
        self.email.setPlaceholderText("Enter Email")
        self.email.setEnabled(False)
        form_layout.addRow(self._make_label("Email"), self.email)

        # Password
        self.password = QLineEdit()
        self.password.setPlaceholderText("Enter Password")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setEnabled(False)
        form_layout.addRow(self._make_label("Password"), self.password)

        # API Key (optional)
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("Optional - API Key")
        self.api_key.setEnabled(False)
        form_layout.addRow(self._make_label("API Key (opt.)"), self.api_key)

        layout.addLayout(form_layout)

        # Info label
        info = QLabel("Kalshi uses email/password for authentication.\nAPI Key is optional for advanced usage.")
        info.setStyleSheet("color: #64748b; font-size: 11px; margin-top: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #94a3b8; font-weight: bold;")
        return lbl

    def _on_enabled_changed(self, state):
        enabled = state == Qt.Checked
        self.email.setEnabled(enabled)
        self.password.setEnabled(enabled)
        self.api_key.setEnabled(enabled)

    def load_from_env(self):
        """Load credentials from environment variables."""
        self.email.setText(os.getenv("KALSHI_EMAIL", ""))
        self.password.setText(os.getenv("KALSHI_PASSWORD", ""))
        self.api_key.setText(os.getenv("KALSHI_API_KEY", ""))

        # Check if kalshi is in enabled platforms
        enabled_platforms = os.getenv("ENABLED_PLATFORMS", "polymarket").lower()
        self.enabled_cb.setChecked("kalshi" in enabled_platforms)
        self._on_enabled_changed(self.enabled_cb.checkState())

    def get_credentials(self):
        """Get KalshiCredentials object."""
        if not self.enabled_cb.isChecked():
            return None
        api_key = self.api_key.text().strip()
        return KalshiCredentials(
            email=self.email.text().strip(),
            password=self.password.text().strip(),
            api_key=api_key if api_key else None
        )

    def is_enabled(self) -> bool:
        return self.enabled_cb.isChecked()

    def validate(self):
        """Validate the credentials."""
        creds = self.get_credentials()
        if creds is None:
            return True, ""  # Not enabled, so valid
        return creds.validate()


class CredentialsPanel(QFrame):
    """
    Panel for managing credentials across multiple platforms.

    Provides a tabbed interface with separate tabs for each platform.
    """

    credentials_changed = Signal(dict)  # Emits all credentials as env dict
    platforms_changed = Signal(list)    # Emits list of enabled platforms

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Header
        header = QLabel("Platform Credentials")
        header.setObjectName("subheader")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #e2e8f0;")
        layout.addWidget(header)

        # Tabs for each platform
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #334155;
                border-radius: 8px;
                background: #1e293b;
            }
            QTabBar::tab {
                background: #334155;
                color: #94a3b8;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #1e293b;
                color: #e2e8f0;
            }
            QTabBar::tab:hover:!selected {
                background: #475569;
            }
        """)

        # Polymarket Tab
        self.poly_tab = PolymarketCredentialsTab()
        self.tabs.addTab(self.poly_tab, "Polymarket")

        # Kalshi Tab
        self.kalshi_tab = KalshiCredentialsTab()
        self.tabs.addTab(self.kalshi_tab, "Kalshi")

        layout.addWidget(self.tabs)

        # Multi-Platform Options
        options_group = QGroupBox("Multi-Platform Options")
        options_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        options_layout = QVBoxLayout(options_group)

        self.cross_platform_cb = QCheckBox("Enable Cross-Platform Arbitrage")
        self.cross_platform_cb.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.cross_platform_cb.setToolTip(
            "Detect arbitrage opportunities between Polymarket and Kalshi\n"
            "when the same question has different prices on each platform."
        )
        # Load from env
        cross_enabled = os.getenv("CROSS_PLATFORM_ARBITRAGE", "false").lower() in ("true", "1", "yes")
        self.cross_platform_cb.setChecked(cross_enabled)
        options_layout.addWidget(self.cross_platform_cb)

        layout.addWidget(options_group)

        # Save Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("Save Credentials")
        self.save_btn.setFixedHeight(40)
        self.save_btn.setFixedWidth(150)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: #10b981;
                color: white;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #059669;
            }
            QPushButton:pressed {
                background: #047857;
            }
        """)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _on_save(self):
        """Save all credentials to .env file."""
        # Validate first
        poly_valid, poly_error = self.poly_tab.validate()
        if not poly_valid:
            QMessageBox.warning(self, "Validation Error", f"Polymarket: {poly_error}")
            return

        kalshi_valid, kalshi_error = self.kalshi_tab.validate()
        if not kalshi_valid:
            QMessageBox.warning(self, "Validation Error", f"Kalshi: {kalshi_error}")
            return

        # Check at least one platform is enabled
        if not self.poly_tab.is_enabled() and not self.kalshi_tab.is_enabled():
            QMessageBox.warning(self, "Validation Error", "At least one platform must be enabled.")
            return

        # Build env dict
        env_dict = {}

        # Polymarket credentials
        poly_creds = self.poly_tab.get_credentials()
        if poly_creds:
            env_dict.update(poly_creds.to_env_dict())
        else:
            # Keep empty values if not enabled
            env_dict.update({
                "POLY_API_KEY": "",
                "POLY_API_SECRET": "",
                "POLY_API_PASSPHRASE": "",
                "PRIVATE_KEY": ""
            })

        # Kalshi credentials
        kalshi_creds = self.kalshi_tab.get_credentials()
        if kalshi_creds:
            env_dict.update(kalshi_creds.to_env_dict())
        else:
            env_dict.update({
                "KALSHI_EMAIL": "",
                "KALSHI_PASSWORD": "",
                "KALSHI_API_KEY": ""
            })

        # Enabled platforms
        enabled = []
        if self.poly_tab.is_enabled():
            enabled.append("polymarket")
        if self.kalshi_tab.is_enabled():
            enabled.append("kalshi")
        env_dict["ENABLED_PLATFORMS"] = ",".join(enabled)

        # Cross-platform option
        env_dict["CROSS_PLATFORM_ARBITRAGE"] = "true" if self.cross_platform_cb.isChecked() else "false"

        # Save to .env
        self._save_to_env(env_dict)

        # Emit signals
        self.credentials_changed.emit(env_dict)
        self.platforms_changed.emit(enabled)

        QMessageBox.information(self, "Success", "Credentials saved successfully!")

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
                    k = line.split("=", 1)[0].strip()
                    env_vars[k] = True

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
                if k not in keys_handled:
                    new_lines.append(f"{k}={v}\n")

            with open(env_path, "w") as f:
                f.writelines(new_lines)

            logger.info("Credentials saved to .env")
        except Exception as e:
            from backend.logger import logger
            logger.error(f"Failed to save credentials: {e}")
            raise

    def get_enabled_platforms(self) -> list:
        """Get list of enabled platforms."""
        platforms = []
        if self.poly_tab.is_enabled():
            platforms.append("polymarket")
        if self.kalshi_tab.is_enabled():
            platforms.append("kalshi")
        return platforms

    def is_cross_platform_enabled(self) -> bool:
        """Check if cross-platform arbitrage is enabled."""
        return self.cross_platform_cb.isChecked()

    def reload_from_env(self):
        """Reload all credentials from environment."""
        self.poly_tab.load_from_env()
        self.kalshi_tab.load_from_env()
        cross_enabled = os.getenv("CROSS_PLATFORM_ARBITRAGE", "false").lower() in ("true", "1", "yes")
        self.cross_platform_cb.setChecked(cross_enabled)
