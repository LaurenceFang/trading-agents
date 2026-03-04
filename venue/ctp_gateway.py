from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vnpy_ctp.gateway import CtpGateway

logger = logging.getLogger(__name__)


class CtpGatewayWrapper:
    """Wrapper for vnpy_ctp CtpGateway managing connection lifecycle."""

    def __init__(self, config: dict) -> None:
        """Initialize CTP gateway with configuration.

        Args:
            config: Dictionary containing:
                - broker_id: CTP broker ID (e.g., "9999")
                - user_id: CTP user ID (from env var CTP_USER_ID)
                - password: CTP password (from env var CTP_PASSWORD)
                - app_id: CTP application ID
                - auth_code: CTP auth code (from env var CTP_AUTH_CODE)
                - front_addr: CTP front address (e.g., "tcp://180.168.146.187:10130")
        """
        self.broker_id: str = config["broker_id"]
        self.user_id: str = config.get("user_id") or os.getenv("CTP_USER_ID", "")
        self.password: str = config.get("password") or os.getenv("CTP_PASSWORD", "")
        self.app_id: str = config["app_id"]
        self.auth_code: str = config.get("auth_code") or os.getenv("CTP_AUTH_CODE", "")
        self.front_addr: str = config["front_addr"]

        self._gateway: CtpGateway | None = None
        self._connected: bool = False
        self._login_event: asyncio.Event = asyncio.Event()
        self._reconnect_task: asyncio.Task | None = None
        self._reconnect_interval: float = 1.0
        self._max_reconnect_interval: float = 60.0
        self._should_reconnect: bool = True

    @property
    def is_connected(self) -> bool:
        """Return whether gateway is connected and authenticated."""
        return self._connected

    async def connect(self) -> None:
        """Connect to CTP front, authenticate, and login.

        Raises:
            TimeoutError: If login does not complete within 30 seconds.
        """
        if self._connected:
            logger.info("CTP gateway already connected")
            return

        logger.info(
            "Connecting to CTP gateway",
            extra={
                "broker_id": self.broker_id,
                "user_id": self.user_id,
                "front_addr": self.front_addr,
            },
        )

        self._login_event.clear()
        self._should_reconnect = True

        try:
            from vnpy_ctp.gateway import CtpGateway

            self._gateway = CtpGateway()

            self._gateway.on_front_connected = self._on_front_connected
            self._gateway.on_front_disconnected = self._on_front_disconnected
            self._gateway.on_rsp_authenticate = self._on_rsp_authenticate
            self._gateway.on_rsp_user_login = self._on_rsp_user_login

            self._gateway.connect(
                {
                    "td_address": self.front_addr,
                    "brokerid": self.broker_id,
                    "userid": self.user_id,
                    "password": self.password,
                    "appid": self.app_id,
                    "auth_code": self.auth_code,
                }
            )

            try:
                await asyncio.wait_for(self._login_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.error("CTP login timeout after 30 seconds")
                raise TimeoutError("CTP login timeout")

            self._connected = True
            logger.info("CTP gateway connected and authenticated successfully")

            if self._reconnect_task is None or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())

        except Exception as e:
            logger.error(f"Failed to connect to CTP gateway: {e}", exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Disconnect from CTP gateway and stop reconnect loop."""
        self._should_reconnect = False

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._gateway:
            try:
                self._gateway.close()
            except Exception as e:
                logger.warning(f"Error closing CTP gateway: {e}")

        self._connected = False
        self._login_event.clear()
        logger.info("CTP gateway disconnected")

    def _on_front_connected(self) -> None:
        """Handle OnFrontConnected callback."""
        logger.info("CTP front connected")

        if self._gateway:
            req = {
                "BrokerID": self.broker_id,
                "UserID": self.user_id,
                "AuthCode": self.auth_code,
                "AppID": self.app_id,
            }
            self._gateway.authenticate(req, reqid=1)

    def _on_front_disconnected(self, reason: int) -> None:
        """Handle OnFrontDisconnected callback."""
        logger.warning(f"CTP front disconnected, reason: {reason}")
        self._connected = False
        self._login_event.clear()

    def _on_rsp_authenticate(
        self, data: dict, error: dict | None, reqid: int, last: bool
    ) -> None:
        """Handle OnRspAuthenticate callback."""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(
                f"CTP authentication failed: {error.get('ErrorMsg', 'Unknown error')}"
            )
            return

        logger.info("CTP authentication successful, proceeding to login")

        if self._gateway:
            req = {
                "BrokerID": self.broker_id,
                "UserID": self.user_id,
                "Password": self.password,
            }
            self._gateway.login(req, reqid=2)

    def _on_rsp_user_login(
        self, data: dict, error: dict | None, reqid: int, last: bool
    ) -> None:
        """Handle OnRspUserLogin callback."""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(
                f"CTP login failed: {error.get('ErrorMsg', 'Unknown error')}"
            )
            return

        logger.info("CTP login successful")
        self._login_event.set()

    async def _reconnect_loop(self) -> None:
        """Background task to handle automatic reconnection with exponential backoff."""
        while self._should_reconnect:
            await asyncio.sleep(self._reconnect_interval)

            if self._connected or not self._should_reconnect:
                continue

            logger.info(
                f"Attempting to reconnect to CTP (interval: {self._reconnect_interval:.1f}s)"
            )

            try:
                self._login_event.clear()

                if self._gateway:
                    self._gateway.connect(
                        {
                            "td_address": self.front_addr,
                            "brokerid": self.broker_id,
                            "userid": self.user_id,
                            "password": self.password,
                            "appid": self.app_id,
                            "auth_code": self.auth_code,
                        }
                    )

                    try:
                        await asyncio.wait_for(self._login_event.wait(), timeout=30.0)
                        self._connected = True
                        self._reconnect_interval = 1.0
                        logger.info("CTP reconnection successful")
                    except asyncio.TimeoutError:
                        logger.warning("CTP reconnection timeout")
                        self._reconnect_interval = min(
                            self._reconnect_interval * 2, self._max_reconnect_interval
                        )

            except Exception as e:
                logger.error(f"CTP reconnection error: {e}", exc_info=True)
                self._reconnect_interval = min(
                    self._reconnect_interval * 2, self._max_reconnect_interval
                )

    def get_gateway(self) -> CtpGateway:
        """Get the underlying vnpy_ctp CtpGateway instance.

        Raises:
            RuntimeError: If gateway is not initialized.
        """
        if self._gateway is None:
            raise RuntimeError("CTP gateway not initialized")
        return self._gateway
