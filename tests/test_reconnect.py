"""Tests for RPC reconnect behavior."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_reconnect_gives_up_after_max_attempts():
    from adapter import DeltaChatAdapter

    adapter = MagicMock(spec=DeltaChatAdapter)
    adapter.connect = AsyncMock(return_value=False)
    adapter.disconnect = AsyncMock()
    adapter._reconnecting = False
    adapter._mark_disconnected = MagicMock()

    with patch("adapter.asyncio.sleep"):
        result = await DeltaChatAdapter._reconnect(adapter)
    assert result is False
    assert adapter.connect.call_count == 5
    adapter._mark_disconnected.assert_called_once()


@pytest.mark.asyncio
async def test_reconnect_is_idempotent():
    from adapter import DeltaChatAdapter

    adapter = MagicMock(spec=DeltaChatAdapter)
    adapter.connect = AsyncMock(return_value=True)
    adapter.disconnect = AsyncMock()
    adapter._reconnecting = True  # already reconnecting
    adapter._mark_connected = MagicMock()

    result = await DeltaChatAdapter._reconnect(adapter)
    assert result is False
    adapter.connect.assert_not_called()


@pytest.mark.asyncio
async def test_reconnect_succeeds_on_first_attempt():
    from adapter import DeltaChatAdapter

    adapter = MagicMock(spec=DeltaChatAdapter)
    adapter.connect = AsyncMock(return_value=True)
    adapter.disconnect = AsyncMock()
    adapter._reconnecting = False
    adapter._mark_connected = MagicMock()

    result = await DeltaChatAdapter._reconnect(adapter)
    assert result is True
    adapter.connect.assert_awaited_once()
    adapter._mark_connected.assert_called_once()


@pytest.mark.asyncio
async def test_reconnect_succeeds_after_retries():
    from adapter import DeltaChatAdapter

    adapter = MagicMock(spec=DeltaChatAdapter)
    adapter.connect = AsyncMock(side_effect=[False, False, True])
    adapter.disconnect = AsyncMock()
    adapter._reconnecting = False
    adapter._mark_disconnected = MagicMock()
    adapter._mark_connected = MagicMock()

    with patch("adapter.asyncio.sleep"):
        result = await DeltaChatAdapter._reconnect(adapter)
    assert result is True
    assert adapter.connect.call_count == 3
    adapter._mark_connected.assert_called_once()
