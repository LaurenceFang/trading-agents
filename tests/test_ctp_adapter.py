from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.venue_order_spec import VenueOrderSpec, VenueOrderStatus, VenuePosition, VenueReceipt
from venue.ctp_adapter import CTPAdapter
from venue.ctp_callback_handler import CtpCallbackHandler


@pytest.fixture
def mock_gateway():
    """Create a mock CTP gateway."""
    gateway = MagicMock()
    gateway.is_connected = True
    gateway.send_order = MagicMock()
    gateway.cancel_order = MagicMock()
    gateway.query_order = MagicMock()
    gateway.query_position = MagicMock()
    gateway.on_rtn_order = None
    gateway.on_rtn_trade = None
    gateway.on_err_rtn_order_insert = None
    gateway.on_err_rtn_order_action = None
    gateway.on_rsp_qry_order = None
    gateway.on_rsp_qry_investor_position = None
    return gateway


@pytest.fixture
def ctp_config():
    """Create CTP configuration."""
    return {
        "broker_id": "9999",
        "user_id": "test_user",
        "password": "test_pass",
        "app_id": "client_tradagent_1.0.0",
        "auth_code": "test_auth",
        "front_addr": "tcp://180.168.146.187:10130",
    }


@pytest.fixture
def ctp_adapter(ctp_config, mock_gateway):
    """Create CTP adapter with mocked gateway.

    Patch target must be 'venue.ctp_adapter.CtpGatewayWrapper' (the name as
    imported in the adapter module), NOT 'venue.ctp_gateway.CtpGatewayWrapper'.
    Using the wrong module path means the adapter still instantiates the real
    class and the mock is never used.
    """
    with patch("venue.ctp_adapter.CtpGatewayWrapper") as mock_wrapper:
        wrapper_instance = MagicMock()
        wrapper_instance.is_connected = True
        wrapper_instance.get_gateway.return_value = mock_gateway
        wrapper_instance.connect = AsyncMock()
        wrapper_instance.disconnect = AsyncMock()
        mock_wrapper.return_value = wrapper_instance

        adapter = CTPAdapter(ctp_config)
        yield adapter


@pytest.mark.asyncio
async def test_submit_order_success(ctp_adapter, mock_gateway):
    """Test successful order submission returns SENT receipt."""
    spec = VenueOrderSpec(
        symbol="rb2510",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1"),
        price=Decimal("4000"),
        client_order_id="test_order_1",
    )

    mock_gateway.send_order.return_value = None

    async def trigger_callback():
        await asyncio.sleep(0.01)
        receipt = VenueReceipt(
            client_order_id="test_order_1",
            exchange_order_id="CTP-001",
            status="SENT",
            raw_response={},
            timestamp=datetime.now(timezone.utc),
        )
        ctp_adapter._on_order_update(receipt)

    asyncio.create_task(trigger_callback())

    receipt = await ctp_adapter.submit_order(spec)

    assert receipt.client_order_id == "test_order_1"
    assert receipt.status == "SENT"
    assert ctp_adapter.submit_count == 1


@pytest.mark.asyncio
async def test_submit_order_timeout(ctp_adapter, mock_gateway):
    """Test order submission timeout raises TimeoutError."""
    spec = VenueOrderSpec(
        symbol="rb2510",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1"),
        price=Decimal("4000"),
        client_order_id="test_order_timeout",
    )

    mock_gateway.send_order.return_value = None

    with pytest.raises(TimeoutError, match="Order submission timeout"):
        await ctp_adapter.submit_order(spec)


@pytest.mark.asyncio
async def test_cancel_order_success(ctp_adapter, mock_gateway):
    """Test successful order cancellation returns CANCELED receipt."""
    mock_gateway.cancel_order.return_value = None

    async def trigger_callback():
        await asyncio.sleep(0.01)
        receipt = VenueReceipt(
            client_order_id="test_order_1",
            exchange_order_id="CTP-001",
            status="CANCELED",
            raw_response={},
            timestamp=datetime.now(timezone.utc),
        )
        ctp_adapter._on_order_update(receipt)

    asyncio.create_task(trigger_callback())

    receipt = await ctp_adapter.cancel_order("test_order_1")

    assert receipt.client_order_id == "test_order_1"
    assert receipt.status == "CANCELED"
    assert ctp_adapter.cancel_count == 1


@pytest.mark.asyncio
async def test_duplicate_order_rejected(ctp_adapter):
    """Test duplicate order submission returns REJECTED receipt."""
    spec = VenueOrderSpec(
        symbol="rb2510",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1"),
        price=Decimal("4000"),
        client_order_id="test_order_1",
    )

    ctp_adapter._submitted_orders.add("test_order_1")

    receipt = await ctp_adapter.submit_order(spec)

    assert receipt.client_order_id == "test_order_1"
    assert receipt.status == "REJECTED"
    assert receipt.raw_response == {"error": "Duplicate client_order_id"}


