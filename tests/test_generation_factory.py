import unittest
from unittest.mock import patch

from backend.generation_factory import create_generation_provider
from backend.settings import DEFAULT_GROQ_MAX_COMPLETION_TOKENS, DEFAULT_GROQ_MODEL, GenerationSettings, get_generation_settings


class GenerationFactoryTests(unittest.TestCase):
    def test_missing_provider_defaults_to_groq(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = get_generation_settings()
        self.assertEqual((settings.provider, settings.model), ("groq", DEFAULT_GROQ_MODEL))

    def test_explicit_groq_selects_groq(self):
        with patch.dict("os.environ", {"LLM_PROVIDER": "groq"}, clear=True):
            self.assertEqual(get_generation_settings().provider, "groq")

    def test_explicit_openai_compatible_selects_generic_adapter(self):
        settings = GenerationSettings("openai_compatible", None, "model", 30, 2048, "https://example.test/v1", ("example.test",))
        with patch("backend.generation_factory.OpenAICompatibleGenerator", return_value="openai") as constructor:
            self.assertEqual(create_generation_provider(settings), "openai")
        constructor.assert_called_once_with(settings)

    def test_disabled_returns_none(self):
        self.assertIsNone(create_generation_provider(GenerationSettings("disabled", None, "", 30, 2048)))

    def test_unknown_provider_returns_none_without_fallback(self):
        settings = GenerationSettings("unknown", None, "", 30, 2048)
        with patch("backend.generation_factory.GroqGenerator") as groq, patch("backend.generation_factory.OpenAICompatibleGenerator") as generic:
            self.assertIsNone(create_generation_provider(settings))
        groq.assert_not_called(); generic.assert_not_called()

    def test_settings_failure_returns_none(self):
        with patch("backend.generation_factory.get_generation_settings", side_effect=ValueError("bad settings")):
            self.assertIsNone(create_generation_provider())

    def test_provider_constructor_failure_returns_none(self):
        with patch("backend.generation_factory.GroqGenerator", side_effect=ValueError("bad configuration")):
            self.assertIsNone(create_generation_provider(GenerationSettings("groq", "fixture", "model", 30, 2048)))

    def test_missing_openai_base_url_returns_none(self):
        self.assertIsNone(create_generation_provider(GenerationSettings("openai_compatible", None, "model", 30, 2048)))

    def test_invalid_structured_output_mode_returns_none(self):
        settings = GenerationSettings("openai_compatible", None, "model", 30, 2048, "https://example.test", ("example.test",), "invalid")
        self.assertIsNone(create_generation_provider(settings))

    def test_missing_model_returns_none(self):
        for provider, api_key, base_url, hosts in (("groq", "fixture", None, ()), ("openai_compatible", None, "https://example.test", ("example.test",))):
            with self.subTest(provider=provider):
                settings = GenerationSettings(provider, api_key, "", 30, 2048, base_url, hosts)
                self.assertIsNone(create_generation_provider(settings))

    def test_missing_allowlist_returns_none(self):
        settings = GenerationSettings("openai_compatible", None, "model", 30, 2048, "https://example.test")
        self.assertIsNone(create_generation_provider(settings))

    def test_generic_variables_do_not_override_groq_configuration(self):
        environment = {"LLM_PROVIDER": "groq", "GROQ_MODEL": "groq-model", "LLM_MODEL": "generic-model", "LLM_BASE_URL": "https://example.test/v1", "LLM_ALLOWED_HOSTS": "example.test"}
        with patch.dict("os.environ", environment, clear=True): settings = get_generation_settings()
        self.assertEqual(settings.model, "groq-model"); self.assertIsNone(settings.base_url); self.assertEqual(settings.allowed_hosts, ())

    def test_groq_variables_do_not_override_openai_compatible_configuration(self):
        environment = {"LLM_PROVIDER": "openai_compatible", "LLM_MODEL": "generic-model", "LLM_BASE_URL": "https://example.test/v1", "LLM_ALLOWED_HOSTS": "example.test", "GROQ_MODEL": "groq-model"}
        with patch.dict("os.environ", environment, clear=True): settings = get_generation_settings()
        self.assertEqual(settings.model, "generic-model"); self.assertEqual(settings.base_url, "https://example.test/v1")

    def test_disabled_ignores_provider_variables_and_constructs_no_client(self):
        environment = {"LLM_PROVIDER": "disabled", "GROQ_MODEL": "groq-model", "LLM_MODEL": "generic-model", "LLM_BASE_URL": "https://example.test/v1", "LLM_ALLOWED_HOSTS": "example.test"}
        with patch.dict("os.environ", environment, clear=True), patch("backend.generation_factory.GroqGenerator") as groq, patch("backend.generation_factory.OpenAICompatibleGenerator") as generic:
            self.assertIsNone(create_generation_provider())
        groq.assert_not_called(); generic.assert_not_called()

    def test_invalid_token_values_fall_back_to_default(self):
        for provider, name in (("groq", "GROQ_MAX_COMPLETION_TOKENS"), ("openai_compatible", "LLM_MAX_COMPLETION_TOKENS")):
            with self.subTest(provider=provider), patch.dict("os.environ", {"LLM_PROVIDER": provider, name: "not-a-number"}, clear=True):
                self.assertEqual(get_generation_settings().max_completion_tokens, DEFAULT_GROQ_MAX_COMPLETION_TOKENS)

    def test_out_of_range_token_values_fall_back_to_default(self):
        with patch.dict("os.environ", {"GROQ_MAX_COMPLETION_TOKENS": "99999"}, clear=True):
            self.assertEqual(get_generation_settings().max_completion_tokens, DEFAULT_GROQ_MAX_COMPLETION_TOKENS)

    def test_invalid_timeout_fails_settings_and_factory_returns_none(self):
        for value in ("not-a-number", "0"):
            with self.subTest(value=value), patch.dict("os.environ", {"LLM_TIMEOUT_SECONDS": value}, clear=True):
                with self.assertRaises(ValueError): get_generation_settings()
                self.assertIsNone(create_generation_provider())

    def test_invalid_model_returns_none(self):
        settings = GenerationSettings("openai_compatible", None, "bad\nmodel", 30, 2048, "https://example.test", ("example.test",))
        self.assertIsNone(create_generation_provider(settings))

    def test_factory_unsafe_provider_name_never_leaks(self):
        for provider in ("unsafe\nprovider", "caf\u00e9", "x" * 41, None):
            with self.subTest(provider=repr(provider)), self.assertLogs("backend.generation_factory", level="WARNING") as captured:
                self.assertIsNone(create_generation_provider(GenerationSettings(provider, None, "model", 30, 2048)))
            logs = "\n".join(captured.output)
            self.assertIn("provider=invalid", logs)
            self.assertNotIn(str(provider), logs)


if __name__ == "__main__":
    unittest.main()
