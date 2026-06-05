"""Delta Chat platform plugin for Hermes Agent."""

from pathlib import Path

# Import adapter registration
from .adapter import register_platform, register_rpc_tools


def register(ctx):
    """Register Delta Chat platform adapter and bundled skills."""
    register_platform(ctx)
    register_rpc_tools(ctx)

    # Register bundled webxdc-converter skill
    skills_dir = Path(__file__).parent / "skills"
    webxdc_skill = skills_dir / "webxdc-converter" / "SKILL.md"
    if webxdc_skill.exists():
        ctx.register_skill("webxdc-converter", webxdc_skill)
