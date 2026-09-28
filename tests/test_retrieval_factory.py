import unittest
from unittest.mock import patch

from backend.retrieval_factory import create_retrieval_provider
from backend.settings import RetrievalSettings, get_retrieval_settings


class RetrievalFactoryTests(unittest.TestCase):
    def test_missing_provider_defaults_to_local(self):
        configured = object()
        with patch.dict("os.environ", {}, clear=True), patch("backend.retrieval_factory.Retriever", return_value=configured) as raw, patch("backend.retrieval_factory.LocalChromaRetriever", return_value="local") as constructor:
            self.assertEqual(get_retrieval_settings().provider, "chroma_local")
            self.assertEqual(create_retrieval_provider(), "local")
        raw.assert_called_once_with(data_path="data/processed/generated_v3", persist_path="data/chroma", collection_name="bis_toys_v3_e73aab14a72f7908_39b347ab687e")
        constructor.assert_called_once_with(configured)

    def test_explicit_local_provider_is_case_normalized(self):
        configured = object()
        settings = RetrievalSettings(provider="CHROMA_LOCAL")
        with patch("backend.retrieval_factory.Retriever", return_value=configured) as raw, patch("backend.retrieval_factory.LocalChromaRetriever", return_value="local") as constructor:
            self.assertEqual(create_retrieval_provider(settings), "local")
        raw.assert_called_once_with(
            data_path="data/processed/generated_v3",
            persist_path="data/chroma",
            collection_name="bis_toys_v3_e73aab14a72f7908_39b347ab687e",
        )
        constructor.assert_called_once_with(configured)

    def test_disabled_provider_returns_none_without_constructing_local_adapter(self):
        with patch("backend.retrieval_factory.LocalChromaRetriever") as constructor:
            self.assertIsNone(create_retrieval_provider(RetrievalSettings(provider="disabled")))
        constructor.assert_not_called()

    def test_disabled_provider_ignores_irrelevant_environment_values(self):
        environment = {"RETRIEVAL_PROVIDER": "disabled", "RETRIEVAL_LOCAL_PATH": "C:\\private\\sentinel", "LLM_MODEL": "irrelevant"}
        with patch.dict("os.environ", environment, clear=True), patch("backend.retrieval_factory.LocalChromaRetriever") as constructor:
            self.assertIsNone(create_retrieval_provider())
        constructor.assert_not_called()

    def test_unknown_provider_does_not_fall_back(self):
        with patch("backend.retrieval_factory.LocalChromaRetriever") as constructor:
            self.assertIsNone(create_retrieval_provider(RetrievalSettings(provider="unknown")))
        constructor.assert_not_called()

    def test_unsafe_provider_value_is_not_logged(self):
        value = "unsafe\nprovider"
        with self.assertLogs("backend.retrieval_factory", level="WARNING") as captured:
            self.assertIsNone(create_retrieval_provider(RetrievalSettings(provider=value)))
        self.assertIn("provider=invalid", "\n".join(captured.output))
        self.assertNotIn(value, "\n".join(captured.output))

    def test_non_string_provider_and_constructor_failure_return_none(self):
        self.assertIsNone(create_retrieval_provider(RetrievalSettings(provider=None)))
        with patch("backend.retrieval_factory.LocalChromaRetriever", side_effect=RuntimeError("private constructor detail")):
            with self.assertLogs("backend.retrieval_factory", level="WARNING") as captured:
                self.assertIsNone(create_retrieval_provider(RetrievalSettings(provider="chroma_local")))
        self.assertNotIn("private constructor detail", "\n".join(captured.output))

    def test_generation_environment_does_not_change_retrieval_selection(self):
        environment = {"LLM_PROVIDER": "disabled", "LLM_API_KEY": "ignored", "GROQ_MODEL": "ignored"}
        with patch.dict("os.environ", environment, clear=True):
            self.assertEqual(get_retrieval_settings().provider, "chroma_local")


if __name__ == "__main__":
    unittest.main()
