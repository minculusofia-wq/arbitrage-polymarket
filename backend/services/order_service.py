"""
Order execution service.
"""
import asyncio
import time
from typing import Optional, Tuple
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from backend.config import Config
from backend.logger import logger
from backend.models.trade import Trade, Position, TradeStatus

# Maximum time window for trade execution
MAX_EXECUTION_WINDOW = 20  # seconds


class OrderService:
    """
    Service for executing trades on Polymarket.
    """

    def __init__(self, client, config: Config):
        self.client = client
        self.config = config
        self.positions: list = []

    async def execute_arbitrage(self, trade: Trade) -> bool:
        """
        Execute an arbitrage trade by buying both YES and NO tokens.
        Returns True if successful, False otherwise.
        """
        start_time = time.time()
        logger.info(f"Executing Trade for {trade.market_id}")

        trade.status = TradeStatus.EXECUTING

        # Calculate shares
        capital = self.config.CAPITAL_PER_TRADE
        shares = capital / trade.cost
        shares = round(shares, 2)

        if shares <= 0:
            trade.status = TradeStatus.FAILED
            trade.error = "Invalid share amount"
            return False

        # Check execution window
        if time.time() - start_time > MAX_EXECUTION_WINDOW:
            logger.error("Execution window exceeded. Aborting.")
            trade.status = TradeStatus.FAILED
            trade.error = "Execution window exceeded"
            return False

        logger.info(f"Buying {shares} shares of YES and NO.")

        loop = asyncio.get_running_loop()

        # Execute both orders in parallel
        t1 = loop.run_in_executor(
            None,
            lambda: self._place_order(trade.yes_token_id, shares, trade.yes_price)
        )
        t2 = loop.run_in_executor(
            None,
            lambda: self._place_order(trade.no_token_id, shares, trade.no_price)
        )

        results = await asyncio.gather(t1, t2, return_exceptions=True)

        success = all(not isinstance(r, Exception) and r is not None for r in results)

        if success:
            logger.info("Trade Executed Successfully.")
            trade.status = TradeStatus.EXECUTED
            position = Position(
                market_id=trade.market_id,
                size=shares,
                entry_cost=trade.cost,
                timestamp=time.time()
            )
            self.positions.append(position)
            return True
        else:
            logger.error(f"Trade Partial Failure or Error: {results}")
            logger.critical(
                f"PARTIAL FILL RISK for {trade.market_id}: "
                "One or both orders may have failed. Check positions manually!"
            )
            trade.status = TradeStatus.PARTIAL
            trade.error = str(results)
            return False

    def _place_order(self, token_id: str, amount: float, price: float) -> Optional[dict]:
        """
        Place a single Fill-or-Kill order.
        """
        if self.client is None:
            raise RuntimeError("Client not initialized - cannot place order")

        try:
            resp = self.client.create_and_post_order(
                OrderArgs(
                    price=price,
                    size=amount,
                    side=BUY,
                    token_id=token_id,
                    order_type=OrderType.FOK
                )
            )
            return resp
        except Exception as e:
            logger.error(f"Order Failed: {e}")
            raise e

    def get_positions(self) -> list:
        """Get all open positions."""
        return self.positions
