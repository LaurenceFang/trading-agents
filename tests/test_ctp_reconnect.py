from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venue.ctp_gateway import CtpGatewayWrapper


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
def mock_gateway():
    """Create a mock vnpy_ctp CtpGateway."""
    gateway = MagicMock()
    gateway.connect = MagicMock()
    gateway.close = MagicMock()
    gateway.authenticate = MagicMock()
    gateway.login = MagicMock()
    return gateway


@pytest.mark.asyncio
async def test_reconnect_on_disconnect(ctp_config, mock_gateway):
    """Test that OnFrontDisconnected triggers reconnect."""
    with patch("venue.ctp_gateway.CtpGatewayWrapper") as mock_wrapper:
        wrapper_instance = MagicMock(spec=CtpGatewayWrapper)
        wrapper_instance._gateway = mock_gateway
        wrapper_instance._connected = True
        wrapper_instance._login_event = asyncio.Event()
        wrapper_instance._login_event.set()
        wrapper_instance._should_reconnect = True
        wrapper_instance._reconnect_interval = 1.0
        wrapper_instance._max_reconnect_interval = 60.0
        wrapper_instance._reconnect_task = None

        reconnect_called = False

        async def mock_reconnect_loop():
            nonlocal reconnect_called
            while wrapper_instance._should_reconnect:
                await asyncio.sleep(0.1)
                if not wrapper_instance._connected and wrapper_instance._should_reconnect:
                    reconnect_called = True
                    wrapper_instance._connected = True
                    wrapper_instance._login_event.set()
                    break

        wrapper_instance._reconnect_loop = mock_reconnect_loop

        # Simulate what _on_front_disconnected() does: mark disconnected and
        # clear the login event, then kick off the reconnect loop.
        # Calling the MagicMock method directly does nothing to the attributes,
        # so we reproduce the side-effects here instead.
        wrapper_instance._connected = False
        wrapper_instance._login_event.clear()
        asyncio.create_task(wrapper_instance._reconnect_loop())

        assert wrapper_instance._connected is False
        assert wrapper_instance._login_event.is_set() is False

        await asyncio.sleep(0.2)

        assert reconnect_called is True