@pytest.mark.asyncio
async def test_query_positions_empty(ctp_adapter, mock_gateway):
    """Test query_positions returns empty list when no positions."""
    mock_gateway.query_position.return_value = None

    async def trigger_callback():
        # query_positions() registers the local handler on mock_gateway before
        # hitting the first await, so by the time this sleep finishes the
        # attribute is already the real callable.
        await asyncio.sleep(0.01)
        mock_gateway.on_rsp_qry_investor_position({}, None, 1, True)

    asyncio.create_task(trigger_callback())

    positions = await ctp_adapter.query_positions()

    assert positions == []


@pytest.mark.asyncio
async def test_query_positions_long(ctp_adapter, mock_gateway):
    """Test query_positions correctly parses long position."""
    mock_gateway.query_position.return_value = None

    position_data = {
        "InstrumentID": "rb2510",
        "Position": "10",
        "YdPosition": "0",
        "TodayPosition": "10",
        "ShortPosition": "0",
        "OpenPrice": "4000",
    }

    async def trigger_callback():
        await asyncio.sleep(0.01)
        mock_gateway.on_rsp_qry_investor_position(position_data, None, 1, True)

    asyncio.create_task(trigger_callback())

    positions = await ctp_adapter.query_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "rb2510"
    assert positions[0].side == "LONG"
    assert positions[0].quantity == Decimal("10")
    assert positions[0].entry_price == Decimal("4000")


@pytest.mark.asyncio
async def test_get_market_status_connected(ctp_adapter):
    """Test get_market_status returns correct status when connected."""
    status = await ctp_adapter.get_market_status("rb2510")

    assert status.symbol == "rb2510"
    assert status.can_market_order is True
    assert status.can_limit_order is True
    assert status.is_halted is False


@pytest.mark.asyncio
async def test_get_market_status_disconnected(ctp_adapter):
    """Test get_market_status returns correct status when disconnected."""
    ctp_adapter._gateway.is_connected = False

    status = await ctp_adapter.get_market_status("rb2510")

    assert status.symbol == "rb2510"
    assert status.can_market_order is False
    assert status.can_limit_order is False
    assert status.is_halted is True


@pytest.mark.asyncio
async def test_submit_order_market(ctp_adapter, mock_gateway):
    """Test market order submission."""
    spec = VenueOrderSpec(
        symbol="rb2510",
        side="SELL",
        order_type="MARKET",
        quantity=Decimal("1"),
        price=None,
        client_order_id="test_market_order",
    )

    mock_gateway.send_order.return_value = None

    async def trigger_callback():
        await asyncio.sleep(0.01)
        receipt = VenueReceipt(
            client_order_id="test_market_order",
            exchange_order_id="CTP-002",
            status="SENT",
            raw_response={},
            timestamp=datetime.now(timezone.utc),
        )
        ctp_adapter._on_order_update(receipt)

    asyncio.create_task(trigger_callback())

    receipt = await ctp_adapter.submit_order(spec)

    assert receipt.client_order_id == "test_market_order"
    assert receipt.status == "SENT"


@pytest.mark.asyncio
async def test_submit_order_with_reduce_only(ctp_adapter, mock_gateway):
    """Test order submission with reduce_only flag."""
    spec = VenueOrderSpec(
        symbol="rb2510",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("1"),
        price=Decimal("4000"),
        reduce_only=True,
        client_order_id="test_reduce_order",
    )

    mock_gateway.send_order.return_value = None

    async def trigger_callback():
        await asyncio.sleep(0.01)
        receipt = VenueReceipt(
            client_order_id="test_reduce_order",
            exchange_order_id="CTP-003",
            status="SENT",
            raw_response={},
            timestamp=datetime.now(timezone.utc),
        )
        ctp_adapter._on_order_update(receipt)

    asyncio.create_task(trigger_callback())

    receipt = await ctp_adapter.submit_order(spec)

    assert receipt.client_order_id == "test_reduce_order"
    assert receipt.status == "SENT"


@pytest.mark.asyncio
async def test_query_order(ctp_adapter, mock_gateway):
    """Test querying order status."""
    mock_gateway.query_order.return_value = None

    order_data = {
        "OrderSysID": "CTP-004",
        "OrderStatus": "1f",
        "VolumeTraded": "1",
        "AvgPrice": "4000",
    }

    async def trigger_callback():
        await asyncio.sleep(0.01)
        mock_gateway.on_rsp_qry_order(order_data, None, 1, True)

    asyncio.create_task(trigger_callback())

    status = await ctp_adapter.query_order("test_order_query")

    assert status.client_order_id == "test_order_query"
    assert status.exchange_order_id == "CTP-004"
    assert status.status == "FILLED"
    assert status.filled_quantity == Decimal("1")
    assert status.filled_price == Decimal("4000")


@pytest.mark.asyncio
async def test_submit_order_while_disconnected(ctp_adapter):
    """Test submit_order raises ConnectionError when disconnected."""
    ctp_adapter._gateway.is_connected = False

    spec = VenueOrderSpec(
        symbol="rb2510",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1"),
        price=Decimal("4000"),
        client_order_id="test_disconnected_order",
    )

    with pytest.raises(ConnectionError, match="CTP gateway not connected"):
        await ctp_adapter.submit_order(spec)
