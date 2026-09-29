"""HTTP contracts for provenance-first catalogue endpoints."""

import unittest

from fastapi.testclient import TestClient

from backend.main import create_app


class CatalogueApiTests(unittest.TestCase):
    def test_exact_is_number_returns_provenance_bearing_record(self):
        with TestClient(create_app()) as client:
            response = client.get("/api/catalogue/standards", params={"q": "is-4151:2015"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["record_count"], 1)
        self.assertTrue(body["coverage_note"].startswith("Only locally verified"))
        self.assertEqual(body["results"], [{
            "identifier": "IS 4151:2015",
            "title": "Protective Helmet for Two Wheeler Riders",
            "category": "Helmet",
            "edition_year": "2015",
            "status": "Title and identifier verified from the cited BIS product manual",
            "official_url": "https://www.bis.gov.in/wp-content/uploads/2024/12/PM_IS_4151_-Dec-24.pdf",
            "retrieved_at": "2024-12",
            "provenance": "BIS Product Manual PM/IS 4151/3/Dec 2024, page 1",
            "evidence_filename": "PM_IS_4151_-Dec-24.pdf",
            "evidence_page": 1,
        }])

    def test_keyword_and_unknown_result_do_not_invent_a_standard(self):
        with TestClient(create_app()) as client:
            helmet = client.get("/api/catalogue/standards", params={"q": "helmet"})
            unknown = client.get("/api/catalogue/standards", params={"q": "pressure cooker"})

        self.assertEqual([row["identifier"] for row in helmet.json()["results"]], ["IS 4151:2015"])
        self.assertEqual(unknown.json()["results"], [])

    def test_pagination_and_invalid_page_are_explicit(self):
        with TestClient(create_app()) as client:
            second_page = client.get("/api/catalogue/standards", params={"page": 2, "page_size": 1})
            invalid_page = client.get("/api/catalogue/standards", params={"page": 0})

        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(second_page.json()["results"], [])
        self.assertEqual(invalid_page.status_code, 422)

    def test_detail_is_normalized_and_unknown_is_not_found(self):
        with TestClient(create_app()) as client:
            found = client.get("/api/v1/catalogue/standards/is%204151%3A2015")
            missing = client.get("/api/catalogue/standards/IS%2099999%3A2026")

        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["identifier"], "IS 4151:2015")
        self.assertEqual(missing.status_code, 404)
