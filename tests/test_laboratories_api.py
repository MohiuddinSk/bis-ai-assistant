"""Dated BIS LIMS snapshot contracts: lab identity is not an IS scope."""

import unittest

from fastapi.testclient import TestClient

from backend.main import create_app


class LaboratoriesApiTests(unittest.TestCase):
    def test_search_by_is_product_name_and_location(self):
        with TestClient(create_app()) as client:
            by_is = client.get("/api/laboratories", params={"q": "IS 4151", "page_size": 2})
            by_product = client.get("/api/laboratories", params={"q": "steel"})
            by_name = client.get("/api/laboratories", params={"q": "PRESTO"})
            by_location = client.get("/api/v1/laboratories", params={"q": "Noida"})
        body = by_is.json()
        self.assertEqual(by_is.status_code, 200)
        self.assertGreaterEqual(body["laboratory_count"], 400)
        self.assertGreaterEqual(body["capability_count"], 300)
        self.assertGreater(body["total_matches"], len(body["results"]))
        self.assertEqual(len(body["results"]), 2)
        self.assertTrue(all(result["capabilities"] for result in body["results"]))
        self.assertTrue(all("4151" in scope["standard_identifier"] for result in body["results"] for scope in result["capabilities"]))
        self.assertGreater(by_product.json()["total_matches"], 0)
        self.assertTrue(any("PRESTO" in row["laboratory"]["name"] for row in by_name.json()["results"]))
        self.assertGreater(by_location.json()["total_matches"], 0)

    def test_multiple_scopes_preserve_own_charge_and_validity_context(self):
        with TestClient(create_app()) as client:
            result = client.get("/api/laboratories", params={"q": "EKO PRO ENGINEERS", "page_size": 20})
        rows = result.json()["results"]
        self.assertTrue(rows)
        scope_rows = [scope for row in rows for scope in row["capabilities"]]
        self.assertGreaterEqual(len(scope_rows), 2)
        self.assertTrue(all(scope["source_url"].startswith("https://lims.bis.gov.in/") for scope in scope_rows))
        self.assertTrue(all(scope["charge_amount"] is None or scope["tax_treatment"] == "Excluding taxes" for scope in scope_rows))
        self.assertTrue(all(scope["scope_valid_until"] is None for scope in scope_rows))
        self.assertTrue(any(scope["search_validity_date"] for scope in scope_rows))

    def test_missing_price_is_null_and_unknown_or_invalid_requests_are_explicit(self):
        with TestClient(create_app()) as client:
            hallmark = client.get("/api/laboratories", params={"q": "IS 1417", "page_size": 100})
            empty = client.get("/api/laboratories", params={"q": "nonsensequasar"})
            invalid = client.get("/api/laboratories", params={"page": 0})
            missing = client.get("/api/laboratories/not-a-real-lab")
        self.assertTrue(any(scope["charge_amount"] is None for row in hallmark.json()["results"] for scope in row["capabilities"]))
        self.assertEqual(empty.json()["total_matches"], 0)
        self.assertEqual(empty.json()["results"], [])
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(missing.status_code, 404)

    def test_lab_detail_exposes_provenance_without_claiming_live_recognition(self):
        with TestClient(create_app()) as client:
            result = client.get("/api/laboratories/8138306")
        self.assertEqual(result.status_code, 200)
        lab = result.json()["laboratory"]
        self.assertEqual(lab["code"], "8138306")
        self.assertIn("Noida", lab["location"])
        self.assertIsNone(lab["recognition_status"])
        self.assertTrue(lab["official_url"].startswith("https://lims.bis.gov.in/"))
        self.assertIn("BIS LIMS", lab["provenance"])
