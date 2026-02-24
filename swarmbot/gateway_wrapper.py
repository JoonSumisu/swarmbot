import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict

# --- 1. Environment Setup & Vendoring ---
# Ensure we load the local VENDORED nanobot, not system one
# And make sure the top-level swarmbot package is importable even when
# this file is executed directly via `python gateway_wrapper.py`.
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from swarmbot.config_manager import load_config
from swarmbot.swarm.manager import SwarmManager

# Setup Logger
logger = logging.getLogger("swarmbot.gateway")
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --- 2. Initialize Swarm Manager ---
SWARM_MANAGER = None
try:
    cfg = load_config()
    SWARM_MANAGER = SwarmManager.from_swarmbot_config(cfg)
    logger.info("SwarmManager initialized for Gateway interception.")
except Exception as e:
    logger.error(f"Failed to init SwarmManager: {e}")

# --- 3. Bind vendored nanobot as top-level module name ---
try:
    import swarmbot.nanobot as vendored_nanobot
    sys.modules.setdefault("nanobot", vendored_nanobot)
    logger.info("Bound vendored swarmbot.nanobot as top-level 'nanobot' module")
except Exception as e:
    logger.error(f"Could not bind vendored nanobot package: {e}")

# --- 4. Define Patch Logic ---

# Instead of monkeypatching the method, we replace the class entirely.
# This ensures that when nanobot instantiates AgentLoop, it gets our SwarmAgentLoop.
try:
    from swarmbot.swarm.agent_adapter import SwarmAgentLoop
    import nanobot.agent.loop as agent_loop_module
    
    # Replace the class in the module
    agent_loop_module.AgentLoop = SwarmAgentLoop
    logger.info("Successfully replaced AgentLoop class with SwarmAgentLoop.")

except ImportError as e:
    logger.error(f"Failed to import SwarmAgentLoop or nanobot module: {e}")
except Exception as e:
    logger.error(f"Unexpected error during class replacement: {e}")

# --- 5. Run Application ---
if __name__ == "__main__":
    try:
        from nanobot.cli.commands import app
        app()
    except ImportError as e:
        logger.error(f"Could not import nanobot.cli.commands.app: {e}")
    except Exception as e:
        logger.error(f"Error while running nanobot.cli.commands.app: {e}", exc_info=True)
