"""Real-index wizard endpoint checks; read-only and provider-key free."""
import unittest
from fastapi.testclient import TestClient
from backend.main import create_app
from retrieval.search import Retriever

class InvalidGenerator:
    model="fake-no-key"
    def generate(self,*_args,**_kwargs): return "invalid"

BASE={"role":"manufacturer","product_description":"Toy","power_type":"not_sure","intended_age_group":"not_sure","goal":"not_sure","application_stage":"researching","additional_context":None}

class ComplianceRealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client=TestClient(create_app(retriever_factory=Retriever,generator_factory=InvalidGenerator)); cls.client.__enter__()
    @classmethod
    def tearDownClass(cls): cls.client.__exit__(None,None,None)
    def guide(self,**values): return self.client.post("/api/compliance/guide",json={**BASE,**values}).json()["guidance"]
    def test_battery_standard_is_grounded(self):
        result=self.guide(product_description="Battery-operated toy car",power_type="battery_operated",goal="identify_standards")
        self.assertTrue(result["grounded"]); self.assertIn("primary standard is IS 15644",result["answer"]); self.assertIn("IS 9873",result["answer"]); self.assertIn("secondary",result["answer"]); self.assertGreaterEqual(len(result["citations"]),2)
    def test_artisan_exemption_remains_conditional(self):
        result=self.guide(role="artisan",product_description="Handmade toy",goal="check_exemption")
        self.assertTrue(result["grounded"]); self.assertIn("not all handmade toys",result["answer"].lower()); self.assertIn("manufactured and sold",result["answer"].lower()); self.assertIn("registered",result["answer"].lower()); self.assertIn("development commissioner",result["answer"].lower())
    def test_new_series_checklist_is_partial(self):
        result=self.guide(product_description="New toy series",goal="add_new_series",application_stage="scope_extension")
        self.assertTrue(result["grounded"]); self.assertIn("partial",result["answer"].lower()); self.assertIn("declaration",result["answer"].lower()); self.assertIn("starting ages",result["answer"].lower()); self.assertIn("fee declaration",result["answer"].lower())
    def test_unclear_profile_is_safe(self):
        result=self.guide(product_description="Not sure toy")
        self.assertTrue(result["insufficient_evidence"] or "clar" in result["answer"].lower() or "not sure" in result["answer"].lower())
    def test_out_of_domain_product_does_not_invent_toy_requirement(self):
        result=self.guide(product_description="Industrial solar inverter",goal="identify_standards")
        self.assertTrue(result["insufficient_evidence"]); self.assertNotIn("IS 15644",result["answer"])

if __name__=="__main__": unittest.main()
