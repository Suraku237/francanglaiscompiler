import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from filelock import Timeout

from backend import analyzer, coursework, coursework_export, coursework_store
from backend.config import Settings
from backend.main import create_app
from backend.tests.test_api import ApiTestCase
from backend.tests.test_compiler_workspace import CompilerHostedCase
from backend.tests.test_hosted import HISTORY
from backend.workspace_backups import validate_archive
from backend.shared_workspace import SharedWorkspaceStore as WorkspaceStore
from compiler.lexer import tokenizer
from compiler.parser.service import DEFAULT_GRAMMAR
from data_collector import dataset


class AnalyzerTests(ApiTestCase):
    def entry(self, text, **fields):
        response = self.client.post("/api/dataset", json={"text": text, **fields})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def analyze(self, text="taxi", grammar="S -> NOUN"):
        response = self.client.post("/api/analyzer/analyze", json={"text": text, "grammar": grammar})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_state_contains_only_analyzer_configuration_and_corpus_counts(self):
        with patch.object(coursework, "requirements", side_effect=AssertionError("No report readiness")), \
                patch.object(coursework_store, "list_screenshots", side_effect=AssertionError("No screenshot list")), \
                patch.object(coursework, "analyze_grammar", side_effect=AssertionError("No grammar preparation")):
            response = self.client.get("/api/analyzer")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "grammar": DEFAULT_GRAMMAR.strip(),
            "lexical_spec": coursework.lexical_spec(),
            "stats": {"total": 0, "sentences": 0},
        })
        self.assertFalse((self.directory / "coursework" / "project.json").exists())
        self.entry("taxi", entry_type="Word")
        self.entry("Le taxi don refuse.", entry_type="Sentence")
        self.entry("je wanda", entry_type="Phrase")
        saved = self.client.put("/api/analyzer/grammar", json={"grammar": "  S -> NOUN\n"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json(), {"grammar": "S -> NOUN"})
        state = self.client.get("/api/analyzer").json()
        self.assertEqual(set(state), {"grammar", "lexical_spec", "stats"})
        self.assertEqual(state["grammar"], "S -> NOUN")
        self.assertEqual(state["stats"], {"total": 3, "sentences": 1})

    def test_one_preparation_uses_identical_manual_and_corpus_tokens_with_raw_annotations(self):
        word = self.entry("zandolo", entry_type="Word", language="francanglais",
                          lexical_category="NOUN", review_status="approved")
        text = "  Le ZANDOLO DON\tREFUSE.\r\nJE   WANDA !  "
        sentence = self.entry(text)
        expected_lexical = self.client.post("/api/analyze", json={"text": text}).json()
        before = self.client.get("/api/dataset").json()
        with patch.object(analyzer, "analyze_grammar", wraps=analyzer.analyze_grammar) as prepare, \
                patch.object(analyzer, "build_lexicon", wraps=analyzer.build_lexicon) as learn, \
                patch.object(coursework, "build_lexicon", wraps=coursework.build_lexicon) as relearn, \
                patch.object(dataset, "load_all", wraps=dataset.load_all) as load, \
                patch.object(analyzer, "parse_analysis", wraps=analyzer.parse_analysis) as manual_parse, \
                patch.object(coursework, "parse_analysis", wraps=coursework.parse_analysis) as corpus_parse, \
                patch.object(coursework, "requirements", side_effect=AssertionError("No report readiness")):
            body = self.analyze(text, DEFAULT_GRAMMAR)
        prepare.assert_called_once_with(DEFAULT_GRAMMAR.strip())
        learn.assert_called_once()
        relearn.assert_not_called()
        load.assert_called_once_with()
        manual_parse.assert_called_once()
        self.assertEqual(corpus_parse.call_count, 2)
        prepared = manual_parse.call_args.args[0]
        self.assertTrue(all(call.args[0] is prepared for call in corpus_parse.call_args_list))
        self.assertEqual(manual_parse.call_args.args[1], body["lexical"]["tokens"])
        self.assertEqual(set(body), {"text", "lexical", "grammar", "parse", "corpus", "approval"})
        self.assertEqual(body["text"], text)
        self.assertEqual({key: body["lexical"][key] for key in expected_lexical}, expected_lexical)
        self.assertEqual(body["lexical"]["verb_phrases"], ["DON\tREFUSE", "JE   WANDA"])
        self.assertEqual(body["lexical"]["slang_expressions"], ["JE   WANDA"])
        self.assertEqual(body["lexical"]["statistics"]["total_tokens"], len(body["lexical"]["tokens"]))
        self.assertEqual(set(body["corpus"]), {"lexical", "tests", "summary"})
        lexical = body["corpus"]["lexical"]
        statements = {row["id"]: row for row in lexical["statements"]}
        self.assertEqual(set(statements), {word["id"], sentence["id"]})
        self.assertEqual(statements[sentence["id"]]["tokens"], body["lexical"]["tokens"])
        self.assertEqual(statements[sentence["id"]]["text"], text)
        self.assertEqual(statements[sentence["id"]]["slang_expressions"], ["JE   WANDA"])
        self.assertIn({"token": "zandolo", "count": 2}, lexical["frequencies"])
        self.assertIn({
            "normalized": "zandolo",
            "forms": [{"text": "zandolo", "count": 1}, {"text": "ZANDOLO", "count": 1}],
        }, lexical["variations"])
        same_input_test = next(row for row in body["corpus"]["tests"] if row["id"] == sentence["id"])
        self.assertEqual({key: same_input_test[key] for key in body["parse"]}, body["parse"])
        self.assertEqual(self.client.get("/api/dataset").json(), before)

    def test_unsaved_grammar_is_used_without_saving_manual_input_or_changing_corpus(self):
        entry = self.entry("waka", source_location="Synthetic fixture", notes="Keep provenance")
        before = self.client.get("/api/dataset").json()
        saved_grammar = self.client.get("/api/analyzer").json()["grammar"]
        body = self.analyze("  taxi  ", "S -> NOUN")
        self.assertTrue(body["parse"]["accepted"])
        self.assertEqual(body["grammar"]["original"], {"S": [["NOUN"]]})
        self.assertEqual(body["corpus"]["summary"], {"accepted": 0, "rejected": 1, "total": 1})
        self.assertEqual([case["id"] for case in body["corpus"]["tests"]], [entry["id"]])
        self.assertEqual(self.client.get("/api/dataset").json(), before)
        self.assertEqual(self.client.get("/api/analyzer").json()["grammar"], saved_grammar)

    def test_veux_reaches_parser_as_verb_and_acceptance_still_depends_on_grammar(self):
        for word in ("veux", "Veux", "VEUX"):
            text = f"  je\t{word} acheter\n"
            for grammar, accepted in (
                ("S -> FRENCH_FUNCTION_WORD VERB VERB", True),
                ("S -> NOUN", False),
            ):
                with self.subTest(word=word, grammar=grammar):
                    body = self.analyze(text, grammar)
                    self.assertEqual(body["text"], text)
                    self.assertEqual(body["lexical"]["tokens"], [
                        {"text": "je", "category": "FRENCH_FUNCTION_WORD"},
                        {"text": word, "category": "VERB"},
                        {"text": "acheter", "category": "VERB"},
                    ])
                    self.assertEqual(body["lexical"]["statistics"]["category_counts"], {
                        "FRENCH_FUNCTION_WORD": 1, "VERB": 2,
                    })
                    self.assertEqual(body["parse"]["accepted"], accepted)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)

    def test_sentence_statistics_count_all_actual_tokens_separately_from_collection(self):
        self.entry("taxi taxi")
        before = self.client.get("/api/dataset").json()
        text = "  Je veux veux, VEUX + + 12\t"
        with patch.object(tokenizer, "analyze_sentence", wraps=tokenizer.analyze_sentence) as lexer:
            body = self.analyze(text)
        self.assertEqual([call.args[0] for call in lexer.call_args_list], [text, "taxi taxi"])
        self.assertEqual(body["lexical"]["statistics"], {
            "frequencies": [
                {"token": "veux", "count": 3}, {"token": "+", "count": 2},
                {"token": "je", "count": 1}, {"token": ",", "count": 1},
                {"token": "12", "count": 1},
            ],
            "category_counts": {
                "FRENCH_FUNCTION_WORD": 1, "VERB": 3, "PUNCTUATION": 1, "UNKNOWN": 2, "NUMBER": 1,
            },
            "variations": [{
                "normalized": "veux",
                "forms": [{"text": "veux", "count": 2}, {"text": "VEUX", "count": 1}],
            }],
            "unknown_tokens": [{"token": "+", "count": 2}],
            "total_tokens": 8,
        })
        self.assertEqual(body["lexical"]["slang_expressions"], [])
        corpus = body["corpus"]["lexical"]
        self.assertEqual(corpus["total_tokens"], 2)
        self.assertEqual(corpus["frequencies"], [{"token": "taxi", "count": 2}])
        self.assertEqual(corpus["category_counts"], {"NOUN": 2})
        self.assertEqual(self.client.get("/api/dataset").json(), before)

    def test_statistics_preserve_existing_unicode_variation_and_support_one_shot_tokens(self):
        tokens = iter([
            {"text": "École", "category": "NOUN"},
            {"text": "école", "category": "NOUN"},
            {"text": "ecole", "category": "UNKNOWN"},
        ])
        self.assertEqual(coursework.token_statistics(tokens), {
            "frequencies": [{"token": "école", "count": 2}, {"token": "ecole", "count": 1}],
            "category_counts": {"NOUN": 2, "UNKNOWN": 1},
            "variations": [{
                "normalized": "ecole",
                "forms": [{"text": "École", "count": 1}, {"text": "école", "count": 1},
                          {"text": "ecole", "count": 1}],
            }],
            "unknown_tokens": [{"token": "ecole", "count": 1}],
            "total_tokens": 3,
        })

    def test_empty_and_whitespace_inputs_are_actually_lexed_and_test_epsilon(self):
        for text in ("", " \r\n\t ", " " * 4000):
            for grammar, accepted in (("S -> epsilon", True), ("S -> NOUN", False)):
                with self.subTest(text=repr(text[:20]), grammar=grammar):
                    with patch.object(tokenizer, "analyze_sentence", wraps=tokenizer.analyze_sentence) as lexer:
                        body = self.analyze(text, grammar)
                    lexer.assert_called_once_with(text, {})
                    self.assertEqual(body["text"], text)
                    self.assertEqual(body["lexical"], {
                        "tokens": [], "code_mixed_spans": [], "verb_phrases": [], "slang_expressions": [],
                        "statistics": {
                            "frequencies": [], "category_counts": {}, "variations": [],
                            "unknown_tokens": [], "total_tokens": 0,
                        },
                    })
                    self.assertEqual(body["parse"]["accepted"], accepted)
                    self.assertEqual(body["parse"]["consumed"], 0)
                    self.assertEqual(body["parse"]["error"] is None, accepted)
                    self.assertTrue(body["parse"]["trace"])
                    self.assertEqual(body["corpus"]["summary"], {"accepted": 0, "rejected": 0, "total": 0})

    def test_unknown_symbols_are_preserved_and_never_treated_as_a_wildcard(self):
        text = "taxi +\t🙂"
        body = self.analyze(text)
        self.assertEqual(body["lexical"]["tokens"], [
            {"text": "taxi", "category": "NOUN"},
            {"text": "+", "category": "UNKNOWN"},
            {"text": "🙂", "category": "UNKNOWN"},
        ])
        self.assertFalse(body["parse"]["accepted"])
        self.assertIn("UNKNOWN", body["parse"]["error"])
        explicit = self.analyze(text, "S -> NOUN UNKNOWN UNKNOWN")
        self.assertTrue(explicit["parse"]["accepted"])
        self.assertEqual(explicit["parse"]["consumed"], 3)
        self.assertTrue(any("never as a wildcard" in warning for warning in explicit["grammar"]["warnings"]))

    def test_conflicts_are_returned_and_reject_both_manual_and_corpus_parses(self):
        self.entry("taxi")
        body = self.analyze(grammar="S -> A | B\nA -> NOUN\nB -> NOUN")
        self.assertFalse(body["grammar"]["is_ll1"])
        self.assertEqual(body["grammar"]["conflicts"], [
            {"nonterminal": "S", "terminal": "NOUN", "productions": [["A"], ["B"]]},
        ])
        self.assertNotIn("NOUN", body["grammar"]["table"].get("S", {}))
        for parsed in (body["parse"], *body["corpus"]["tests"]):
            self.assertFalse(parsed["accepted"])
            self.assertIn("No conflicting production was selected", parsed["error"])
            self.assertTrue(parsed["trace"])
        self.assertEqual(body["corpus"]["summary"], {"accepted": 0, "rejected": 1, "total": 1})

    def test_conflicting_reviewed_annotations_stay_unknown(self):
        for language, category in (("francanglais", "NOUN"), ("pidgin", "VERB")):
            self.entry("zandolo", entry_type="Word", language=language,
                       lexical_category=category, review_status="approved")
        body = self.analyze("zandolo")
        self.assertEqual(body["lexical"]["tokens"], [{"text": "zandolo", "category": "UNKNOWN"}])
        self.assertFalse(body["parse"]["accepted"])
        self.assertEqual(body["corpus"]["lexical"]["unknown_tokens"], [{"token": "zandolo", "count": 2}])
        self.assertEqual(body["corpus"]["summary"], {"accepted": 0, "rejected": 2, "total": 2})

    def test_invalid_requests_and_grammars_have_explicit_errors(self):
        for grammar in ("", " \t ", "S ->", "S -> MISSING", "x" * 12001,
                        "S -> " + " ".join(["NOUN"] * 21)):
            for path, payload in (
                ("/api/analyzer/grammar", {"grammar": grammar}),
                ("/api/analyzer/analyze", {"grammar": grammar, "text": ""}),
            ):
                with self.subTest(path=path, grammar=grammar[:50]):
                    method = self.client.put if path.endswith("/grammar") else self.client.post
                    response = method(path, json=payload)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertTrue(response.json()["detail"])
        for payload in (
            {"grammar": "S -> NOUN"}, {"text": "taxi"}, {"text": None, "grammar": "S -> NOUN"},
            {"text": 7, "grammar": "S -> NOUN"}, {"text": "x" * 4001, "grammar": "S -> NOUN"},
            {"text": "taxi", "grammar": "S -> NOUN", "extra": "not accepted"},
        ):
            response = self.client.post("/api/analyzer/analyze", json=payload)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.put("/api/analyzer/grammar", json={
            "grammar": "S -> NOUN", "discussion": "Not a grammar field",
        }).status_code, 422)

    def test_parser_limits_reject_without_truncating_lexical_results(self):
        body = self.analyze(" ".join(["taxi"] * 257), "S -> NOUN S | epsilon")
        self.assertEqual(len(body["lexical"]["tokens"]), 257)
        self.assertFalse(body["parse"]["accepted"])
        self.assertIn("256-token limit", body["parse"]["error"])
        body = self.analyze("z" * 1001, "S -> UNKNOWN")
        self.assertEqual(body["lexical"]["tokens"], [{"text": "z" * 1001, "category": "UNKNOWN"}])
        self.assertFalse(body["parse"]["accepted"])
        self.assertIn("1000-character", body["parse"]["error"])

    def test_corpus_limits_are_kept_before_computation(self):
        cases = (
            ([{"text": "taxi"}] * 501, "500 entries"),
            ([{"text": "x" * 4000}] * 26, "100000 text characters"),
            ([{"text": "x" * 4001}], "4000 characters"),
        )
        for entries, detail in cases:
            with self.subTest(detail=detail), patch.object(dataset, "load_all", return_value=entries), \
                    patch.object(analyzer, "analyze_grammar", side_effect=AssertionError("Reject before preparation")):
                response = self.client.post("/api/analyzer/analyze", json={"text": "", "grammar": "S -> epsilon"})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn(detail, response.json()["detail"])

    def test_lexer_failure_is_not_disguised_as_empty_success(self):
        with patch.object(tokenizer, "analyze_sentence", side_effect=ValueError("Synthetic lexer failure")):
            response = self.client.post("/api/analyzer/analyze", json={"text": "", "grammar": "S -> epsilon"})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json(), {"detail": "Synthetic lexer failure"})

    def test_report_export_is_not_exposed_or_executed(self):
        with patch.object(coursework_export, "export_bundle", side_effect=AssertionError("No report generation")):
            self.assertEqual(self.client.get("/api/coursework/export").status_code, 404)
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertNotIn("/api/coursework/export", paths)
        self.assertEqual(set(paths["/api/analyzer"]), {"get"})
        self.assertEqual(set(paths["/api/analyzer/grammar"]), {"put"})
        self.assertEqual(set(paths["/api/analyzer/analyze"]), {"post"})


