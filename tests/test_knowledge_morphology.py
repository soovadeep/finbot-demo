import copy
import unittest

from finbot.demo import run_demo
from finbot.knowledge import Index, lexical_form
from finbot.tools import DEMO_DOCS


class KnowledgeMorphology(unittest.TestCase):
    def setUp(self):
        self.index = Index()
        for page in DEMO_DOCS:
            self.index.upsert_page(copy.deepcopy(page))

    def test_available_cap_and_disclosure_policy_retrieves_for_singular_card(self):
        question = "What is the credit card surcharge cap and disclosure rule?"
        hits = self.index.search(question, groups=["support"])
        self.assertEqual(hits[0]["source_url"], "https://wiki.example.com/surcharge")
        result = run_demo(question)
        self.assertIn("capped at 3 percent", result["final"]["answer"])
        self.assertIn("disclosed before payment", result["final"]["answer"])

    def test_related_forms_do_not_expand_to_irrelevant_queries(self):
        for question in ("credit cards surcharge rules", "credit card surcharges rules"):
            self.assertTrue(self.index.search(question))
        for question in ("mortgage early repayment penalties", "credit mortgage foreclosure timetable"):
            self.assertEqual(self.index.search(question), [])

    def test_codes_singular_endings_and_access_filters_are_preserved(self):
        for token in ("05", "51", "status", "business", "analysis"):
            self.assertEqual(lexical_form(token), token)
        private = copy.deepcopy(DEMO_DOCS[1])
        private["access"] = ["private"]
        index = Index()
        index.upsert_page(private)
        self.assertEqual(index.search("credit card surcharge", groups=["support"]), [])
        self.assertTrue(index.search("credit card surcharge", groups=["private"]))

    def test_reingestion_updates_normalized_index(self):
        page = copy.deepcopy(DEMO_DOCS[1])
        page["html"] = "<p>Mortgage prepayment penalties.</p>"
        self.index.upsert_page(page)
        self.assertEqual(self.index.search("credit card surcharge cap and disclosure rule"), [])
        self.assertTrue(self.index.search("mortgage prepayment penalty"))


if __name__ == "__main__":
    unittest.main()
