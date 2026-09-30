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
        self.assertGreaterEqual(body["record_count"], 23813)
        self.assertEqual(body["total_matches"], 1)
        self.assertIn("metadata", body["coverage_note"])
        self.assertEqual([{key: value for key, value in row.items() if key in {
            "identifier", "title", "category", "edition_year", "status", "official_url",
            "retrieved_at", "provenance", "evidence_filename", "evidence_page",
        }} for row in body["results"]], [{
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

    def test_new_toy_metadata_has_official_provenance_without_claiming_applicability(self):
        with TestClient(create_app()) as client:
            electric = client.get("/api/catalogue/standards", params={"q": "is-15644:2006"})
            mechanical = client.get("/api/catalogue/standards", params={"q": "IS 9873 Part 1:2019"})

        self.assertEqual(electric.status_code, 200)
        self.assertEqual(mechanical.status_code, 200)
        self.assertEqual([row["identifier"] for row in electric.json()["results"]], ["IS 15644:2006"])
        self.assertEqual([row["identifier"] for row in mechanical.json()["results"]], ["IS 9873 Part 1:2019"])
        for record in (electric.json()["results"][0], mechanical.json()["results"][0]):
            self.assertTrue(record["official_url"].startswith("https://www.bis.gov.in/"))
            self.assertIn("BIS", record["provenance"])
            self.assertIn("not an applicability decision", record["status"])
            self.assertIsNone(record["evidence_filename"])

    def test_keyword_and_unknown_result_do_not_invent_a_standard(self):
        with TestClient(create_app()) as client:
            helmet = client.get("/api/catalogue/standards", params={"q": "helmet"})
            unknown = client.get("/api/catalogue/standards", params={"q": "pressure cooker"})

        self.assertIn("IS 4151:2015", [row["identifier"] for row in helmet.json()["results"]])
        self.assertGreater(helmet.json()["total_matches"], 1)
        self.assertGreaterEqual(unknown.json()["total_matches"], 1)
        self.assertTrue(all("pressure" in row["title"].casefold() or "cooker" in row["title"].casefold()
                            for row in unknown.json()["results"]))

    def test_pagination_and_invalid_page_are_explicit(self):
        with TestClient(create_app()) as client:
            second_page = client.get("/api/catalogue/standards", params={"page": 4, "page_size": 1})
            far_page = client.get("/api/catalogue/standards", params={"page": 999999, "page_size": 1})
            invalid_page = client.get("/api/catalogue/standards", params={"page": 0})

        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.json()["results"]), 1)
        self.assertEqual(second_page.json()["total_matches"], second_page.json()["record_count"])
        self.assertEqual(far_page.json()["results"], [])
        self.assertEqual(invalid_page.status_code, 422)

    def test_part_section_year_title_and_source_category_search(self):
        with TestClient(create_app()) as client:
            part = client.get("/api/catalogue/standards", params={"q": "IS 302 Part 2 Sec 24:2026"})
            keyword = client.get("/api/catalogue/standards", params={"q": "Forensic Sciences Vocabulary"})
            filtered = client.get("/api/catalogue/standards", params={"category": "Terminology", "page_size": 2})
        self.assertEqual(part.json()["results"][0]["identifier"], "IS 302 (Part 2/Sec 24):2026")
        self.assertEqual(part.json()["results"][0]["part"], "2")
        self.assertEqual(part.json()["results"][0]["section"], "24")
        self.assertEqual(keyword.json()["results"][0]["identifier"], "IS 17742 (Part 1):2026")
        self.assertEqual(len(filtered.json()["results"]), 2)
        self.assertGreater(filtered.json()["total_matches"], 2)
        self.assertTrue(all(row["category"] == "Terminology" for row in filtered.json()["results"]))

    def test_detail_is_normalized_and_unknown_is_not_found(self):
        with TestClient(create_app()) as client:
            found = client.get("/api/v1/catalogue/standards/is%204151%3A2015")
            missing = client.get("/api/catalogue/standards/IS%2099999%3A2026")

        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["identifier"], "IS 4151:2015")
        self.assertEqual(missing.status_code, 404)
