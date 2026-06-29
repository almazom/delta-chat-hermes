"""Delta Chat RPC tools for the Hermes adapter."""

import asyncio
import json
import logging
import os
from typing import Any, Callable, Optional

from chat_tokens import DESTRUCTIVE_METHODS, resolve_chat_token

logger = logging.getLogger("hermes_plugins.deltachat.tools")

# Type alias: resolve an opaque chat_token to the adapter that owns it.
AdapterResolver = Callable[[Optional[str]], Optional[Any]]
DefaultAdapterGetter = Callable[[], Optional[Any]]

# Explicit allowlist of read-only, chat-scoped RPC methods for dc_safe_rpc_call.
# Defense-in-depth: DESTRUCTIVE_METHODS and delete_/remove_ prefixes are still blocked.
SAFE_CHAT_METHODS = frozenset(
    {
        "get_basic_chat_info",
        "get_chat_contacts",
        "get_chat_description",
        "get_chat_encryption_info",
        "get_chat_ephemeral_timer",
        "get_chat_media",
        "get_chat_securejoin_qr_code",
        "get_chat_securejoin_qr_code_svg",
        "get_draft",
        "get_first_unread_message_of_chat",
        "get_fresh_msg_cnt",
        "get_full_chat_by_id",
        "get_locations",
        "get_message_ids",
        "get_message_list_items",
        "get_past_chat_contacts",
        "get_similar_chat_ids",
        "is_chat_muted",
        "is_sending_locations_to_chat",
        "can_send",
        "search_messages",
    }
)


async def _fetch_spec(rpc_server_path: str, spec_cache: Optional[dict]) -> dict:
    """Fetch and cache the OpenRPC spec from deltachat-rpc-server --openrpc."""
    if spec_cache is not None:
        return spec_cache
    proc = await asyncio.create_subprocess_exec(
        rpc_server_path,
        "--openrpc",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"deltachat-rpc-server --openrpc failed: {stderr.decode().strip()}")
    return json.loads(stdout.decode())


def _build_params(
    method_entry: dict,
    account_id: Any,
    chat_id: Any,
    user_params: list,
) -> list:
    """Build positional params by inserting accountId/chatId at their spec positions.

    This avoids hard-coding chatId at index 1, which is wrong for methods such as
    search_messages whose parameter order is (accountId, query, chatId, ...).
    """
    param_names = [p["name"] for p in method_entry.get("params", [])]
    full_params = [None] * len(param_names)
    user_iter = iter(user_params or [])
    for idx, name in enumerate(param_names):
        if name == "accountId":
            full_params[idx] = account_id
        elif name == "chatId":
            full_params[idx] = chat_id
        else:
            try:
                full_params[idx] = next(user_iter)
            except StopIteration:
                break
    return full_params


