"""
Backtest Dashboard Widget for Polymarket Arbitrage Bot.

Provides a comprehensive interface for:
- Configuring and running backtests
- Viewing results and metrics
- Exporting data to CSV
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QDateTimeEdit, QDoubleSpinBox, QProgressBar, QGroupBox,
    QSplitter, QAbstractItemView, QFileDialog, QMessageBox,
    QComboBox, QGridLayout, QSpinBox
)
from PySide6.QtCore import Qt, Signal, Slot, QDateTime, QTimer

if TYPE_CHECKING:
    from backend.services.backtest_engine import BacktestEngine, BacktestResult, BacktestTrade


class StatCard(QFrame):
    """Individual stat card for metrics display."""

    def __init__(self, icon: str, title: str, value: str = "—"):
        super().__init__()
        self.setObjectName("statCard")
        self.setStyleSheet("""
            #statCard {
                background-color: #1e293b;
                border-radius: 8px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(5)

        # Header with icon and title
        header = QLabel(f"{icon} {title}")
        header.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        layout.addWidget(header)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        layout.addWidget(self.value_label)

    def set_value(self, value: str, color: str = "#ffffff"):
        self.value_label.setText(value)
        self.value_label.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")


class BacktestConfigPanel(QFrame):
    """Configuration panel for backtest parameters."""

    run_requested = Signal(dict)  # Emits config dict
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header
        header = QLabel("Backtest Configuration")
        header.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        # Date range section
        date_group = QGroupBox("Date Range")
        date_group.setStyleSheet("""
            QGroupBox {
                color: #94a3b8;
                font-weight: bold;
                border: 1px solid #334155;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        date_layout = QVBoxLayout(date_group)

        # From date
        from_layout = QHBoxLayout()
        from_label = QLabel("From:")
        from_label.setStyleSheet("color: #94a3b8;")
        from_label.setFixedWidth(50)
        self.start_date = QDateTimeEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDateTime(QDateTime.currentDateTime().addDays(-7))
        self.start_date.setStyleSheet("""
            QDateTimeEdit {
                background-color: #1e293b;
                color: #ffffff;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        from_layout.addWidget(from_label)
        from_layout.addWidget(self.start_date)
        date_layout.addLayout(from_layout)

        # To date
        to_layout = QHBoxLayout()
        to_label = QLabel("To:")
        to_label.setStyleSheet("color: #94a3b8;")
        to_label.setFixedWidth(50)
        self.end_date = QDateTimeEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDateTime(QDateTime.currentDateTime())
        self.end_date.setStyleSheet("""
            QDateTimeEdit {
                background-color: #1e293b;
                color: #ffffff;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        to_layout.addWidget(to_label)
        to_layout.addWidget(self.end_date)
        date_layout.addLayout(to_layout)

        layout.addWidget(date_group)

        # Capital settings
        capital_group = QGroupBox("Capital Settings")
        capital_group.setStyleSheet("""
            QGroupBox {
                color: #94a3b8;
                font-weight: bold;
                border: 1px solid #334155;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        capital_layout = QVBoxLayout(capital_group)

        spinbox_style = """
            QDoubleSpinBox, QSpinBox {
                background-color: #1e293b;
                color: #ffffff;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 5px;
            }
        """

        # Initial capital
        init_layout = QHBoxLayout()
        init_label = QLabel("Initial:")
        init_label.setStyleSheet("color: #94a3b8;")
        init_label.setFixedWidth(80)
        self.initial_capital = QDoubleSpinBox()
        self.initial_capital.setRange(100, 1000000)
        self.initial_capital.setValue(10000)
        self.initial_capital.setPrefix("$")
        self.initial_capital.setStyleSheet(spinbox_style)
        init_layout.addWidget(init_label)
        init_layout.addWidget(self.initial_capital)
        capital_layout.addLayout(init_layout)

        # Per trade
        trade_layout = QHBoxLayout()
        trade_label = QLabel("Per Trade:")
        trade_label.setStyleSheet("color: #94a3b8;")
        trade_label.setFixedWidth(80)
        self.capital_per_trade = QDoubleSpinBox()
        self.capital_per_trade.setRange(10, 10000)
        self.capital_per_trade.setValue(100)
        self.capital_per_trade.setPrefix("$")
        self.capital_per_trade.setStyleSheet(spinbox_style)
        trade_layout.addWidget(trade_label)
        trade_layout.addWidget(self.capital_per_trade)
        capital_layout.addLayout(trade_layout)

        layout.addWidget(capital_group)

        # Strategy settings
        strategy_group = QGroupBox("Strategy Parameters")
        strategy_group.setStyleSheet("""
            QGroupBox {
                color: #94a3b8;
                font-weight: bold;
                border: 1px solid #334155;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        strategy_layout = QVBoxLayout(strategy_group)

        # Min margin
        margin_layout = QHBoxLayout()
        margin_label = QLabel("Min Margin:")
        margin_label.setStyleSheet("color: #94a3b8;")
        margin_label.setFixedWidth(80)
        self.min_margin = QDoubleSpinBox()
        self.min_margin.setRange(0.001, 0.1)
        self.min_margin.setValue(0.02)
        self.min_margin.setSingleStep(0.005)
        self.min_margin.setDecimals(3)
        self.min_margin.setSuffix(" (2%)")
        self.min_margin.setStyleSheet(spinbox_style)
        margin_layout.addWidget(margin_label)
        margin_layout.addWidget(self.min_margin)
        strategy_layout.addLayout(margin_layout)

        # Cooldown
        cooldown_layout = QHBoxLayout()
        cooldown_label = QLabel("Cooldown:")
        cooldown_label.setStyleSheet("color: #94a3b8;")
        cooldown_label.setFixedWidth(80)
        self.cooldown = QSpinBox()
        self.cooldown.setRange(0, 300)
        self.cooldown.setValue(30)
        self.cooldown.setSuffix(" sec")
        self.cooldown.setStyleSheet(spinbox_style)
        cooldown_layout.addWidget(cooldown_label)
        cooldown_layout.addWidget(self.cooldown)
        strategy_layout.addLayout(cooldown_layout)

        layout.addWidget(strategy_group)

        # Data status
        self.data_status = QLabel("No data available")
        self.data_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
        self.data_status.setWordWrap(True)
        layout.addWidget(self.data_status)

        # Buttons
        btn_layout = QHBoxLayout()

        self.run_btn = QPushButton("Run Backtest")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #6b7280; }
        """)
        self.run_btn.clicked.connect(self._on_run)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #dc2626; }
            QPushButton:disabled { background-color: #6b7280; }
        """)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)

        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                text-align: center;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress)

        layout.addStretch()

    def _on_run(self):
        config = {
            'start_time': self.start_date.dateTime().toPython(),
            'end_time': self.end_date.dateTime().toPython(),
            'initial_capital': self.initial_capital.value(),
            'capital_per_trade': self.capital_per_trade.value(),
            'min_profit_margin': self.min_margin.value(),
            'cooldown_seconds': float(self.cooldown.value()),
            'markets_filter': None
        }
        self.run_requested.emit(config)

    def set_running(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.progress.setVisible(running)
        if running:
            self.progress.setValue(0)

    def update_progress(self, value: float, message: str = ""):
        self.progress.setValue(int(value))
        if message:
            self.progress.setFormat(f"{message}")

    def update_data_status(self, has_data: bool, snapshot_count: int = 0,
                           start_date: str = None, end_date: str = None):
        if has_data:
            self.data_status.setText(
                f"Data available: {snapshot_count:,} snapshots\n"
                f"Range: {start_date or 'N/A'} to {end_date or 'N/A'}"
            )
            self.data_status.setStyleSheet("color: #10b981; font-size: 11px;")
            self.run_btn.setEnabled(True)
        else:
            self.data_status.setText(
                "No data available.\n"
                "Enable data collection and run the bot to collect snapshots."
            )
            self.data_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
            self.run_btn.setEnabled(False)


class BacktestResultsPanel(QFrame):
    """Displays backtest results with metrics cards."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header
        header = QLabel("Backtest Results")
        header.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        # Metrics grid
        grid = QGridLayout()
        grid.setSpacing(10)

        self.total_pnl = StatCard("💰", "Total P&L", "—")
        self.win_rate = StatCard("🎯", "Win Rate", "—")
        self.total_trades = StatCard("📊", "Trades", "—")
        self.max_drawdown = StatCard("📉", "Max DD", "—")
        self.avg_roi = StatCard("📈", "Avg ROI", "—")
        self.opportunities = StatCard("🔍", "Detected", "—")

        grid.addWidget(self.total_pnl, 0, 0)
        grid.addWidget(self.win_rate, 0, 1)
        grid.addWidget(self.total_trades, 0, 2)
        grid.addWidget(self.max_drawdown, 1, 0)
        grid.addWidget(self.avg_roi, 1, 1)
        grid.addWidget(self.opportunities, 1, 2)

        layout.addLayout(grid)

        # Capital summary
        self.capital_summary = QLabel("")
        self.capital_summary.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.capital_summary.setWordWrap(True)
        layout.addWidget(self.capital_summary)

    def update_results(self, result: 'BacktestResult'):
        """Update display with backtest results."""
        # Total P&L
        pnl_color = "#10b981" if result.total_pnl >= 0 else "#ef4444"
        pnl_text = f"${result.total_pnl:+,.2f}"
        self.total_pnl.set_value(pnl_text, pnl_color)

        # Win rate
        wr_color = "#10b981" if result.win_rate >= 50 else "#f59e0b" if result.win_rate >= 30 else "#ef4444"
        self.win_rate.set_value(f"{result.win_rate:.1f}%", wr_color)

        # Total trades
        self.total_trades.set_value(str(result.total_trades))

        # Max drawdown
        dd_pct = result.max_drawdown * 100
        dd_color = "#10b981" if dd_pct < 5 else "#f59e0b" if dd_pct < 10 else "#ef4444"
        self.max_drawdown.set_value(f"{dd_pct:.1f}%", dd_color)

        # Avg ROI
        roi_color = "#10b981" if result.avg_roi > 0 else "#ef4444"
        self.avg_roi.set_value(f"{result.avg_roi:.2f}%", roi_color)

        # Opportunities
        self.opportunities.set_value(str(result.opportunities_detected))

        # Capital summary
        self.capital_summary.setText(
            f"Starting: ${result.starting_capital:,.2f} | "
            f"Ending: ${result.ending_capital:,.2f} | "
            f"Peak: ${result.peak_capital:,.2f}\n"
            f"Executed: {result.opportunities_executed} | "
            f"Skipped (cooldown): {result.opportunities_skipped_cooldown} | "
            f"Skipped (capital): {result.opportunities_skipped_capital}"
        )

    def clear(self):
        """Clear results display."""
        for card in [self.total_pnl, self.win_rate, self.total_trades,
                     self.max_drawdown, self.avg_roi, self.opportunities]:
            card.set_value("—")
        self.capital_summary.setText("")


class BacktestTradesTable(QFrame):
    """Table showing individual backtest trades."""

    export_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.trades: List[Dict] = []
        self.current_result: Optional['BacktestResult'] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header with export button
        header_layout = QHBoxLayout()
        header = QLabel("Simulated Trades")
        header.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:disabled { background-color: #6b7280; }
        """)
        self.export_btn.clicked.connect(self.export_requested.emit)
        self.export_btn.setEnabled(False)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Time", "Market", "Shares", "YES $", "NO $",
            "Entry", "P&L", "ROI %"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a;
                color: #ffffff;
                border: 1px solid #334155;
                border-radius: 4px;
                gridline-color: #334155;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #1e40af;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #334155;
                font-weight: bold;
            }
        """)

        layout.addWidget(self.table)

    def set_trades(self, result: 'BacktestResult'):
        """Populate table with backtest trades."""
        self.table.setRowCount(0)
        self.trades = []
        self.current_result = result

        for trade in result.trades:
            self._add_trade_row(trade)

        self.export_btn.setEnabled(len(result.trades) > 0)

    def _add_trade_row(self, trade: 'BacktestTrade'):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Format timestamp
        if isinstance(trade.timestamp, datetime):
            ts_str = trade.timestamp.strftime('%m-%d %H:%M')
        else:
            ts_str = str(trade.timestamp)[:16]

        # Truncate market ID
        market_short = trade.market_id[:12] + "..." if len(trade.market_id) > 15 else trade.market_id

        items = [
            QTableWidgetItem(ts_str),
            QTableWidgetItem(market_short),
            QTableWidgetItem(f"{trade.shares:.1f}"),
            QTableWidgetItem(f"${trade.yes_price:.4f}"),
            QTableWidgetItem(f"${trade.no_price:.4f}"),
            QTableWidgetItem(f"${trade.entry_cost:.2f}"),
            QTableWidgetItem(f"${trade.expected_pnl:+.2f}"),
            QTableWidgetItem(f"{trade.roi:+.2f}%")
        ]

        green = "#10b981"
        red = "#ef4444"
        white = "#ffffff"

        for i, item in enumerate(items):
            item.setTextAlignment(Qt.AlignCenter)
            if i == 6:  # P&L
                color = green if trade.expected_pnl >= 0 else red
                item.setForeground(Qt.GlobalColor.white)
                item.setBackground(Qt.GlobalColor.transparent)
            elif i == 7:  # ROI
                color = green if trade.roi >= 0 else red
                item.setForeground(Qt.GlobalColor.white)
            else:
                color = white
            self.table.setItem(row, i, item)

        self.trades.append(trade)

    def clear(self):
        """Clear the table."""
        self.table.setRowCount(0)
        self.trades = []
        self.current_result = None
        self.export_btn.setEnabled(False)


class BacktestWidget(QWidget):
    """Main backtest dashboard widget - combines all panels."""

    def __init__(self, backtest_engine: Optional['BacktestEngine'] = None):
        super().__init__()
        self.engine = backtest_engine
        self._backtest_task: Optional[asyncio.Task] = None
        self._setup_ui()
        self._connect_signals()

        # Update data status periodically
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_data_status)
        self._status_timer.start(10000)  # Every 10 seconds

        # Initial status update
        QTimer.singleShot(100, self._update_data_status)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)

        # Left: Config
        self.config_panel = BacktestConfigPanel()
        self.config_panel.setMaximumWidth(320)
        self.config_panel.setMinimumWidth(280)
        splitter.addWidget(self.config_panel)

        # Right: Results (vertical split)
        right_splitter = QSplitter(Qt.Vertical)

        self.results_panel = BacktestResultsPanel()
        right_splitter.addWidget(self.results_panel)

        self.trades_table = BacktestTradesTable()
        right_splitter.addWidget(self.trades_table)

        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 3)

        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

    def _connect_signals(self):
        self.config_panel.run_requested.connect(self._run_backtest)
        self.config_panel.cancel_requested.connect(self._cancel_backtest)
        self.trades_table.export_requested.connect(self._export_trades)

    def set_engine(self, engine: 'BacktestEngine'):
        """Set the backtest engine."""
        self.engine = engine
        self._update_data_status()

    def _update_data_status(self):
        """Update data availability status."""
        if not self.engine:
            self.config_panel.update_data_status(False)
            return

        try:
            stats = self.engine.get_data_stats()
            if stats['has_data']:
                date_range = stats.get('date_range', {})
                self.config_panel.update_data_status(
                    True,
                    stats['snapshot_count'],
                    date_range.get('start', '')[:10] if date_range.get('start') else None,
                    date_range.get('end', '')[:10] if date_range.get('end') else None
                )
            else:
                self.config_panel.update_data_status(False)
        except Exception as e:
            self.config_panel.update_data_status(False)

    def _run_backtest(self, config_dict: dict):
        """Run backtest with given configuration."""
        if not self.engine:
            QMessageBox.warning(self, "Error", "Backtest engine not initialized")
            return

        # Clear previous results
        self.results_panel.clear()
        self.trades_table.clear()

        # Import here to avoid circular imports
        from backend.services.backtest_engine import BacktestConfig

        config = BacktestConfig(**config_dict)

        self.config_panel.set_running(True)

        # Set up callbacks
        def on_progress(value: float, message: str):
            self.config_panel.update_progress(value, message)

        self.engine.on_progress = on_progress

        # Run backtest in background
        async def run():
            try:
                result = await self.engine.run_backtest(config)
                self.results_panel.update_results(result)
                self.trades_table.set_trades(result)
            except Exception as e:
                QMessageBox.critical(self, "Backtest Error", str(e))
            finally:
                self.config_panel.set_running(False)

        # Schedule the coroutine
        try:
            loop = asyncio.get_event_loop()
            self._backtest_task = loop.create_task(run())
        except RuntimeError:
            # No event loop running, create one
            asyncio.run(run())

    def _cancel_backtest(self):
        """Cancel running backtest."""
        if self.engine:
            self.engine.cancel()
        if self._backtest_task:
            self._backtest_task.cancel()
        self.config_panel.set_running(False)

    def _export_trades(self):
        """Export trades to CSV file."""
        if not self.trades_table.current_result:
            QMessageBox.warning(self, "Export", "No results to export")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Backtest Results",
            f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )

        if filename:
            try:
                self.trades_table.current_result.export_to_csv(filename)
                QMessageBox.information(self, "Export", f"Results exported to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
    def sync_with_config(self, config_data: dict):
        """Sync backtest parameters with main bot config."""
        if 'CAPITAL_PER_TRADE' in config_data:
            try:
                self.config_panel.capital_per_trade.setValue(float(config_data['CAPITAL_PER_TRADE']))
            except (ValueError, TypeError):
                pass
        
        if 'MIN_PROFIT_MARGIN' in config_data:
            try:
                self.config_panel.min_margin.setValue(float(config_data['MIN_PROFIT_MARGIN']))
            except (ValueError, TypeError):
                pass

        if 'COOLDOWN_SECONDS' in config_data:
            try:
                self.config_panel.cooldown.setValue(int(config_data['COOLDOWN_SECONDS']))
            except (ValueError, TypeError):
                pass
        
        # Also sync paper balance if applicable
        if 'PAPER_INITIAL_BALANCE' in config_data:
            try:
                self.config_panel.initial_capital.setValue(float(config_data['PAPER_INITIAL_BALANCE']))
            except (ValueError, TypeError):
                pass
