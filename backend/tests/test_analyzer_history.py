import copy
import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from filelock import Timeout

from backend import analyzer, coursework, coursework_store
from backend.analyzer_models import RecordedTest
from backend.collection import CollectionError
from backend.config import Settings
from backend.main import create_app
from backend.shared_workspace import SharedWorkspaceStore
from backend.tests.test_api import ApiTestCase
from backend.tests.test_compiler_workspace import CompilerHostedCase
from backend.workspace_backups import validate_archive
from backend.workspaces import WorkspaceStore
from compiler.lexer import tokenizer
from data_collector import dataset


class AnalyzerHistoryCase:
    def record(self, text="taxi", grammar="S -> NOUN", *, request_id=None, client=None):
        response = (client or self.client).post("/api/analyzer/tests", json={
            "request_id": request_id or str(uuid4()), "text": text, "grammar": grammar,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def report(self, *, client=None, **params):
        response = (client or self.client).get("/api/analyzer/tests", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def collected(self, text="taxi", **fields):
        response = self.client.post("/api/dataset", json={"text": text, **fields})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()


class AnalyzerHistoryTests(AnalyzerHistoryCase, ApiTestCase):
    def test_empty_report_has_no_inferred_metadata_or_acceptance(self):
        self.collected()
        report = self.report()
        self.assertEqual(report, {
            "summary": {"total": 0, "accepted": 0, "rejected": 0, "acceptance_rate": None},
            "statistics": {
                "frequencies": [], "category_counts": {}, "variations": [], "unknown_tokens": [],
                "total_tokens": 0, "raw_frequencies": [], "normalized_frequencies": [],
            },
            "unknown_review": [], "topic_counts": {}, "language_counts": {}, "tests": [],
            "offset": 0, "limit": 25,
        })

    def test_one_manual_computation_persists_raw_result_without_parsing_or_saving_collection(self):
        text = "  Le TAXI DON\tREFUSE.\r\nJE   WANDA !  "
        grammar = "S -> NOUN"
        with patch.object(coursework, "parse_corpus", side_effect=AssertionError("No corpus parse")), \
                patch.object(coursework, "lexical_report", side_effect=AssertionError("No corpus tokenization")), \
                patch.object(coursework, "read_corpus", side_effect=AssertionError("No legacy corpus limits")), \
                patch.object(dataset, "save_all", side_effect=AssertionError("Do not save Collection")), \
                patch.object(dataset, "load_all", wraps=dataset.load_all) as load, \
                patch.object(analyzer, "analyze_grammar", wraps=analyzer.analyze_grammar) as prepare, \
                patch.object(analyzer, "build_lexicon", wraps=analyzer.build_lexicon) as learn, \
                patch.object(tokenizer, "analyze_sentence", wraps=tokenizer.analyze_sentence) as lex, \
                patch.object(analyzer, "parse_analysis", wraps=analyzer.parse_analysis) as parse:
            record = self.record(text, " \n" + grammar + "\t ")
        load.assert_called_once_with()
        prepare.assert_called_once_with(grammar)
        learn.assert_called_once_with([])
        lex.assert_called_once_with(text, {})
        parse.assert_called_once()
        self.assertEqual(set(record), {
            "id", "created_at", "grammar_source", "text", "lexical", "grammar", "parse", "metadata",
        })
        self.assertEqual(record["text"], text)
        self.assertEqual(record["grammar_source"], grammar)
        self.assertEqual(record["metadata"], {"topics": [], "languages": [], "matching_entries": 0})
        self.assertEqual(record["lexical"]["verb_phrases"], ["DON\tREFUSE", "JE   WANDA"])
        self.assertEqual(record["lexical"]["slang_expressions"], ["JE   WANDA"])
        self.assertIsNotNone(datetime.fromisoformat(record["created_at"]).tzinfo)
        self.assertEqual(self.client.get(f"/api/analyzer/tests/{record['id']}").json(), record)
        self.assertEqual(self.make_client().get(f"/api/analyzer/tests/{record['id']}").json(), record)
        self.assertTrue((self.directory / "coursework" / "analyzer-tests.sqlite3").is_file())
        self.assertFalse((self.directory / "coursework" / "project.json").exists())
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)

    def test_idempotent_retry_and_reads_use_immutable_snapshot_after_vocabulary_and_grammar_change(self):
        entry = self.collected("zandolo", entry_type="Word", lexical_category="NOUN",
                               review_status="approved", category="Campus Life")
        identifier = str(uuid4())
        saved = self.record("zandolo", request_id=identifier)
        self.assertEqual(saved["metadata"], {
            "topics": ["Campus Life"], "languages": ["francanglais"], "matching_entries": 1,
        })
        self.assertEqual(saved["lexical"]["tokens"], [{"text": "zandolo", "category": "NOUN"}])
        self.assertEqual(self.client.patch(f"/api/dataset/{entry['id']}", json={
            "lexical_category": "VERB", "review_status": "approved", "category": "Other",
        }).status_code, 200)
        self.assertEqual(self.client.put("/api/analyzer/grammar", json={"grammar": "S -> VERB"}).status_code, 200)
        with patch.object(dataset, "load_all", side_effect=AssertionError("No vocabulary reads on retry or GET")), \
                patch.object(analyzer, "analyze_grammar", side_effect=AssertionError("No grammar reanalysis")), \
                patch.object(tokenizer, "analyze_sentence", side_effect=AssertionError("No re-tokenization")), \
                patch.object(analyzer, "parse_analysis", side_effect=AssertionError("No parsing")):
            self.assertEqual(self.record("zandolo", " \tS -> NOUN\r\n ", request_id=identifier), saved)
            self.assertEqual(self.client.get(f"/api/analyzer/tests/{identifier}").json(), saved)
            report = self.report()
        self.assertEqual(report["summary"]["total"], 1)
        self.assertEqual(report["statistics"]["category_counts"], {"NOUN": 1})
        self.assertEqual(report["topic_counts"], {"Campus Life": 1})
        self.assertEqual(self.record("zandolo", "S -> VERB")["lexical"]["tokens"][0]["category"], "VERB")
        self.assertEqual(self.report()["summary"]["total"], 2)

    def test_metadata_uses_only_exact_raw_matches_and_retains_multiple_declared_labels(self):
        for language, category in (("francanglais", "Campus Life"), ("pidgin", "Other")):
            self.collected("zandolo", language=language, category=category)
        matched = self.record("zandolo")
        self.assertEqual(matched["metadata"], {
            "topics": ["Campus Life", "Other"], "languages": ["francanglais", "pidgin"], "matching_entries": 2,
        })
        for text in (" ZANDOLO ", " zandolo "):
            self.assertEqual(self.record(text)["metadata"], {"topics": [], "languages": [], "matching_entries": 0})
        self.assertEqual(self.report()["topic_counts"], {"Campus Life": 1, "Other": 1, "Not recorded": 2})
        self.assertEqual(self.report()["language_counts"], {"francanglais": 1, "pidgin": 1, "Not recorded": 2})
        self.collected("taxi", language="unspecified")
        self.record()
        self.assertEqual(self.report()["language_counts"]["unspecified"], 1)

    def test_deliberate_repeats_count_but_retries_conflicts_and_pure_analysis_do_not(self):
        identifier = str(uuid4())
        saved = self.record(request_id=identifier)
        self.assertEqual(self.record(request_id=identifier), saved)
        self.record()
        self.record("waka")
        for text, grammar in (("taxi ", "S -> NOUN"), ("TAXI", "S -> NOUN"), ("taxi", "S ->  NOUN")):
            response = self.client.post("/api/analyzer/tests", json={
                "request_id": identifier, "text": text, "grammar": grammar,
            })
            self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.client.post("/api/analyzer/analyze", json={
            "text": "taxi", "grammar": "S -> NOUN",
        }).status_code, 200)
        report = self.report()
        self.assertEqual(report["summary"]["total"], 3)
        self.assertEqual(report["summary"]["accepted"], 2)
        self.assertEqual(report["summary"]["rejected"], 1)
        self.assertAlmostEqual(report["summary"]["acceptance_rate"], 200 / 3)
        self.assertEqual(report["statistics"]["total_tokens"], 3)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)

    def test_all_unicode_token_counts_unknown_occurrences_and_variations_are_exact(self):
        text = "École école ecole Zzzq zzzq + 12. STRASSE Straße l’amour l'amour İ i K K E\u0301 e\u0301"
        self.record(text)
        self.record(text)
        self.record("", "S -> epsilon")
        report = self.report()
        stats = report["statistics"]
        self.assertEqual(stats["total_tokens"], 36)
        self.assertEqual(stats["category_counts"], {
            "UNKNOWN": 26, "NOUN": 4, "NUMBER": 2, "PUNCTUATION": 2, "ENGLISH_FUNCTION_WORD": 2,
        })
        self.assertEqual({item["token"]: item["count"] for item in stats["frequencies"]}, {
            "école": 4, "ecole": 2, "zzzq": 4, "+": 2, "12": 2, ".": 2, "strasse": 4,
            "l’amour": 2, "l'amour": 2, "i\u0307": 2, "i": 2, "k": 4, "e\u0301": 4,
        })
        self.assertEqual({item["token"]: item["count"] for item in stats["raw_frequencies"]}, {
            token: 2 for token in ("École", "école", "ecole", "Zzzq", "zzzq", "+", "12", ".", "STRASSE",
                                  "Straße", "l’amour", "l'amour", "İ", "i", "K", "K", "E\u0301", "e\u0301")
        })
        self.assertEqual({item["token"]: item["count"] for item in stats["normalized_frequencies"]}, {
            "ecole": 6, "zzzq": 4, "+": 2, "12": 2, ".": 2, "strasse": 4, "l'amour": 4, "i": 4, "k": 4, "e": 4,
        })
        for name in ("frequencies", "raw_frequencies", "normalized_frequencies", "unknown_tokens"):
            self.assertEqual(stats[name], sorted(stats[name], key=lambda item: (-item["count"], item["token"])))
        unknown = {item["token"]: item for item in report["unknown_review"]}
        self.assertEqual(unknown["zzzq"], {"token": "zzzq", "count": 4, "tests": 2, "forms": ["Zzzq", "zzzq"]})
        self.assertEqual(unknown["strasse"], {
            "token": "strasse", "count": 4, "tests": 2, "forms": ["STRASSE", "Straße"],
        })
        self.assertEqual(unknown["i\u0307"], {"token": "i\u0307", "count": 2, "tests": 2, "forms": ["İ"]})
        self.assertNotIn("i", unknown)
        self.assertEqual({item["normalized"]: item["forms"] for item in stats["variations"]}["ecole"], [
            {"text": "ecole", "count": 2}, {"text": "École", "count": 2}, {"text": "école", "count": 2},
        ])
        self.assertEqual(report["summary"]["total"], 3)
        self.assertEqual(report["summary"]["accepted"], 1)
        self.assertEqual(report["topic_counts"], {"Not recorded": 3})

    def test_unknown_review_does_not_relabel_earlier_tests_when_annotations_change(self):
        self.record("zandolo")
        self.collected("zandolo", entry_type="Word", lexical_category="NOUN", review_status="approved")
        self.record("zandolo")
        report = self.report()
        self.assertEqual(report["statistics"]["category_counts"], {"UNKNOWN": 1, "NOUN": 1})
        self.assertEqual(report["unknown_review"], [{"token": "zandolo", "count": 1, "tests": 1, "forms": ["zandolo"]}])

    def test_pagination_is_stable_and_aggregates_every_test_not_just_the_page(self):
        stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with patch("backend.analyzer_history.datetime") as clock:
            clock.now.return_value = stamp
            records = [self.record() for _ in range(31)]
        ids = [record["id"] for record in reversed(records)]
        first = self.report()
        second = self.report(offset=25, limit=25)
        beyond = self.report(offset=1000, limit=1)
        self.assertEqual([item["id"] for item in first["tests"]], ids[:25])
        self.assertEqual([item["id"] for item in second["tests"]], ids[25:])
        self.assertEqual(beyond["tests"], [])
        for report in (first, second, beyond):
            self.assertEqual(report["summary"], {
                "total": 31, "accepted": 31, "rejected": 0, "acceptance_rate": 100.0,
            })
            self.assertEqual(report["statistics"]["raw_frequencies"], [{"token": "taxi", "count": 31}])
            self.assertTrue(all(set(item) == {
                "id", "created_at", "text", "accepted", "token_count", "error",
            } for item in report["tests"]))

    def test_history_has_no_500_item_cap_and_manual_input_has_no_legacy_collection_cap(self):
        saved = RecordedTest.model_validate(self.record())
        with dataset.dataset_lock():
            for _ in range(500):
                coursework_store.save_analyzer_test(saved.model_copy(update={"id": str(uuid4())}))
        entries = [
            {"text": "untested", "entry_type": "Sentence", "language": "unspecified", "category": "Other"}
            for _ in range(501)
        ]
        with patch.object(dataset, "load_all", return_value=entries):
            self.record()
        report = self.report()
        self.assertEqual(report["summary"]["total"], 502)
        self.assertEqual(report["statistics"]["total_tokens"], 502)
        self.assertEqual(report["statistics"]["frequencies"], [{"token": "taxi", "count": 502}])
        self.assertEqual(len(report["tests"]), 25)

    def test_empty_inputs_conflicts_and_parser_limit_rejections_are_saved_without_truncation(self):
        for text, grammar, accepted in (
            ("", "S -> epsilon", True), (" \r\n\t ", "S -> NOUN", False),
            ("taxi", "S -> A | B\nA -> NOUN\nB -> NOUN", False),
            (" ".join(["taxi"] * 257), "S -> NOUN S | epsilon", False),
            ("z" * 1001, "S -> UNKNOWN", False),
        ):
            with self.subTest(text=text[:20]):
                saved = self.record(text, grammar)
                self.assertEqual(saved["text"], text)
                self.assertEqual(saved["parse"]["accepted"], accepted)
                self.assertEqual(self.client.get(f"/api/analyzer/tests/{saved['id']}").json(), saved)
        report = self.report()
        self.assertEqual(report["summary"], {"total": 5, "accepted": 1, "rejected": 4, "acceptance_rate": 20.0})
        self.assertEqual(report["statistics"]["total_tokens"], 259)

    def test_invalid_requests_query_bounds_and_identifiers_never_create_tests(self):
        valid = {"request_id": str(uuid4()), "text": "", "grammar": "S -> epsilon"}
        invalid = (
            {**valid, "request_id": "not-uuid"},
            {**valid, "request_id": "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"},
            {**valid, "request_id": None}, {**valid, "text": None}, {**valid, "text": 7},
            {**valid, "text": "x" * 4001}, {**valid, "grammar": " "}, {**valid, "grammar": "S ->"},
            {**valid, "grammar": "S -> MISSING"}, {**valid, "grammar": "x" * 12001},
            {**valid, "grammar": "S -> " + " ".join(["NOUN"] * 21)}, {**valid, "corpus": []},
            {key: value for key, value in valid.items() if key != "request_id"},
        )
        for payload in invalid:
            response = self.client.post("/api/analyzer/tests", json=payload)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertTrue(response.json()["detail"])
        for params in ({"offset": -1}, {"limit": 0}, {"limit": 101}, {"offset": "bad"}, {"limit": 1.5}):
            self.assertEqual(self.client.get("/api/analyzer/tests", params=params).status_code, 422)
        self.assertEqual(self.client.get("/api/analyzer/tests/not-uuid").status_code, 422)
        self.assertEqual(self.client.get("/api/analyzer/tests/" + str(uuid4())).status_code, 404)
        self.assertEqual(self.report()["summary"]["total"], 0)

    def test_concurrent_retries_compute_once_and_conflicting_reuse_returns_conflict(self):
        identifier = str(uuid4())
        payload = {"request_id": identifier, "text": "taxi", "grammar": "S -> NOUN"}
        with patch.object(tokenizer, "analyze_sentence", wraps=tokenizer.analyze_sentence) as lex, \
                ThreadPoolExecutor(max_workers=4) as executor:
            responses = list(executor.map(lambda _: self.client.post("/api/analyzer/tests", json=payload), range(6)))
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertTrue(all(response.json() == responses[0].json() for response in responses))
        lex.assert_called_once()
        conflict_id = str(uuid4())
        payloads = [
            {"request_id": conflict_id, "text": text, "grammar": "S -> NOUN"} for text in ("taxi", "waka")
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda item: self.client.post("/api/analyzer/tests", json=item), payloads))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        self.assertEqual(self.report()["summary"]["total"], 2)

    def test_storage_failures_are_redacted_and_failed_records_do_not_count(self):
        for error, status in ((OSError("PRIVATE path"), 500), (sqlite3.OperationalError("PRIVATE database"), 500),
                              (Timeout("PRIVATE lock"), 503)):
            with self.subTest(error=type(error).__name__), patch.object(
                coursework_store, "save_analyzer_test", side_effect=error,
            ):
                response = self.client.post("/api/analyzer/tests", json={
                    "request_id": str(uuid4()), "text": "taxi", "grammar": "S -> NOUN",
                })
            self.assertEqual(response.status_code, status, response.text)
            self.assertNotIn("PRIVATE", response.text)
        self.assertEqual(self.report()["summary"]["total"], 0)
        saved = self.record()
        for method, path in (
            ("load_analyzer_test", f"/api/analyzer/tests/{saved['id']}"),
            ("iter_analyzer_tests", "/api/analyzer/tests"),
        ):
            with patch.object(coursework_store, method, side_effect=sqlite3.DatabaseError("PRIVATE failure")), \
                    self.assertLogs("backend.coursework_api", level="ERROR") as logs:
                response = self.client.get(path)
            self.assertEqual(response.status_code, 500, response.text)
            self.assertNotIn("PRIVATE", response.text + "".join(logs.output))
        self.assertEqual(self.report()["summary"]["total"], 1)

    def test_corrupted_snapshot_is_not_returned_as_unchecked_json(self):
        saved = self.record()
        saved["lexical"]["statistics"]["total_tokens"] = 100
        path = self.directory / "coursework" / "analyzer-tests.sqlite3"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE analyzer_tests SET data=?", (json.dumps(saved),))
        for route in ("/api/analyzer/tests", f"/api/analyzer/tests/{saved['id']}"):
            with self.assertLogs("backend.coursework_api", level="ERROR") as logs:
                response = self.client.get(route)
            self.assertEqual(response.status_code, 500, response.text)
            self.assertNotIn(saved["id"], response.text + "".join(logs.output))


