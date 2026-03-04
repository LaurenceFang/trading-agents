"""Tests for CTP query_account (ReqQryTradingAccount).

Covers:
- Successful account query returns VenueAccountInfo
- All numeric fields parse correctly to Decimal
- ConnectionError when not connected
- TimeoutError when CTP does not respond
- CTP error response raises Exception with friendly Chinese message
- Zero/None field values default to Decimal("0")
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venue.ctp_adapter import CTPAdapter, VenueAccountInfo
from venue.ctp_error_codes import format_ctp_error, get_error_label, get_error_description


CONFIG = {
    "broker_id": "9999",
    "user_id": "test_user",
    "password": "test_pass",
    "app_id": "client_aiagentts_1.0.0",
    "auth_code": "0000000000000000",
    "front_addr": "tcp://180.168.146.187:10130",
}

SAMPLE_ACCOUNT_DATA = {
    "AccountID": "test_user",
    "BrokerID": "9999",
    "Balance": 500000.00,
    "Available": 380000.00,
    "CurrMargin": 120000.00,
    "FrozenMargin": 5000.00,
    "FrozenCash": 200.00,
    "PositionProfit": 3500.00,
    "Commission": 150.00,
}


def _make_adapter() -> CTPAdapter:
    adapter = CTPAdapter(CONFIG)
    adapter._gateway = MagicMock()
    adapter._gateway.is_connected = True
    return adapter


def _make_mock_gateway_with_account(data: dict, error: dict | None = None) -> MagicMock:
    """Return a mock gateway whose query_account immediately fires the callback."""
    mock_gw = MagicMock()

    def fake_query_account(req, reqid):
        handler = mock_gw.on_rsp_qry_trading_account
        handler(data, error, reqid, True)

    mock_gw.query_account = fake_query_account
    mock_gw.on_rsp_qry_trading_account = None
    return mock_gw


class TestQueryAccount:
    """Unit tests for CTPAdapter.query_account()."""

    @pytest.mark.asyncio
    async def test_successful_query_returns_account_info(self) -> None:
        """Successful account query must return populated VenueAccountInfo."""
        adapter = _make_adapter()
        mock_gw = _make_mock_gateway_with_account(SAMPLE_ACCOUNT_DATA)
        adapter._gateway.get_gateway = MagicMock(return_value=mock_gw)

        result = await adapter.query_account()

        assert isinstance(result, VenueAccountInfo)
        assert result.account_id == "test_user"
        assert result.broker_id == "9999"
        assert result.balance == Decimal("500000.0")
        assert result.available == Decimal("380000.0")
        assert result.margin == Decimal("120000.0")
        assert result.frozen_margin == Decimal("5000.0")
        assert result.frozen_cash == Decimal("200.0")
        assert result.profit_loss == Decimal("3500.0")
        assert result.commission == Decimal("150.0")

    @pytest.mark.asyncio
    async def test_connection_error_when_not_connected(self) -> None:
        """query_account must raise ConnectionError if gateway is not connected."""
        adapter = _make_adapter()
        adapter._gateway.is_connected = False

        with pytest.raises(ConnectionError, match="CTP gateway not connected"):
            await adapter.query_account()

    @pytest.mark.asyncio
    async def test_ctp_error_response_raises_exception(self) -> None:
        """CTP error response (ErrorID != 0) must raise Exception with friendly msg."""
        adapter = _make_adapter()
        mock_gw = _make_mock_gateway_with_account(
            data={},
            error={"ErrorID": 6, "ErrorMsg": "资金不足"},
        )
        adapter._gateway.get_gateway = MagicMock(return_value=mock_gw)

        with pytest.raises(Exception, match="资金不足"):
            await adapter.query_account()

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_error(self) -> None:
        """query_account must raise TimeoutError when CTP does not respond."""
        adapter = _make_adapter()
        mock_gw = MagicMock()
        mock_gw.on_rsp_qry_trading_account = None

        def fake_query_never_fires(req, reqid):
            pass  # do not call the callback → causes timeout

        mock_gw.query_account = fake_query_never_fires
        adapter._gateway.get_gateway = MagicMock(return_value=mock_gw)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(TimeoutError, match="Query account timeout"):
                await adapter.query_account()

    @pytest.mark.asyncio
    async def test_zero_and_none_fields_default_to_decimal_zero(self) -> None:
        """Missing or zero numeric fields must default to Decimal('0')."""
        sparse_data = {
            "AccountID": "test_user",
            "BrokerID": "9999",
            # All numeric fields absent
        }
        adapter = _make_adapter()
        mock_gw = _make_mock_gateway_with_account(sparse_data)
        adapter._gateway.get_gateway = MagicMock(return_value=mock_gw)

        result = await adapter.query_account()

        assert result.balance == Decimal("0")
        assert result.available == Decimal("0")
        assert result.margin == Decimal("0")
        assert result.profit_loss == Decimal("0")
        assert result.commission == Decimal("0")

    @pytest.mark.asyncio
    async def test_query_account_restores_original_callback(self) -> None:
        """Original on_rsp_qry_trading_account callback must be restored after query."""
        adapter = _make_adapter()
        sentinel = object()
        mock_gw = _make_mock_gateway_with_account(SAMPLE_ACCOUNT_DATA)
        mock_gw.on_rsp_qry_trading_account = sentinel
        adapter._gateway.get_gateway = MagicMock(return_value=mock_gw)

        await adapter.query_account()

        assert mock_gw.on_rsp_qry_trading_account is sentinel


class TestCtpErrorCodes:
    """Unit tests for ctp_error_codes module."""

    def test_known_error_returns_correct_label(self) -> None:
        assert get_error_label(6) == "资金不足"
        assert get_error_label(7) == "持仓不足"
        assert get_error_label(35) == "穿透认证失败"
        assert get_error_label(20) == "登录失败"

    def test_unknown_error_returns_fallback(self) -> None:
        label = get_error_label(9999)
        assert label == "未知错误"

    def test_get_error_description_known(self) -> None:
        desc = get_error_description(6)
        assert "资金" in desc

    def test_get_error_description_unknown_includes_code(self) -> None:
        desc = get_error_description(9999)
        assert "9999" in desc

    def test_format_ctp_error_includes_label_and_raw(self) -> None:
        result = format_ctp_error(6, "资金不足")
        assert "资金不足" in result
        assert "[" in result  # has label bracket

    def test_format_ctp_error_empty_raw_msg(self) -> None:
        result = format_ctp_error(6, "")
        assert "资金不足" in result
        assert "CTP原文" not in result

    def test_format_ctp_error_zero_is_success(self) -> None:
        result = format_ctp_error(0, "")
        assert "成功" in result

    def test_format_ctp_error_auth_failure(self) -> None:
        result = format_ctp_error(35, "AppID不合法")
        assert "穿透认证失败" in result
        assert "AppID不合法" in result
