"""Delta Chat platform plugin for Hermes Agent."""

from pathlib import Path

# Import adapter registration
from .adapter import register_platform, register_rpc_tools, _store_tool_ctx


def register(ctx):
    """Register Delta Chat platform adapter and bundled skills."""
    _store_tool_ctx(ctx)
    register_platform(ctx)
    # RPC tools are registered per-adapter on connect() using the stashed ctx.
