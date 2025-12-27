
import asyncio
import os
import logging
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QTextEdit, QLabel, QFrame, QMessageBox
)
from PySide6.QtCore import Slot, Signal

# Frontend Imports
from frontend.styles import THEME_STYLES
from frontend.components.market_monitor import MarketMonitorWidget
from frontend.components.config_widget import ConfigWidget

# Backend Imports
from backend.logger import logger
from backend.config import Config
from backend.arbitrage import ArbitrageBot

# Logging Handler for UI
class QtLogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        msg = self.format(record)
        self.callback(msg)

class MainWindow(QMainWindow):
    # Signal for thread-safe UI updates from asyncio
    opportunity_signal = Signal(str, float, float)

    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        self.bot = None
        self.bot_task = None

        # Connect signal to monitor for thread-safe updates
        self.opportunity_signal.connect(self._on_opportunity)
        
        # Window Setup
        self.setWindowTitle("POLYMARKET ARBITRAGE PRO")
        self.resize(1280, 850)
        self.setStyleSheet(THEME_STYLES)
        
        # Central Layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # --- Left Column (Monitor & Logs) ---
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(20)
        
        # Header
        title = QLabel("POLYMARKET ARBITRAGE BOT")
        title.setObjectName("header")
        left_layout.addWidget(title)
        
        # Monitor
        self.monitor = MarketMonitorWidget()
        left_layout.addWidget(self.monitor, stretch=2)
        
        # Logs
        log_container = QFrame()
        log_container.setObjectName("card")
        log_layout = QVBoxLayout(log_container)
        log_label = QLabel("📟 System Logs")
        log_label.setObjectName("subheader")
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        
        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log_console)
        
        left_layout.addWidget(log_container, stretch=1)
        
        main_layout.addWidget(left_col, stretch=7)
        
        # --- Right Column (Config) ---
        self.config_widget = ConfigWidget()
        self.config_widget.start_requested.connect(self.start_bot)
        self.config_widget.stop_requested.connect(self.stop_bot)
        
        main_layout.addWidget(self.config_widget, stretch=3)
        
        # Wiring Logs
        handler = QtLogHandler(self.append_log)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', '%H:%M:%S'))
        logger.addHandler(handler)
        
        # Load Env
        self.config_widget.load_defaults()

    def append_log(self, msg):
        self.log_console.append(msg)
        # Check for Opportunity logs to update Monitor
        if "ARBITRAGE FOUND" in msg or "Executing Trade" in msg:
             # Basic distinct parsing or Event Bus preferred
             pass

    @Slot(str, float, float)
    def _on_opportunity(self, market_id: str, yes_price: float, no_price: float):
        """Thread-safe slot to update monitor from signal."""
        self.monitor.add_opportunity(market_id, yes_price, no_price)

    def start_bot(self, data):
        # Apply Env vars from UI
        import os
        for k, v in data.items():
            if v:
                os.environ[k] = v
        
        try:
            cfg = Config.load()
            self.bot = ArbitrageBot(cfg)
            
            # Connect UI Callback using Qt Signal for thread-safety
            self.bot.on_opportunity = lambda market_id, yes_price, no_price: self.opportunity_signal.emit(market_id, yes_price, no_price)

            # Start Task
            self.bot_task = self.loop.create_task(self.bot.run())
            logger.info("Bot Engine Started.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.config_widget.on_stop() # Reset buttons

    def stop_bot(self):
        if self.bot:
            self.bot.stop()
        if self.bot_task:
            try:
                self.bot_task.cancel()
            except Exception as e:
                logger.warning(f"Error cancelling task: {e}")
        logger.info("Bot Engine Stopped.")
