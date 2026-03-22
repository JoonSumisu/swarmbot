import importlib
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestNanobotConfigBridge(unittest.TestCase):
    def setUp(self):
        self.test_home = "/tmp/swarmbot_test_home_nanobot_bridge"
        if os.path.exists(self.test_home):
            shutil.rmtree(self.test_home)
        os.makedirs(self.test_home, exist_ok=True)

        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.test_home

        for m in [
            "swarmbot.config_manager",
            "swarmbot",
            "nanobot",
            "nanobot.config.loader",
            "nanobot.config.schema",
            "nanobot.channels.manager",
            "nanobot.bus.queue",
        ]:
            if m in sys.modules:
                del sys.modules[m]

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home

        if os.path.exists(self.test_home):
            shutil.rmtree(self.test_home)

    def test_loads_from_swarmbot_config_only(self):
        import swarmbot.config_manager as cm

        cfg = cm.SwarmbotConfig()
        cfg.providers[0].name = "custom"
        cfg.providers[0].base_url = "http://localhost:1234/v1"
        cfg.providers[0].api_key = "k"
        cfg.providers[0].model = "custom/model"
        cfg.providers[0].max_tokens = 123
        cfg.providers[0].temperature = 0.42
        cfg.channels = {
            "feishu": cm.ChannelConfig(
                enabled=True,
                config={"appId": "app_x", "appSecret": "sec_y"},
            )
        }
        cm.save_config(cfg)

        import swarmbot
        import nanobot.config.loader as nl

        ncfg = nl.load_config()

        self.assertEqual(ncfg.agents.defaults.model, "custom/model")
        self.assertEqual(ncfg.agents.defaults.max_tokens, 123)
        self.assertAlmostEqual(ncfg.agents.defaults.temperature, 0.42)
        self.assertEqual(ncfg.providers.custom.api_key, "k")
        self.assertEqual(ncfg.providers.custom.api_base, "http://localhost:1234/v1")

        self.assertTrue(ncfg.channels.feishu.enabled)
        self.assertEqual(ncfg.channels.feishu.app_id, "app_x")
        self.assertEqual(ncfg.channels.feishu.app_secret, "sec_y")

    def test_channel_manager_sees_feishu_enabled(self):
        import swarmbot.config_manager as cm

        cfg = cm.SwarmbotConfig()
        cfg.providers[0].model = "custom/model"
        cfg.channels = {
            "feishu": cm.ChannelConfig(enabled=True, config={"app_id": "x", "app_secret": "y"})
        }
        cm.save_config(cfg)

        import swarmbot
        import nanobot.config.loader as nl
        from nanobot.bus.queue import MessageBus
        from nanobot.channels.manager import ChannelManager

        ncfg = nl.load_config()
        manager = ChannelManager(ncfg, MessageBus())
        self.assertIn("feishu", manager.enabled_channels)

    def test_save_back_to_swarmbot_config(self):
        import swarmbot.config_manager as cm

        cfg = cm.SwarmbotConfig()
        cfg.providers[0].base_url = "http://localhost:1234/v1"
        cfg.providers[0].api_key = "k"
        cfg.providers[0].model = "custom/model"
        cfg.channels = {}
        cm.save_config(cfg)

        import swarmbot
        import nanobot.config.loader as nl

        ncfg = nl.load_config()
        ncfg.agents.defaults.model = "new/model"
        ncfg.providers.custom.api_key = "new_key"
        ncfg.providers.custom.api_base = "http://localhost:9999/v1"
        ncfg.channels.feishu.enabled = True
        ncfg.channels.feishu.app_id = "a"
        ncfg.channels.feishu.app_secret = "b"

        nl.save_config(ncfg)

        cm2 = importlib.reload(cm)
        cfg2 = cm2.load_config()
        self.assertEqual(cfg2.providers[0].model, "new/model")
        self.assertEqual(cfg2.providers[0].api_key, "new_key")
        self.assertEqual(cfg2.providers[0].base_url, "http://localhost:9999/v1")
        self.assertIn("feishu", cfg2.channels)
        self.assertTrue(cfg2.channels["feishu"].enabled)


if __name__ == "__main__":
    unittest.main()