class HostedAnalyzerHistoryTests(AnalyzerHistoryCase, CompilerHostedCase):
    def test_authentication_csrf_origin_and_private_response_headers(self):
        identifier = str(uuid4())
        payload = {"request_id": identifier, "text": "taxi", "grammar": "S -> NOUN"}
        self.assertEqual(self.client.post("/api/analyzer/tests", json=payload).status_code, 401)
        for path in ("/api/analyzer/tests", f"/api/analyzer/tests/{identifier}"):
            self.assertEqual(self.client.get(path).status_code, 401)
        user = self.register()
        store = SharedWorkspaceStore(self.root, user["id"])
        version = store.version
        for headers in ({"X-CSRF-Token": ""}, {"Origin": "https://attacker.example"}):
            response = self.client.post("/api/analyzer/tests", headers=headers, json=payload)
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(store.version, version)
        self.assertEqual(self.report()["summary"]["total"], 0)
        saved = self.record(request_id=identifier)
        for path in ("/api/analyzer/tests", f"/api/analyzer/tests/{saved['id']}"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("no-store", response.headers["cache-control"])
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertFalse(self.legacy_coursework.exists())

    def test_all_accounts_share_tests_but_idempotency_keys_remain_actor_scoped(self):
        owner = self.register()
        identifier = str(uuid4())
        first = self.record(request_id=identifier)
        project = str(uuid4())
        self.client.headers["X-Mboa-Project"] = project
        self.assertEqual(self.report()["summary"]["total"], 1)
        self.assertEqual(self.client.get(f"/api/analyzer/tests/{first['id']}").json(), first)
        self.assertEqual(self.record(request_id=identifier), first)
        conflict = self.client.post("/api/analyzer/tests", json={
            "request_id": identifier, "text": "waka", "grammar": "S -> VERB",
        })
        self.assertEqual(conflict.status_code, 409)
        self.client.headers.pop("X-Mboa-Project")
        self.assertEqual(self.client.get(f"/api/analyzer/tests/{first['id']}", params={"project": project}).json(), first)
        store = SharedWorkspaceStore(self.root, owner["id"])
        before = store.export_document()["analyzer_tests"]
        other = self.other()
        self.register(other, "second@example.com")
        self.assertEqual(self.report(client=other)["summary"]["total"], 1)
        visible = other.get(f"/api/analyzer/tests/{first['id']}").json()
        self.assertEqual(visible, {**first, "ownership": {**first["ownership"], "can_edit": False}})
        self.assertEqual(other.get("/api/analyzer/tests", params={"project": project}).status_code, 200)
        second = self.record("zandolo", "S -> UNKNOWN", request_id=identifier, client=other)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.report()["summary"]["total"], 2)
        self.assertEqual([row for row in store.export_document()["analyzer_tests"] if row["id"] == first["id"]], before)

    def test_version_concurrent_retries_reopen_and_project_deletion_guard(self):
        user = self.register()
        project = str(uuid4())
        self.client.headers["X-Mboa-Project"] = project
        store = SharedWorkspaceStore(self.root, user["id"])
        version = store.version
        identifier = str(uuid4())
        payload = {"request_id": identifier, "text": "  taxi \r\n", "grammar": "S -> NOUN"}
        with patch.object(tokenizer, "analyze_sentence", wraps=tokenizer.analyze_sentence) as lex, \
                ThreadPoolExecutor(max_workers=3) as executor:
            responses = list(executor.map(lambda _: self.client.post("/api/analyzer/tests", json=payload), range(4)))
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertTrue(all(response.json() == responses[0].json() for response in responses))
        lex.assert_called_once()
        saved = responses[0].json()
        self.assertEqual(store.version, version + 1)
        self.assertEqual(self.record(payload["text"], request_id=identifier), saved)
        self.report()
        self.assertEqual(store.version, version + 1)
        self.assertEqual(self.client.delete(f"/api/workspace/projects/{project}").status_code, 409)
        app = create_app(Settings(), auth_settings=self.settings,
                         mailer=lambda address, _subject, text: self.mail.append((address, text)))
        reopened = self.stack.enter_context(TestClient(app, headers={"Origin": "http://testserver"}))
        self.login(reopened)
        reopened.headers["X-Mboa-Project"] = project
        self.assertEqual(reopened.get(f"/api/analyzer/tests/{saved['id']}").json(), saved)
        self.assertEqual(self.report(client=reopened)["statistics"]["total_tokens"], 1)

    def test_sqlite_insert_and_version_are_one_atomic_commit(self):
        user = self.register()
        store = SharedWorkspaceStore(self.root, user["id"])
        before = store.export_document()
        identifier = str(uuid4())
        with patch.object(WorkspaceStore, "bump", side_effect=sqlite3.OperationalError("PRIVATE write failure")), \
                self.assertLogs("backend.coursework_api", level="ERROR") as logs:
            response = self.client.post("/api/analyzer/tests", json={
                "request_id": identifier, "text": "taxi", "grammar": "S -> NOUN",
            })
        self.assertEqual(response.status_code, 500, response.text)
        self.assertNotIn("PRIVATE", response.text + "".join(logs.output))
        self.assertEqual(store.export_document(), before)
        self.assertEqual(self.report()["summary"]["total"], 0)
        self.assertEqual(self.client.get(f"/api/analyzer/tests/{identifier}").status_code, 404)
        self.record(request_id=identifier)
        self.assertEqual(store.version, before["version"] + 1)

    def test_existing_workspace_schema_migrates_without_changing_saved_work(self):
        user = self.register()
        self.entry(text="Stored collection")
        self.save_profile(grammar="S -> NOUN", discussion="Keep this.")
        store = SharedWorkspaceStore(self.root, user["id"])
        before = store.export_document()
        with store.connection() as db:
            db.execute("DROP TABLE analyzer_tests")
        reopened = SharedWorkspaceStore(self.root, user["id"])
        self.assertEqual(reopened.export_document(), before)
        self.record()
        after = reopened.export_document()
        for key in ("projects", "entries", "history", "revisions", "coursework", "screenshots"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(len(after["analyzer_tests"]), 1)

    def test_backups_roundtrip_shared_tests_and_mutation_invalidates_preview(self):
        user = self.register()
        first_request = str(uuid4())
        second_request = str(uuid4())
        first = self.record("  taxi \r\n", request_id=first_request)
        project = str(uuid4())
        self.client.headers["X-Mboa-Project"] = project
        second = self.record("waka", "S -> VERB", request_id=second_request)
        store = SharedWorkspaceStore(self.root, user["id"])
        content = self.backup()
        document, _ = validate_archive(content)
        self.assertEqual(document["format"], 4)
        self.assertEqual(len(document["analyzer_tests"]), 2)
        self.assertEqual({row["project_id"] for row in document["analyzer_tests"]}, {"default"})
        preview = self.preview(content)
        self.assertEqual(preview["counts"]["analyzer_tests"], 2)
        self.record("zandolo")
        self.assertEqual(self.restore(preview).status_code, 409)
        current = store.export_document()
        preview = self.preview(content)
        with patch.object(tokenizer, "analyze_sentence", side_effect=AssertionError("Do not retokenize a backup")), \
                patch.object(analyzer, "parse_analysis", side_effect=AssertionError("Do not reparse a backup")):
            restored = self.restore(preview)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(store.export_document()["analyzer_tests"], document["analyzer_tests"])
        for scope, saved, request_id in (("default", first, first_request), (project, second, second_request)):
            self.client.headers["X-Mboa-Project"] = scope
            self.assertEqual(self.client.get(f"/api/analyzer/tests/{saved['id']}").json(), saved)
            self.assertEqual(self.record(saved["text"], saved["grammar_source"], request_id=request_id), saved)
            self.assertEqual(self.report()["summary"]["total"], 2)
        safety = self.client.get(f"/api/workspace/backups/{restored.json()['pre_restore_backup_id']}/download")
        self.assertEqual(validate_archive(safety.content)[0]["analyzer_tests"], current["analyzer_tests"])

    def test_legacy_backups_validate_offline_but_cannot_replace_shared_records(self):
        user = self.register()
        entry = self.entry(text="Legacy collection")
        store = SharedWorkspaceStore(self.root, user["id"])
        for version in (1, 2):
            original = store.export_document()
            for key in ("ownership", "test_requests", "legacy_profiles"):
                original.pop(key)
            original.pop("analyzer_tests")
            original["format"] = version
            if version == 1:
                original.pop("coursework")
                original.pop("screenshots")
            before = copy.deepcopy(original)
            normalized = WorkspaceStore.validate_document(original)
            self.assertEqual(original, before)
            self.assertEqual(normalized["format"], 3)
            self.assertEqual(normalized["analyzer_tests"], [])
            preview = self.client.post("/api/workspace/backups/preview", files={
                "file": ("legacy.zip", self.archive_document(original)),
            })
            self.assertEqual(preview.status_code, 422)
            self.assertEqual(self.report()["summary"]["total"], 0)
            self.assertEqual(self.client.get("/api/dataset").json()["entries"], [entry])

    def test_invalid_backup_snapshots_are_rejected_before_any_live_mutation(self):
        user = self.register()
        self.record()
        store = SharedWorkspaceStore(self.root, user["id"])
        original = store.export_document()
        mutations = (
            lambda record: record.update(id=str(uuid4())),
            lambda record: record.update(created_at="not-a-timestamp"),
            lambda record: record.update(grammar_source=" S -> NOUN "),
            lambda record: record.update(grammar_source="S -> MISSING"),
            lambda record: record.update(grammar_source="S -> VERB"),
            lambda record: record["lexical"]["tokens"][0].update(category="INVENTED"),
            lambda record: record["lexical"]["statistics"].update(total_tokens=100),
            lambda record: record["parse"].update(accepted="true"),
            lambda record: record["parse"].update(consumed=0),
            lambda record: record["grammar"].update(table={"S": ["not a table"]}),
            lambda record: record["grammar"].update(transformed={}),
            lambda record: record["grammar"].update(is_ll1=False),
            lambda record: record["metadata"].update(topics=["Invented"], matching_entries=0),
            lambda record: record["metadata"].update(languages=["not a declared language"]),
            lambda record: record.update(corpus={"unexpected": "snapshot"}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                invalid = copy.deepcopy(original)
                row = invalid["analyzer_tests"][0]
                record = json.loads(row["data"])
                mutate(record)
                row["data"] = json.dumps(record)
                with self.assertRaises(CollectionError) as failure:
                    WorkspaceStore.validate_document(invalid)
                self.assertEqual(failure.exception.status_code, 422)
                response = self.client.post("/api/workspace/backups/preview", files={
                    "file": ("invalid.zip", self.archive_document(invalid)),
                })
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(store.export_document(), original)
        for change in (
            lambda doc: doc["analyzer_tests"].append(copy.deepcopy(doc["analyzer_tests"][0])),
            lambda doc: doc["analyzer_tests"][0].update(project_id=str(uuid4())),
            lambda doc: doc["analyzer_tests"][0].update(unrecognized="field"),
            lambda doc: doc.pop("analyzer_tests"),
        ):
            invalid = copy.deepcopy(original)
            change(invalid)
            with self.assertRaises(CollectionError):
                WorkspaceStore.validate_document(invalid)
        self.assertEqual(store.export_document(), original)

    def test_failed_backup_restore_rolls_back_analyzer_deletion_and_workspace_version(self):
        user = self.register()
        self.record()
        content = self.backup()
        self.record("waka")
        store = SharedWorkspaceStore(self.root, user["id"])
        before = store.export_document()
        preview = self.preview(content)
        with store.connection() as db:
            db.execute("""
                CREATE TRIGGER fail_analyzer_restore BEFORE INSERT ON analyzer_tests
                BEGIN SELECT RAISE(ABORT, 'PRIVATE synthetic restore failure'); END
            """)
        response = self.restore(preview)
        self.assertEqual(response.status_code, 500, response.text)
        self.assertNotIn("PRIVATE", response.text)
        self.assertEqual(store.export_document(), before)
        self.assertEqual(self.report()["summary"]["total"], 2)


if __name__ == "__main__":
    unittest.main()
