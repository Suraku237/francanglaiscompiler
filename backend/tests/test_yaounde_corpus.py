from uuid import uuid4

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.tests.test_analyzer_history import AnalyzerHistoryCase
from backend.tests.test_compiler_workspace import CompilerHostedCase
from backend.workspace_backups import validate_archive
from compiler.parser.yaounde import GRAMMAR, LIMITATIONS, RATIONALE
from compiler.tests.yaounde_cases import CORPUS_CASES


class YaoundeCorpusTests(AnalyzerHistoryCase, CompilerHostedCase):
    def test_final_grammar_and_all_twelve_results_are_shared_persistent_and_non_destructive(self):
        user = self.register()
        entries = [self.collected(case.text, entry_type="Sentence") for case in CORPUS_CASES]
        before = self.client.get("/api/dataset").json()
        revisions = self.client.get("/api/workspace/revisions").json()["revisions"]
        historical = self.record("Je go au march\u00e9.", "S -> NOUN")
        profile = self.save_profile(grammar=GRAMMAR, grammar_rationale=RATIONALE, limitations=LIMITATIONS)
        self.assertEqual(profile["grammar"], GRAMMAR.strip())
        self.assertFalse(profile["manual_transcription_confirmed"])
        self.assertEqual(profile["collection_method"], "")
        state = self.client.get("/api/analyzer").json()
        self.assertEqual(state["grammar"], GRAMMAR.strip())
        self.assertEqual(state["grammar_ownership"]["owner_id"], user["id"])
        requests = [str(uuid4()) for _ in CORPUS_CASES]
        results = [
            self.record(case.text, state["grammar"], request_id=request_id)
            for case, request_id in zip(CORPUS_CASES, requests)
        ]
        self.assertEqual(sum(row["parse"]["accepted"] for row in results), 10)
        self.assertEqual(sum(row["approval"]["accepted"] for row in results), 10)
        for case, result in zip(CORPUS_CASES, results):
            self.assertEqual(result["text"], case.text)
            self.assertEqual(result["parse"]["accepted"], case.accepted)
            self.assertTrue(result["grammar"]["is_ll1"])
            self.assertEqual(result["metadata"]["matching_entries"], 1)
            self.assertEqual(result["ownership"]["owner_id"], user["id"])
            self.assertEqual(result["grammar_source"], GRAMMAR.strip())
            self.assertEqual(self.client.get(f"/api/analyzer/tests/{result['id']}").json(), result)
        self.assertEqual(self.record(CORPUS_CASES[0].text, GRAMMAR, request_id=requests[0]), results[0])
        self.assertEqual(self.report()["summary"]["total"], 13)
        self.assertEqual(self.report()["grammar_summary"]["accepted"], 10)
        self.assertEqual(self.client.get("/api/dataset").json(), before)
        self.assertEqual(self.client.get("/api/workspace/revisions").json()["revisions"], revisions)
        self.assertEqual(self.client.get(f"/api/analyzer/tests/{historical['id']}").json(), historical)
        document, _ = validate_archive(self.backup())
        self.assertEqual(len(document["entries"]), len(entries))
        self.assertEqual(len(document["analyzer_tests"]), 13)
        self.assertEqual(len(document["coursework"]), 1)
        app = create_app(Settings(), auth_settings=self.settings)
        with TestClient(app, headers={"Origin": "http://testserver"}) as reopened:
            self.login(reopened)
            self.assertEqual(reopened.get("/api/analyzer").json()["grammar"], GRAMMAR.strip())
            self.assertEqual(reopened.get("/api/analyzer/tests").json()["summary"]["total"], 13)
            self.assertEqual(reopened.get(f"/api/analyzer/tests/{results[8]['id']}").json(), results[8])

        other = self.other()
        self.register(other, "peer@example.com")
        self.assertFalse(other.get("/api/analyzer").json()["grammar_ownership"]["can_edit"])
        self.assertEqual(other.get("/api/analyzer").json()["grammar"], GRAMMAR.strip())
        self.assertEqual(self.report(client=other)["summary"]["total"], 13)
        self.assertEqual(other.put("/api/analyzer/grammar", json={"grammar": "S -> UNKNOWN"}).status_code, 403)
        self.assertEqual(other.get(f"/api/analyzer/tests/{results[0]['id']}").json()["lexical"], results[0]["lexical"])
