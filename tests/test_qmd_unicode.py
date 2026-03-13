import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swarmbot.memory.qmd_wrapper import EmbeddedQMD


def test_qmd_surrogate_safe():
    with tempfile.TemporaryDirectory() as td:
        store = EmbeddedQMD(td)
        bad = "hello-\udce6-world"
        store.add(bad, collection="unicode", meta={"nested": {"k": "v-\udce6"}})
        out = store.search("probe-\udce6", collection="unicode", limit=3)
        assert isinstance(out, list)


if __name__ == "__main__":
    test_qmd_surrogate_safe()
    print("qmd unicode test passed")
