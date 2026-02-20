from __future__ import annotations

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Basic Chrome DevTools Protocol (CDP) client wrapper or local browser controller
# Inspired by OpenClaw browser tool

@dataclass
class BrowserConfig:
    executable_path: str = ""  # Auto-detect if empty
    headless: bool = False
    user_data_dir: str = ""    # Profile path


class LocalBrowserTool:
    """
    A simplified local browser controller that can:
    1. Launch/Attach to a Chrome instance (isolated profile).
    2. Navigate to URL.
    3. Get page content (snapshot).
    4. Execute JS (simple actions).
    
    This is a wrapper around a headless chrome or similar driver.
    For this implementation, we'll use a simple 'chrome --headless --dump-dom' approach 
    or similar lightweight interaction if full CDP is too heavy for this snippet.
    
    However, requested feature is "OpenClaw style", which implies a persistent browser session.
    We will implement a persistent subprocess controller.
    """
    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._cdp_port = 9222
        
    def start(self) -> str:
        """Start the browser process."""
        if self._process and self._process.poll() is None:
            return "Browser already running."
            
        cmd = [
            self.config.executable_path or "google-chrome", # Fallback to path
            f"--remote-debugging-port={self._cdp_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--user-data-dir=/tmp/swarmbot_browser_profile", # Isolated profile
        ]
        
        if self.config.headless:
            cmd.append("--headless=new")
            
        try:
            # We assume google-chrome or chromium is in PATH if not specified
            if not self.config.executable_path:
                # Simple detection logic
                for browser in ["google-chrome", "chromium", "brave-browser", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]:
                    if subprocess.run(["which", browser], capture_output=True).returncode == 0:
                        cmd[0] = browser
                        break
            
            self._process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2) # Wait for startup
            return f"Browser started on port {self._cdp_port}"
        except Exception as e:
            return f"Failed to start browser: {e}"

    def stop(self) -> str:
        if self._process:
            self._process.terminate()
            self._process = None
            return "Browser stopped."
        return "Browser not running."

    def open_page(self, url: str) -> str:
        """Open a URL in a new tab using CDP (via curl/requests or simple command)."""
        # For simplicity in this env without heavy dependencies like playwright/pyppeteer,
        # we use simple CDP HTTP endpoints.
        try:
            # Create new target
            import urllib.request
            resp = urllib.request.urlopen(f"http://localhost:{self._cdp_port}/json/new?{url}")
            target = json.loads(resp.read())
            return f"Opened {url}, target_id: {target['id']}"
        except Exception as e:
            return f"Failed to open page (is browser running?): {e}"

    def snapshot(self) -> str:
        """Get text content of the current active page."""
        # Using a simple trick: dump DOM via CDP evaluation
        try:
            import urllib.request
            # Get list of targets to find active one
            resp = urllib.request.urlopen(f"http://localhost:{self._cdp_port}/json")
            targets = json.loads(resp.read())
            page = next((t for t in targets if t['type'] == 'page'), None)
            
            if not page:
                return "No active page found."
                
            # Use websocket or just return basic info? 
            # Full DOM dump via pure HTTP CDP is tricky without a WS client.
            # Fallback: Use a CLI tool if available or just return metadata for now.
            # Real OpenClaw uses a robust CDP client.
            # Here we will simulate a "read" by just fetching the URL directly if simple, 
            # OR better: use 'chrome --headless --dump-dom URL' for one-off reads if process is not persistent.
            
            # For this lightweight implementation, let's implement the "One-off Read" mode 
            # which is more robust for simple agents than maintaining a long-lived WS connection.
            return f"Active Tab: {page['url']}\n(Full DOM snapshot requires CDP Websocket client)"
            
        except Exception as e:
            return f"Snapshot failed: {e}"

    def one_off_read(self, url: str) -> str:
        """
        Headless one-off read. Best for search results and simple pages.
        """
        cmd = [
            self.config.executable_path or "google-chrome",
            "--headless=new",
            "--dump-dom",
            url
        ]
        # Detect browser again if needed
        if not self.config.executable_path:
             for browser in ["google-chrome", "chromium", "brave-browser"]:
                if subprocess.run(["which", browser], capture_output=True).returncode == 0:
                    cmd[0] = browser
                    break
                    
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                # Simple HTML to Text conversion could happen here
                return result.stdout[:10000] # Truncate
            return f"Error reading page: {result.stderr}"
        except Exception as e:
            return f"Execution error: {e}"

