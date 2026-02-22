import unittest
import os
import shutil
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from swarmbot.memory.qmd import QMDMemoryStore
from swarmbot.memory.qmd_wrapper import EmbeddedQMD
import swarmbot.memory.qmd as qmd_module

class TestQMDSurrogates(unittest.TestCase):
    def setUp(self):
        self.test_dir = "/tmp/swarmbot_test_qmd"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_embedded_qmd_sanitization(self):
        qmd = EmbeddedQMD(self.test_dir)
        # String with surrogate (half of a pair) which is invalid in UTF-8
        bad_string = "Hello \ud800 World" 
        
        try:
            # Should not raise error
            qmd.add(bad_string, collection="test")
        except UnicodeEncodeError:
            self.fail("EmbeddedQMD.add raised UnicodeEncodeError on surrogate string")
        
        # Verify it was saved (sanitized)
        results = qmd.search("Hello", collection="test")
        self.assertTrue(len(results) > 0)
        # The invalid char should be replaced (usually by replacement char � or ignored depending on impl)
        # In our implementation we used errors='replace', so it should be valid utf-8 now.
        
    def test_qmd_store_persistence(self):
        # Patch WORKSPACE_PATH to point to temp dir
        original_ws = qmd_module.WORKSPACE_PATH
        qmd_module.WORKSPACE_PATH = self.test_dir
        
        try:
            store = QMDMemoryStore()
            # Explicitly set qmd root to temp dir since __init__ uses WORKSPACE_PATH
            store._qmd_root = os.path.join(self.test_dir, "qmd")
            store.embedded_qmd = EmbeddedQMD(store._qmd_root)
            
            bad_string = "Hello \ud800 World"
            
            try:
                # This triggers persist_to_qmd and file write
                store.persist_to_qmd(bad_string, collection="test")
            except UnicodeEncodeError:
                self.fail("QMDMemoryStore.persist_to_qmd raised UnicodeEncodeError on surrogate string")
            
            # Verify file exists
            coll_dir = os.path.join(self.test_dir, "qmd", "test")
            self.assertTrue(os.path.exists(coll_dir))
            files = os.listdir(coll_dir)
            self.assertTrue(len(files) > 0)
            
            # Verify file content
            with open(os.path.join(coll_dir, files[0]), "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                self.assertIn("Hello", content)
                
        finally:
            qmd_module.WORKSPACE_PATH = original_ws

if __name__ == "__main__":
    unittest.main()