class HostedAnalyzerTests(CompilerHostedCase):
    def test_analyzer_requires_authentication_csrf_and_same_origin(self):
        self.assertEqual(self.client.get("/api/analyzer").status_code, 401)
        self.assertEqual(self.client.put("/api/analyzer/grammar", json={"grammar": "S -> NOUN"}).status_code, 401)
        request = {"text": "taxi", "grammar": "S -> NOUN"}
        self.assertEqual(self.client.post("/api/analyzer/analyze", json=request).status_code, 401)
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        before = store.export_document()
        for headers in ({"X-CSRF-Token": ""}, {"Origin": "https://attacker.example"}):
            for response in (
                self.client.put("/api/analyzer/grammar", json={"grammar": "S -> NOUN"}, headers=headers),
                self.client.post("/api/analyzer/analyze", json=request, headers=headers),
            ):
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.client.get("/api/analyzer").status_code, 200)
        self.assertEqual(self.client.post("/api/analyzer/analyze", json=request).status_code, 200)
        self.assertEqual(self.client.get("/api/coursework/export").status_code, 404)
        self.assertEqual(store.export_document(), before)

    def test_grammar_corpus_and_annotations_are_shared_with_creator_only_saves(self):
        first_user = self.register()
        first = self.entry(text="zandolo", entry_type="Word", lexical_category="NOUN", review_status="approved")
        self.assertEqual(self.client.put("/api/analyzer/grammar", json={"grammar": "S -> NOUN"}).status_code, 200)
        request = {"text": "zandolo", "grammar": "S -> NOUN"}
        first_body = self.client.post("/api/analyzer/analyze", json=request).json()
        self.assertTrue(first_body["parse"]["accepted"])
        self.assertEqual([row["id"] for row in first_body["corpus"]["tests"]], [first["id"]])
        second_project = str(uuid4())
        self.client.headers["X-Mboa-Project"] = second_project
        shared = self.client.get("/api/analyzer").json()
        self.assertEqual(shared["stats"], {"total": 1, "sentences": 0})
        self.assertEqual(shared["grammar"], "S -> NOUN")
        selected = self.client.get("/api/analyzer", params={"project": second_project}).json()
        self.assertEqual(selected["grammar"], "S -> NOUN")
        selected_body = self.client.post("/api/analyzer/analyze", params={"project": second_project},
                                         json=request).json()
        self.assertTrue(selected_body["parse"]["accepted"])
        self.assertEqual([row["id"] for row in selected_body["corpus"]["tests"]], [first["id"]])
        first_before = WorkspaceStore(self.root, first_user["id"]).export_document()
        other = self.other()
        self.register(other, "second@example.com")
        self.assertEqual(other.get("/api/analyzer").json()["stats"], {"total": 1, "sentences": 0})
        other_body = other.post("/api/analyzer/analyze", json=request).json()
        self.assertEqual(other_body["lexical"]["tokens"], [{"text": "zandolo", "category": "NOUN"}])
        self.assertEqual([row["id"] for row in other_body["corpus"]["tests"]], [first["id"]])
        for response in (
            other.get("/api/analyzer", params={"project": second_project}),
            other.post("/api/analyzer/analyze", params={"project": second_project}, json=request),
        ):
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(other.put("/api/analyzer/grammar", json={"grammar": "S -> UNKNOWN"}).status_code, 403)
        self.assertEqual(WorkspaceStore(self.root, first_user["id"]).export_document(), first_before)

    def test_grammar_only_save_preserves_legacy_profile_history_screenshots_and_backups(self):
        user = self.register()
        profile = self.save_profile(
            group_members=["Amina", "Benoit", "Chantal"], grammar="S -> VERB",
            manual_transcription_confirmed=True, grammar_rationale="Keep the original rationale.",
            discussion="Keep the original discussion.", collection_method="Keep original manual provenance.",
            limitations="Keep the original limitations.",
        )
        self.entry(text="  taxi\t ", notes="Raw\nnotes", contributor="Test contributor", source_location="Test fixture")
        image = self.screenshot("Stored evidence")
        image_bytes = self.client.get(image["url"]).content
        self.assertEqual(self.client.post("/api/workspace/history", json=HISTORY).status_code, 201)
        store = WorkspaceStore(self.root, user["id"])
        before = store.export_document()
        backup = self.backup()
        preview = self.preview(backup)
        backups_before = self.client.get("/api/workspace/backups").json()
        response = self.client.put("/api/analyzer/grammar", json={"grammar": " \tS -> NOUN\r\n "})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["grammar"], "S -> NOUN")
        self.assertEqual(response.json()["grammar_ownership"]["owner_id"], user["id"])
        after = store.export_document()
        self.assertEqual(after["version"], before["version"] + 1)
        for key in ("projects", "entries", "history", "revisions", "screenshots"):
            self.assertEqual(after[key], before[key], key)
        expected_profile = {**profile, "grammar": "S -> NOUN"}
        self.assertEqual(json.loads(after["coursework"][0]["data"]), expected_profile)
        self.assertEqual(self.client.get("/api/coursework").json()["project"], expected_profile)
        self.assertEqual(self.client.get(image["url"]).content, image_bytes)
        self.assertEqual(self.client.get("/api/workspace/backups").json(), {
            **backups_before, "workspace_version": before["version"] + 1,
        })
        archived, _ = validate_archive(backup)
        self.assertEqual(json.loads(archived["coursework"][0]["data"]), profile)
        self.assertEqual(self.restore(preview).status_code, 409)
        self.assertEqual(store.export_document(), after)
        app = create_app(Settings(), auth_settings=self.settings,
                         mailer=lambda address, _subject, text: self.mail.append((address, text)))
        reopened = self.stack.enter_context(TestClient(app, headers={"Origin": "http://testserver"}))
        self.login(reopened)
        self.assertEqual(reopened.get("/api/analyzer").json()["grammar"], "S -> NOUN")
        self.assertEqual(reopened.get("/api/coursework").json()["project"], expected_profile)

    def test_failed_grammar_saves_keep_the_previous_profile_and_workspace_version(self):
        user = self.register()
        self.save_profile(grammar="S -> NOUN", discussion="Do not erase this legacy field.")
        store = WorkspaceStore(self.root, user["id"])
        before = store.export_document()
        for grammar in ("S -> MISSING", "S ->", "x" * 12001):
            response = self.client.put("/api/analyzer/grammar", json={"grammar": grammar})
            self.assertEqual(response.status_code, 422, response.text)
        with patch.object(WorkspaceStore, "save_coursework", side_effect=sqlite3.OperationalError("PRIVATE storage path")):
            response = self.client.put("/api/analyzer/grammar", json={"grammar": "S -> VERB"})
        self.assertEqual(response.status_code, 500, response.text)
        self.assertNotIn("PRIVATE", response.text)
        with patch.object(WorkspaceStore, "load_coursework", side_effect=Timeout("PRIVATE.lock")):
            response = self.client.put("/api/analyzer/grammar", json={"grammar": "S -> VERB"})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn("PRIVATE", response.text)
        self.assertEqual(store.export_document(), before)

    def test_analysis_holds_one_workspace_snapshot_and_never_mutates_it(self):
        user = self.register()
        self.entry(text="zandolo", entry_type="Word", lexical_category="NOUN", review_status="approved")
        self.entry(text="  ZANDOLO taxi  ")
        store = WorkspaceStore(self.root, user["id"])
        before = store.export_document()
        locks = []
        original_lexer = tokenizer.analyze_sentence

        def observe_lexer(text, learned):
            locks.append(dataset.dataset_lock().is_locked)
            return original_lexer(text, learned)

        with patch.object(dataset, "load_all", wraps=dataset.load_all) as load, \
                patch.object(tokenizer, "analyze_sentence", side_effect=observe_lexer):
            response = self.client.post("/api/analyzer/analyze", json={
                "text": "zandolo", "grammar": "S -> NOUN | NOUN NOUN",
            })
        self.assertEqual(response.status_code, 200, response.text)
        load.assert_called_once_with()
        self.assertEqual(locks, [True, True, True])
        self.assertTrue(response.json()["parse"]["accepted"])
        self.assertEqual(response.json()["corpus"]["summary"], {"accepted": 2, "rejected": 0, "total": 2})
        self.assertEqual(store.export_document(), before)

    def test_grammar_read_modify_write_is_locked_against_concurrent_profile_updates(self):
        user = self.register()
        original_profile = self.save_profile(grammar="S -> VERB", collection_method="Preserved provenance.")
        store = WorkspaceStore(self.root, user["id"])
        version = store.version
        loaded = Event()
        release = Event()
        locks = []
        load_project = coursework_store.load_project
        save_project = coursework_store.save_project

        def observe_load():
            profile = load_project()
            locks.append(dataset.dataset_lock().is_locked)
            loaded.set()
            if not release.wait(20):
                raise AssertionError("Grammar test did not release the reader.")
            return profile

        def observe_save(profile):
            locks.append(dataset.dataset_lock().is_locked)
            return save_project(profile)

        def update_discussion():
            with store.lock():
                profile = store.load_coursework()
                assert profile is not None
                store.save_coursework(profile.model_copy(update={"discussion": "Concurrent retained discussion."}))

        with ThreadPoolExecutor(max_workers=2) as executor, \
                patch.object(coursework_store, "load_project", side_effect=observe_load), \
                patch.object(coursework_store, "save_project", side_effect=observe_save):
            grammar_save = executor.submit(
                self.client.put, "/api/analyzer/grammar", json={"grammar": "S -> NOUN"},
            )
            try:
                self.assertTrue(loaded.wait(10), "Grammar request never read the profile.")
                with self.assertRaises(Timeout):
                    with store.lock().acquire(timeout=0):
                        pass
                discussion_save = executor.submit(update_discussion)
            finally:
                release.set()
            response = grammar_save.result(timeout=20)
            discussion_save.result(timeout=20)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(locks, [True, True])
        self.assertEqual(store.version, version + 2)
        profile = store.load_coursework()
        assert profile is not None
        self.assertEqual(profile.model_dump(), {
            **original_profile, "grammar": "S -> NOUN", "discussion": "Concurrent retained discussion.",
        })
