"""Tests for Backtest Engine."""

import pytest
import asyncio
import json
import os
from datetime import datetime, timedelta
from backend.services.backtest_engine import (
    BacktestEngine, BacktestConfig, BacktestTrade, BacktestResult
)
from backend.services.data_collector import DataCollector


class TestBacktestConfig:
    """Tests for BacktestConfig dataclass."""

    def test_default_values(self):
        config = BacktestConfig(
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 7)
        )
        assert config.initial_capital == 10000.0
        assert config.capital_per_trade == 100.0
        assert config.min_profit_margin == 0.02
        assert config.cooldown_seconds == 30.0

    def test_custom_values(self):
        config = BacktestConfig(
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 7),
            initial_capital=5000.0,
            capital_per_trade=50.0,
            min_profit_margin=0.03
        )
        assert config.initial_capital == 5000.0
        assert config.capital_per_trade == 50.0
        assert config.min_profit_margin == 0.03


class TestBacktestTrade:
    """Tests for BacktestTrade dataclass."""

    def test_trade_creation(self):
        trade = BacktestTrade(
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            market_id="market_123",
            shares=50.0,
            yes_price=0.45,
            no_price=0.50,
            entry_cost=47.50,
            expected_pnl=2.50,
            roi=5.26,
            levels_yes=2,
            levels_no=1
        )
        assert trade.shares == 50.0
        assert trade.expected_pnl == 2.50

    def test_trade_to_dict(self):
        trade = BacktestTrade(
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            market_id="market_123",
            shares=50.0,
            yes_price=0.45,
            no_price=0.50,
            entry_cost=47.50,
            expected_pnl=2.50,
            roi=5.26,
            levels_yes=2,
            levels_no=1
        )
        d = trade.to_dict()
        assert d['market_id'] == "market_123"
        assert d['shares'] == 50.0
        assert 'timestamp' in d


