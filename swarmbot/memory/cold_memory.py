from .qmd import QMDMemoryStore

class ColdMemory(QMDMemoryStore):
    """
    L4 Cold Memory: Semantic Search DB (QMD).
    Stores facts, experiences, theories derived from Warm Memory.
    """
    def search_text(self, query: str, limit: int = 5) -> str:
        results = self.search(query, limit=limit)
        if not results:
            return ""
        return "\n".join([str(r) for r in results])