def register_rpc_tools(
    ctx,
    resolve_adapter: AdapterResolver,
    get_default_adapter: Optional[DefaultAdapterGetter] = None,
) -> None:
    """Register Delta Chat RPC tools once, dispatching to the right adapter at runtime.

    Tools that operate on a chat (dc_safe_rpc_call, dc_start_call, dc_end_call)
    resolve the adapter from the chat_token. Spec tools resolve the default adapter.
    This avoids the last-connected-profile overwriting tool handlers in a
    multi-profile Hermes process.
    """
    get_default_adapter = get_default_adapter or (lambda: None)

    def _current_adapter_for_token(chat_token: Optional[str]) -> Optional[Any]:
        adapter = resolve_adapter(chat_token)
        if adapter is None and not chat_token:
            adapter = get_default_adapter()
        return adapter

    async def _get_spec(adapter: Any) -> dict:
        if adapter.state.spec_cache is None:
            rpc_server_path = adapter._get_rpc_server_path()
            adapter.state.spec_cache = await _fetch_spec(rpc_server_path, None)
        return adapter.state.spec_cache

    async def _spec_handler(args: dict = None, **kwargs) -> str:
        adapter = get_default_adapter()
        if adapter is None or adapter.rpc is None:
            return json.dumps({"error": "Delta Chat is not connected"})
        try:
            return json.dumps(await _get_spec(adapter), indent=2)
        except Exception as e:
            return f"Error: {e}"

    async def _chat_spec_handler(args: dict = None, **kwargs) -> str:
        adapter = get_default_adapter()
        if adapter is None or adapter.rpc is None:
            return json.dumps({"error": "Delta Chat is not connected"})
        try:
            spec = await _get_spec(adapter)
        except Exception as e:
            return f"Error: {e}"
        safe_methods = [
            m
            for m in spec.get("methods", [])
            if m["name"] in SAFE_CHAT_METHODS and any(p["name"] == "chatId" for p in m.get("params", []))
        ]
        return json.dumps({**spec, "methods": safe_methods}, indent=2)

    async def _call_handler(args: dict, **kwargs) -> str:
        method = (args or {}).get("method")
        params = (args or {}).get("params") or []
        if not method or not isinstance(method, str):
            return json.dumps({"error": "Missing 'method' (snake_case RPC name)."})
        adapter = get_default_adapter()
        if adapter is None or adapter.rpc is None:
            return json.dumps({"error": "Delta Chat is not connected"})
        try:
            result = await getattr(adapter.rpc, method)(*params)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _safe_call_handler(args: dict, **kwargs) -> Any:
        method = (args or {}).get("method")
        chat_token = (args or {}).get("chat_token")
        params = (args or {}).get("params") or []
        if not method or not isinstance(method, str):
            return json.dumps({"error": "Missing 'method' (snake_case RPC name). Use dc_chat_rpc_spec to find one."})

        adapter = _current_adapter_for_token(chat_token)
        if chat_token and adapter is None:
            return json.dumps({"error": "Unknown chat_token — use the [dc:chat=...] value from your message"})
        if adapter is None or adapter.rpc is None:
            return json.dumps({"error": "Delta Chat is not connected"})

        # Reject disallowed methods before spending an RPC round-trip on token resolution.
        if (
            method not in SAFE_CHAT_METHODS
            or method in DESTRUCTIVE_METHODS
            or method.startswith("delete_")
            or method.startswith("remove_")
        ):
            return json.dumps(
                {"error": f"'{method}' is not allowed in safe mode — use dc_rpc_spec for unrestricted access"}
            )

        store = adapter.state.chat_tokens
        real_chat_id = await resolve_chat_token(store, adapter.rpc, adapter.account_id, chat_token)
        if real_chat_id is None:
            return json.dumps({"error": "Unknown chat_token — use the [dc:chat=...] value from your message"})

        try:
            spec = await _get_spec(adapter)
        except Exception as e:
            return json.dumps({"error": f"Could not fetch spec: {e}"})

        method_entry = next((m for m in spec.get("methods", []) if m["name"] == method), None)
        if method_entry is None:
            return json.dumps(
                {"error": f"Unknown method '{method}' — use dc_chat_rpc_spec to browse available methods"}
            )

        param_names = [p["name"] for p in method_entry.get("params", [])]
        if "chatId" not in param_names:
            return json.dumps({"error": f"'{method}' has no chatId parameter — use dc_rpc_call for non-chat methods"})

        full_params = _build_params(method_entry, adapter.account_id, real_chat_id, params)

        try:
            result = await getattr(adapter.rpc, method)(*full_params)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _end_call_handler(args: dict, **kwargs) -> str:
        args = args or {}
        chat_token = args.get("chat_token")
        adapter = _current_adapter_for_token(chat_token)
        if chat_token and adapter is None:
            return json.dumps({"error": "Unknown chat_token — use the [dc:chat=...] value from your message"})
        if adapter is None or adapter._call_manager is None:
            return json.dumps({"error": "No active call"})

        store = adapter.state.chat_tokens
        real_chat_id = await resolve_chat_token(store, adapter.rpc, adapter.account_id, chat_token)
        if real_chat_id is None:
            return json.dumps({"error": "Unknown chat_token — use the [dc:chat=...] value from your message"})

        if str(real_chat_id) not in adapter._call_manager.active_chat_ids():
            return json.dumps({"error": "No active call for this chat"})

        success = await adapter._call_manager.request_hangup(str(real_chat_id))
        if success:
            return json.dumps({"success": True, "message": "Call ended"})
        return json.dumps({"error": "Failed to end call"})

    async def _start_call_handler(args: dict, **kwargs) -> str:
        args = args or {}
        chat_token = args.get("chat_token")
        opening = (args.get("opening") or args.get("topic") or "").strip()
        adapter = _current_adapter_for_token(chat_token)
        if chat_token and adapter is None:
            return json.dumps({"error": "Unknown chat_token — use the [dc:chat=...] value"})
        if adapter is None or adapter._call_manager is None:
            return json.dumps({"error": "Delta Chat not connected"})

        if not opening:
            return json.dumps({"error": "Provide 'opening' — the exact words to say when they pick up."})

        store = adapter.state.chat_tokens
        real_chat_id = await resolve_chat_token(store, adapter.rpc, adapter.account_id, chat_token)
        if real_chat_id is None:
            return json.dumps({"error": "Unknown chat_token — use the [dc:chat=...] value"})

        chat_id_str = str(real_chat_id)
        if chat_id_str in adapter._call_manager.active_chat_ids():
            return json.dumps({"error": "A call is already active for this chat"})

        try:
            msg_id = await adapter._call_manager.start_call(chat_id_str, opening=opening)
            return json.dumps(
                {
                    "success": True,
                    "msg_id": msg_id,
                    "message": ("Call connected — the opening line is being " "spoken and the conversation is live."),
                }
            )
        except asyncio.TimeoutError:
            return json.dumps({"error": "Call was not answered"})
        except Exception as e:
            logger.error("start_call failed: %s", e, exc_info=True)
            return json.dumps({"error": f"Failed to start call: {e}"})

    ctx.register_tool(
        name="dc_rpc_spec",
        toolset="deltachat",
        schema={
            "description": (
                "Fetch the full OpenRPC specification of the running Delta Chat RPC server. "
                "Lists every available method with parameter types and descriptions. "
                "Only call this when the user explicitly asks for low-level Delta Chat API access. "
                "Use dc_chat_rpc_spec instead when you only need chat-scoped methods."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
        handler=_spec_handler,
        is_async=True,
        emoji="📋",
    )

    ctx.register_tool(
        name="dc_chat_rpc_spec",
        toolset="deltachat",
        schema={
            "description": (
                "Fetch the OpenRPC spec filtered to methods that accept a chatId parameter, "
                "excluding all destructive operations. "
                "Only call this when you are about to use dc_safe_rpc_call for an explicit user request "
                "that cannot be handled by normal messaging tools."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
        handler=_chat_spec_handler,
        is_async=True,
        emoji="📋",
    )

    if os.getenv("DELTACHAT_ENABLE_RAW_RPC"):
        logger.warning(
            "DELTACHAT_ENABLE_RAW_RPC is set: dc_rpc_call grants unrestricted RPC access. "
            "Only enable in trusted debugging contexts."
        )
        ctx.register_tool(
            name="dc_rpc_call",
            toolset="deltachat",
            schema={
                "description": (
                    "Call any Delta Chat RPC method directly by name and params. "
                    "Use dc_rpc_spec first to see available methods. "
                    "CAUTION: unrestricted access — can modify or delete account data. "
                    "Prefer dc_safe_rpc_call for chat-scoped operations."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": (
                                "RPC method name in snake_case (e.g. 'get_account_info'). "
                                "Use dc_rpc_spec to see all available methods."
                            ),
                        },
                        "params": {
                            "type": "array",
                            "description": "Full positional parameters. account_id is always 1.",
                            "default": [],
                        },
                    },
                    "required": ["method"],
                },
            },
            handler=_call_handler,
            is_async=True,
            emoji="⚡",
        )

    ctx.register_tool(
        name="dc_safe_rpc_call",
        toolset="deltachat",
        schema={
            "description": (
                "Call a chat-scoped Delta Chat RPC method safely. "
                "Only use this when the user explicitly asks for a Delta Chat-specific operation "
                "that cannot be done with the normal send, send_file, send_voice, or delete_message tools. "
                "Do NOT call this for routine message handling, reading messages, or sending replies — "
                "those go through the standard tools. "
                "accountId and chatId are injected automatically from the chat_token. "
                "Destructive methods are blocked. Use dc_chat_rpc_spec first to find the method name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": (
                            "RPC method name in snake_case (e.g. 'get_chat_contacts'). "
                            "Must accept chatId. Use dc_chat_rpc_spec to browse available methods."
                        ),
                    },
                    "chat_token": {
                        "type": "string",
                        "description": (
                            "The opaque chat token from the [dc:chat=...] line "
                            "in the current message. Never use a token from a different conversation."
                        ),
                    },
                    "params": {
                        "type": "array",
                        "description": (
                            "Extra positional parameters after accountId and chatId. "
                            "accountId (always 1) and chatId are injected automatically."
                        ),
                        "default": [],
                    },
                },
                "required": ["method", "chat_token"],
            },
        },
        handler=_safe_call_handler,
        is_async=True,
        emoji="🔒",
    )

    ctx.register_tool(
        name="dc_end_call",
        toolset="deltachat",
        schema={
            "description": (
                "End the active voice call. "
                "The goodbye message is spoken first (via normal send), then this "
                "tool waits until TTS finishes playing before disconnecting. "
                "Only use this when the user explicitly says goodbye or asks to end the call. "
                "Identify the call to end with the chat_token from the active chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_token": {
                        "type": "string",
                        "description": (
                            "The opaque chat token from the [dc:chat=...] line in a message "
                            "from the active call. Never use a token from another conversation."
                        ),
                    },
                },
                "required": ["chat_token"],
            },
        },
        handler=_end_call_handler,
        is_async=True,
        emoji="📞",
    )

    ctx.register_tool(
        name="dc_start_call",
        toolset="deltachat",
        schema={
            "description": (
                "Place an outgoing voice call to a Delta Chat contact and talk to them. "
                "Use this to proactively call someone — e.g. from a scheduled/cron task "
                "(a reminder, an alert, a check-in). Creates the WebRTC offer, rings the "
                "contact, and blocks until they answer (or times out if unanswered). "
                "Once connected you speak normally; the conversation runs like an incoming "
                "call. Identify the recipient with the chat_token from one of their messages."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_token": {
                        "type": "string",
                        "description": (
                            "The opaque chat token from the [dc:chat=...] line in a message "
                            "from the person to call. Never use a token from another conversation."
                        ),
                    },
                    "opening": {
                        "type": "string",
                        "description": (
                            "The EXACT words to say the instant they pick up "
                            '(e.g. "Hi Simon, quick reminder to take your medication."). '
                            "Synthesized while the phone is still ringing and played "
                            "immediately on answer — no startup delay. Write it as natural "
                            "speech, not a topic label."
                        ),
                    },
                },
                "required": ["chat_token", "opening"],
            },
        },
        handler=_start_call_handler,
        is_async=True,
        emoji="📞",
    )
