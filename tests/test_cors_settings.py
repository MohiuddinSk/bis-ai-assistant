"""Focused tests for production CORS origin configuration."""

import os
import unittest
from unittest.mock import patch

from backend.settings import ALLOWED_ORIGINS, get_allowed_origins


class CorsOriginSettingsTests(unittest.TestCase):
    def test_defaults_to_localhost_origins(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_allowed_origins(), ALLOWED_ORIGINS)

    def test_accepts_one_netlify_https_origin(self):
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": "https://bis-demo.netlify.app"}, clear=True):
            self.assertEqual(get_allowed_origins(), ("https://bis-demo.netlify.app",))

    def test_accepts_comma_separated_origins(self):
        value = "https://one.netlify.app,http://localhost:5173"
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": value}, clear=True):
            self.assertEqual(get_allowed_origins(), ("https://one.netlify.app", "http://localhost:5173"))

    def test_normalizes_whitespace_trailing_slashes_and_duplicates(self):
        value = " https://one.netlify.app/ , http://localhost:5173///,https://one.netlify.app "
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": value}, clear=True):
            self.assertEqual(get_allowed_origins(), ("https://one.netlify.app", "http://localhost:5173"))

    def test_ignores_wildcards_and_invalid_values(self):
        value = "*,javascript:alert(1),ftp://example.com,https://*.netlify.app,https://good.netlify.app/path,https://good.netlify.app"
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": value}, clear=True):
            self.assertEqual(get_allowed_origins(), ("https://good.netlify.app",))

    def test_falls_back_safely_when_no_environment_value_is_valid(self):
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": "*,not-an-origin"}, clear=True):
            self.assertEqual(get_allowed_origins(), ALLOWED_ORIGINS)


if __name__ == "__main__":
    unittest.main()
