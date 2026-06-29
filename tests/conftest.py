"""Pytest fixtures for Delta Chat plugin integration tests.

Provides mocks for Hermes gateway module that match the real API.
"""

import sys
import os
from unittest.mock import MagicMock, Mock, AsyncMock
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Mock Hermes gateway module BEFORE any imports that might need it
# ---------------------------------------------------------------------------


class MockMessageType(Enum):
    """Mock of gateway.platforms.base.MessageType."""

    TEXT = "text"
    FILE = "file"
    IMAGE = "image"
    AUDIO = "audio"
    VOICE = "voice"
    STICKER = "sticker"
    GIF = "gif"


@dataclass
class MockSendResult:
    """Mock of gateway.platforms.base.SendResult."""

    success: bool
    error: Optional[str] = None
    message_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MockSource:
    """Mock of gateway.platforms.base.Source."""

    chat_id: str
    chat_name: str
    chat_type: str
    user_id: str
    user_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MockMessageEvent:
    """Mock of gateway.platforms.base.MessageEvent."""

    text: str
    message_type: MockMessageType
    source: MockSource
    message_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class MockPlatform(Enum):
    """Mock of gateway.config.Platform."""

    DELTACHAT = "deltachat-platform"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"

    def __str__(self) -> str:
        return self.value


@dataclass
class MockPlatformConfig:
    """Mock of gateway.config.PlatformConfig."""

    name: str
    platform: MockPlatform
    extra: Optional[Dict[str, Any]] = None
    enabled: bool = True


class MockHermesConfig:
    """Mock of gateway.config module."""

    Platform = MockPlatform
    PlatformConfig = MockPlatformConfig

    @staticmethod
    def get_hermes_home() -> str:
        """Mock get_hermes_home - returns temp dir or HERMES_HOME env."""
        # Allow override via HERMES_HOME_TEST environment variable for testing
        test_home = os.environ.get("HERMES_HOME_TEST")
        if test_home:
            return test_home
        return os.environ.get("HERMES_HOME", "/tmp/hermes-test")


class MockMessageViewtype(Enum):
    """Mock of deltachat2.types.MessageViewtype."""

    TEXT = "Text"
    IMAGE = "Image"
    AUDIO = "Audio"
    VIDEO = "Video"
    VOICE = "Voice"
    FILE = "File"


@dataclass
class MockMsgData:
    """Mock of deltachat2.types.MsgData."""

    text: Optional[str] = None
    html: Optional[str] = None
    viewtype: Optional[Any] = None
    file: Optional[str] = None
    location: Optional[Any] = None
    quoted_message_id: Optional[Any] = None


class MockEventType(str, Enum):
    """Mock of deltachat2.types.EventType.

    Subclassing str lets enum members compare equal to their string values,
    matching the real deltachat2 API where event kinds are enum instances.
    """

    INCOMING_MSG = "IncomingMsg"
    MSG_DELIVERED = "MsgDelivered"
    MSG_FAILED = "MsgFailed"
    INCOMING_CALL = "IncomingCall"
    CALL_ENDED = "CallEnded"
    OUTGOING_CALL_ACCEPTED = "OutgoingCallAccepted"
    INCOMING_CALL_ACCEPTED = "IncomingCallAccepted"


class MockDeltaChat2Types:
    """Mock of deltachat2.types module."""

    MsgData = MockMsgData
    MessageViewtype = MockMessageViewtype
    EventType = MockEventType


class MockBasePlatformAdapter:
    """Mock of gateway.platforms.base.BasePlatformAdapter."""

    def __init__(self, config: MockPlatformConfig, platform: MockPlatform):
        self.config = config
        self.platform = platform
        self._connected = False
        self._disconnected = False

    def _mark_connected(self) -> None:
        """Mark adapter as connected."""
        self._connected = True

    def _mark_disconnected(self) -> None:
        """Mark adapter as disconnected."""
        self._disconnected = True

    def build_source(
        self,
        chat_id: str,
        chat_name: str,
        chat_type: str,
        user_id: str,
        user_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MockSource:
        """Build a source object for message events."""
        return MockSource(
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type=chat_type,
            user_id=user_id,
            user_name=user_name,
            metadata=metadata or {},
        )

    async def handle_message(self, event: MockMessageEvent) -> None:
        """Handle a message event (to be overridden by adapter)."""
        pass


class MockGatewayBase:
    """Mock of gateway.platforms.base module."""

    BasePlatformAdapter = MockBasePlatformAdapter
    SendResult = MockSendResult
    MessageEvent = MockMessageEvent
    MessageType = MockMessageType


# ---------------------------------------------------------------------------
# Install mocks into sys.modules
# ---------------------------------------------------------------------------

# Create mock gateway module hierarchy
gateway_module = MagicMock()
gateway_platforms = MagicMock()
gateway_platforms_base = MockGatewayBase()
gateway_config_module = MockHermesConfig()

sys.modules["gateway"] = gateway_module
sys.modules["gateway.platforms"] = gateway_platforms
sys.modules["gateway.platforms.base"] = gateway_platforms_base
sys.modules["gateway.config"] = gateway_config_module

# Set up the actual module references
gateway_module.platforms = gateway_platforms
gateway_module.platforms.base = gateway_platforms_base
gateway_module.config = gateway_config_module

# Mock deltachat2 types so adapter imports resolve without the real package.
deltachat2_module = MagicMock()
deltachat2_module.types = MockDeltaChat2Types()
sys.modules["deltachat2"] = deltachat2_module
sys.modules["deltachat2.types"] = MockDeltaChat2Types()


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

import pytest  # noqa: E402


@pytest.fixture
def platform_config():
    """Create a mock PlatformConfig."""
    return MockPlatformConfig(
        name="deltachat-platform",
        platform=MockPlatform.DELTACHAT,
        extra={"rpc_server": "deltachat-rpc-server"},
        enabled=True,
    )


@pytest.fixture
def mock_platform_config():
    """Create a mock PlatformConfig for tests that need it."""
    return MockPlatformConfig(
        name="test",
        platform=MockPlatform.DELTACHAT,
        extra={"rpc_server": "deltachat-rpc-server"},
    )


@pytest.fixture
def mock_rpc():
    """Create a mock deltachat2.Rpc instance."""
    rpc = MagicMock()
    # Make call an async method that returns a coroutine
    rpc.call = AsyncMock()
    rpc.start = AsyncMock()
    rpc.close = Mock()
    # Common direct RPC methods used by the adapter are awaited as coroutines.
    rpc.get_system_info = AsyncMock()
    rpc.send_msg = AsyncMock()
    rpc.get_basic_chat_info = AsyncMock()
    rpc.get_message = AsyncMock()
    rpc.get_contact = AsyncMock()
    rpc.markseen_msgs = AsyncMock()
    return rpc
