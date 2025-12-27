
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, 
    QHeaderView, QTableWidgetItem, QFrame,
    QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QIcon

class MarketMonitorWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("📡 Live Market Feed")
        header.setObjectName("subheader")
        layout.addWidget(header)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        # Using concise, financial style headers
        self.table.setHorizontalHeaderLabels([
            "MARKET", "YES ($)", "NO ($)", "SPREAD", "ROI %", "ACTION"
        ])
        
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False) # Handled by CSS/Logic if needed
        
        layout.addWidget(self.table)
        
    def add_opportunity(self, market_id, yes_price, no_price):
        # Insert at top
        self.table.insertRow(0)
        
        cost = yes_price + no_price
        roi = ((1.0 - cost) / cost * 100) if cost > 0 else 0
        
        # Format Items
        items = [
            QTableWidgetItem(str(market_id)[:15] + "..."),
            QTableWidgetItem(f"{yes_price:.3f}"),
            QTableWidgetItem(f"{no_price:.3f}"),
            QTableWidgetItem(f"{cost:.3f}"),
            QTableWidgetItem(f"+{roi:.2f}%"),
            QTableWidgetItem("OPPORTUNITY" if cost < 1.0 else "WATCHING")
        ]
        
        # Coloring
        green = QColor("#00e676")
        red = QColor("#ef4444")
        text_white = QColor("#ffffff")
        
        for i, item in enumerate(items):
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(text_white)
            if i == 4: # ROI
                item.setForeground(green if roi > 0 else red)
                item.setFont(self.font()) # Default bold handled by stylesheet?
            
            self.table.setItem(0, i, item)
            
        # Limit rows
        if self.table.rowCount() > 50:
            self.table.removeRow(50)
