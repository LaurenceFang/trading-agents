from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state_writer import StateWriter

from core.venue_order_spec import VenueOrderSpec, VenueOrderStatus, VenuePosition, VenueReceipt
from venue.base import MarketStatus as BaseMarketStatus
from venue.ctp_callback_handler import CtpCallbackHandler
from venue.ctp_gateway import CtpGatewayWrapper

logger = logging.getLogger(__name__)


@dataclass
class VenueAccountInfo:
    """Account balance and margin information from CTP."""

    account_id: str
    broker_id: str
    balance: Decimal           # 动态权益
    available: Decimal         # 可用资金
    margin: Decimal            # 占用保证金
    frozen_margin: Decimal     # 冻结保证金
    frozen_cash: Decimal       # 冻结资金（手续费等）
    profit_loss: Decimal       # 盯市盈亏
    commission: Decimal        # 当日手续费
    updated_at: datetime


class CTPAdapter:
    """CTP adapter using vnpy_ctp to connect to SimNow trading environment."""

    def __init__(self, config: dict, state_writer: StateWriter | None = None) -> None:
        """Initialize CTP adapter with configuration.

        Args:
            config: Dictionary containing CTP connection parameters.
            state_writer: Optional StateWriter for persisting order/position state.
        """
        self._config = config
        self._state_writer = state_writer

        self._gateway = CtpGatewayWrapper(config)

        # Create callback handler immediately (no gateway interaction needed)
        self._callback_handler = CtpCallbackHandler(
            on_order_update=self._on_order_update,
            on_trade_update=self._on_trade_update,
        )

        self._order_futures: dict[str, asyncio.Future[VenueReceipt]] = {}
        self._submitted_orders: set[str] = set()

        self.submit_count: int = 0
        self.cancel_count: int = 0
        # Note: _setup_callbacks() is NOT called here.
        # Gateway callbacks are registered in connect() after the
        # underlying CtpGateway object is initialized.

    def _setup_callbacks(self) -> None:
        """Register CTP callback handlers on the live gateway.

        Must be called AFTER connect() because get_gateway() requires
        the underlying CtpGateway to be initialized.
        """
        gateway = self._gateway.get_gateway()
        if hasattr(gateway, "on_rtn_order"):
            gateway.on_rtn_order = self._callback_handler.on_rtn_order
        if hasattr(gateway, "on_rtn_trade"):
            gateway.on_rtn_trade = self._callback_handler.on_rtn_trade
        if hasattr(gateway, "on_err_rtn_order_insert"):
            gateway.on_err_rtn_order_insert = self._callback_handler.on_err_rtn_order_insert
        if hasattr(gateway, "on_err_rtn_order_action"):
            gateway.on_err_rtn_order_action = self._callback_handler.on_err_rtn_order_action

    async def connect(self) -> None:
        """Connect to CTP gateway and register callbacks."""
        await self._gateway.connect()
        self._setup_callbacks()

    async def disconnect(self) -> None:
        """Disconnect from CTP gateway."""
        await self._gateway.disconnect()

    async def submit_order(self, spec: VenueOrderSpec) -> VenueReceipt:
        """Submit an order to CTP.

        Args:
            spec: VenueOrderSpec with order details.

        Returns:
            VenueReceipt with order acknowledgment.

        Raises:
            ConnectionError: If gateway is not connected.
            TimeoutError: If order submission times out after 10 seconds.
        """
        if not self._gateway.is_connected:
            raise ConnectionError("CTP gateway not connected")

        if spec.client_order_id in self._submitted_orders:
            now = datetime.now(timezone.utc)
            receipt = VenueReceipt(
                client_order_id=spec.client_order_id,
                exchange_order_id="",
                status="REJECTED",
                raw_response={"error": "Duplicate client_order_id"},
                timestamp=now,
            )
            return receipt

        self.submit_count += 1
        self._submitted_orders.add(spec.client_order_id)

        future: asyncio.Future[VenueReceipt] = asyncio.Future()
        self._order_futures[spec.client_order_id] = future

        try:
            gateway = self._gateway.get_gateway()

            req = {
                "InstrumentID": spec.symbol,
                "OrderRef": spec.client_order_id,
                "Direction": CtpCallbackHandler.map_side(spec.side),
                "OffsetFlag": CtpCallbackHandler.map_offset_flag(spec.reduce_only),
                "HedgeFlag": CtpCallbackHandler.map_hedge_flag(spec.hedge_flag),
                "VolumeTotalOriginal": int(spec.quantity),
            }

            if spec.order_type == "LIMIT" and spec.price is not None:
                req["LimitPrice"] = float(spec.price)
                req["OrderPriceType"] = "2"
            elif spec.order_type == "MARKET":
                req["OrderPriceType"] = "1"
            elif spec.order_type == "STOP":
                req["OrderPriceType"] = "3"
                if spec.price is not None:
                    req["StopPrice"] = float(spec.price)

            if spec.time_in_force == "IOC":
                req["TimeCondition"] = "3"
            elif spec.time_in_force == "FOK":
                req["TimeCondition"] = "4"
            else:
                req["TimeCondition"] = "1"

            gateway.send_order(req, reqid=1)

            try:
                receipt = await asyncio.wait_for(future, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error(f"Order submission timeout: {spec.client_order_id}")
                raise TimeoutError(f"Order submission timeout: {spec.client_order_id}")

            if self._state_writer:
                from core.state_schema import OrderState

                order_state = OrderState(
                    order_id=receipt.exchange_order_id or spec.client_order_id,
                    client_order_id=spec.client_order_id,
                    symbol=spec.symbol,
                    venue="CTP",
                    side=spec.side,
                    quantity=str(spec.quantity),
                    price=str(spec.price) if spec.price else None,
                    status=receipt.status,
                    strategy_id="",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    updated_at=receipt.timestamp.isoformat(),
                    filled_quantity="0",
                    filled_price="0",
                )
                await self._state_writer.write_order(order_state)

            return receipt

        except Exception as e:
            logger.error(f"Error submitting order: {e}", exc_info=True)
            raise
        finally:
            self._order_futures.pop(spec.client_order_id, None)

    async def cancel_order(self, client_order_id: str) -> VenueReceipt:
        """Cancel an order by client_order_id.

        Args:
            client_order_id: Client-side order identifier.

        Returns:
            VenueReceipt with cancel acknowledgment.

        Raises:
            ConnectionError: If gateway is not connected.
            TimeoutError: If cancel request times out after 10 seconds.
        """
        if not self._gateway.is_connected:
            raise ConnectionError("CTP gateway not connected")

        self.cancel_count += 1

        future: asyncio.Future[VenueReceipt] = asyncio.Future()
        self._order_futures[client_order_id] = future

        try:
            gateway = self._gateway.get_gateway()

            req = {
                "OrderRef": client_order_id,
                "ActionFlag": "0",
            }

            gateway.cancel_order(req, reqid=2)

            try:
                receipt = await asyncio.wait_for(future, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error(f"Cancel order timeout: {client_order_id}")
                raise TimeoutError(f"Cancel order timeout: {client_order_id}")

            return receipt

        except Exception as e:
            logger.error(f"Error canceling order: {e}", exc_info=True)
            raise
        finally:
            self._order_futures.pop(client_order_id, None)

    async def query_order(self, client_order_id: str) -> VenueOrderStatus:
        """Query order status from CTP.

        Args:
            client_order_id: Client-side order identifier.

        Returns:
            VenueOrderStatus with current order state.
        """
        if not self._gateway.is_connected:
            raise ConnectionError("CTP gateway not connected")

        gateway = self._gateway.get_gateway()

        req = {
            "OrderRef": client_order_id,
        }

        query_future: asyncio.Future[dict] = asyncio.Future()

        def on_rsp_qry_order(data: dict, error: dict | None, reqid: int, last: bool) -> None:
            if not query_future.done():
                if error and error.get("ErrorID", 0) != 0:
                    query_future.set_exception(
                        Exception(f"Query order failed: {error.get('ErrorMsg', 'Unknown error')}")
                    )
                else:
                    query_future.set_result(data or {})

        if hasattr(gateway, "on_rsp_qry_order"):
            original_handler = gateway.on_rsp_qry_order
            gateway.on_rsp_qry_order = on_rsp_qry_order

        try:
            gateway.query_order(req, reqid=3)

            try:
                data = await asyncio.wait_for(query_future, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error(f"Query order timeout: {client_order_id}")
                raise TimeoutError(f"Query order timeout: {client_order_id}")

            order_sys_id = data.get("OrderSysID", "")
            status = data.get("OrderStatus", "")
            volume_traded = data.get("VolumeTraded", "0")
            avg_price = data.get("AvgPrice", "0")

            ctp_status = self._callback_handler._map_ctp_status(status)

            from core.venue_order_spec import VenueOrderStatus

            return VenueOrderStatus(
                client_order_id=client_order_id,
                exchange_order_id=order_sys_id,
                status=ctp_status,
                filled_quantity=Decimal(str(volume_traded)),
                filled_price=Decimal(str(avg_price)) if avg_price else Decimal("0"),
                updated_at=datetime.now(timezone.utc),
            )

        finally:
            if hasattr(gateway, "on_rsp_qry_order") and 'original_handler' in locals():
                gateway.on_rsp_qry_order = original_handler

    async def query_positions(self) -> list[VenuePosition]:
        """Query current positions from CTP.

        Returns:
            List of VenuePosition objects.
        """
        if not self._gateway.is_connected:
            raise ConnectionError("CTP gateway not connected")

        gateway = self._gateway.get_gateway()

        req = {}

        query_future: asyncio.Future[list[dict]] = asyncio.Future()
        positions_data: list[dict] = []

        def on_rsp_qry_investor_position(data: dict, error: dict | None, reqid: int, last: bool) -> None:
            if data:
                positions_data.append(data)
            if last and not query_future.done():
                if error and error.get("ErrorID", 0) != 0:
                    query_future.set_exception(
                        Exception(f"Query positions failed: {error.get('ErrorMsg', 'Unknown error')}")
                    )
                else:
                    query_future.set_result(positions_data.copy())

        if hasattr(gateway, "on_rsp_qry_investor_position"):
            original_handler = gateway.on_rsp_qry_investor_position
            gateway.on_rsp_qry_investor_position = on_rsp_qry_investor_position

        try:
            gateway.query_position(req, reqid=4)

            try:
                data_list = await asyncio.wait_for(query_future, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("Query positions timeout")
                raise TimeoutError("Query positions timeout")

            positions: list[VenuePosition] = []

            for data in data_list:
                symbol = data.get("InstrumentID", "")
                if not symbol:
                    continue

                long_pos = Decimal(str(data.get("Position", "0")))
                short_pos = Decimal(str(data.get("YdPosition", "0")))

                net_long = long_pos - short_pos
                net_short = short_pos - long_pos

                if net_long > 0:
                    entry_price = Decimal(str(data.get("OpenPrice", "0")))
                    positions.append(
                        VenuePosition(
                            symbol=symbol,
                            venue="CTP",
                            side="LONG",
                            quantity=net_long,
                            entry_price=entry_price,
                            unrealized_pnl=Decimal("0"),
                            updated_at=datetime.now(timezone.utc),
                        )
                    )

                if net_short > 0:
                    entry_price = Decimal(str(data.get("OpenPrice", "0")))
                    positions.append(
                        VenuePosition(
                            symbol=symbol,
                            venue="CTP",
                            side="SHORT",
                            quantity=net_short,
                            entry_price=entry_price,
                            unrealized_pnl=Decimal("0"),
                            updated_at=datetime.now(timezone.utc),
                        )
                    )

            return positions

        finally:
            if hasattr(gateway, "on_rsp_qry_investor_position") and 'original_handler' in locals():
                gateway.on_rsp_qry_investor_position = original_handler

    async def query_account(self) -> VenueAccountInfo:
        """Query account balance and margin info from CTP (ReqQryTradingAccount).

        Returns:
            VenueAccountInfo with balance, available funds, margin, and P&L.

        Raises:
            ConnectionError: If gateway is not connected.
            TimeoutError: If query does not complete within 10 seconds.
            Exception: If CTP returns an error response.
        """
        if not self._gateway.is_connected:
            raise ConnectionError("CTP gateway not connected")

        gateway = self._gateway.get_gateway()

        query_future: asyncio.Future[dict] = asyncio.Future()

        def on_rsp_qry_trading_account(
            data: dict, error: dict | None, reqid: int, last: bool
        ) -> None:
            if not query_future.done():
                if error and error.get("ErrorID", 0) != 0:
                    from venue.ctp_error_codes import format_ctp_error
                    error_id = error.get("ErrorID", 99)
                    raw_msg = error.get("ErrorMsg", "")
                    msg = format_ctp_error(error_id, raw_msg)
                    query_future.set_exception(Exception(f"Query account failed: {msg}"))
                else:
                    query_future.set_result(data or {})

        original_handler = None
        if hasattr(gateway, "on_rsp_qry_trading_account"):
            original_handler = gateway.on_rsp_qry_trading_account
            gateway.on_rsp_qry_trading_account = on_rsp_qry_trading_account

        try:
            req = {
                "BrokerID": self._config.get("broker_id", ""),
                "InvestorID": self._config.get("user_id") or os.getenv("CTP_USER_ID", ""),
                "CurrencyID": "CNY",
            }
            gateway.query_account(req, reqid=5)

            try:
                data = await asyncio.wait_for(query_future, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("Query account timeout")
                raise TimeoutError("Query account timeout")

            account_id = data.get("AccountID", "")
            broker_id = data.get("BrokerID", "")

            def to_decimal(val: object) -> Decimal:
                try:
                    return Decimal(str(val)) if val not in (None, "", 0) else Decimal("0")
                except Exception:
                    return Decimal("0")

            info = VenueAccountInfo(
                account_id=account_id,
                broker_id=broker_id,
                balance=to_decimal(data.get("Balance")),
                available=to_decimal(data.get("Available")),
                margin=to_decimal(data.get("CurrMargin")),
                frozen_margin=to_decimal(data.get("FrozenMargin")),
                frozen_cash=to_decimal(data.get("FrozenCash")),
                profit_loss=to_decimal(data.get("PositionProfit")),
                commission=to_decimal(data.get("Commission")),
                updated_at=datetime.now(timezone.utc),
            )

            logger.info(
                "Account query successful",
                extra={
                    "account_id": account_id,
                    "balance": str(info.balance),
                    "available": str(info.available),
                    "margin": str(info.margin),
                },
            )

            return info

        finally:
            if original_handler is not None and hasattr(gateway, "on_rsp_qry_trading_account"):
                gateway.on_rsp_qry_trading_account = original_handler

    async def get_market_status(self, symbol: str) -> BaseMarketStatus:
        """Get market status for a symbol.

        Args:
            symbol: Unified symbol.

        Returns:
            MarketStatus with tradability information.
        """
        is_connected = self._gateway.is_connected

        return BaseMarketStatus(
            symbol=symbol,
            can_market_order=is_connected,
            can_limit_order=is_connected,
            is_halted=not is_connected,
            best_bid=None,
            best_ask=None,
            updated_at=datetime.now(timezone.utc),
        )

    def _on_order_update(self, receipt: VenueReceipt) -> None:
        """Handle order status update from CTP callback.

        Args:
            receipt: VenueReceipt with updated order status.
        """
        future = self._order_futures.get(receipt.client_order_id)
        if future and not future.done():
            future.set_result(receipt)

        if self._state_writer:
            from core.state_schema import OrderState

            order_state = OrderState(
                order_id=receipt.exchange_order_id or receipt.client_order_id,
                client_order_id=receipt.client_order_id,
                symbol="",
                venue="CTP",
                side="",
                quantity="0",
                price=None,
                status=receipt.status,
                strategy_id="",
                created_at="",
                updated_at=receipt.timestamp.isoformat(),
                filled_quantity="0",
                filled_price="0",
            )
            asyncio.create_task(self._state_writer.write_order(order_state))

    def _on_trade_update(self, status: dict) -> None:
        """Handle trade execution update from CTP callback.

        Args:
            status: Dictionary with trade details.
        """
        logger.info(f"Trade update: {status}")
