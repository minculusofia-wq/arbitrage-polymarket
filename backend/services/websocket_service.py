"""
WebSocket connection service with reconnection support.
"""
import asyncio
import json
from typing import Callable, List, Optional
import websockets
from backend.config import Config
from backend.logger import logger


class WebSocketService:
    """
    Service for managing WebSocket connections to Polymarket.
    Includes automatic reconnection with exponential backoff.
    """

    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.on_message: Optional[Callable[[dict], None]] = None

    async def connect_and_listen(self, token_ids: List[str]) -> None:
        """
        Connect to WebSocket and listen for messages.
        """
        if not token_ids:
            logger.warning("No tokens to subscribe to.")
            return

        async with websockets.connect(self.config.CLOB_WS_URL) as ws:
            self.ws = ws
            logger.info("Connected to Polymarket WebSocket.")

            # Subscribe to level2 feeds for all tokens
            for tid in token_ids:
                msg = {"type": "subscribe", "channel": "level2", "token_id": tid}
                await ws.send(json.dumps(msg))

            logger.info(f"Subscribed to price feeds for {len(token_ids)} tokens.")

            while self.running:
                try:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if self.on_message:
                        await self.on_message(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.error("WebSocket connection closed.")
                    break
                except Exception as e:
                    logger.error(f"WS Error: {e}")
                    await asyncio.sleep(1)

    async def connect_with_retry(self, token_ids: List[str], max_retries: int = 5) -> None:
        """
        Connect with automatic reconnection using exponential backoff.
        """
        self.running = True
        attempt = 0

        while self.running and attempt < max_retries:
            try:
                await self.connect_and_listen(token_ids)
                if not self.running:
                    break
                # If we get here, connection was closed - retry
                attempt += 1
                wait_time = min(2 ** attempt, 60)  # Cap at 60 seconds
                logger.warning(f"Reconnecting in {wait_time}s... (attempt {attempt}/{max_retries})")
                await asyncio.sleep(wait_time)
            except Exception as e:
                logger.error(f"Connection error: {e}")
                attempt += 1
                wait_time = min(2 ** attempt, 60)
                logger.warning(f"Reconnecting in {wait_time}s... (attempt {attempt}/{max_retries})")
                await asyncio.sleep(wait_time)

        if attempt >= max_retries:
            logger.error("Max reconnection attempts reached. Stopping.")

    def stop(self) -> None:
        """Stop the WebSocket connection."""
        self.running = False
        logger.info("WebSocket service stopping...")
