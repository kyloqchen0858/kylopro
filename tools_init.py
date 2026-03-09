"""
Kylopro workspace tools initializer.
nanobot AgentLoop auto-loads this file and calls register_tools().
create_local_provider() is also used by commands.py for heartbeat routing.
"""
import sys
from pathlib import Path

# Add Kylopro-Nexus to path so we can import core modules
_kylopro_root = Path(__file__).resolve().parent
if str(_kylopro_root) not in sys.path:
    sys.path.insert(0, str(_kylopro_root))

from core.kylopro_tools import register_kylopro_tools
from core.local_provider import create_local_provider  # noqa: F401 — re-exported for commands.py


def register_tools(agent_loop) -> None:
    """Called by nanobot AgentLoop._register_workspace_tools()."""
    register_kylopro_tools(agent_loop)

    # BrainHooks: 自动注入 KyloBrain 上下文 + 自动记录 episode
    try:
        from core.brain_hooks import install_brain_hooks
        install_brain_hooks(agent_loop)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("BrainHooks install failed: %s", e)
