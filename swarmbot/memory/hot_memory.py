from pathlib import Path
import os
import time
import re

class HotMemory:
    """
    L2 Hot Memory: Short-term persistent memory (1-7 days).
    File: hot_memory.md
    Content: Past events, Present context, Future plans, Todo list.
    Max entries: 20 (configurable), oldest entries removed when exceeded.
    """
    MAX_ENTRIES = 20

    def __init__(self, workspace_path: str, max_entries: int = None):
        self.file_path = Path(workspace_path) / "hot_memory.md"
        self.max_entries = max_entries or self.MAX_ENTRIES
        self._ensure_file()

    def _ensure_file(self):
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text("# Hot Memory\n\n## Past (Recent)\n\n## Present\n\n## Future\n\n## Todo List\n", encoding="utf-8")

    def read(self) -> str:
        return self.file_path.read_text(encoding="utf-8")

    def update(self, content: str):
        """Direct overwrite (used by agents or self-optimization)"""
        self.file_path.write_text(content, encoding="utf-8")

    def add_important(self, content: str, category: str = "Important"):
        """
        Add important information with capacity limit.
        When exceeding max_entries, remove oldest entries from 'Past' section.
        """
        content = content.strip()
        if not content:
            return
        
        current = self.read()
        lines = current.split('\n')
        
        # Find or create Past section
        past_idx = -1
        for i, line in enumerate(lines):
            if line.strip() == "## Past (Recent)":
                past_idx = i
                break
        
        if past_idx == -1:
            # No Past section, add it
            lines.insert(0, "## Past (Recent)")
            lines.insert(1, "")
            past_idx = 1
        
        # Add new entry with timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        new_entry = f"- [{timestamp}] {category}: {content}"
        
        # Find where Past section ends (next ## or end)
        past_end = len(lines)
        for i in range(past_idx + 1, len(lines)):
            if lines[i].startswith("## "):
                past_end = i
                break
        
        # Insert new entry
        lines.insert(past_end, new_entry)
        
        # Enforce capacity limit - remove oldest entries (skip first 2 lines after ## Past)
        lines = self._enforce_capacity(lines, past_idx)
        
        self.update('\n'.join(lines))

    def _enforce_capacity(self, lines: list, past_idx: int) -> list:
        """Remove oldest entries if exceeding max_entries"""
        # Collect all entry lines in Past section
        entry_lines = []
        other_lines = []
        
        in_past = False
        for i, line in enumerate(lines):
            if line.strip() == "## Past (Recent)":
                in_past = True
                other_lines.append(line)
            elif line.startswith("## ") and in_past:
                # End of Past section
                in_past = False
                other_lines.append(line)
            elif in_past and line.strip().startswith("- ["):
                entry_lines.append(line)
            elif in_past and line.strip() == "":
                # Empty line in past section, skip
                continue
            else:
                other_lines.append(line)
        
        # Keep only the newest entries (up to max_entries)
        entry_lines = entry_lines[-self.max_entries:]
        
        # Rebuild lines
        result = []
        in_past = False
        past_added = False
        for line in lines:
            if line.strip() == "## Past (Recent)":
                in_past = True
                past_added = True
                result.append(line)
            elif line.startswith("## ") and in_past:
                # Add remaining entries before next section
                result.extend(entry_lines)
                result.append("")
                in_past = False
                result.append(line)
            elif in_past:
                if line.strip().startswith("- ["):
                    # Skip - will be added from entry_lines
                    continue
                elif line.strip() == "":
                    continue
                else:
                    result.append(line)
            else:
                result.append(line)
        
        # If Past was at end, add entries
        if past_added and in_past:
            result.extend(entry_lines)
        
        return result

    def append_todo(self, item: str):
        content = self.read()
        if "## Todo List" in content:
            lines = content.split('\n')
            new_lines = []
            inserted = False
            for line in lines:
                new_lines.append(line)
                if line.strip() == "## Todo List":
                    new_lines.append(f"- [ ] {item}")
                    inserted = True
            if not inserted:
                new_lines.append("\n## Todo List")
                new_lines.append(f"- [ ] {item}")
            self.update("\n".join(new_lines))
        else:
            self.update(content + f"\n\n## Todo List\n- [ ] {item}")