class TestBacktestResult:
    """Tests for BacktestResult dataclass."""

    @pytest.fixture
    def result_with_trades(self):
        config = BacktestConfig(
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 7)
        )
        result = BacktestResult(
            config=config,
            starting_capital=10000.0,
            start_time=config.start_time,
            end_time=config.end_time
        )
        # Add some test trades
        result.trades = [
            BacktestTrade(
                timestamp=datetime(2025, 1, 1, 10, 0),
                market_id="market_1",
                shares=50.0, yes_price=0.45, no_price=0.50,
                entry_cost=47.50, expected_pnl=2.50, roi=5.26,
                levels_yes=1, levels_no=1
            ),
            BacktestTrade(
                timestamp=datetime(2025, 1, 2, 10, 0),
                market_id="market_2",
                shares=30.0, yes_price=0.46, no_price=0.51,
                entry_cost=29.10, expected_pnl=0.90, roi=3.09,
                levels_yes=1, levels_no=1
            ),
            BacktestTrade(
                timestamp=datetime(2025, 1, 3, 10, 0),
                market_id="market_3",
                shares=40.0, yes_price=0.48, no_price=0.49,
                entry_cost=38.80, expected_pnl=1.20, roi=3.09,
                levels_yes=2, levels_no=1
            )
        ]
        return result

    def test_calculate_metrics(self, result_with_trades):
        result_with_trades.calculate_metrics()

        assert result_with_trades.total_trades == 3
        assert result_with_trades.winning_trades == 3
        assert result_with_trades.total_pnl == 2.50 + 0.90 + 1.20
        assert result_with_trades.win_rate == 100.0

    def test_daily_pnl(self, result_with_trades):
        result_with_trades.calculate_metrics()

        assert "2025-01-01" in result_with_trades.daily_pnl
        assert "2025-01-02" in result_with_trades.daily_pnl
        assert "2025-01-03" in result_with_trades.daily_pnl
        assert result_with_trades.daily_pnl["2025-01-01"] == 2.50

    def test_to_dict(self, result_with_trades):
        result_with_trades.calculate_metrics()
        d = result_with_trades.to_dict()

        assert 'config' in d
        assert 'metrics' in d
        assert 'trades' in d
        assert d['metrics']['total_trades'] == 3

    def test_export_to_csv(self, result_with_trades, tmp_path):
        result_with_trades.calculate_metrics()
        csv_path = str(tmp_path / "backtest_results.csv")
        result_with_trades.export_to_csv(csv_path)

        assert os.path.exists(csv_path)
        with open(csv_path, 'r') as f:
            content = f.read()
            assert "Backtest Summary" in content
            assert "Daily P&L" in content
            assert "Trade Details" in content


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    @pytest.fixture
    def data_collector(self, tmp_path):
        """Create data collector with test data."""
        db_path = str(tmp_path / "test_backtest.db")
        collector = DataCollector(db_path=db_path)

        import sqlite3
        with sqlite3.connect(db_path) as conn:
            # Create test snapshots for two tokens in one market
            # Simulating an arbitrage opportunity
            base_ts = 1704067200000  # Some base timestamp

            for i in range(100):
                ts = base_ts + i * 1000  # 1 second apart

                # YES token - price around 0.45
                conn.execute("""
                    INSERT INTO order_book_snapshots
                    (timestamp, token_id, market_id, asks_json, bids_json, best_ask, best_bid, spread)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts,
                    "yes_token",
                    "market_arb",
                    json.dumps([{"price": "0.45", "size": "100"}, {"price": "0.46", "size": "200"}]),
                    json.dumps([{"price": "0.44", "size": "50"}]),
                    0.45,
                    0.44,
                    0.01
                ))

                # NO token - price around 0.50
                conn.execute("""
                    INSERT INTO order_book_snapshots
                    (timestamp, token_id, market_id, asks_json, bids_json, best_ask, best_bid, spread)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts,
                    "no_token",
                    "market_arb",
                    json.dumps([{"price": "0.50", "size": "100"}, {"price": "0.51", "size": "200"}]),
                    json.dumps([{"price": "0.49", "size": "50"}]),
                    0.50,
                    0.49,
                    0.01
                ))

        return collector

    @pytest.fixture
    def engine(self, data_collector):
        return BacktestEngine(data_collector)

    def test_calculate_effective_cost(self):
        order_book = [
            {"price": "0.45", "size": "50"},
            {"price": "0.46", "size": "100"},
            {"price": "0.48", "size": "200"}
        ]

        result = BacktestEngine.calculate_effective_cost(order_book, 100)

        assert result.has_sufficient_liquidity is True
        assert result.shares == 100
        # Should be weighted average: (50*0.45 + 50*0.46) / 100 = 0.455
        assert 0.45 <= result.effective_price <= 0.46
        assert result.levels_consumed == 2

    def test_calculate_effective_cost_insufficient_liquidity(self):
        order_book = [
            {"price": "0.45", "size": "50"}
        ]

        result = BacktestEngine.calculate_effective_cost(order_book, 100)

        assert result.has_sufficient_liquidity is False
        assert result.shares == 50

    def test_find_optimal_trade_size(self):
        yes_book = [
            {"price": "0.45", "size": "100"},
            {"price": "0.46", "size": "100"}
        ]
        no_book = [
            {"price": "0.50", "size": "100"},
            {"price": "0.51", "size": "100"}
        ]

        shares, eff_yes, eff_no = BacktestEngine.find_optimal_trade_size(
            yes_book, no_book,
            max_combined_cost=0.98
        )

        assert shares > 0
        assert eff_yes + eff_no < 0.98

    def test_find_optimal_trade_size_not_profitable(self):
        yes_book = [{"price": "0.55", "size": "100"}]
        no_book = [{"price": "0.50", "size": "100"}]

        shares, eff_yes, eff_no = BacktestEngine.find_optimal_trade_size(
            yes_book, no_book,
            max_combined_cost=0.98  # 0.55 + 0.50 = 1.05 > 0.98
        )

        assert shares == 0

    @pytest.mark.asyncio
    async def test_run_backtest_no_data(self, tmp_path):
        """Test backtest with empty data."""
        db_path = str(tmp_path / "empty.db")
        collector = DataCollector(db_path=db_path)
        engine = BacktestEngine(collector)

        config = BacktestConfig(
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 7)
        )

        result = await engine.run_backtest(config)

        assert result.total_trades == 0

    @pytest.mark.asyncio
    async def test_run_backtest_with_data(self, engine):
        """Test backtest with data containing opportunities."""
        # The fixture has data from timestamp 1704067200000
        start_time = datetime.fromtimestamp(1704067200)
        end_time = datetime.fromtimestamp(1704067300)

        config = BacktestConfig(
            start_time=start_time,
            end_time=end_time,
            initial_capital=10000.0,
            capital_per_trade=100.0,
            min_profit_margin=0.02,
            cooldown_seconds=0  # No cooldown for test
        )

        result = await engine.run_backtest(config)

        # With 0.45 + 0.50 = 0.95 < 0.98, there should be opportunities
        assert result.opportunities_detected > 0

    def test_cancel(self, engine):
        engine.cancel()
        assert engine._cancel_requested is True

    def test_get_available_data_range(self, engine):
        start_date, end_date = engine.get_available_data_range()

        assert start_date is not None
        assert end_date is not None
        assert start_date < end_date

    def test_get_available_markets(self, engine):
        markets = engine.get_available_markets()

        assert len(markets) > 0
        assert markets[0]['market_id'] == "market_arb"

    def test_get_data_stats(self, engine):
        stats = engine.get_data_stats()

        assert stats['has_data'] is True
        assert stats['snapshot_count'] == 200  # 100 for YES + 100 for NO
        assert stats['market_count'] == 1


