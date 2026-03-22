from pathlib import Path
import os
import time

class HotMemory:
    """
    L2 Hot Memory: Short-term persistent memory (1-7 days).
    File: hot_memory.md
    Content: Past events, Present context, Future plans, Todo list.
    """
    def __init__(self, workspace_path: str):
        self.file_path = Path(workspace_path) / "hot_memory.md"
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
