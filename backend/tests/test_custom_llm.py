"""自定义 OpenAI 兼容网关（custom 模型）后端测试：不发起真实网络请求。"""
import os
import sys
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routers.system import _is_supported_model
from ai.llm_client import LLMClient


class CustomModelSupportedTests(unittest.TestCase):
    def test_builtin_models_always_supported(self):
        self.assertTrue(_is_supported_model("deepseek"))
        self.assertTrue(_is_supported_model("gemini"))

    def test_custom_unsupported_without_base_url(self):
        with patch("config.CUSTOM_LLM_BASE_URL", ""):
            self.assertFalse(_is_supported_model("custom"))

    def test_custom_supported_with_base_url(self):
        with patch("config.CUSTOM_LLM_BASE_URL", "https://gw.example.com/v1"):
            self.assertTrue(_is_supported_model("custom"))

    def test_unknown_model_rejected(self):
        self.assertFalse(_is_supported_model("claude"))


class CustomChatTests(unittest.TestCase):
    def _patch_env(self, **kv):
        """设置 CUSTOM_* 环境变量；用完后恢复。"""
        return patch.dict(
            os.environ,
            {
                "CUSTOM_LLM_BASE_URL": "https://gw.example.com/v1",
                "CUSTOM_LLM_API_KEY": "sk-test",
                "CUSTOM_LLM_MODEL_ID": "deepseek-v4-flash#claude",
                **kv,
            },
        )

    def test_custom_requires_base_url(self):
        client = LLMClient(model="custom")
        with self._patch_env(CUSTOM_LLM_BASE_URL=""):
            with self.assertRaises(ValueError):
                client._custom([{"role": "user", "content": "hi"}])

    def test_custom_requires_api_key(self):
        client = LLMClient(model="custom")
        with self._patch_env(CUSTOM_LLM_API_KEY=""):
            with self.assertRaises(ValueError):
                client._custom([{"role": "user", "content": "hi"}])

    def test_custom_posts_openai_compatible_payload(self):
        client = LLMClient(model="custom")

        class FakeResp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "你好"}}]}

        captured = {}

        def fake_post(url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResp()

        from unittest.mock import Mock

        mock_client = Mock()
        mock_client.post.side_effect = fake_post

        with self._patch_env():
            with patch(
                "ai.llm_client._get_llm_http_client",
                return_value=mock_client,
            ):
                out = client.chat("分析一下", system="你是缠论助手")

        self.assertEqual(out, "你好")
        self.assertEqual(captured["url"], "https://gw.example.com/v1/chat/completions")
        self.assertEqual(
            captured["headers"]["Authorization"],
            "Bearer sk-test",
        )
        self.assertEqual(captured["json"]["model"], "deepseek-v4-flash#claude")
        self.assertEqual(captured["json"]["messages"][0]["role"], "system")


if __name__ == "__main__":
    unittest.main()