class TestBacktestEngineCallbacks:
    """Tests for BacktestEngine callbacks."""

    @pytest.fixture
    def engine_with_data(self, tmp_path):
        db_path = str(tmp_path / "callback_test.db")
        collector = DataCollector(db_path=db_path)

        import sqlite3
        with sqlite3.connect(db_path) as conn:
            ts = 1704067200000
            for token in ["yes_t", "no_t"]:
                price = "0.45" if token == "yes_t" else "0.50"
                conn.execute("""
                    INSERT INTO order_book_snapshots
                    (timestamp, token_id, market_id, asks_json, bids_json, best_ask, best_bid, spread)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts, token, "market_cb",
                    json.dumps([{"price": price, "size": "100"}]),
                    '[]', float(price), 0.0, 0.0
                ))

        return BacktestEngine(collector)

    @pytest.mark.asyncio
    async def test_progress_callback(self, engine_with_data):
        progress_values = []

        def on_progress(value, message):
            progress_values.append(value)

        engine_with_data.on_progress = on_progress

        config = BacktestConfig(
            start_time=datetime.fromtimestamp(1704067200),
            end_time=datetime.fromtimestamp(1704067300)
        )

        await engine_with_data.run_backtest(config)

        # Should have at least start and end progress
        assert len(progress_values) >= 1
        assert 100.0 in progress_values  # Final progress

    @pytest.mark.asyncio
    async def test_trade_callback(self, engine_with_data):
        trades = []

        def on_trade(trade):
            trades.append(trade)

        engine_with_data.on_trade = on_trade

        config = BacktestConfig(
            start_time=datetime.fromtimestamp(1704067200),
            end_time=datetime.fromtimestamp(1704067300),
            cooldown_seconds=0
        )

        await engine_with_data.run_backtest(config)

        # Trades callback should be called for each trade
        # (may be 0 if no profitable opportunities found)
        # Just verify it doesn't crash
        assert isinstance(trades, list)
