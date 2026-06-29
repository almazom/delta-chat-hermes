"""Opaque chat token mapping for the Delta Chat Hermes adapter."""

import logging
import secrets
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("hermes_plugins.deltachat.tokens")


# Methods that mutate or destroy chat data — blocked from dc_safe_rpc_call.
DESTRUCTIVE_METHODS = frozenset({
    "delete_chat",
    "delete_messages",
    "delete_messages_for_all",
    "remove_contact_from_chat",
    "remove_draft",
    "leave_group",
})


@dataclass
class ChatTokenStore:
    """Per-adapter in-memory token cache."""
    chat_id_to_token: Dict[int, str] = field(default_factory=dict)
    chat_token_to_id: Dict[str, int] = field(default_factory=dict)


async def get_or_create_chat_token(
    store: ChatTokenStore, rpc, account_id: int, chat_id: int
) -> str:
    """Return a stable opaque token for *chat_id* scoped to *store*."""
    if chat_id in store.chat_id_to_token:
        return store.chat_id_to_token[chat_id]

    dc_key = f"ui.hermes.chat_token.{chat_id}"
    try:
        existing = await rpc.get_config(account_id, dc_key)
    except Exception:
        existing = None

    if existing:
        token = existing
    else:
        token = secrets.token_hex(8)
        try:
            await rpc.set_config(account_id, dc_key, token)
            await rpc.set_config(account_id, f"ui.hermes.token_chat.{token}", str(chat_id))
        except Exception as e:
            logger.warning("Could not persist chat token to DC config: %s", e)

    store.chat_id_to_token[chat_id] = token
    store.chat_token_to_id[token] = chat_id
    return token


async def resolve_chat_token(
    store: ChatTokenStore, rpc, account_id: int, token: str
) -> Optional[int]:
    """Resolve an opaque token back to the real chat_id scoped to *store*."""
    if token in store.chat_token_to_id:
        return store.chat_token_to_id[token]

    dc_key = f"ui.hermes.token_chat.{token}"
    try:
        chat_id_str = await rpc.get_config(account_id, dc_key)
    except Exception:
        chat_id_str = None

    if chat_id_str:
        chat_id = int(chat_id_str)
        store.chat_token_to_id[token] = chat_id
        store.chat_id_to_token[chat_id] = token
        return chat_id

    return None
