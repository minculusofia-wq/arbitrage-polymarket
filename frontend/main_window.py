
import asyncio
import os
import logging
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTextEdit, QLabel, QFrame, QMessageBox, QTabWidget
)
from PySide6.QtCore import Slot, Signal

# Frontend Imports
from frontend.styles import THEME_STYLES
from frontend.components.market_monitor import MarketMonitorWidget
from frontend.components.config_widget import ConfigWidget
from frontend.components.pnl_dashboard import PnLDashboard
from frontend.components.trade_history import TradeHistoryWidget

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
    # Signals for thread-safe UI updates from asyncio
    opportunity_signal = Signal(str, float, float)
    trade_signal = Signal(dict)

    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        self.bot = None
        self.bot_task = None

        # Connect signals for thread-safe updates
        self.opportunity_signal.connect(self._on_opportunity)
        self.trade_signal.connect(self._on_trade)

        # Window Setup
        self.setWindowTitle("POLYMARKET ARBITRAGE PRO")
        self.resize(1400, 900)
        self.setStyleSheet(THEME_STYLES)

        # Central Layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # --- Left Column (Dashboard, Monitor, Logs) ---
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15)

        # Header
        title = QLabel("POLYMARKET ARBITRAGE BOT")
        title.setObjectName("header")
        left_layout.addWidget(title)

        # PnL Dashboard
        self.pnl_dashboard = PnLDashboard()
        left_layout.addWidget(self.pnl_dashboard)

        # Tabbed section for Monitor and Trade History
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: transparent;
            }
            QTabBar::tab {
                background: #1e293b;
                color: #94a3b8;
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: #334155;
                color: #ffffff;
            }
        """)

        # Monitor Tab
        self.monitor = MarketMonitorWidget()
        self.tabs.addTab(self.monitor, "Live Market Feed")

        # Trade History Tab
        self.trade_history = TradeHistoryWidget()
        self.tabs.addTab(self.trade_history, "Trade History")

        left_layout.addWidget(self.tabs, stretch=2)

        # Logs
        log_container = QFrame()
        log_container.setObjectName("card")
        log_layout = QVBoxLayout(log_container)
        log_label = QLabel("System Logs")
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

    @Slot(dict)
    def _on_trade(self, trade: dict):
        """Thread-safe slot to update trade history and PnL from signal."""
        self.trade_history.add_trade(trade)
        self.pnl_dashboard.add_trade(trade)

    def start_bot(self, data):
        # Apply Env vars from UI
        import os
        for k, v in data.items():
            if v:
                os.environ[k] = v

        try:
            cfg = Config.load()
            self.bot = ArbitrageBot(cfg)

            # Initialize PnL dashboard with capital
            self.pnl_dashboard.set_initial_balance(cfg.CAPITAL_PER_TRADE)

            # Connect UI Callbacks using Qt Signals for thread-safety
            self.bot.on_opportunity = lambda market_id, yes_price, no_price: self.opportunity_signal.emit(market_id, yes_price, no_price)
            self.bot.on_trade = lambda trade: self.trade_signal.emit(trade)

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
