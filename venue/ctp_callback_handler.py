from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from core.venue_order_spec import VenueReceipt

logger = logging.getLogger(__name__)


class CtpCallbackHandler:
    """Handle CTP trading callbacks and convert to internal events."""

    CTP_STATUS_MAP = {
        "0a": "SENT",
        "0b": "SENT",
        "1f": "FILLED",
        "20": "CANCELED",
        "21": "CANCELED",
        "22": "CANCELED",
        "23": "CANCELED",
        "24": "CANCELED",
        "25": "CANCELED",
        "26": "CANCELED",
        "27": "CANCELED",
        "28": "CANCELED",
        "29": "CANCELED",
        "2a": "CANCELED",
        "2b": "CANCELED",
        "2c": "CANCELED",
        "2d": "CANCELED",
        "2e": "CANCELED",
        "2f": "CANCELED",
        "30": "CANCELED",
        "31": "CANCELED",
        "32": "CANCELED",
        "33": "CANCELED",
        "34": "CANCELED",
        "35": "CANCELED",
        "36": "CANCELED",
        "37": "CANCELED",
        "38": "CANCELED",
        "39": "CANCELED",
        "3a": "CANCELED",
        "3b": "CANCELED",
        "3c": "CANCELED",
        "3d": "CANCELED",
        "3e": "CANCELED",
        "3f": "CANCELED",
        "40": "CANCELED",
        "41": "CANCELED",
        "42": "CANCELED",
        "43": "CANCELED",
        "44": "CANCELED",
        "45": "CANCELED",
        "46": "CANCELED",
        "47": "CANCELED",
        "48": "CANCELED",
        "49": "CANCELED",
        "4a": "CANCELED",
        "4b": "CANCELED",
        "4c": "CANCELED",
        "4d": "CANCELED",
        "4e": "CANCELED",
        "4f": "CANCELED",
        "50": "CANCELED",
        "51": "CANCELED",
        "52": "CANCELED",
        "53": "CANCELED",
        "54": "CANCELED",
        "55": "CANCELED",
        "56": "CANCELED",
        "57": "CANCELED",
        "58": "CANCELED",
        "59": "CANCELED",
        "5a": "CANCELED",
        "5b": "CANCELED",
        "5c": "CANCELED",
        "5d": "CANCELED",
        "5e": "CANCELED",
        "5f": "CANCELED",
        "60": "CANCELED",
        "61": "CANCELED",
        "62": "CANCELED",
        "63": "CANCELED",
        "64": "CANCELED",
        "65": "CANCELED",
        "66": "CANCELED",
        "67": "CANCELED",
        "68": "CANCELED",
        "69": "CANCELED",
        "6a": "CANCELED",
        "6b": "CANCELED",
        "6c": "CANCELED",
        "6d": "CANCELED",
        "6e": "CANCELED",
        "6f": "CANCELED",
        "70": "CANCELED",
        "71": "CANCELED",
        "72": "CANCELED",
        "73": "CANCELED",
        "74": "CANCELED",
        "75": "CANCELED",
        "76": "CANCELED",
        "77": "CANCELED",
        "78": "CANCELED",
        "79": "CANCELED",
        "7a": "CANCELED",
        "7b": "CANCELED",
        "7c": "CANCELED",
        "7d": "CANCELED",
        "7e": "CANCELED",
        "7f": "CANCELED",
        "80": "CANCELED",
        "81": "CANCELED",
        "82": "CANCELED",
        "83": "CANCELED",
        "84": "CANCELED",
        "85": "CANCELED",
        "86": "CANCELED",
        "87": "CANCELED",
        "88": "CANCELED",
        "89": "CANCELED",
        "8a": "CANCELED",
        "8b": "CANCELED",
        "8c": "CANCELED",
        "8d": "CANCELED",
        "8e": "CANCELED",
        "8f": "CANCELED",
        "90": "CANCELED",
        "91": "CANCELED",
        "92": "CANCELED",
        "93": "CANCELED",
        "94": "CANCELED",
        "95": "CANCELED",
        "96": "CANCELED",
        "97": "CANCELED",
        "98": "CANCELED",
        "99": "CANCELED",
        "9a": "CANCELED",
        "9b": "CANCELED",
        "9c": "CANCELED",
        "9d": "CANCELED",
        "9e": "CANCELED",
        "9f": "CANCELED",
        "a0": "CANCELED",
        "a1": "CANCELED",
        "a2": "CANCELED",
        "a3": "CANCELED",
        "a4": "CANCELED",
        "a5": "CANCELED",
        "a6": "CANCELED",
        "a7": "CANCELED",
        "a8": "CANCELED",
        "a9": "CANCELED",
        "aa": "CANCELED",
        "ab": "CANCELED",
        "ac": "CANCELED",
        "ad": "CANCELED",
        "ae": "CANCELED",
        "af": "CANCELED",
        "b0": "CANCELED",
        "b1": "CANCELED",
        "b2": "CANCELED",
        "b3": "CANCELED",
        "b4": "CANCELED",
        "b5": "CANCELED",
        "b6": "CANCELED",
        "b7": "CANCELED",
        "b8": "CANCELED",
        "b9": "CANCELED",
        "ba": "CANCELED",
        "bb": "CANCELED",
        "bc": "CANCELED",
        "bd": "CANCELED",
        "be": "CANCELED",
        "bf": "CANCELED",
        "c0": "CANCELED",
        "c1": "CANCELED",
        "c2": "CANCELED",
        "c3": "CANCELED",
        "c4": "CANCELED",
        "c5": "CANCELED",
        "c6": "CANCELED",
        "c7": "CANCELED",
        "c8": "CANCELED",
        "c9": "CANCELED",
        "ca": "CANCELED",
        "cb": "CANCELED",
        "cc": "CANCELED",
        "cd": "CANCELED",
        "ce": "CANCELED",
        "cf": "CANCELED",
        "d0": "CANCELED",
        "d1": "CANCELED",
        "d2": "CANCELED",
        "d3": "CANCELED",
        "d4": "CANCELED",
        "d5": "CANCELED",
        "d6": "CANCELED",
        "d7": "CANCELED",
        "d8": "CANCELED",
        "d9": "CANCELED",
        "da": "CANCELED",
        "db": "CANCELED",
        "dc": "CANCELED",
        "dd": "CANCELED",
        "de": "CANCELED",
        "df": "CANCELED",
        "e0": "CANCELED",
        "e1": "CANCELED",
        "e2": "CANCELED",
        "e3": "CANCELED",
        "e4": "CANCELED",
        "e5": "CANCELED",
        "e6": "CANCELED",
        "e7": "CANCELED",
        "e8": "CANCELED",
        "e9": "CANCELED",
        "ea": "CANCELED",
        "eb": "CANCELED",
        "ec": "CANCELED",
        "ed": "CANCELED",
        "ee": "CANCELED",
        "ef": "CANCELED",
        "f0": "CANCELED",
        "f1": "CANCELED",
        "f2": "CANCELED",
        "f3": "CANCELED",
        "f4": "CANCELED",
        "f5": "CANCELED",
        "f6": "CANCELED",
        "f7": "CANCELED",
        "f8": "CANCELED",
        "f9": "CANCELED",
        "fa": "CANCELED",
        "fb": "CANCELED",
        "fc": "CANCELED",
        "fd": "CANCELED",
        "fe": "CANCELED",
        "ff": "CANCELED",
    }

    def __init__(
        self,
        on_order_update: Callable[[VenueReceipt], None],
        on_trade_update: Callable[[dict], None],
    ) -> None:
        """Initialize callback handler with event callbacks.

        Args:
            on_order_update: Callback for order status updates.
            on_trade_update: Callback for trade execution updates.
        """
        self._on_order_update = on_order_update
        self._on_trade_update = on_trade_update

    def on_rtn_order(self, p_order: dict) -> None:
        """Handle OnRtnOrder callback from CTP.

        Args:
            p_order: CTP order data dictionary.
        """
        if not p_order:
            return

        try:
            order_ref = p_order.get("OrderRef", "")
            exchange_id = p_order.get("ExchangeID", "")
            order_sys_id = p_order.get("OrderSysID", "")
            status = p_order.get("OrderStatus", "")

            receipt = self._convert_order_status(p_order)
            self._on_order_update(receipt)

            logger.info(
                "Order status updated",
                extra={
                    "order_ref": order_ref,
                    "exchange_id": exchange_id,
                    "order_sys_id": order_sys_id,
                    "status": status,
                },
            )

        except Exception as e:
            logger.error(f"Error processing OnRtnOrder: {e}", exc_info=True)

    def on_rtn_trade(self, p_trade: dict) -> None:
        """Handle OnRtnTrade callback from CTP.

        Args:
            p_trade: CTP trade data dictionary.
        """
        if not p_trade:
            return

        try:
            order_ref = p_trade.get("OrderRef", "")
            exchange_id = p_trade.get("ExchangeID", "")
            trade_id = p_trade.get("TradeID", "")
            price = p_trade.get("Price", "0")
            volume = p_trade.get("Volume", "0")

            status = {
                "order_ref": order_ref,
                "exchange_id": exchange_id,
                "trade_id": trade_id,
                "price": str(price),
                "volume": str(volume),
                "trade_time": p_trade.get("TradeTime", ""),
                "trade_date": p_trade.get("TradeDate", ""),
            }

            self._on_trade_update(status)

            logger.info(
                "Trade executed",
                extra={
                    "order_ref": order_ref,
                    "exchange_id": exchange_id,
                    "trade_id": trade_id,
                    "price": price,
                    "volume": volume,
                },
            )

        except Exception as e:
            logger.error(f"Error processing OnRtnTrade: {e}", exc_info=True)

    def on_err_rtn_order_insert(self, p_order: dict, p_rsp_info: dict) -> None:
        """Handle OnErrRtnOrderInsert callback (order insertion error).

        Args:
            p_order: CTP order data dictionary.
            p_rsp_info: CTP response info with error details.
        """
        if not p_order:
            return

        try:
            from venue.ctp_error_codes import format_ctp_error

            order_ref = p_order.get("OrderRef", "")
            error_id = p_rsp_info.get("ErrorID", 0) if p_rsp_info else 0
            raw_msg = p_rsp_info.get("ErrorMsg", "") if p_rsp_info else ""
            friendly_msg = format_ctp_error(error_id, raw_msg)

            logger.error(
                "Order insertion failed",
                extra={
                    "order_ref": order_ref,
                    "error_id": error_id,
                    "error_msg": friendly_msg,
                },
            )

            from core.venue_order_spec import VenueReceipt

            receipt = VenueReceipt(
                venue_order_id="",
                client_order_id=order_ref,
                status="REJECTED",
                filled_quantity=Decimal("0"),
                filled_price=Decimal("0"),
                timestamp=datetime.now(timezone.utc).isoformat(),
                raw_response={
                    "error": {
                        "error_id": str(error_id),
                        "error_msg": friendly_msg,
                        "raw_ctp_msg": raw_msg,
                    },
                    "ctp_order": p_order,
                },
            )

            self._on_order_update(receipt)

        except Exception as e:
            logger.error(f"Error processing OnErrRtnOrderInsert: {e}", exc_info=True)

    def on_err_rtn_order_action(self, p_order_action: dict, p_rsp_info: dict) -> None:
        """Handle OnErrRtnOrderAction callback (order action error).

        Args:
            p_order_action: CTP order action data dictionary.
            p_rsp_info: CTP response info with error details.
        """
        if not p_order_action:
            return

        try:
            from venue.ctp_error_codes import format_ctp_error

            order_ref = p_order_action.get("OrderRef", "")
            error_id = p_rsp_info.get("ErrorID", 0) if p_rsp_info else 0
            raw_msg = p_rsp_info.get("ErrorMsg", "") if p_rsp_info else ""
            friendly_msg = format_ctp_error(error_id, raw_msg)

            logger.error(
                "Order action failed",
                extra={
                    "order_ref": order_ref,
                    "error_id": error_id,
                    "error_msg": friendly_msg,
                },
            )

        except Exception as e:
            logger.error(f"Error processing OnErrRtnOrderAction: {e}", exc_info=True)

    def _convert_order_status(self, p_order: dict) -> VenueReceipt:
        """Convert CTP order status to VenueReceipt.

        Args:
            p_order: CTP order data dictionary.

        Returns:
            VenueReceipt with mapped status.
        """
        from core.venue_order_spec import VenueReceipt

        order_ref = p_order.get("OrderRef", "")
        order_sys_id = p_order.get("OrderSysID", "")
        status = p_order.get("OrderStatus", "")

        ctp_status = self._map_ctp_status(status)

        filled_qty = Decimal(str(p_order.get("VolumeTraded", "0")))
        filled_price = Decimal("0")

        if filled_qty > 0:
            avg_price = p_order.get("AvgPrice", "0")
            if avg_price and avg_price != "0":
                filled_price = Decimal(str(avg_price))

        receipt = VenueReceipt(
            venue_order_id=order_sys_id or "",
            client_order_id=order_ref,
            status=ctp_status,
            filled_quantity=filled_qty,
            filled_price=filled_price,
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw_response={"ctp_order": p_order},
        )

        return receipt

    def _map_ctp_status(self, ctp_status: str) -> str:
        """Map CTP order status to VenueReceipt status.

        Args:
            ctp_status: CTP order status string.

        Returns:
            Mapped status string: "SENT", "FILLED", "CANCELED", or "REJECTED".
        """
        if not ctp_status:
            return "SENT"

        status_lower = ctp_status.lower()

        if status_lower in ("0a", "0b"):
            return "SENT"
        elif status_lower == "1f":
            return "FILLED"
        elif status_lower.startswith(("2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f")):
            return "CANCELED"
        else:
            return "SENT"

    @staticmethod
    def map_side(side: str) -> str:
        """Map VenueOrderSpec side to CTP direction.

        Args:
            side: "BUY" or "SELL".

        Returns:
            CTP direction: "0" for buy, "1" for sell.
        """
        return "0" if side == "BUY" else "1"

    @staticmethod
    def map_offset_flag(reduce_only: bool) -> str:
        """Map VenueOrderSpec reduce_only to CTP offset flag.

        Args:
            reduce_only: True for close position, False for open.

        Returns:
            CTP offset flag: "0" for open, "1" for close.
        """
        return "1" if reduce_only else "0"

    @staticmethod
    def map_hedge_flag(hedge_flag: str) -> str:
        """Map VenueOrderSpec hedge_flag to CTP hedge flag.

        Args:
            hedge_flag: "SPEC" or "HEDGE".

        Returns:
            CTP hedge flag: "1" for spec, "2" for hedge.
        """
        return "2" if hedge_flag == "HEDGE" else "1"
