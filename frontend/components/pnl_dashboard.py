
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout
)
from PySide6.QtCore import Qt
from typing import List, Dict, Optional
from datetime import datetime, date


class StatCard(QFrame):
    """Individual stat card for the dashboard."""

    def __init__(self, icon: str, title: str, value: str = "$0.00"):
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


class PnLDashboard(QFrame):
    """Real-time profit/loss dashboard."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")

        self.trades: List[Dict] = []
        self.positions: List[Dict] = []
        self.initial_balance: float = 0.0
        self.current_balance: float = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel("📊 Performance Dashboard")
        header.setObjectName("subheader")
        layout.addWidget(header)

        # Stats Grid
        grid = QGridLayout()
        grid.setSpacing(10)

        # Row 1: Balance, Today P&L, Total P&L
        self.balance_card = StatCard("💰", "Balance", "$0.00")
        self.pnl_today_card = StatCard("📈", "Today", "+$0.00")
        self.pnl_total_card = StatCard("📊", "Total P&L", "+$0.00")

        grid.addWidget(self.balance_card, 0, 0)
        grid.addWidget(self.pnl_today_card, 0, 1)
        grid.addWidget(self.pnl_total_card, 0, 2)

        # Row 2: Win Rate, Avg ROI, Trades Count
        self.win_rate_card = StatCard("🎯", "Win Rate", "0%")
        self.avg_roi_card = StatCard("📉", "Avg ROI", "0%")
        self.trades_count_card = StatCard("🔢", "Trades", "0")

        grid.addWidget(self.win_rate_card, 1, 0)
        grid.addWidget(self.avg_roi_card, 1, 1)
        grid.addWidget(self.trades_count_card, 1, 2)

        layout.addLayout(grid)

    def set_initial_balance(self, balance: float):
        """Set the initial balance for P&L calculations."""
        self.initial_balance = balance
        self.current_balance = balance
        self._update_display()

    def add_trade(self, trade: Dict):
        """Add a completed trade to history."""
        self.trades.append(trade)

        # Update balance based on P&L
        pnl = trade.get('pnl', 0)
        self.current_balance += pnl

        self._update_display()

    def update_positions(self, positions: List[Dict]):
        """Update open positions."""
        self.positions = positions
        self._update_display()

    def _update_display(self):
        """Refresh all dashboard stats."""
        # Balance
        self.balance_card.set_value(f"${self.current_balance:,.2f}")

        # Total P&L
        total_pnl = sum(t.get('pnl', 0) for t in self.trades)
        pnl_color = "#00e676" if total_pnl >= 0 else "#ef4444"
        pnl_text = f"+${total_pnl:,.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):,.2f}"
        self.pnl_total_card.set_value(pnl_text, pnl_color)

        # Today's P&L
        today = date.today()
        today_trades = []
        for t in self.trades:
            ts = t.get('timestamp')
            if isinstance(ts, datetime):
                if ts.date() == today:
                    today_trades.append(t)
            # Skip trades without valid timestamp

        today_pnl = sum(t.get('pnl', 0) for t in today_trades)
        today_color = "#00e676" if today_pnl >= 0 else "#ef4444"
        today_text = f"+${today_pnl:,.2f}" if today_pnl >= 0 else f"-${abs(today_pnl):,.2f}"
        self.pnl_today_card.set_value(today_text, today_color)

        # Win Rate
        if self.trades:
            wins = sum(1 for t in self.trades if t.get('pnl', 0) > 0)
            win_rate = (wins / len(self.trades)) * 100
            rate_color = "#00e676" if win_rate >= 50 else "#f59e0b" if win_rate >= 30 else "#ef4444"
            self.win_rate_card.set_value(f"{win_rate:.1f}%", rate_color)
        else:
            self.win_rate_card.set_value("0%")

        # Average ROI
        if self.trades:
            rois = [t.get('roi', 0) for t in self.trades if 'roi' in t]
            avg_roi = sum(rois) / len(rois) if rois else 0
            roi_color = "#00e676" if avg_roi >= 0 else "#ef4444"
            roi_sign = "+" if avg_roi >= 0 else ""
            self.avg_roi_card.set_value(f"{roi_sign}{avg_roi:.2f}%", roi_color)
        else:
            self.avg_roi_card.set_value("0%")

        # Trades Count
        self.trades_count_card.set_value(str(len(self.trades)))

    def reset(self):
        """Reset all stats."""
        self.trades.clear()
        self.positions.clear()
        self.current_balance = self.initial_balance
        self._update_display()
