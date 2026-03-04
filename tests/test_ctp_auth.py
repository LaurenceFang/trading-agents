"""Tests for CTP authentication flow (穿透式认证).

Covers:
- Successful authenticate → login sequence
- Authentication failure (wrong AuthCode)
- Login failure (wrong password)
- Reconnect re-triggers authenticate → login
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from venue.ctp_gateway import CtpGatewayWrapper


CONFIG = {
    "broker_id": "9999",
    "user_id": "test_user",
    "password": "test_pass",
    "app_id": "client_aiagentts_1.0.0",
    "auth_code": "0000000000000000",
    "front_addr": "tcp://180.168.146.187:10130",
}


class TestCtpAuthFlow:
    """Tests for the full CTP authenticate → login flow."""

    def _make_wrapper(self) -> CtpGatewayWrapper:
        return CtpGatewayWrapper(CONFIG)

    def test_on_front_connected_calls_authenticate(self) -> None:
        """_on_front_connected must call gateway.authenticate with correct AppID."""
        wrapper = self._make_wrapper()
        mock_gateway = MagicMock()
        wrapper._gateway = mock_gateway

        wrapper._on_front_connected()

        mock_gateway.authenticate.assert_called_once()
        call_args = mock_gateway.authenticate.call_args[0][0]
        assert call_args["AppID"] == "client_aiagentts_1.0.0"
        assert call_args["AuthCode"] == CONFIG["auth_code"]
        assert call_args["BrokerID"] == CONFIG["broker_id"]
        assert call_args["UserID"] == CONFIG["user_id"]

    def test_on_rsp_authenticate_success_calls_login(self) -> None:
        """Successful authenticate response must trigger ReqUserLogin."""
        wrapper = self._make_wrapper()
        mock_gateway = MagicMock()
        wrapper._gateway = mock_gateway

        wrapper._on_rsp_authenticate(
            data={"BrokerID": "9999"},
            error={"ErrorID": 0, "ErrorMsg": ""},
            reqid=1,
            last=True,
        )

        mock_gateway.login.assert_called_once()
        login_args = mock_gateway.login.call_args[0][0]
        assert login_args["BrokerID"] == CONFIG["broker_id"]
        assert login_args["UserID"] == CONFIG["user_id"]
        assert login_args["Password"] == CONFIG["password"]

    def test_on_rsp_authenticate_failure_does_not_login(self) -> None:
        """Failed authenticate must NOT call login."""
        wrapper = self._make_wrapper()
        mock_gateway = MagicMock()
        wrapper._gateway = mock_gateway

        wrapper._on_rsp_authenticate(
            data={},
            error={"ErrorID": 35, "ErrorMsg": "AppID不合法"},
            reqid=1,
            last=True,
        )

        mock_gateway.login.assert_not_called()

    def test_on_rsp_user_login_success_sets_event(self) -> None:
        """Successful login response must set the _login_event."""
        wrapper = self._make_wrapper()

        assert not wrapper._login_event.is_set()

        wrapper._on_rsp_user_login(
            data={"UserID": "test_user", "FrontID": 1, "SessionID": 123},
            error={"ErrorID": 0, "ErrorMsg": ""},
            reqid=2,
            last=True,
        )

        assert wrapper._login_event.is_set()

    def test_on_rsp_user_login_failure_does_not_set_event(self) -> None:
        """Failed login must NOT set the _login_event."""
        wrapper = self._make_wrapper()

        wrapper._on_rsp_user_login(
            data={},
            error={"ErrorID": 20, "ErrorMsg": "密码错误"},
            reqid=2,
            last=True,
        )

        assert not wrapper._login_event.is_set()

    def test_on_rsp_user_login_none_error_sets_event(self) -> None:
        """Login response with error=None (success) must still set _login_event."""
        wrapper = self._make_wrapper()

        wrapper._on_rsp_user_login(
            data={"UserID": "test_user"},
            error=None,
            reqid=2,
            last=True,
        )

        assert wrapper._login_event.is_set()

    def test_app_id_is_correct(self) -> None:
        """AppID must exactly match client_aiagentts_1.0.0 per 穿透式认证 spec."""
        wrapper = self._make_wrapper()
        assert wrapper.app_id == "client_aiagentts_1.0.0"

    @pytest.mark.asyncio
    async def test_connect_timeout_raises_timeout_error(self) -> None:
        """connect() must raise TimeoutError when login event is never set."""
        wrapper = self._make_wrapper()

        async def mock_connect_never_fires(*args, **kwargs):
            # Never set _login_event
            await asyncio.sleep(999)

        mock_gateway_cls = MagicMock()
        mock_gateway_instance = MagicMock()
        mock_gateway_cls.return_value = mock_gateway_instance
        mock_gateway_instance.connect = mock_connect_never_fires

        with patch("venue.ctp_gateway.CtpGateway", mock_gateway_cls):
            with patch.object(wrapper, "_login_event") as mock_event:
                mock_event.wait = AsyncMock(side_effect=asyncio.TimeoutError)
                mock_event.clear = MagicMock()
                mock_event.is_set = MagicMock(return_value=False)

                with pytest.raises(TimeoutError, match="CTP login timeout"):
                    await wrapper.connect()

    @pytest.mark.asyncio
    async def test_disconnect_after_connect_clears_state(self) -> None:
        """disconnect() must mark gateway as not connected and clear login event."""
        wrapper = self._make_wrapper()
        wrapper._connected = True
        wrapper._login_event.set()
        wrapper._gateway = MagicMock()
        wrapper._should_reconnect = True

        await wrapper.disconnect()

        assert not wrapper._connected
        assert not wrapper._login_event.is_set()

    def test_front_disconnected_clears_connected_flag(self) -> None:
        """_on_front_disconnected must clear _connected and _login_event."""
        wrapper = self._make_wrapper()
        wrapper._connected = True
        wrapper._login_event.set()

        wrapper._on_front_disconnected(reason=4097)

        assert not wrapper._connected
        assert not wrapper._login_event.is_set()
