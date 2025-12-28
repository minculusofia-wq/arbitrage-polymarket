
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from datetime import datetime
from typing import List, Dict
import csv
import os


class TradeHistoryWidget(QFrame):
    """Historical trades table with export functionality."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.trades: List[Dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header with export button
        header_layout = QHBoxLayout()

        header = QLabel("📜 Trade History")
        header.setObjectName("subheader")
        header_layout.addWidget(header)

        header_layout.addStretch()

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setFixedHeight(30)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        self.export_btn.clicked.connect(self.export_to_csv)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Time", "Market", "Side", "Shares",
            "Entry", "Exit", "P&L", "Status"
        ])

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                alternate-background-color: #1e293b;
            }
        """)

        layout.addWidget(self.table)

    def add_trade(self, trade: Dict):
        """Add a trade to the history table."""
        self.trades.insert(0, trade)  # Add to beginning

        # Insert row at top
        self.table.insertRow(0)

        # Extract trade data
        timestamp = trade.get('timestamp', datetime.now())
        market_id = trade.get('market_id', 'Unknown')
        side = trade.get('side', 'BOTH')
        shares = trade.get('shares', 0)
        entry_cost = trade.get('entry_cost', 0)
        exit_value = trade.get('exit_value', 1.0)  # For arbitrage, this is $1 per share
        pnl = trade.get('pnl', 0)
        status = trade.get('status', 'EXECUTED')

        # Format time
        time_str = timestamp.strftime('%H:%M:%S') if isinstance(timestamp, datetime) else str(timestamp)

        # Create items
        items = [
            QTableWidgetItem(time_str),
            QTableWidgetItem(str(market_id)[:20] + "..." if len(str(market_id)) > 20 else str(market_id)),
            QTableWidgetItem(side),
            QTableWidgetItem(f"{shares:.1f}"),
            QTableWidgetItem(f"${entry_cost:.2f}"),
            QTableWidgetItem(f"${exit_value:.2f}"),
            QTableWidgetItem(f"${pnl:+.2f}"),
            QTableWidgetItem(status)
        ]

        # Colors
        green = QColor("#00e676")
        red = QColor("#ef4444")
        white = QColor("#ffffff")
        gray = QColor("#94a3b8")

        for i, item in enumerate(items):
            item.setTextAlignment(Qt.AlignCenter)

            if i == 6:  # P&L column
                item.setForeground(green if pnl >= 0 else red)
            elif i == 7:  # Status column
                if status == "EXECUTED":
                    item.setForeground(green)
                elif status == "FAILED":
                    item.setForeground(red)
                else:
                    item.setForeground(gray)
            else:
                item.setForeground(white)

            self.table.setItem(0, i, item)

        # Limit to 100 rows
        while self.table.rowCount() > 100:
            self.table.removeRow(self.table.rowCount() - 1)
            self.trades.pop()

    def export_to_csv(self):
        """Export trade history to CSV file."""
        if not self.trades:
            QMessageBox.information(self, "Export", "No trades to export.")
            return

        # Default filename
        default_name = f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # File dialog
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Trades",
            default_name,
            "CSV Files (*.csv)"
        )

        if not filename:
            return

        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow([
                    "Timestamp", "Market ID", "Side", "Shares",
                    "Entry Cost", "Exit Value", "P&L", "Status",
                    "YES Price", "NO Price", "ROI %"
                ])

                # Data
                for trade in self.trades:
                    timestamp = trade.get('timestamp', datetime.now())
                    time_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)

                    writer.writerow([
                        time_str,
                        trade.get('market_id', ''),
                        trade.get('side', ''),
                        trade.get('shares', 0),
                        trade.get('entry_cost', 0),
                        trade.get('exit_value', 0),
                        trade.get('pnl', 0),
                        trade.get('status', ''),
                        trade.get('yes_price', 0),
                        trade.get('no_price', 0),
                        trade.get('roi', 0)
                    ])

            QMessageBox.information(
                self,
                "Export Successful",
                f"Exported {len(self.trades)} trades to:\n{filename}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export trades:\n{str(e)}"
            )

    def clear_history(self):
        """Clear all trade history."""
        self.trades.clear()
        self.table.setRowCount(0)
