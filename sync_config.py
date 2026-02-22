
import json
import os
from pathlib import Path

# Load swarmbot config
swarmbot_config_path = Path("/root/.swarmbot/config.json")
nanobot_config_path = Path("/root/.nanobot/config.json")

with open(swarmbot_config_path, "r") as f:
    swarm_config = json.load(f)

# Load nanobot config or create empty
if nanobot_config_path.exists():
    with open(nanobot_config_path, "r") as f:
        nano_config = json.load(f)
else:
    nano_config = {}

# Sync Channels
nano_config["channels"] = swarm_config.get("channels", {})

# Sync Provider/Model
# Swarmbot uses "provider" key for its own config, but nanobot expects "providers" dict
provider_info = swarm_config.get("provider", {})
if provider_info:
    nano_config.setdefault("providers", {})
    nano_config["providers"]["custom"] = {
        "api_key": provider_info.get("api_key", "dummy"),
        "api_base": provider_info.get("base_url", "")
    }
    
    nano_config.setdefault("agents", {}).setdefault("defaults", {})
    nano_config["agents"]["defaults"]["model"] = provider_info.get("model", "")
    nano_config["agents"]["defaults"]["max_tokens"] = provider_info.get("max_tokens", 4096)
    nano_config["agents"]["defaults"]["temperature"] = provider_info.get("temperature", 0.7)

# Ensure directory exists
nanobot_config_path.parent.mkdir(parents=True, exist_ok=True)

with open(nanobot_config_path, "w") as f:
    json.dump(nano_config, f, indent=2)

print(f"Synced config to {nanobot_config_path}")
