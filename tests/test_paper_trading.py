"""Tests for Paper Trading Service."""

import pytest
import asyncio
import tempfile
import os
from datetime import datetime
from backend.services.paper_trading import (
    PaperTradeExecutor, PaperTrade, ITradeExecutor
)


class TestPaperTrade:
    """Tests for PaperTrade dataclass."""

    def test_paper_trade_creation(self):
        trade = PaperTrade(
            id=1,
            platform="polymarket",
            market_id="market_123",
            yes_token="yes_token",
            no_token="no_token",
            shares=10.0,
            yes_price=0.45,
            no_price=0.50,
            entry_cost=9.50,
            expected_pnl=0.50,
            roi=5.26,
            timestamp=datetime.now()
        )
        assert trade.id == 1
        assert trade.market_id == "market_123"
        assert trade.shares == 10.0
        assert trade.platform == "polymarket"

    def test_paper_trade_to_dict(self):
        trade = PaperTrade(
            id=1,
            platform="kalshi",
            market_id="market_123",
            yes_token="yes",
            no_token="no",
            shares=10.0,
            yes_price=0.45,
            no_price=0.50,
            entry_cost=9.50,
            expected_pnl=0.50,
            roi=5.26,
            timestamp=datetime(2025, 1, 15, 10, 30, 0)
        )
        d = trade.to_dict()
        assert d['id'] == 1
        assert d['market_id'] == "market_123"
        assert d['shares'] == 10.0
        assert d['platform'] == "kalshi"
        assert 'timestamp' in d


class TestPaperTradeExecutor:
    """Tests for PaperTradeExecutor."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with temp database."""
        db_path = str(tmp_path / "test_paper_trades.db")
        return PaperTradeExecutor(
            db_path=db_path,
            initial_balance=10000.0,
            fill_probability=1.0,  # Always fill for tests
            slippage_bps=0.0  # No slippage for tests
        )

    def test_get_mode(self, executor):
        assert executor.get_mode() == "PAPER"

    def test_get_balance(self, executor):
        assert executor.get_balance() == 10000.0

    @pytest.mark.asyncio
    async def test_execute_trade_success(self, executor):
        result = await executor.execute_trade(
            market_id="market_123",
            yes_token="yes_token",
            no_token="no_token",
            shares=10.0,
            price_yes=0.45,
            price_no=0.50
        )

        assert result['success'] is True
        assert result['mode'] == "PAPER"
        assert 'trade' in result
        assert result['virtual_balance'] < 10000.0

    @pytest.mark.asyncio
    async def test_execute_trade_insufficient_balance(self, tmp_path):
        db_path = str(tmp_path / "test_paper_trades2.db")
        executor = PaperTradeExecutor(
            db_path=db_path,
            initial_balance=5.0,  # Very low balance
            fill_probability=1.0
        )

        result = await executor.execute_trade(
            market_id="market_123",
            yes_token="yes_token",
            no_token="no_token",
            shares=100.0,  # Would cost ~95 USDC
            price_yes=0.45,
            price_no=0.50
        )

        assert result['success'] is False
        assert result['reason'] == "INSUFFICIENT_VIRTUAL_BALANCE"

    @pytest.mark.asyncio
    async def test_execute_trade_updates_balance(self, executor):
        initial = executor.get_balance()

        await executor.execute_trade(
            market_id="market_123",
            yes_token="yes",
            no_token="no",
            shares=10.0,
            price_yes=0.45,
            price_no=0.50
        )

        # Balance should decrease by entry cost
        assert executor.get_balance() < initial

    @pytest.mark.asyncio
    async def test_execute_multiple_trades(self, executor):
        for i in range(3):
            result = await executor.execute_trade(
                market_id=f"market_{i}",
                yes_token=f"yes_{i}",
                no_token=f"no_{i}",
                shares=10.0,
                price_yes=0.45,
                price_no=0.50
            )
            assert result['success'] is True

        # Should have 3 positions
        assert len(executor.positions) == 3

    def test_get_trades_empty(self, executor):
        trades = executor.get_trades()
        assert len(trades) == 0

    @pytest.mark.asyncio
    async def test_get_trades_after_execution(self, executor):
        await executor.execute_trade(
            market_id="market_123",
            yes_token="yes",
            no_token="no",
            shares=10.0,
            price_yes=0.45,
            price_no=0.50
        )

        trades = executor.get_trades()
        assert len(trades) == 1
        assert trades[0]['market_id'] == "market_123"

    @pytest.mark.asyncio
    async def test_get_statistics(self, executor):
        await executor.execute_trade(
            market_id="market_123",
            yes_token="yes",
            no_token="no",
            shares=10.0,
            price_yes=0.45,
            price_no=0.50
        )

        stats = executor.get_statistics()
        assert stats['total_trades'] == 1
        assert stats['current_balance'] < 10000.0
        assert 'win_rate' in stats

    def test_reset(self, executor):
        executor.virtual_balance = 5000.0
        executor.reset()

        assert executor.get_balance() == 10000.0
        assert len(executor.positions) == 0

    def test_reset_with_new_balance(self, executor):
        executor.reset(initial_balance=20000.0)
        assert executor.get_balance() == 20000.0

    @pytest.mark.asyncio
    async def test_export_to_csv(self, executor, tmp_path):
        await executor.execute_trade(
            market_id="market_123",
            yes_token="yes",
            no_token="no",
            shares=10.0,
            price_yes=0.45,
            price_no=0.50
        )

        csv_path = str(tmp_path / "export.csv")
        result = executor.export_to_csv(csv_path)

        assert os.path.exists(result)
        with open(result, 'r') as f:
            content = f.read()
            assert "market_123" in content
            assert "Paper Trading Summary" in content


class TestPaperTradeExecutorFillProbability:
    """Tests for fill probability simulation."""

    @pytest.mark.asyncio
    async def test_fill_probability_zero(self, tmp_path):
        """With 0% fill probability, no trades should succeed."""
        db_path = str(tmp_path / "test_no_fill.db")
        executor = PaperTradeExecutor(
            db_path=db_path,
            initial_balance=10000.0,
            fill_probability=0.0  # Never fill
        )

        result = await executor.execute_trade(
            market_id="market_123",
            yes_token="yes",
            no_token="no",
            shares=10.0,
            price_yes=0.45,
            price_no=0.50
        )

        assert result['success'] is False
        assert result['reason'] == "SIMULATED_NO_FILL"


class TestPaperTradeExecutorSlippage:
    """Tests for slippage simulation."""

    @pytest.mark.asyncio
    async def test_slippage_increases_cost(self, tmp_path):
        """With slippage, effective cost should increase."""
        db_path = str(tmp_path / "test_slippage.db")
        executor = PaperTradeExecutor(
            db_path=db_path,
            initial_balance=10000.0,
            fill_probability=1.0,
            slippage_bps=50.0  # High slippage for visible effect
        )

        result = await executor.execute_trade(
            market_id="market_123",
            yes_token="yes",
            no_token="no",
            shares=10.0,
            price_yes=0.45,
            price_no=0.50
        )

        assert result['success'] is True
        trade = result['trade']
        # With slippage, prices should be >= original prices
        assert trade['yes_price'] >= 0.45
        assert trade['no_price'] >= 0.50
