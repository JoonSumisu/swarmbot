from pathlib import Path
import os
import time
from typing import Optional

class HotMemoryStore:
    """
    L2 Hot Memory: Simple human-like short-term memory.
    Stores 'Past', 'Present', 'Future', and 'Todo' in a markdown file.
    Global scope (singleton-like access via file).
    """
    
    def __init__(self, workspace_path: str):
        self.file_path = Path(workspace_path) / "hot_memory.md"
        self._init_file()

    def _init_file(self):
        if not self.file_path.exists():
            initial_content = """# Hot Memory

## Short-term Past
- (Empty)

## Present
- (Empty)

## Future / Scheduled
- (Empty)

## Todo List
- [ ] Initialize system
"""
            self.file_path.write_text(initial_content, encoding="utf-8")

    def read(self) -> str:
        """Read the entire hot memory."""
        if not self.file_path.exists():
            self._init_file()
        return self.file_path.read_text(encoding="utf-8")

    def update(self, content: str) -> None:
        """
        Overwrite the hot memory with new content.
        Agents are expected to read, modify, and write back.
        """
        self.file_path.write_text(content, encoding="utf-8")

    def append_todo(self, item: str) -> None:
        """Helper to quickly add a todo item."""
        content = self.read()
        if "## Todo List" in content:
            # Simple append
            new_content = content.replace("## Todo List", f"## Todo List\n- [ ] {item}")
            self.update(new_content)
        else:
            self.update(content + f"\n\n## Todo List\n- [ ] {item}")

    def archive_to_qmd(self, qmd_store) -> str:
        """
        Logic for Overthinking to archive old items.
        For now (1 month trial), we might just log what would be archived.
        """
        # Placeholder for complex archiving logic
        pass