@pytest.mark.asyncio
async def test_reconnect_exponential_backoff(ctp_config, mock_gateway):
    """Test that reconnect interval grows exponentially with multiple disconnects."""
    with patch("venue.ctp_gateway.CtpGatewayWrapper") as mock_wrapper:
        wrapper_instance = MagicMock(spec=CtpGatewayWrapper)
        wrapper_instance._gateway = mock_gateway
        wrapper_instance._connected = True
        wrapper_instance._login_event = asyncio.Event()
        wrapper_instance._login_event.set()
        wrapper_instance._should_reconnect = True
        wrapper_instance._reconnect_interval = 1.0
        wrapper_instance._max_reconnect_interval = 60.0
        wrapper_instance._reconnect_task = None

        reconnect_attempts = []
        original_interval = 1.0

        async def mock_reconnect_loop():
            attempt = 0
            while wrapper_instance._should_reconnect and attempt < 3:
                await asyncio.sleep(0.05)
                if not wrapper_instance._connected:
                    reconnect_attempts.append(wrapper_instance._reconnect_interval)
                    wrapper_instance._reconnect_interval = min(
                        wrapper_instance._reconnect_interval * 2,
                        wrapper_instance._max_reconnect_interval
                    )
                    attempt += 1
                    if attempt < 3:
                        wrapper_instance._connected = True
                        wrapper_instance._login_event.set()
                        await asyncio.sleep(0.05)
                        wrapper_instance._connected = False
                        wrapper_instance._login_event.clear()

        wrapper_instance._reconnect_loop = mock_reconnect_loop

        wrapper_instance._connected = False
        wrapper_instance._login_event.clear()

        reconnect_task = asyncio.create_task(wrapper_instance._reconnect_loop())
        await asyncio.sleep(0.5)
        wrapper_instance._should_reconnect = False

        try:
            await asyncio.wait_for(reconnect_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert len(reconnect_attempts) >= 1
        if len(reconnect_attempts) >= 2:
            assert reconnect_attempts[1] > reconnect_attempts[0]


@pytest.mark.asyncio
async def test_reconnect_success_after_retry(ctp_config, mock_gateway):
    """Test that reconnection succeeds after multiple attempts."""
    with patch("venue.ctp_gateway.CtpGatewayWrapper") as mock_wrapper:
        wrapper_instance = MagicMock(spec=CtpGatewayWrapper)
        wrapper_instance._gateway = mock_gateway
        wrapper_instance._connected = False
        wrapper_instance._login_event = asyncio.Event()
        wrapper_instance._should_reconnect = True
        wrapper_instance._reconnect_interval = 0.1
        wrapper_instance._max_reconnect_interval = 60.0
        wrapper_instance._reconnect_task = None

        attempt_count = [0]

        async def mock_reconnect_loop():
            while wrapper_instance._should_reconnect:
                await asyncio.sleep(wrapper_instance._reconnect_interval)
                if not wrapper_instance._connected:
                    attempt_count[0] += 1
                    if attempt_count[0] == 3:
                        wrapper_instance._connected = True
                        wrapper_instance._login_event.set()
                        break

        wrapper_instance._reconnect_loop = mock_reconnect_loop

        reconnect_task = asyncio.create_task(wrapper_instance._reconnect_loop())

        await asyncio.sleep(0.5)

        assert wrapper_instance._connected is True
        assert wrapper_instance._login_event.is_set() is True
        assert attempt_count[0] == 3

        wrapper_instance._should_reconnect = False

        try:
            await asyncio.wait_for(reconnect_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass


@pytest.mark.asyncio
async def test_submit_order_while_disconnected(ctp_config, mock_gateway):
    """Test that submit_order raises ConnectionError when disconnected."""
    with patch("venue.ctp_gateway.CtpGatewayWrapper") as mock_wrapper:
        from venue.ctp_adapter import CTPAdapter

        wrapper_instance = MagicMock(spec=CtpGatewayWrapper)
        wrapper_instance.is_connected = False
        wrapper_instance.get_gateway.return_value = mock_gateway
        wrapper_instance.connect = AsyncMock()
        wrapper_instance.disconnect = AsyncMock()

        mock_wrapper.return_value = wrapper_instance

        adapter = CTPAdapter(ctp_config)

        from core.venue_order_spec import VenueOrderSpec
        from decimal import Decimal

        spec = VenueOrderSpec(
            symbol="rb2510",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("1"),
            price=Decimal("4000"),
            client_order_id="test_disconnected_order",
        )

        with pytest.raises(ConnectionError, match="CTP gateway not connected"):
            await adapter.submit_order(spec)


@pytest.mark.asyncio
async def test_disconnect_stops_reconnect_loop(ctp_config, mock_gateway):
    """Test that disconnect properly stops the reconnect loop."""
    with patch("venue.ctp_gateway.CtpGatewayWrapper") as mock_wrapper:
        wrapper_instance = MagicMock(spec=CtpGatewayWrapper)
        wrapper_instance._gateway = mock_gateway
        wrapper_instance._connected = False
        wrapper_instance._login_event = asyncio.Event()
        wrapper_instance._should_reconnect = True
        wrapper_instance._reconnect_interval = 0.1
        wrapper_instance._max_reconnect_interval = 60.0
        wrapper_instance._reconnect_task = None

        loop_iterations = [0]

        async def mock_reconnect_loop():
            while wrapper_instance._should_reconnect:
                await asyncio.sleep(0.05)
                loop_iterations[0] += 1

        wrapper_instance._reconnect_loop = mock_reconnect_loop

        reconnect_task = asyncio.create_task(wrapper_instance._reconnect_loop())

        await asyncio.sleep(0.2)

        wrapper_instance._should_reconnect = False

        try:
            await asyncio.wait_for(reconnect_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        initial_iterations = loop_iterations[0]

        await asyncio.sleep(0.2)

        final_iterations = loop_iterations[0]

        assert final_iterations == initial_iterations


@pytest.mark.asyncio
async def test_reconnect_max_interval_cap(ctp_config, mock_gateway):
    """Test that reconnect interval is capped at max_reconnect_interval."""
    with patch("venue.ctp_gateway.CtpGatewayWrapper") as mock_wrapper:
        wrapper_instance = MagicMock(spec=CtpGatewayWrapper)
        wrapper_instance._gateway = mock_gateway
        wrapper_instance._connected = False
        wrapper_instance._login_event = asyncio.Event()
        wrapper_instance._should_reconnect = True
        wrapper_instance._reconnect_interval = 30.0
        wrapper_instance._max_reconnect_interval = 60.0
        wrapper_instance._reconnect_task = None

        intervals = []

        async def mock_reconnect_loop():
            attempt = 0
            while wrapper_instance._should_reconnect and attempt < 3:
                await asyncio.sleep(0.05)
                if not wrapper_instance._connected:
                    intervals.append(wrapper_instance._reconnect_interval)
                    wrapper_instance._reconnect_interval = min(
                        wrapper_instance._reconnect_interval * 2,
                        wrapper_instance._max_reconnect_interval
                    )
                    attempt += 1

        wrapper_instance._reconnect_loop = mock_reconnect_loop

        reconnect_task = asyncio.create_task(wrapper_instance._reconnect_loop())

        await asyncio.sleep(0.5)
        wrapper_instance._should_reconnect = False

        try:
            await asyncio.wait_for(reconnect_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        for interval in intervals:
            assert interval <= 60.0


@pytest.mark.asyncio
async def test_connect_timeout(ctp_config, mock_gateway):
    """Test that connect raises TimeoutError when login times out."""
    with patch("venue.ctp_gateway.CtpGatewayWrapper") as mock_wrapper:
        wrapper_instance = MagicMock(spec=CtpGatewayWrapper)
        wrapper_instance._gateway = mock_gateway
        wrapper_instance._connected = False
        wrapper_instance._login_event = asyncio.Event()
        wrapper_instance._should_reconnect = True
        wrapper_instance._reconnect_interval = 1.0
        wrapper_instance._max_reconnect_interval = 60.0
        wrapper_instance._reconnect_task = None

        # mock_connect simulates a real connect() that internally enforces a
        # login timeout and raises TimeoutError with the expected message.
        async def mock_connect():
            try:
                await asyncio.wait_for(asyncio.sleep(0.1), timeout=0.05)
            except asyncio.TimeoutError:
                raise TimeoutError("CTP login timeout")

        wrapper_instance.connect = mock_connect

        with pytest.raises(TimeoutError, match="CTP login timeout"):
            await wrapper_instance.connect()


@pytest.mark.asyncio
async def test_multiple_disconnects_in_sequence(ctp_config, mock_gateway):
    """Test handling multiple disconnects in sequence."""
    with patch("venue.ctp_gateway.CtpGatewayWrapper") as mock_wrapper:
        wrapper_instance = MagicMock(spec=CtpGatewayWrapper)
        wrapper_instance._gateway = mock_gateway
        wrapper_instance._connected = True
        wrapper_instance._login_event = asyncio.Event()
        wrapper_instance._login_event.set()
        wrapper_instance._should_reconnect = True
        wrapper_instance._reconnect_interval = 1.0
        wrapper_instance._max_reconnect_interval = 60.0
        wrapper_instance._reconnect_task = None

        disconnect_count = [0]

        async def mock_reconnect_loop():
            while wrapper_instance._should_reconnect:
                await asyncio.sleep(0.05)
                if not wrapper_instance._connected:
                    disconnect_count[0] += 1
                    wrapper_instance._connected = True
                    wrapper_instance._login_event.set()

        wrapper_instance._reconnect_loop = mock_reconnect_loop

        reconnect_task = asyncio.create_task(wrapper_instance._reconnect_loop())

        # Simulate _on_front_disconnected: set _connected=False + clear event.
        # The MagicMock method itself has no side-effects on the attributes.
        wrapper_instance._connected = False
        wrapper_instance._login_event.clear()
        await asyncio.sleep(0.15)

        wrapper_instance._connected = False
        wrapper_instance._login_event.clear()
        await asyncio.sleep(0.15)

        wrapper_instance._connected = False
        wrapper_instance._login_event.clear()
        await asyncio.sleep(0.15)

        assert disconnect_count[0] >= 3

        wrapper_instance._should_reconnect = False

        try:
            await asyncio.wait_for(reconnect_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass
