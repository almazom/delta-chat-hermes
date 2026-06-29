"""Delta Chat platform adapter for Hermes Gateway.

Integrates Delta Chat as a messaging platform using deltachat2 (direct JSON-RPC).
"""

import functools
import html
import os
import sys
import asyncio
import logging
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

# Add vendor directory to sys.path so vendored deltachat2 can be imported
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)
_vendor_dir = os.path.join(_plugin_dir, "vendor")
if os.path.exists(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)

from gateway.platforms.base import (
    BasePlatformAdapter,
    SendResult,
    MessageEvent,
    MessageType,
)
from gateway.config import Platform, PlatformConfig

from chat_tokens import ChatTokenStore, get_or_create_chat_token, resolve_chat_token
from media import (
    container_workspace_to_host,
    copy_container_file_to_cache,
    copy_to_hermes_cache,
    extract_media as _extract_media,
    extract_local_files as _extract_local_files,
    filter_media_delivery_paths as _filter_media_delivery_paths,
    filter_local_delivery_paths as _filter_local_delivery_paths,
    resolve_blob_path,
)

# Gateway context stashed at plugin load time; used to register RPC tools once.
_tool_ctx = None

# Multi-profile dispatch state. Tools are registered globally once; handlers resolve
# the correct adapter from the chat_token so multiple profiles do not collide.
_tools_registered = False
_token_to_adapter: Dict[str, "DeltaChatAdapter"] = {}
_default_adapter: Optional["DeltaChatAdapter"] = None


def _store_tool_ctx(ctx) -> None:
    global _tool_ctx
    _tool_ctx = ctx


def _register_global_rpc_tools(ctx) -> None:
    """Register Delta Chat tools once; handlers dispatch by chat_token."""
    global _tools_registered
    if _tools_registered:
        return
    import rpc_tools

    rpc_tools.register_rpc_tools(
        ctx,
        resolve_adapter=lambda token: _token_to_adapter.get(token),
        get_default_adapter=lambda: _default_adapter,
    )
    _tools_registered = True


def _register_chat_token(token: str, adapter: "DeltaChatAdapter") -> None:
    """Map an opaque chat token to the adapter that owns it."""
    _token_to_adapter[token] = adapter


def _unregister_adapter_tokens(adapter: "DeltaChatAdapter") -> None:
    """Remove all token mappings pointing at *adapter*."""
    to_remove = [t for t, a in _token_to_adapter.items() if a is adapter]
    for token in to_remove:
        _token_to_adapter.pop(token, None)


# Must use "hermes_plugins.*" prefix so records appear in gateway.log.
# __name__ resolves to "adapter" (standalone module), which only goes to agent.log.
logger = logging.getLogger("hermes_plugins.deltachat")

# Enable debug logging for RPC if requested
if os.getenv("DELTACHAT_DEBUG"):
    logging.getLogger("deltachat2").setLevel(logging.DEBUG)
    logging.getLogger("deltachat2.IOTransport").setLevel(logging.DEBUG)

# Minimum required Delta Chat core version
# Plugin will NOT connect with older versions
MIN_DC_VERSION = "2.51.0"


def _voice_calls_enabled() -> bool:
    """Return True if experimental WebRTC voice calls are enabled."""
    return os.getenv("DELTACHAT_ENABLE_VOICE_CALLS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# Lazy import to avoid dependency issues if deltachat2 not installed
_DC2_AVAILABLE = None


def _check_dc2_available():
    """Check if deltachat2 is available."""
    global _DC2_AVAILABLE
    if _DC2_AVAILABLE is None:
        try:
            import deltachat2

            _DC2_AVAILABLE = True
            return True
        except ImportError:
            _DC2_AVAILABLE = False
    return _DC2_AVAILABLE


def _parse_version(version_str: str) -> tuple:
    """Parse version string into tuple of ints for comparison.

    Args:
        version_str: Version string like "2.51.0" or "2.51.0-dev"

    Returns:
        Tuple of (major, minor, patch) integers
    """
    try:
        # Remove any suffixes like -dev, -rc1, etc. and leading 'v'
        base_version = version_str.lstrip("v").split("-")[0]
        parts = base_version.split(".")
        # Pad with zeros if needed
        while len(parts) < 3:
            parts.append("0")
        return tuple(int(p) for p in parts[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


async def _check_dc_version(rpc) -> bool:
    """Check Delta Chat core version and enforce minimum.

    Args:
        rpc: DeltaChat2 RPC client

    Returns:
        True if version is compatible, False if too old
    """
    try:
        # Get system info which includes version
        system_info = await rpc.get_system_info()
        dc_version_str = system_info.get("deltachat_core_version", "0.0.0")
        dc_version = _parse_version(dc_version_str)
        min_version = _parse_version(MIN_DC_VERSION)

        if dc_version < min_version:
            logger.error(
                f"Delta Chat version {dc_version_str} is too old. "
                f"This plugin requires {MIN_DC_VERSION} or higher. "
                f"Please update your Delta Chat installation."
            )
            return False
        elif dc_version > min_version:
            logger.warning(
                f"Delta Chat version {dc_version_str} is newer than "
                f"the minimum required ({MIN_DC_VERSION}). "
                f"The API may have changed and there may be errors."
            )

        return True

    except Exception as e:
        logger.error(f"Could not check Delta Chat version: {e}")
        return False


class _AsyncRpc:
    """Wraps synchronous deltachat2.Rpc so every call runs in a thread executor.

    deltachat2.Rpc.transport.call() blocks on a threading.Event until the
    RPC server responds.  Calling it directly from an async function would
    freeze the asyncio event loop.  This wrapper makes every attribute access
    return an async function that runs the underlying sync call in a bounded
    ThreadPoolExecutor, keeping the event loop free while capping thread growth.
    """

    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="dc-rpc-")

    def __init__(self, rpc) -> None:
        object.__setattr__(self, "_rpc", rpc)

    def __getattr__(self, name: str):
        method = getattr(object.__getattribute__(self, "_rpc"), name)

        async def _async_call(*args):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, method, *args)

        return _async_call


@dataclass
class DeltaChatPluginState:
    """All mutable plugin state scoped to a single adapter instance.

    Previously this state lived at module scope, which broke multi-profile
    isolation. Each DeltaChatAdapter now carries its own state object; RPC
    tools and call managers use that instance instead of a global singleton.
    """

    adapter: Optional["DeltaChatAdapter"] = None
    chat_tokens: "ChatTokenStore" = field(default_factory=lambda: ChatTokenStore())
    spec_cache: Optional[dict] = None


class DeltaChatRpcClient:
    """Lifecycle wrapper around the deltachat2 IOTransport and Rpc client.

    Encapsulates transport startup, async RPC wrapping, and readiness polling
    so that the adapter can detect failures and reconnect without duplicating
    this logic.
    """

    def __init__(self, accounts_dir: str, rpc_server_path: str):
        self.accounts_dir = accounts_dir
        self.rpc_server_path = rpc_server_path
        self.transport = None
        self.rpc = None

    async def start(self, timeout: float = 10.0) -> bool:
        """Start the transport and wait until the RPC server is ready."""
        import deltachat2
        from deltachat2.transport import IOTransport

        # IOTransport passes DC_ACCOUNTS_PATH only to the RPC server subprocess,
        # so we do not mutate the global os.environ here. This keeps multiple
        # Hermes profile adapters isolated from each other.
        self.transport = IOTransport(
            accounts_dir=self.accounts_dir,
            rpc_server=self.rpc_server_path,
        )
        self.transport.start()
        self.rpc = _AsyncRpc(deltachat2.Rpc(self.transport))
        return await self._wait_ready(timeout)

    async def _wait_ready(self, timeout: float) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                await self.rpc.get_all_accounts()
                return True
            except Exception:
                await asyncio.sleep(0.5)
        return False

    def stop(self) -> None:
        if self.transport:
            try:
                self.transport.close()
            except Exception as e:
                logger.debug(f"Error closing transport: {e}")
            self.transport = None
        self.rpc = None

    def is_alive(self) -> bool:
        return self.transport is not None and self.rpc is not None


class DeltaChatAdapter(BasePlatformAdapter):
    """Delta Chat platform adapter for Hermes Gateway.

    Uses deltachat2 for direct JSON-RPC access (not abstracted away).
    Each Hermes profile runs its own instance; DC_ACCOUNTS_PATH is scoped to the
    RPC server subprocess so multiple adapters do not interfere with each other.
    """

    def __init__(self, config: PlatformConfig):
        """Initialize the adapter.

        Args:
            config: Hermes PlatformConfig for this profile
        """
        super().__init__(config, Platform("deltachat-platform"))
        self.state = DeltaChatPluginState(adapter=self)
        self.rpc = None
        self._rpc_client = None
        self._transport = None
        self.account_id: Optional[int] = None
        self._event_loop_task: Optional[asyncio.Task] = None
        self._running = False
        self._dc_config_dir: Optional[str] = None
        self._call_manager = None
        self._reconnecting = False

    def _get_dc_config_dir(self) -> str:
        """Get Delta Chat config directory path.

        Returns:
            Path to Delta Chat config directory (<HERMES_HOME>/deltachat-platform/)
        """
        if self._dc_config_dir is None:
            from gateway.config import get_hermes_home

            self._dc_config_dir = os.path.join(get_hermes_home(), "deltachat-platform")
            # Ensure directory exists
            os.makedirs(self._dc_config_dir, exist_ok=True)
        return self._dc_config_dir

    def _get_rpc_server_path(self) -> str:
        """Get deltachat-rpc-server binary path.

        Returns:
            Path to RPC server binary from config, env, or default.
        """
        # From config.extra
        if self.config.extra and self.config.extra.get("rpc_server"):
            return self.config.extra["rpc_server"]

        # From environment
        env_path = os.getenv("DELTACHAT_RPC_SERVER")
        if env_path:
            return env_path

        # Default - assume in PATH
        return "deltachat-rpc-server"

    async def connect(self) -> bool:
        """Connect to Delta Chat via RPC server.

        Starts the RPC server process, initializes the client,
        checks version, and begins listening for events.

        Returns:
            True if connection successful, False otherwise
        """
        if not _check_dc2_available():
            logger.error("deltachat2 is not installed. Run: pip install deltachat2")
            return False

        try:
            import deltachat2
        except ImportError as e:
            logger.error(f"Failed to import deltachat2: {e}")
            return False

        try:
            # Get config directory
            dc_accounts_path = self._get_dc_config_dir()
            logger.debug(f"Using DC accounts directory: {dc_accounts_path}")

            # Get RPC server path
            rpc_server_path = self._get_rpc_server_path()
            logger.debug(f"Using RPC server: {rpc_server_path}")

            # Initialize RPC client lifecycle wrapper
            self._rpc_client = DeltaChatRpcClient(dc_accounts_path, rpc_server_path)
            if not await self._rpc_client.start():
                logger.error("RPC server failed to start")
                self._cleanup()
                return False
            self.rpc = self._rpc_client.rpc

            # Check version - REJECT if too old
            if not await _check_dc_version(self.rpc):
                self._cleanup()
                return False

            # Get or create account - use first available
            accounts = await self.rpc.get_all_accounts()
            if accounts:
                self.account_id = accounts[0]["id"]
                logger.info(f"Using Delta Chat account: {self.account_id}")
            else:
                logger.error(
                    f"No Delta Chat accounts found in {dc_accounts_path}. "
                    "Run: python ~/.hermes/plugins/deltachat-platform/setup.py"
                )
                self._cleanup()
                return False

            # Enable bot mode: auto-accept contact requests
            try:
                await self.rpc.set_config(self.account_id, "bot", "1")
                logger.debug("Bot mode enabled: contact requests will be auto-accepted")
            except Exception as e:
                logger.warning(f"Could not set bot config: {e}")

            # Start IO for the account to receive events
            await self.rpc.start_io(self.account_id)
            logger.debug(f"Started IO for account {self.account_id}")

            # Start event listener
            self._running = True
            self._event_loop_task = asyncio.create_task(self._event_listener())

            self._mark_connected()

            # Register RPC tools once globally. Tool handlers dispatch to the correct
            # adapter at runtime using the chat_token, so multiple Hermes profiles can
            # load this plugin without overwriting each other's tool closures.
            global _default_adapter
            _default_adapter = self
            try:
                if _tool_ctx is not None:
                    _register_global_rpc_tools(_tool_ctx)
            except Exception as e:
                logger.warning(f"Could not register RPC tools: {e}")

            # Voice calls are opt-in; see _voice_calls_enabled() check below.
            self._call_manager = None
            if _voice_calls_enabled():
                try:
                    from call_handler import CallManager

                    self._call_manager = CallManager(self)
                    logger.info("Voice calls enabled")
                except ImportError as e:
                    logger.error("Voice calls enabled but aiortc/deltachat2 missing: %s", e)

            # Log the bot's address for reference
            addr = await self.get_my_address()
            if addr:
                logger.info(f"Delta Chat connected successfully. Bot address: {addr}")
            else:
                logger.info("Delta Chat connected successfully")
            return True

        except Exception as e:
            logger.error(f"Delta Chat connection failed: {e}")
            self._cleanup()
            return False

    def _cleanup(self) -> None:
        """Clean up resources."""
        global _default_adapter
        self._running = False
        if self._event_loop_task:
            self._event_loop_task.cancel()
            self._event_loop_task = None
        if self._rpc_client:
            self._rpc_client.stop()
            self._rpc_client = None
        self.rpc = None
        self.account_id = None
        _unregister_adapter_tokens(self)
        if _default_adapter is self:
            _default_adapter = None

    async def disconnect(self) -> None:
        """Disconnect from Delta Chat."""
        if self._call_manager:
            await self._call_manager.teardown()
            self._call_manager = None
        self._cleanup()
        self._mark_disconnected()
        logger.info("Delta Chat disconnected")

    async def get_my_address(self) -> Optional[str]:
        """Get the Delta Chat account address or SecureJoin link.

        Returns:
            SecureJoin link (e.g., https://delta.chat/s?pk=...) or address (e.g., bot@server.org)
        """
        if not self.rpc or not self.account_id:
            return None

        try:
            # Try to get SecureJoin QR code content (which is the link)
            try:
                qr_content = await self.rpc.get_chat_securejoin_qr_code(
                    self.account_id, None  # chat_id - None for account-level QR
                )
                if qr_content:
                    return qr_content
            except Exception:
                pass

            # Fallback: get account info which should include address
            info = await self.rpc.get_account_info(self.account_id)
            if info:
                # Try different field names for address
                address = info.get("address") or info.get("addr")
                if address:
                    return address
                # Construct from name and server
                name = info.get("name") or info.get("display_name", "")
                server = info.get("server", "")
                if name and server:
                    return f"{name}@{server}"

            # Final fallback: list accounts and find ours
            accounts = await self.rpc.get_all_accounts()
            for acc in accounts:
                if acc.get("id") == self.account_id:
                    name = acc.get("name", acc.get("display_name", ""))
                    server = acc.get("server", "")
                    if name and server:
                        return f"{name}@{server}"
        except Exception as e:
            logger.debug(f"Failed to get account address: {e}")

        return None

    def _format_html_message(self, text: str, max_lines: int = 40) -> tuple:
        """Format long messages with HTML for better readability in Delta Chat.

        If message is longer than max_lines, returns (text_part, html_part)
        where text_part is the first max_lines and html_part is the full
        message with proper styling. Otherwise returns (text, None).

        Args:
            text: The message text
            max_lines: Maximum lines before using HTML (default: 40)

        Returns:
            Tuple of (plain_text, html_text) - html_text is None if not needed
        """
        lines = text.split("\n")
        if len(lines) <= max_lines:
            return (text, None)

        # First max_lines as plain text
        text_part = "\n".join(lines[:max_lines])

        # Full message as HTML with nice formatting; escape to prevent injection
        escaped = html.escape(text).replace("\n", "<br>\n")
        html_part = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 16px;
    line-height: 1.5;
    color: #333;
    background-color: #fff;
    padding: 16px;
    max-width: 800px;
    margin: 0 auto;
}}
</style>
</head>
<body>
{escaped}
</body>
</html>"""

        return (text_part, html_part)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a text message to a Delta Chat chat.

        When a voice call is active for this chat the response is routed to
        TTS and played into the call instead of being sent as a DC message.
        """
        if self._call_manager and self._call_manager.has_active_call(chat_id):
            thread_id = (metadata or {}).get("thread_id")
            if self._call_manager.is_call_thread(thread_id):
                # Reply belongs to the call conversation — speak it into the call.
                # In shared-history mode the placing agent's "call connected" ack
                # also lands here (same session), so drop that one line.
                if self._call_manager.consume_call_ack(chat_id):
                    return SendResult(success=True, message_id=None)
                asyncio.create_task(self._call_manager.play_response(chat_id, content))
                return SendResult(success=True, message_id=None)
            # Reply from the text/chat thread while a call is active (e.g. the
            # agent's "calling you now" line in separate-thread mode, or a
            # concurrent DM) — deliver it as a normal Delta Chat message instead
            # of speaking it into the call. Falls through to the normal send path.
        # Suppress the AI's reply to the internal "call ended" note so we don't
        # text the user a stray message after a call.
        if self._call_manager and self._call_manager.consume_drop_response(chat_id):
            return SendResult(success=True, message_id=None)

        try:
            if not self.rpc or not self.account_id:
                return SendResult(
                    success=False,
                    error="Delta Chat not connected",
                )

            # Format long messages with HTML
            text_part, html_part = self._format_html_message(content)

            quoted_id = int(reply_to) if reply_to else None

            if html_part:
                from deltachat2.types import MsgData, MessageViewtype

                msg_id = await self.rpc.send_msg(
                    self.account_id,
                    int(chat_id),
                    MsgData(
                        text=text_part,
                        html=html_part,
                        viewtype=MessageViewtype.TEXT,
                        quoted_message_id=quoted_id,
                    ),
                )
            else:
                from deltachat2.types import MsgData

                msg_id = await self.rpc.send_msg(
                    self.account_id,
                    int(chat_id),
                    MsgData(text=content, quoted_message_id=quoted_id),
                )

            logger.debug(f"Sent message {msg_id} to chat {chat_id}")
            return SendResult(
                success=True,
                message_id=str(msg_id),
            )

        except Exception as e:
            logger.error(f"Error sending message to chat {chat_id}: {e}")
            return SendResult(
                success=False,
                error=str(e),
            )

    async def send_file(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        """Send a file to a Delta Chat chat via send_msg.

        DC core auto-detects the viewtype from the extension — .xdc files
        are delivered as webxdc apps without any special handling here.
        """
        try:
            if not self.rpc or not self.account_id:
                return SendResult(success=False, error="Delta Chat not connected")

            from deltachat2.types import MsgData

            msg_id = await self.rpc.send_msg(
                self.account_id,
                int(chat_id),
                MsgData(
                    file=file_path,
                    text=caption or "",
                    quoted_message_id=int(reply_to) if reply_to else None,
                ),
            )
            logger.debug(f"Sent file {file_path} as message {msg_id} to chat {chat_id}")
            return SendResult(success=True, message_id=str(msg_id))

        except Exception as e:
            logger.error(f"Error sending file {file_path} to chat {chat_id}: {e}")
            return SendResult(success=False, error=str(e))

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        file_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        """Send a document/file attachment to a Delta Chat chat.

        Delegates to send_file; file_name is ignored because DC derives the
        display name from the blob path.  DC core auto-detects viewtype from
        the file extension (.xdc → webxdc, .pdf → document, etc.).
        """
        return await self.send_file(
            chat_id=chat_id,
            file_path=file_path,
            caption=caption,
            reply_to=reply_to,
            metadata=metadata,
        )

    async def send_image_file(
        self,
        chat_id: str,
        image_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        """Send an image file to a Delta Chat chat.

        Args:
            chat_id: Delta Chat chat ID
            image_path: Path to image file on disk
            caption: Optional caption for the image
            reply_to: Optional message ID to reply to
            metadata: Optional metadata

        Returns:
            SendResult with success status and message ID
        """
        try:
            if not self.rpc or not self.account_id:
                return SendResult(success=False, error="Delta Chat not connected")

            from deltachat2.types import MsgData, MessageViewtype

            msg_id = await self.rpc.send_msg(
                self.account_id,
                int(chat_id),
                MsgData(
                    file=image_path,
                    text=caption or "",
                    viewtype=MessageViewtype.IMAGE,
                    quoted_message_id=int(reply_to) if reply_to else None,
                ),
            )
            logger.debug(f"Sent image {image_path} as message {msg_id} to chat {chat_id}")
            return SendResult(success=True, message_id=str(msg_id))
        except Exception as e:
            logger.error(f"Error sending image {image_path} to chat {chat_id}: {e}")
            return SendResult(success=False, error=str(e))

    async def send_voice(
        self,
        chat_id: str,
        audio_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        """Send a voice message to a Delta Chat chat.

        Delta Chat supports voice messages natively.

        Args:
            chat_id: Delta Chat chat ID
            audio_path: Path to audio file on disk
            caption: Optional caption for the voice message
            reply_to: Optional message ID to reply to
            metadata: Optional metadata

        Returns:
            SendResult with success status and message ID
        """
        import os

        caption_preview = caption[:50] if caption else None
        logger.info(
            "send_voice called: chat_id=%s, audio_path=%s, caption=%s",
            chat_id,
            audio_path,
            caption_preview,
        )
        logger.debug(f"send_voice kwargs: {kwargs}")

        # Validate audio file exists and is accessible
        if not os.path.exists(audio_path):
            logger.error(f"send_voice: Audio file does not exist: {audio_path}")
            return SendResult(
                success=False,
                error=f"Audio file not found: {audio_path}",
            )
        if not os.path.isfile(audio_path):
            logger.error(f"send_voice: Path is not a file: {audio_path}")
            return SendResult(
                success=False,
                error=f"Path is not a file: {audio_path}",
            )
        file_size = os.path.getsize(audio_path)
        logger.info(f"send_voice: Audio file exists, size={file_size} bytes")

        # Delta Chat sends voice messages as files with VOICE viewtype
        from deltachat2.types import MsgData, MessageViewtype

        try:
            if not self.rpc or not self.account_id:
                logger.error(
                    "send_voice: Delta Chat not connected (rpc={}, account_id={})".format(
                        "None" if not self.rpc else "set",
                        "None" if not self.account_id else self.account_id,
                    )
                )
                return SendResult(
                    success=False,
                    error="Delta Chat not connected",
                )

            logger.debug(f"send_voice: Sending to account_id={self.account_id}, chat_id={chat_id}")
            msg_id = await self.rpc.send_msg(
                self.account_id,
                int(chat_id),
                MsgData(
                    file=audio_path,
                    text=caption or "",
                    viewtype=MessageViewtype.VOICE,
                    quoted_message_id=int(reply_to) if reply_to else None,
                ),
            )

            logger.info(f"Sent voice message {msg_id} to chat {chat_id}, file={audio_path}, size={file_size}")
            return SendResult(
                success=True,
                message_id=str(msg_id),
            )

        except Exception as e:
            import traceback

            logger.error(f"Error in send_voice: {e}")
            logger.debug(f"send_voice exception traceback:\n{traceback.format_exc()}")
            return SendResult(
                success=False,
                error=str(e),
            )

    async def send_location(
        self,
        chat_id: str,
        latitude: float,
        longitude: float,
        poi_name: str,
    ) -> SendResult:
        """Send a location/point of interest to a Delta Chat chat.

        Note: In Delta Chat, a single emoji character is displayed as that emoji
        on the map. A text message is displayed as a pin icon that can be clicked
        to view the message.

        Args:
            chat_id: Delta Chat chat ID
            latitude: Latitude in degrees
            longitude: Longitude in degrees
            poi_name: POI name or emoji (e.g., "☕" for coffee, "🏠" for home,
                     or "My favorite café" for a pin with text)

        Returns:
            SendResult with success status and message ID
        """
        try:
            if not self.rpc or not self.account_id:
                return SendResult(
                    success=False,
                    error="Delta Chat not connected",
                )

            from deltachat2.types import MsgData

            # location tuple is (latitude, longitude) per GeoJSON convention
            msg_id = await self.rpc.send_msg(
                self.account_id,
                int(chat_id),
                MsgData(text=poi_name, location=(latitude, longitude)),
            )

            logger.debug(f"Sent location to chat {chat_id}")
            return SendResult(
                success=True,
                message_id=str(msg_id),
            )

        except Exception as e:
            logger.error(f"Error sending location to chat {chat_id}: {e}")
            return SendResult(
                success=False,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Container-to-host file path mapping
    # ------------------------------------------------------------------
    # The Docker LLM sandbox mounts /workspace inside the container to
    #   ~/.hermes/sandboxes/docker/default/workspace/   on the host.
    # When the agent writes output files to /workspace/ and emits MEDIA
    # directives or bare paths, Hermes's path validator runs on the HOST
    # and can't find container-local paths.  These overrides remap any
    # /workspace/<rel> path to the host sandbox path, copy the file to
    # the Hermes documents cache (a validated safe root), and return the
    # cache path so the base-class validator accepts it.
    #
    # The same pattern works for any output file type (.pdf, .html, .zip,
    # .xdc, etc.) — just write to /workspace/ in the container.
    # ------------------------------------------------------------------

    @staticmethod
    def _container_workspace_to_host(container_path: str) -> Optional[str]:
        """Map a /workspace/<rel> container path to its host-side sandbox path."""
        return container_workspace_to_host(container_path)

    def _copy_container_file_to_cache(self, container_path: str) -> Optional[str]:
        """Copy a /workspace/ container file to the Hermes docs cache."""
        return copy_container_file_to_cache(container_path)

    def extract_media(self, content: str):
        """Extend base extract_media to also handle .xdc MEDIA tags."""
        from gateway.platforms.base import BasePlatformAdapter

        return _extract_media(content, BasePlatformAdapter.extract_media)

    def extract_local_files(self, content: str):
        """Extend base to also pick up bare /workspace/*.xdc paths."""
        from gateway.platforms.base import BasePlatformAdapter

        return _extract_local_files(content, BasePlatformAdapter.extract_local_files)

    def filter_media_delivery_paths(self, media_files):
        """Remap /workspace/ container paths to host cache before validation."""
        from gateway.platforms.base import BasePlatformAdapter

        return _filter_media_delivery_paths(media_files, BasePlatformAdapter.filter_media_delivery_paths)

    def filter_local_delivery_paths(self, file_paths):
        """Remap /workspace/ container paths to host cache before validation."""
        from gateway.platforms.base import BasePlatformAdapter

        return _filter_local_delivery_paths(file_paths, BasePlatformAdapter.filter_local_delivery_paths)

    async def _event_listener(self) -> None:
        """Listen for Delta Chat events and forward to Hermes."""
        consecutive_errors = 0
        while self._running:
            try:
                if self._rpc_client is None or not self._rpc_client.is_alive():
                    raise RuntimeError("RPC client is not alive")
                if self.account_id:
                    envelope = await self.rpc.get_next_event()
                    if envelope.get("context_id") == self.account_id:
                        await self._handle_dc_event(envelope.get("event", {}))
                consecutive_errors = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Event listener error ({consecutive_errors}): {e}")
                if consecutive_errors >= 3 and not self._reconnecting:
                    logger.warning("Triggering reconnect due to repeated event-loop errors")
                    asyncio.create_task(self._reconnect())
                    break
                await asyncio.sleep(1)

    async def _reconnect(self) -> bool:
        """Reconnect with exponential backoff."""
        if self._reconnecting:
            return False
        self._reconnecting = True
        logger.info("Delta Chat reconnecting...")
        try:
            await self.disconnect()
        except Exception as e:
            logger.debug(f"Disconnect during reconnect failed (non-fatal): {e}")
        try:
            for attempt in range(1, 6):
                logger.info(f"Reconnect attempt {attempt}/5")
                if await self.connect():
                    logger.info("Delta Chat reconnected successfully")
                    self._mark_connected()
                    return True
                wait = min(2**attempt, 30)
                logger.info(f"Reconnect attempt {attempt} failed; waiting {wait}s")
                await asyncio.sleep(wait)
            logger.error("Delta Chat reconnect failed after 5 attempts")
            self._mark_disconnected()
            return False
        finally:
            self._reconnecting = False

    async def _handle_dc_event(self, event: Dict[str, Any]) -> None:
        """Handle a Delta Chat event and convert to Hermes MessageEvent.

        Args:
            event: Delta Chat event dictionary
        """
        from deltachat2.types import EventType

        event_kind = event.get("kind")

        if event_kind == EventType.INCOMING_MSG:
            await self._handle_incoming_message(event)
        elif event_kind == EventType.MSG_DELIVERED:
            logger.debug(f"Message delivered: {event.get('msg_id')}")
        elif event_kind == EventType.MSG_FAILED:
            logger.warning(f"Message failed: {event.get('msg_id')}")
        elif event_kind == EventType.INCOMING_CALL:
            if self._call_manager:
                asyncio.create_task(self._call_manager.handle_incoming_call(event))
            else:
                logger.info("Incoming call ignored: voice calls disabled")
        elif event_kind == EventType.CALL_ENDED:
            if self._call_manager:
                asyncio.create_task(self._call_manager.handle_call_ended(event))
        elif event_kind == EventType.OUTGOING_CALL_ACCEPTED:
            if self._call_manager:
                asyncio.create_task(self._call_manager.handle_outgoing_call_accepted(event))
        elif event_kind == EventType.INCOMING_CALL_ACCEPTED:
            logger.info("Incoming call accepted msg_id=%s", event.get("msg_id"))
        else:
            logger.debug(f"Unhandled event type: {event_kind}")

    async def _handle_incoming_message(self, event: Dict[str, Any]) -> None:
        """Handle an incoming text message.

        Args:
            event: Delta Chat INCOMING_MSG event
        """
        try:
            chat_id = event.get("chat_id")
            msg_id = event.get("msg_id")

            if not chat_id or not msg_id:
                logger.warning(f"Invalid message event: {event}")
                return

            # Get message details via direct RPC
            msg = await self.rpc.get_message(
                self.account_id,
                int(msg_id),
            )
            if not msg:
                logger.warning(f"Could not retrieve message {msg_id}")
                return

            # Send read receipt immediately
            try:
                await self.rpc.markseen_msgs(self.account_id, [int(msg_id)])
            except Exception as e:
                logger.debug(f"Could not mark message {msg_id} as seen: {e}")

            text = msg.get("text", "")
            view_type = msg.get("view_type", "")
            has_file = bool(msg.get("file") or msg.get("file_mime"))
            # Route to non-text handler when viewtype is non-text OR when the
            # message has a file attachment even if DC reported viewType=Text
            # (happens for image+caption combos or pending downloads).
            if not text or view_type not in ("Text", "", None) or has_file:
                logger.info(
                    "Non-text message: view_type=%r text=%r file=%r file_mime=%r msg_id=%s",
                    view_type,
                    text[:80] if text else text,
                    msg.get("file"),
                    msg.get("file_mime"),
                    msg_id,
                )
                await self._handle_non_text_message(msg, chat_id, msg_id)
                return

            # Get chat info
            chat = await self.rpc.get_basic_chat_info(
                self.account_id,
                int(chat_id),
            )

            # Get sender info
            from_id = msg.get("from_id")
            if from_id:
                contact = await self.rpc.get_contact(
                    self.account_id,
                    int(from_id),
                )
                user_name = (
                    contact.get("name")
                    or contact.get("display_name")
                    or contact.get("name_and_addr")
                    or f"Contact {from_id}"
                )
                user_id = str(from_id)
            else:
                user_name = "Unknown"
                user_id = "unknown"

            # Determine chat type
            chat_type = "group" if chat.get("is_group", False) else "dm"
            chat_name = chat.get("name", f"Chat {chat_id}")

            # Build source
            source = self.build_source(
                chat_id=str(chat_id),
                chat_name=chat_name,
                chat_type=chat_type,
                user_id=user_id,
                user_name=user_name,
            )

            # Append chat token for dc_safe_rpc_call — skip on slash commands so
            # Hermes doesn't misparse the token as part of the command argument.
            if text.startswith("/"):
                text_with_token = text
            else:
                token = await get_or_create_chat_token(self.state.chat_tokens, self.rpc, self.account_id, int(chat_id))
                _register_chat_token(token, self)
                text_with_token = f"{text}\n[dc:chat={token}]"

            # Build and handle message event
            message_event = MessageEvent(
                text=text_with_token,
                message_type=MessageType.TEXT,
                source=source,
                message_id=str(msg_id),
            )
            await self.handle_message(message_event)

        except Exception as e:
            logger.error(f"Error handling message event: {e}")

    def _resolve_blob_path(self, filename: str) -> Optional[str]:
        """Resolve a DC file path to an accessible absolute path.

        The RPC returns whatever path DC core has internally, which may be
        absolute already or relative to the blob directory. Try in order:
        the path as-is, then <dc_config_dir>/blobs/<basename>.
        """
        if not filename:
            return None
        if os.path.exists(filename):
            logger.debug("Blob path exists as-is: %s", filename)
            return filename
        blob_path = os.path.join(self._get_dc_config_dir(), "blobs", os.path.basename(filename))
        if os.path.exists(blob_path):
            logger.debug("Blob path resolved via blobs dir: %s", blob_path)
            return blob_path
        logger.warning("Media file not found at %r or %r", filename, blob_path)
        return None

    def _copy_to_hermes_cache(self, src: str, kind: str) -> str:
        """Copy a DC blob file into the Hermes cache directory and return the new path.

        DC blob paths are not mounted inside the Docker LLM backend, so files
        must live under ~/.hermes/cache/* for STT and vision to reach them.
        Returns the original path on failure so the caller still has something.
        """
        try:
            ext = os.path.splitext(src)[1] or ""
            data = open(src, "rb").read()
            if kind == "audio":
                from gateway.platforms.base import cache_audio_from_bytes

                dest = cache_audio_from_bytes(data, ext=ext or ".ogg")
            elif kind == "image":
                from gateway.platforms.base import cache_image_from_bytes

                dest = cache_image_from_bytes(data, ext=ext or ".jpg")
            else:
                return src
            logger.info("Copied %s blob to Hermes cache: %s -> %s", kind, src, dest)
            return dest
        except Exception as e:
            logger.warning("Could not copy %s to Hermes cache: %s", src, e, exc_info=True)
        return src

    async def _handle_non_text_message(self, msg: Dict, chat_id: str, msg_id: str) -> None:
        """Handle non-text messages (files, images, audio, etc.).

        Args:
            msg: Delta Chat message dictionary (AttrDict — keys already snake_case)
            chat_id: Chat ID (string representation)
            msg_id: Message ID (string representation)
        """
        # AttrDict converts viewType → view_type
        view_type = msg.get("view_type", "")
        filename = msg.get("file", "")
        file_mime = msg.get("file_mime", "") or ""

        # If the file isn't available yet (auto-download still in progress),
        # trigger download_full_message and re-fetch once before proceeding.
        if not filename and view_type not in ("Text", "", None):
            logger.info(
                "_handle_non_text_message: file not ready, triggering download for msg %s",
                msg_id,
            )
            try:
                await self.rpc.download_full_message(self.account_id, int(msg_id))
                await asyncio.sleep(2)
                msg = await self.rpc.get_message(self.account_id, int(msg_id))
                filename = msg.get("file", "")
                file_mime = msg.get("file_mime", "") or ""
                view_type = msg.get("view_type", "")
                logger.info(
                    "_handle_non_text_message: after download: file=%r view_type=%r",
                    filename,
                    view_type,
                )
            except Exception as e:
                logger.warning("_handle_non_text_message: download_full_message failed: %s", e)

        filename_preview = filename[:100] if filename else None
        logger.info(
            "_handle_non_text_message: view_type=%s, chat_id=%s, msg_id=%s, filename=%s",
            view_type,
            chat_id,
            msg_id,
            filename_preview,
        )

        # Resolve sender and chat info (shared by all branches)
        from_id = msg.get("from_id")
        user_name = f"Contact {from_id}" if from_id else "Unknown"
        user_id = str(from_id) if from_id else "unknown"
        try:
            if from_id:
                contact = await self.rpc.get_contact(self.account_id, int(from_id))
                user_name = (
                    contact.get("name") or contact.get("display_name") or contact.get("name_and_addr") or user_name
                )
        except Exception:
            pass

        chat_name = f"Chat {chat_id}"
        chat_type = "dm"
        try:
            chat = await self.rpc.get_basic_chat_info(self.account_id, int(chat_id))
            chat_name = chat.get("name", chat_name)
            chat_type = "group" if chat.get("is_group", False) else "dm"
        except Exception:
            pass

        source = self.build_source(
            chat_id=str(chat_id),
            chat_name=chat_name,
            chat_type=chat_type,
            user_id=user_id,
            user_name=user_name,
        )

        token = await get_or_create_chat_token(self.state.chat_tokens, self.rpc, self.account_id, int(chat_id))
        _register_chat_token(token, self)

        from deltachat2.types import MessageViewtype

        # DC sometimes reports viewType=Text for image+caption messages.
        # Infer the real type from file_mime when that happens.
        if view_type in ("Text", "", None) and filename and file_mime:
            if file_mime.startswith("image/"):
                view_type = MessageViewtype.IMAGE.value
            elif file_mime.startswith("audio/"):
                view_type = MessageViewtype.AUDIO.value
            elif file_mime.startswith("video/"):
                view_type = MessageViewtype.VIDEO.value

        # Voice / Audio — let Hermes handle STT via media_urls
        if view_type in (MessageViewtype.VOICE.value, MessageViewtype.AUDIO.value) and filename:
            resolved = self._resolve_blob_path(filename)
            if resolved:
                resolved = self._copy_to_hermes_cache(resolved, "audio")
            is_voice = view_type == MessageViewtype.VOICE.value
            hermes_type = MessageType.VOICE if is_voice else MessageType.AUDIO
            caption = msg.get("text", "") or ""
            text = f"[{'Voice' if is_voice else 'Audio'} message from {user_name}]"
            if caption:
                text = f"{text}: {caption}"
            text = f"{text}\n[dc:chat={token}]"
            if not resolved:
                logger.warning(f"Voice/audio file not found, forwarding without media: {filename}")
            message_event = MessageEvent(
                text=text,
                message_type=hermes_type,
                source=source,
                message_id=str(msg_id),
                media_urls=[resolved] if resolved else [],
                media_types=[file_mime or ("audio/ogg" if is_voice else "audio/mpeg")],
            )
            await self.handle_message(message_event)

        # Image
        elif (
            view_type
            in (
                MessageViewtype.IMAGE.value,
                MessageViewtype.GIF.value,
                MessageViewtype.STICKER.value,
            )
            and filename
        ):
            resolved = self._resolve_blob_path(filename)
            if resolved:
                resolved = self._copy_to_hermes_cache(resolved, "image")
            caption = msg.get("text", "") or ""
            text = f"[Image from {user_name}]"
            if caption:
                text = f"{text}: {caption}"
            text = f"{text}\n[dc:chat={token}]"
            message_event = MessageEvent(
                text=text,
                message_type=MessageType.PHOTO,
                source=source,
                message_id=str(msg_id),
                media_urls=[resolved] if resolved else [],
                media_types=[file_mime or "image/jpeg"],
            )
            await self.handle_message(message_event)

        # File / document (including .xdc webxdc apps)
        elif view_type in (MessageViewtype.FILE.value, MessageViewtype.VIDEO.value) and filename:
            resolved = self._resolve_blob_path(filename)
            if resolved:
                try:
                    from gateway.platforms.base import cache_document_from_bytes

                    data = open(resolved, "rb").read()
                    file_name = msg.get("file_name") or os.path.basename(resolved)
                    resolved = cache_document_from_bytes(data, file_name)
                    logger.info("Copied document to Hermes cache: %s", resolved)
                except Exception as e:
                    logger.warning("Could not copy document to Hermes cache: %s", e)
            caption = msg.get("text", "") or ""
            file_name = msg.get("file_name") or os.path.basename(filename)
            text = f"[File from {user_name}: {file_name}]"
            if caption:
                text = f"{text}: {caption}"
            text = f"{text}\n[dc:chat={token}]"
            message_event = MessageEvent(
                text=text,
                message_type=MessageType.DOCUMENT,
                source=source,
                message_id=str(msg_id),
                media_urls=[resolved] if resolved else [],
                media_types=[file_mime or "application/octet-stream"],
            )
            await self.handle_message(message_event)

        elif view_type == "Call":
            # DC sends a Call info message (Missed call / Call ended) after calls.
            # The actual call is handled via IncomingCall/CallEnded events — ignore this.
            logger.debug("Ignoring Call info message msg_id=%s text=%r", msg_id, msg.get("text"))

        else:
            logger.debug(f"Unhandled view_type={view_type}, file={filename}")

    async def _handle_audio_message_UNUSED(self, msg: Dict, chat_id: str, msg_id: str, filename: str) -> None:
        # KEPT FOR REFERENCE ONLY — superseded by _handle_non_text_message
        # which emits MessageType.VOICE/AUDIO with media_urls and lets Hermes STT handle it.
        """Handle audio/voice message by transcribing and forwarding as text.

        Args:
            msg: Delta Chat message dictionary
            chat_id: Chat ID (string representation)
            msg_id: Message ID (string representation)
            filename: Local filepath to audio file
        """
        import os

        logger.info(f"_handle_audio_message START: chat_id={chat_id}, msg_id={msg_id}, filename={filename}")
        logger.info(f"Original filename: {filename}")
        logger.info(f"File exists at original path: {os.path.exists(filename)}")
        if filename:
            logger.info(f"Absolute path: {os.path.abspath(filename)}")
            logger.info(f"Filename basename: {os.path.basename(filename)}")
        logger.info(
            "Message data: msg_type=%s, from_id=%s, timestamp=%s",
            msg.get("msg_type"),
            msg.get("from_id"),
            msg.get("timestamp"),
        )

        if not filename:
            logger.warning("_handle_audio_message: No filename in audio message, cannot process")
            return

        # For Delta Chat, the file might be in blob directory
        if not os.path.exists(filename):
            logger.info("_handle_audio_message: File not at original path, searching blob directory...")
            dc_blob_dir = os.path.join(self._get_dc_config_dir(), "blobs")
            logger.info(f"Blob directory: {dc_blob_dir}, exists: {os.path.exists(dc_blob_dir)}")
            if os.path.exists(dc_blob_dir):
                blob_path = os.path.join(dc_blob_dir, os.path.basename(filename))
                logger.info(f"Trying blob path: {blob_path}, exists: {os.path.exists(blob_path)}")
                if os.path.exists(blob_path):
                    filename = blob_path
                    logger.info(f"Found file in blob dir: {filename}")
                else:
                    blob_path_no_ext = os.path.join(dc_blob_dir, os.path.splitext(os.path.basename(filename))[0])
                    logger.info(
                        f"Trying blob path (no ext): {blob_path_no_ext}, exists: {os.path.exists(blob_path_no_ext)}"
                    )
                    if os.path.exists(blob_path_no_ext):
                        filename = blob_path_no_ext
                        logger.info(f"Found file in blob dir (no ext): {filename}")

        if not os.path.exists(filename):
            logger.error(f"_handle_audio_message: Audio file not found at any location: {filename}")
            logger.error("_handle_audio_message: Cannot transcribe - file unavailable")
            # Still notify about the voice message
            from_id = msg.get("from_id")
            user_name = f"Contact {from_id}" if from_id else "Unknown"
            chat_type = "group" if msg.get("is_group", False) else "dm"
            try:
                chat = await self.rpc.get_basic_chat_info(self.account_id, int(chat_id))
                chat_name = chat.get("name", f"Chat {chat_id}")
            except Exception:
                chat_name = f"Chat {chat_id}"
            source = self.build_source(
                chat_id=str(chat_id),
                chat_name=chat_name,
                chat_type=chat_type,
                user_id=str(from_id) if from_id else "unknown",
                user_name=user_name,
            )
            from gateway.platforms.base import MessageEvent, MessageType

            message_event = MessageEvent(
                text=f"[Voice message from {user_name}]",
                message_type=MessageType.TEXT,
                source=source,
                message_id=str(msg_id),
                metadata={"chat_id": str(chat_id), "msg_type": "voice"},
            )
            logger.info("_handle_audio_message: Forwarding notification message (no file)")
            await self.handle_message(message_event)
            return

        # File exists - get stats
        file_size = os.path.getsize(filename)
        logger.info(f"_handle_audio_message: Audio file found: {filename}, size={file_size} bytes")
        logger.info(f"_handle_audio_message: Transcribing audio message: {filename}")

        # Get sender info
        from_id = msg.get("from_id")
        if from_id:
            try:
                contact = await self.rpc.get_contact(self.account_id, int(from_id))
                user_name = (
                    contact.get("name")
                    or contact.get("display_name")
                    or contact.get("name_and_addr")
                    or f"Contact {from_id}"
                )
            except Exception:
                user_name = f"Contact {from_id}"
        else:
            user_name = "Unknown"

        # Get chat info
        chat_name = ""
        try:
            chat = await self.rpc.get_basic_chat_info(self.account_id, int(chat_id))
            chat_name = chat.get("name", f"Chat {chat_id}")
        except Exception:
            chat_name = f"Chat {chat_id}"

        # Try to transcribe
        transcribed_text = None
        transcription_attempted = False
        logger.info("_handle_audio_message: Checking for LLM transcription capability...")
        try:
            # Try Hermes STT
            try:
                from gateway.llm import llm

                logger.info(f"_handle_audio_message: llm module imported, type={type(llm)}")
                has_transcribe = hasattr(llm, "transcribe_audio_file")
                logger.info(f"_handle_audio_message: llm.transcribe_audio_file available: {has_transcribe}")
                if has_transcribe:
                    transcription_attempted = True
                    logger.info("_handle_audio_message: Calling llm.transcribe_audio_file...")
                    transcription_result = await llm.transcribe_audio_file(filename)
                    logger.info(f"_handle_audio_message: Transcription result: {transcription_result}")
                    if transcription_result and transcription_result.get("text"):
                        transcribed_text = transcription_result["text"]
                        logger.info(
                            f"_handle_audio_message: Transcribed text (first 200 chars): {transcribed_text[:200]}"
                        )
                    else:
                        logger.warning("_handle_audio_message: Transcription returned empty or no text field")
                else:
                    logger.warning("_handle_audio_message: LLM does NOT have transcribe_audio_file method")
            except Exception as e:
                import traceback

                logger.warning(f"_handle_audio_message: llm.transcribe_audio_file failed: {e}")
                logger.debug(f"_handle_audio_message: llm.transcribe_audio_file traceback:\n{traceback.format_exc()}")
        except Exception as e:
            import traceback

            logger.warning(f"_handle_audio_message: Transcription outer exception: {e}")
            logger.debug(f"_handle_audio_message: Transcription traceback:\n{traceback.format_exc()}")

        # Build response
        chat_type = "group" if msg.get("is_group", False) else "dm"
        source = self.build_source(
            chat_id=str(chat_id),
            chat_name=chat_name,
            chat_type=chat_type,
            user_id=str(from_id) if from_id else "unknown",
            user_name=user_name,
        )

        from gateway.platforms.base import MessageEvent, MessageType

        if transcribed_text:
            full_text = f"[Voice message from {user_name}]: {transcribed_text}"
            logger.info("_handle_audio_message: SUCCESS - voice message transcribed and will be forwarded")
        else:
            full_text = f"[Voice message from {user_name}]"
            if transcription_attempted:
                logger.warning("_handle_audio_message: Transcription attempted but returned no text")
            else:
                logger.warning(
                    "_handle_audio_message: NO TRANSCRIPTION - "
                    "llm.transcribe_audio_file not available, file will be forwarded as notification only"
                )

        logger.debug(f"_handle_audio_message: Final message text: {full_text[:150]}")
        message_event = MessageEvent(
            text=full_text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=str(msg_id),
            metadata={
                "chat_id": str(chat_id),
                "from_id": str(from_id) if from_id else "unknown",
                "filename": filename,
                "msg_type": "voice",
                "timestamp": msg.get("timestamp"),
                "transcribed": transcribed_text is not None,
                "file_size": file_size,
            },
        )
        logger.info("_handle_audio_message: Forwarding message to Hermes...")
        await self.handle_message(message_event)
        logger.info("_handle_audio_message: COMPLETE - Audio message handled successfully")

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get metadata for a chat.

        Args:
            chat_id: Delta Chat chat ID

        Returns:
            Dictionary with chat info (name, type, etc.)
        """
        try:
            if self.rpc and self.account_id:
                chat = await self.rpc.get_basic_chat_info(
                    self.account_id,
                    int(chat_id),
                )
                return {
                    "name": chat.get("name", chat_id),
                    "type": "group" if chat.get("is_group") else "dm",
                }
        except Exception as e:
            logger.warning(f"Error getting chat info for {chat_id}: {e}")
        return {"name": chat_id, "type": "dm"}

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        """Delete a message from a Delta Chat chat.

        Args:
            chat_id: Delta Chat chat ID
            message_id: Message ID to delete

        Returns:
            True if deletion successful, False otherwise
        """
        try:
            if self.rpc and self.account_id:
                await self.rpc.delete_messages(
                    self.account_id,
                    [int(message_id)],
                )
                logger.debug(f"Deleted message {message_id} from chat {chat_id}")
                return True
        except Exception as e:
            logger.error(f"Error deleting message {message_id} from chat {chat_id}: {e}")
            return False
        return False


def check_requirements() -> bool:
    """Check if deltachat2 and deltachat-rpc-server are available."""
    import shutil

    # Check Python package
    try:
        import deltachat2
    except ImportError:
        return False

    # Check binary
    rpc_server = os.getenv("DELTACHAT_RPC_SERVER", "deltachat-rpc-server")
    if shutil.which(rpc_server):
        return True

    return False


def validate_config(config) -> bool:
    """Validate platform configuration."""
    return check_requirements()


def _env_enablement() -> Optional[Dict[str, Any]]:
    """Seed PlatformConfig from environment variables."""
    import shutil

    rpc_server = os.getenv("DELTACHAT_RPC_SERVER", "deltachat-rpc-server").strip()

    # Check if binary exists
    if not shutil.which(rpc_server):
        # Try without path
        if shutil.which("deltachat-rpc-server"):
            rpc_server = "deltachat-rpc-server"
        else:
            return None

    result = {"rpc_server": rpc_server}

    # Add home channel if set
    home_channel = os.getenv("DELTACHAT_HOME_CHANNEL")
    if home_channel:
        result["home_channel"] = {
            "chat_id": home_channel,
            "name": "Home",
        }

    return result


def register_platform(ctx):
    """Register Delta Chat platform adapter with Hermes."""
    ctx.register_platform(
        name="deltachat-platform",
        label="Delta Chat",
        adapter_factory=lambda cfg: DeltaChatAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        required_env=["DELTACHAT_RPC_SERVER"],
        env_enablement_fn=_env_enablement,
        cron_deliver_env_var="DELTACHAT_HOME_CHANNEL",
        emoji="💬",
        platform_hint=(
            "You are chatting via Delta Chat. "
            "Delta Chat does NOT support markdown formatting or message editing. "
            "Messages longer than 40 lines will be automatically formatted with HTML. "
            "For very long content, consider sending as a document file instead. "
            "You CAN send voice messages (use send_voice tool), videos, images, files, "
            "and delete messages. "
            "When a user sends a voice message, it is automatically transcribed — "
            "just respond to the transcribed content normally. "
            "Location messages can be sent to share points of interest on a map. "
            "You CAN build and send webxdc mini apps and other files (PDF, HTML, etc.). "
            "MANDATORY: before attempting to build any webxdc app, you MUST first call "
            "skill_view('plugin:deltachat-platform:webxdc-converter') to load the build instructions. "
            "For file delivery from the Docker sandbox: write output files to /workspace/ (NOT /tmp/), "
            "then use a MEDIA directive — e.g. 'MEDIA:/workspace/app.xdc'. "
            "The adapter maps /workspace/ paths to the host and sends via send_document. "
            "DC core auto-detects .xdc as webxdc — just send it as a regular file. "
            "Each message ends with a [dc:chat=<token>] metadata tag. "
            "IGNORE this tag during normal conversation — it is only needed if you call dc_safe_rpc_call. "
            "Do NOT call dc_safe_rpc_call, dc_chat_rpc_spec, or dc_rpc_spec unless the user explicitly "
            "asks for a Delta Chat-specific operation that cannot be done with the standard tools."
        ),
        max_message_length=3200,
    )

    # Register bundled skills so skill_view('deltachat-platform:<name>') resolves them.
    from pathlib import Path as _Path

    skills_dir = _Path(_plugin_dir) / "skills"
    logger.info(f"Checking for skills in: {skills_dir}")
    if skills_dir.is_dir():
        for skill_dir in skills_dir.iterdir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.is_file():
                try:
                    ctx.register_skill(skill_dir.name, skill_md)
                    logger.info("Registered plugin skill: %s from %s", skill_dir.name, skill_md)
                except Exception as e:
                    logger.warning("Could not register skill %s: %s", skill_dir.name, e)
    else:
        logger.warning("Skills directory not found: %s", skills_dir)
