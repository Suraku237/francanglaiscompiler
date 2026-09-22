"""Regression tests for calculated grammar analysis and predictive parsing."""

from copy import deepcopy
from itertools import product
import json
import unittest
from unittest.mock import patch
from typing import Any

from compiler.lexer.tokenizer import analyze_sentence
from compiler.parser import service
from compiler.parser.analysis import (
    calculate_first,
    calculate_follow,
    left_recursive_nonterminals,
    nullable_nonterminals,
)
from compiler.parser.grammar import (
    Grammar,
    GrammarError,
    MAX_ALTERNATIVES,
    MAX_GRAMMAR_CHARACTERS,
    MAX_NONTERMINALS,
    MAX_RHS_LENGTH,
    TERMINAL_CATEGORIES,
    read_grammar,
)
from compiler.parser.predictive import MAX_INPUT_TOKENS, MAX_TOKEN_TEXT_LENGTH
from compiler.parser.service import (
    DEFAULT_GRAMMAR,
    analyze_grammar,
    parse_analysis,
    parse_tokens,
)


def token_stream(*categories: str) -> list[dict[str, str]]:
    return [{"text": category.lower(), "category": category} for category in categories]


def bounded_language(grammar: Grammar, start: str, max_length: int) -> set[tuple[str, ...]]:
    """Independent finite-language fixed point, not based on parser tables."""
    languages: dict[str, set[tuple[str, ...]]] = {lhs: set() for lhs in grammar}
    changed = True
    while changed:
        changed = False
        for lhs, alternatives in grammar.items():
            for rhs in alternatives:
                words: set[tuple[str, ...]] = {()}
                for symbol in rhs:
                    suffixes = languages[symbol] if symbol in grammar else {(symbol,)}
                    words = {
                        prefix + suffix
                        for prefix in words
                        for suffix in suffixes
                        if len(prefix) + len(suffix) <= max_length
                    }
                additions = words - languages[lhs]
                if additions:
                    languages[lhs].update(additions)
                    changed = True
    return languages[start]


class GrammarNotationTests(unittest.TestCase):
    def test_comments_repeated_definitions_forward_references_and_start_order(self) -> None:
        grammar = read_grammar("""
            # A complete comment.
            Sentence -> Item | epsilon

            Item -> NOUN # An inline comment.
            Sentence -> VERB
        """)
        self.assertEqual(list(grammar), ["Sentence", "Item"])
        self.assertEqual(grammar, {"Sentence": [["Item"], [], ["VERB"]], "Item": [["NOUN"]]})

    def test_every_real_lexer_category_is_a_supported_terminal(self) -> None:
        expected = {
            "NUMBER", "PUNCTUATION", "SLANG", "PIDGIN_MARKER", "NOUN", "VERB",
            "FRENCH_FUNCTION_WORD", "ENGLISH_FUNCTION_WORD", "ENGLISH_VERB_LIKE",
            "FRENCH_VERB_LIKE", "UNKNOWN",
        }
        self.assertEqual(set(TERMINAL_CATEGORIES), expected)
        analysis = analyze_grammar("S -> " + " | ".join(TERMINAL_CATEGORIES))
        self.assertEqual(set(analysis["terminals"]), expected)
        for category in expected:
            with self.subTest(category=category):
                self.assertTrue(parse_analysis(analysis, token_stream(category))["accepted"])

    def test_empty_grammar_and_missing_arrow_are_rejected(self) -> None:
        for text in ("", " \n# comment", "S : NOUN", "S => NOUN", "S -> NOUN -> VERB"):
            with self.subTest(text=text), self.assertRaises(GrammarError):
                analyze_grammar(text)

    def test_empty_alternatives_require_explicit_epsilon(self) -> None:
        for text in ("S ->", "S -> | NOUN", "S -> NOUN |", "S -> NOUN || VERB"):
            with self.subTest(text=text), self.assertRaisesRegex(GrammarError, "empty alternative"):
                read_grammar(text)

    def test_epsilon_must_stand_alone(self) -> None:
        for text in ("S -> epsilon NOUN", "S -> NOUN epsilon", "S -> epsilon epsilon"):
            with self.subTest(text=text), self.assertRaisesRegex(GrammarError, "must stand alone"):
                read_grammar(text)
        self.assertEqual(read_grammar("S -> epsilon"), {"S": [[]]})

    def test_nonterminal_identifiers_and_reserved_names(self) -> None:
        for lhs in ("1S", "Bad-name", "Bad name", "é", "$", "epsilon", "NOUN"):
            with self.subTest(lhs=lhs), self.assertRaises(GrammarError):
                read_grammar(f"{lhs} -> VERB")
        self.assertEqual(read_grammar("_Sentence2 -> NOUN"), {"_Sentence2": [["NOUN"]]})

    def test_quoted_literal_and_end_marker_symbols_are_not_terminals(self) -> None:
        for symbol in ("'NOUN'", '"NOUN"', "$", "ε", ".", "NOUN*", "word"):
            with self.subTest(symbol=symbol), self.assertRaises(GrammarError):
                read_grammar(f"S -> {symbol}")

    def test_unknown_symbol_reports_line_and_spelling_suggestion(self) -> None:
        with self.assertRaisesRegex(GrammarError, "Line 1: unknown symbol 'Subjet'.*'Subject'"):
            read_grammar("S -> Subjet VERB\nSubject -> NOUN")

    def test_non_string_grammar_is_a_value_error(self) -> None:
        invalid: Any = None
        with self.assertRaisesRegex(ValueError, "must be a string"):
            analyze_grammar(invalid)

    def test_duplicate_productions_do_not_create_artificial_conflicts(self) -> None:
        analysis = analyze_grammar("S -> NOUN | NOUN\nS -> NOUN")
        self.assertEqual(analysis["original"], {"S": [["NOUN"]]})
        self.assertEqual(analysis["conflicts"], [])
        self.assertTrue(analysis["is_ll1"])

    def test_character_limit_boundary(self) -> None:
        prefix = "S -> NOUN\n#"
        text = prefix + "x" * (MAX_GRAMMAR_CHARACTERS - len(prefix))
        self.assertEqual(read_grammar(text), {"S": [["NOUN"]]})
        with self.assertRaisesRegex(GrammarError, "character limit"):
            read_grammar(text + "x")

    def test_original_nonterminal_limit_boundary(self) -> None:
        text = "\n".join(f"N{i} -> NOUN" for i in range(MAX_NONTERMINALS))
        self.assertEqual(len(read_grammar(text)), MAX_NONTERMINALS)
        with self.assertRaisesRegex(GrammarError, "nonterminal limit"):
            read_grammar(text + "\nOverflow -> NOUN")

    def test_alternative_limit_counts_even_duplicate_input_alternatives(self) -> None:
        text = "S -> " + " | ".join(["NOUN"] * MAX_ALTERNATIVES)
        self.assertEqual(read_grammar(text), {"S": [["NOUN"]]})
        with self.assertRaisesRegex(GrammarError, "alternative limit"):
            read_grammar(text + " | NOUN")

    def test_rhs_length_limit_boundary(self) -> None:
        text = "S -> " + " ".join(["NOUN"] * MAX_RHS_LENGTH)
        self.assertEqual(len(read_grammar(text)["S"][0]), MAX_RHS_LENGTH)
        with self.assertRaisesRegex(GrammarError, "right-hand side exceeds"):
            read_grammar(text + " NOUN")


class FirstFollowTests(unittest.TestCase):
    def test_nullable_sequences_first_follow_and_epsilon_table_entry(self) -> None:
        text = "S -> A B C\nA -> NOUN | epsilon\nB -> VERB | epsilon\nC -> NUMBER | epsilon"
        analysis = analyze_grammar(text)
        self.assertEqual(nullable_nonterminals(analysis["transformed"]), {"S", "A", "B", "C"})
        self.assertEqual(analysis["first"], {
            "S": ["NOUN", "NUMBER", "VERB", "epsilon"],
            "A": ["NOUN", "epsilon"],
            "B": ["VERB", "epsilon"],
            "C": ["NUMBER", "epsilon"],
        })
        self.assertEqual(analysis["follow"], {
            "S": ["$"], "A": ["$", "NUMBER", "VERB"], "B": ["$", "NUMBER"], "C": ["$"],
        })
        self.assertEqual(analysis["table"]["S"]["$"], ["A", "B", "C"])
        self.assertEqual(analysis["table"]["A"]["VERB"], [])
        self.assertTrue(analysis["is_ll1"])
        for categories in ((), ("NOUN",), ("VERB", "NUMBER"), ("NOUN", "VERB", "NUMBER")):
            with self.subTest(categories=categories):
                self.assertTrue(parse_analysis(analysis, token_stream(*categories))["accepted"])

    def test_fixed_points_propagate_across_later_definitions(self) -> None:
        analysis = analyze_grammar("S -> A\nA -> B\nB -> C\nC -> NOUN | epsilon")
        self.assertEqual(analysis["first"], {lhs: ["NOUN", "epsilon"] for lhs in "SABC"})
        self.assertEqual(analysis["follow"], {lhs: ["$"] for lhs in "SABC"})

    def test_follow_covers_repeated_occurrences_and_nullable_suffixes(self) -> None:
        analysis = analyze_grammar("S -> A A NUMBER\nA -> NOUN | epsilon")
        self.assertEqual(analysis["follow"]["A"], ["NOUN", "NUMBER"])
        self.assertEqual(analysis["follow"]["S"], ["$"])
        self.assertNotIn("epsilon", analysis["follow"]["A"])

    def test_fixed_points_terminate_on_nullable_cycles_without_rewriting(self) -> None:
        grammar = read_grammar("S -> A NUMBER\nA -> B | epsilon\nB -> A | NOUN")
        first = calculate_first(grammar)
        follow = calculate_follow(grammar, "S", first)
        self.assertEqual(nullable_nonterminals(grammar), {"A", "B"})
        self.assertEqual(first["S"], {"NOUN", "NUMBER"})
        self.assertEqual(first["A"], {"NOUN", "epsilon"})
        self.assertEqual(first["B"], {"NOUN", "epsilon"})
        self.assertEqual(follow, {"S": {"$"}, "A": {"NUMBER"}, "B": {"NUMBER"}})

    def test_terminal_after_nullable_prefix_blocks_further_first_symbols(self) -> None:
        analysis = analyze_grammar("S -> A NOUN VERB\nA -> epsilon")
        self.assertEqual(analysis["first"]["S"], ["NOUN"])
        self.assertEqual(analysis["follow"]["A"], ["NOUN"])


class TransformationTests(unittest.TestCase):
    def test_direct_left_recursion_has_real_before_and_after(self) -> None:
        analysis = analyze_grammar("S -> S NOUN | VERB")
        self.assertEqual(analysis["transformed"], {
            "S": [["VERB", "S_LR1"]], "S_LR1": [["NOUN", "S_LR1"], []],
        })
        step = analysis["steps"][0]
        self.assertEqual(step["operation"], "eliminate_direct_left_recursion")
        self.assertEqual(step["before"], analysis["original"])
        self.assertEqual(step["after"], analysis["transformed"])
        self.assertNotEqual(step["before"], step["after"])
        self.assertTrue(analysis["is_ll1"])

    def test_indirect_recursion_is_substituted_then_eliminated(self) -> None:
        analysis = analyze_grammar("S -> A\nA -> S NOUN | VERB")
        self.assertTrue(analysis["is_ll1"])
        self.assertEqual(left_recursive_nonterminals(analysis["transformed"]), [])
        operations = [step["operation"] for step in analysis["steps"]]
        self.assertIn("substitute_indirect_left_recursion", operations)
        self.assertIn("eliminate_direct_left_recursion", operations)
        self.assertEqual(analysis["steps"][0]["after"]["A"], [["A", "NOUN"], ["VERB"]])
        self.assertTrue(parse_analysis(analysis, token_stream("VERB", "NOUN", "NOUN"))["accepted"])

    def test_indirect_recursion_across_three_nonterminals(self) -> None:
        analysis = analyze_grammar("S -> A\nA -> B\nB -> S NOUN | VERB")
        self.assertTrue(analysis["is_ll1"])
        self.assertEqual(left_recursive_nonterminals(analysis["transformed"]), [])
        self.assertTrue(parse_analysis(analysis, token_stream("VERB", "NOUN"))["accepted"])

    def test_epsilon_base_is_preserved_by_direct_elimination(self) -> None:
        analysis = analyze_grammar("S -> S NOUN | epsilon")
        self.assertTrue(analysis["is_ll1"])
        self.assertEqual(analysis["transformed"]["S"], [["S_LR1"]])
        self.assertTrue(parse_analysis(analysis, [])["accepted"])
        self.assertTrue(parse_analysis(analysis, token_stream("NOUN", "NOUN"))["accepted"])

    def test_nested_factoring_reaches_a_fixed_point_including_epsilon_suffixes(self) -> None:
        text = (
            "S -> NOUN VERB NUMBER | NOUN VERB SLANG | NOUN PUNCTUATION | NOUN "
            "| VERB NUMBER | VERB"
        )
        analysis = analyze_grammar(text)
        factors = [step for step in analysis["steps"] if step["operation"] == "left_factor"]
        self.assertGreaterEqual(len(factors), 3)
        self.assertTrue(analysis["is_ll1"])
        for alternatives in analysis["transformed"].values():
            leading_symbols = [rhs[0] for rhs in alternatives if rhs]
            self.assertEqual(len(leading_symbols), len(set(leading_symbols)))
        for categories in (("NOUN",), ("NOUN", "VERB", "SLANG"), ("VERB",), ("VERB", "NUMBER")):
            self.assertTrue(parse_analysis(analysis, token_stream(*categories))["accepted"])

    def test_generated_names_never_overwrite_user_nonterminals(self) -> None:
        recursive = analyze_grammar("S -> S NOUN | VERB\nS_LR1 -> NUMBER")
        self.assertEqual(recursive["transformed"]["S_LR1"], [["NUMBER"]])
        self.assertIn("S_LR2", recursive["transformed"])
        factored = analyze_grammar("S -> NOUN VERB | NOUN\nS_LF1 -> NUMBER")
        self.assertEqual(factored["transformed"]["S_LF1"], [["NUMBER"]])
        self.assertIn("S_LF2", factored["transformed"])
        for lhs in factored["nonterminals"] + recursive["nonterminals"]:
            self.assertRegex(lhs, r"^[A-Za-z_][A-Za-z0-9_]*$")

    def test_steps_form_an_immutable_contiguous_history(self) -> None:
        analysis = analyze_grammar(DEFAULT_GRAMMAR)
        previous = analysis["original"]
        for step in analysis["steps"]:
            self.assertEqual(set(step), {"operation", "before", "after", "description"})
            self.assertEqual(step["before"], previous)
            self.assertTrue(step["description"])
            previous = step["after"]
        self.assertEqual(previous, analysis["transformed"])
        expected = deepcopy(analysis["transformed"])
        analysis["steps"][0]["after"]["Sentence"][0].append("UNKNOWN")
        self.assertEqual(analysis["transformed"], expected)
        self.assertNotIn("UNKNOWN", analysis["steps"][1]["before"]["Sentence"][0])

    def test_noop_stages_explain_that_no_rewrite_was_performed(self) -> None:
        analysis = analyze_grammar("S -> NOUN")
        self.assertEqual(len(analysis["steps"]), 2)
        for step in analysis["steps"]:
            self.assertEqual(step["before"], step["after"])
            self.assertIn("No ", step["description"])

    def test_rewrites_preserve_bounded_languages_and_predictive_acceptance(self) -> None:
        grammars = [
            "S -> S NOUN | VERB",
            "S -> S NOUN | epsilon",
            "S -> S NOUN | S VERB | NUMBER | SLANG",
            "S -> A\nA -> S NOUN | VERB",
            "S -> NOUN VERB NUMBER | NOUN VERB | NOUN | VERB",
            "S -> A NOUN | VERB\nA -> S NUMBER | SLANG",
        ]
        for text in grammars:
            with self.subTest(grammar=text):
                analysis = analyze_grammar(text)
                original_language = bounded_language(analysis["original"], analysis["start_symbol"], 4)
                transformed_language = bounded_language(
                    analysis["transformed"], analysis["start_symbol"], 4
                )
                self.assertEqual(original_language, transformed_language)
                if analysis["is_ll1"]:
                    alphabet = analysis["terminals"]
                    for length in range(5):
                        for word in product(alphabet, repeat=length):
                            result = parse_analysis(analysis, token_stream(*word))
                            self.assertEqual(result["accepted"], word in original_language, word)

    def test_degenerate_and_nullable_recursive_suffixes_fail_explicitly(self) -> None:
        cases = [
            ("S -> S", "recursive suffix is empty"),
            ("S -> S | NOUN", "recursive suffix is empty"),
            ("S -> S NOUN", "no nonrecursive alternative"),
            ("S -> A\nA -> S", "recursive suffix is empty"),
            ("S -> S A | VERB\nA -> epsilon", "recursive suffix is nullable"),
        ]
        for text, message in cases:
            with self.subTest(grammar=text), self.assertRaisesRegex(GrammarError, message):
                analyze_grammar(text)

    def test_nullable_prefix_left_recursion_is_not_mislabeled_as_ll1(self) -> None:
        analysis = analyze_grammar("S -> A S NOUN | VERB\nA -> epsilon")
        self.assertFalse(analysis["is_ll1"])
        self.assertTrue(analysis["conflicts"])
        self.assertTrue(any("Left recursion remains" in warning for warning in analysis["warnings"]))
        self.assertFalse(parse_analysis(analysis, token_stream("VERB"))["accepted"])

    def test_unproductive_hidden_recursion_is_diagnosed_even_without_table_conflicts(self) -> None:
        analysis = analyze_grammar("S -> A S\nA -> epsilon")
        self.assertEqual(analysis["conflicts"], [])
        self.assertFalse(analysis["is_ll1"])
        result = parse_analysis(analysis, [])
        self.assertFalse(result["accepted"])
        self.assertIn("left recursion", result["error"])

    def test_exponential_substitution_has_an_expansion_limit(self) -> None:
        lines = ["N0 -> NOUN | VERB"]
        lines += [f"N{i} -> N{i - 1} NOUN | N{i - 1} VERB" for i in range(1, 12)]
        with self.assertRaisesRegex(GrammarError, "expansion limit"):
            analyze_grammar("\n".join(lines))

    def test_generated_rhs_growth_is_bounded(self) -> None:
        lines = ["N0 -> " + " ".join(["NOUN"] * MAX_RHS_LENGTH)]
        lines += [
            f"N{i} -> N{i - 1} " + " ".join(["VERB"] * (MAX_RHS_LENGTH - 1))
            for i in range(1, 8)
        ]
        with self.assertRaisesRegex(GrammarError, "right-hand side is too long"):
            analyze_grammar("\n".join(lines))

    def test_step_snapshot_work_and_nonterminal_budgets_are_enforced(self) -> None:
        cases = [
            ("MAX_TRANSFORMATION_STEPS", 1, "S -> S NOUN | VERB", "step limit"),
            ("MAX_SNAPSHOT_UNITS", 1, "S -> NOUN", "snapshot-size limit"),
            ("MAX_EXPANSION_ATTEMPTS", 1, "S -> NOUN | VERB\nA -> S", "work limit"),
            ("MAX_TRANSFORMED_NONTERMINALS", 1, "S -> S NOUN | VERB", "nonterminals"),
            ("MAX_TRANSFORMED_SYMBOLS", 1, "S -> NOUN VERB", "production symbols"),
        ]
        for constant, value, text, message in cases:
            with self.subTest(constant=constant):
                with patch(f"compiler.parser.analysis.{constant}", value):
                    with self.assertRaisesRegex(GrammarError, message):
                        analyze_grammar(text)


class ConflictAndContractTests(unittest.TestCase):
    def test_first_first_conflicts_keep_all_productions_and_omit_ambiguous_cell(self) -> None:
        analysis = analyze_grammar("S -> A | B | C\nA -> NOUN\nB -> NOUN\nC -> NOUN")
        self.assertFalse(analysis["is_ll1"])
        self.assertEqual(analysis["conflicts"], [{
            "nonterminal": "S", "terminal": "NOUN", "productions": [["A"], ["B"], ["C"]],
        }])
        self.assertNotIn("NOUN", analysis["table"]["S"])
        self.assertTrue(any("conflicts" in warning for warning in analysis["warnings"]))

    def test_first_follow_conflict_includes_epsilon_production(self) -> None:
        analysis = analyze_grammar("S -> A NOUN\nA -> NOUN | epsilon")
        self.assertEqual(analysis["conflicts"], [{
            "nonterminal": "A", "terminal": "NOUN", "productions": [["NOUN"], []],
        }])
        self.assertNotIn("NOUN", analysis["table"]["A"])

    def test_nullable_alternatives_conflict_on_end_marker(self) -> None:
        analysis = analyze_grammar("S -> A | B\nA -> epsilon\nB -> epsilon")
        self.assertEqual(analysis["conflicts"], [{
            "nonterminal": "S", "terminal": "$", "productions": [["A"], ["B"]],
        }])
        self.assertFalse(parse_analysis(analysis, [])["accepted"])

    def test_all_parsing_is_disabled_for_a_conflicting_grammar(self) -> None:
        result = parse_tokens(
            "S -> A | B | VERB\nA -> NOUN\nB -> NOUN", token_stream("VERB")
        )
        self.assertFalse(result["accepted"])
        self.assertIn("conflict at (S, NOUN)", result["error"])
        self.assertEqual(result["consumed"], 0)
        self.assertEqual(len(result["trace"]), 1)
        self.assertTrue(result["trace"][-1]["action"].startswith("Reject:"))

    def test_output_contract_and_determinism(self) -> None:
        first = analyze_grammar(DEFAULT_GRAMMAR)
        second = analyze_grammar(DEFAULT_GRAMMAR)
        self.assertEqual(set(first), {
            "original", "transformed", "start_symbol", "terminals", "nonterminals", "steps",
            "first", "follow", "table", "conflicts", "is_ll1", "warnings",
        })
        self.assertEqual(json.dumps(first), json.dumps(second))
        self.assertEqual(first["nonterminals"], list(first["transformed"]))
        self.assertEqual(first["terminals"], sorted(first["terminals"]))
        self.assertNotIn("$", first["terminals"])
        self.assertNotIn("epsilon", first["terminals"])
        self.assertTrue(all(isinstance(warning, str) for warning in first["warnings"]))

    def test_unreachable_and_unproductive_rules_have_explanatory_warnings(self) -> None:
        analysis = analyze_grammar("S -> NOUN\nUnused -> VERB Unused")
        self.assertTrue(any("unreachable" in warning and "Unused" in warning for warning in analysis["warnings"]))
        self.assertTrue(any("finite token" in warning and "Unused" in warning for warning in analysis["warnings"]))

    def test_first_follow_and_conflicts_are_calculated_for_the_edited_grammar(self) -> None:
        noun = analyze_grammar("S -> NOUN")
        verb = analyze_grammar("S -> VERB")
        self.assertEqual(noun["first"]["S"], ["NOUN"])
        self.assertEqual(verb["first"]["S"], ["VERB"])
        self.assertEqual(noun["table"]["S"], {"NOUN": ["NOUN"]})
        self.assertEqual(verb["table"]["S"], {"VERB": ["VERB"]})
        self.assertNotEqual(noun["table"], verb["table"])


class DefaultAnalysisCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        service._default_analysis_json.cache_clear()
        self.addCleanup(service._default_analysis_json.cache_clear)

    def test_only_exact_public_default_is_prepared_once(self) -> None:
        with patch("compiler.parser.service._analyze_grammar", wraps=service._analyze_grammar) as prepare:
            first = analyze_grammar(DEFAULT_GRAMMAR)
            second = analyze_grammar(DEFAULT_GRAMMAR)
        self.assertEqual(first, second)
        prepare.assert_called_once_with(DEFAULT_GRAMMAR)
        self.assertEqual(service._default_analysis_json.cache_info().maxsize, 1)
        self.assertIsInstance(service._default_analysis_json(), str)

    def test_mutating_returned_default_analysis_cannot_poison_the_cache(self) -> None:
        first = analyze_grammar(DEFAULT_GRAMMAR)
        expected = deepcopy(first)
        first["table"]["Sentence"].clear()
        first["steps"][0]["after"].clear()
        first["original"].clear()
        first["first"].clear()
        first["warnings"].append("caller-specific")
        self.assertEqual(analyze_grammar(DEFAULT_GRAMMAR), expected)
        self.assertTrue(parse_tokens(DEFAULT_GRAMMAR, token_stream("VERB"))["accepted"])

    def test_saved_default_uses_the_same_preparation_without_sharing_mutations(self) -> None:
        saved_default = DEFAULT_GRAMMAR.strip()
        with patch("compiler.parser.service._analyze_grammar", wraps=service._analyze_grammar) as prepare:
            first = analyze_grammar(saved_default)
            expected = deepcopy(first)
            first["table"]["Sentence"].clear()
            self.assertEqual(analyze_grammar(saved_default), expected)
            self.assertEqual(analyze_grammar(DEFAULT_GRAMMAR), expected)
        prepare.assert_called_once_with(DEFAULT_GRAMMAR)

    def test_custom_grammars_and_private_comments_are_never_cached(self) -> None:
        custom = DEFAULT_GRAMMAR + "\n# private project annotation"
        with patch("compiler.parser.service._analyze_grammar", wraps=service._analyze_grammar) as prepare:
            first = analyze_grammar(custom)
            first["warnings"].append("private result mutation")
            second = analyze_grammar(custom)
            analyze_grammar("S -> NOUN")
            analyze_grammar("S -> VERB")
        self.assertEqual(prepare.call_count, 4)
        self.assertNotIn("private result mutation", second["warnings"])
        self.assertEqual(service._default_analysis_json.cache_info().currsize, 0)

    def test_warming_default_does_not_bypass_custom_limits_or_conflict_refusal(self) -> None:
        analyze_grammar(DEFAULT_GRAMMAR)
        with self.assertRaises(GrammarError):
            analyze_grammar("S -> NOUN\n#" + "x" * MAX_GRAMMAR_CHARACTERS)
        conflicting = "S -> A | B\nA -> NOUN\nB -> NOUN"
        self.assertFalse(parse_tokens(conflicting, token_stream("NOUN"))["accepted"])
        self.assertFalse(parse_tokens("S -> NOUN", token_stream("UNKNOWN"))["accepted"])


class PredictiveParserTests(unittest.TestCase):
    def test_multiword_annotations_do_not_hide_unconsumed_terminals(self) -> None:
        lexical = analyze_sentence("DROP\tME")
        tokens = [token._asdict() for token in lexical["tokens"]]
        result = parse_tokens("S -> VERB", tokens)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["consumed"], 1)
        self.assertIn("trailing token UNKNOWN", result["error"])
        exact = parse_tokens("S -> VERB UNKNOWN", tokens)
        self.assertTrue(exact["accepted"])
        self.assertEqual(exact["consumed"], 2)

    def test_exact_table_driven_trace_and_complete_consumption(self) -> None:
        result = parse_tokens("S -> NOUN VERB", token_stream("NOUN", "VERB"))
        self.assertEqual(set(result), {"accepted", "error", "trace", "consumed"})
        self.assertTrue(result["accepted"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["consumed"], 2)
        self.assertEqual(result["trace"], [
            {"stack": ["$", "S"], "remaining": ["NOUN", "VERB", "$"], "action": "Apply S -> NOUN VERB"},
            {"stack": ["$", "VERB", "NOUN"], "remaining": ["NOUN", "VERB", "$"], "action": "Match NOUN"},
            {"stack": ["$", "VERB"], "remaining": ["VERB", "$"], "action": "Match VERB"},
            {"stack": ["$"], "remaining": ["$"], "action": "Accept: input fully consumed."},
        ])

    def test_terminal_mismatch_reports_partial_consumption(self) -> None:
        result = parse_tokens("S -> NOUN VERB", token_stream("NOUN", "NUMBER"))
        self.assertFalse(result["accepted"])
        self.assertEqual(result["consumed"], 1)
        self.assertIn("Expected VERB, found NUMBER", result["error"])
        self.assertEqual(result["trace"][-1]["remaining"], ["NUMBER", "$"])

    def test_extra_input_is_never_accepted(self) -> None:
        result = parse_tokens("S -> NOUN", token_stream("NOUN", "VERB"))
        self.assertFalse(result["accepted"])
        self.assertIn("trailing token VERB", result["error"])
        self.assertEqual(result["consumed"], 1)

    def test_missing_table_cell_reports_expected_categories(self) -> None:
        result = parse_tokens("S -> NOUN | VERB", token_stream("NUMBER"))
        self.assertFalse(result["accepted"])
        self.assertIn("No production for S with lookahead NUMBER", result["error"])
        self.assertIn("expected: NOUN, VERB", result["error"])
        self.assertEqual(result["consumed"], 0)

    def test_empty_input_accepts_only_a_nullable_start(self) -> None:
        accepted = parse_tokens("S -> epsilon", [])
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["consumed"], 0)
        self.assertEqual(accepted["trace"][0]["action"], "Apply S -> epsilon")
        self.assertFalse(parse_tokens("S -> NOUN", [])["accepted"])
        self.assertFalse(parse_tokens(DEFAULT_GRAMMAR, [])["accepted"])

    def test_unknown_is_not_a_wildcard_and_requires_an_explicit_rule(self) -> None:
        self.assertFalse(parse_tokens("S -> NOUN", token_stream("UNKNOWN"))["accepted"])
        explicit = analyze_grammar("S -> UNKNOWN")
        self.assertTrue(parse_analysis(explicit, token_stream("UNKNOWN"))["accepted"])
        self.assertFalse(parse_analysis(explicit, token_stream("NOUN"))["accepted"])
        self.assertTrue(any("never as a wildcard" in warning for warning in explicit["warnings"]))

    def test_cached_analysis_and_tokens_are_not_mutated(self) -> None:
        analysis = analyze_grammar(DEFAULT_GRAMMAR)
        tokens = token_stream("VERB", "NOUN", "PUNCTUATION")
        original_analysis = deepcopy(analysis)
        original_tokens = deepcopy(tokens)
        with patch("compiler.parser.service.analyze_grammar", side_effect=AssertionError("recalculated")):
            first = parse_analysis(analysis, tokens)
            second = parse_analysis(analysis, tokens)
        self.assertEqual(first, second)
        self.assertTrue(first["accepted"])
        self.assertEqual(analysis, original_analysis)
        self.assertEqual(tokens, original_tokens)
        self.assertIsNot(first["trace"], second["trace"])

    def test_invalid_token_shapes_and_categories_are_rejected(self) -> None:
        invalid_inputs: list[Any] = [
            None, (), ["NOUN"], [{}], [{"text": "noun"}],
            [{"category": "NOUN"}], [{"text": 1, "category": "NOUN"}],
            [{"text": "noun", "category": None}],
            [{"text": "noun", "category": "NOT_A_LEXER_CATEGORY"}],
            [{"text": "$", "category": "$"}],
            [{"text": "epsilon", "category": "epsilon"}],
        ]
        analysis = analyze_grammar("S -> NOUN")
        for tokens in invalid_inputs:
            with self.subTest(tokens=tokens):
                result = parse_analysis(analysis, tokens)
                self.assertFalse(result["accepted"])
                self.assertEqual(result["consumed"], 0)
                self.assertTrue(result["error"])
                self.assertTrue(result["trace"][-1]["action"].startswith("Reject:"))

    def test_input_token_limit_and_boundary_acceptance(self) -> None:
        analysis = analyze_grammar("S -> NOUN S | epsilon")
        result = parse_analysis(analysis, token_stream(*(["NOUN"] * MAX_INPUT_TOKENS)))
        self.assertTrue(result["accepted"])
        self.assertEqual(result["consumed"], MAX_INPUT_TOKENS)
        oversized = parse_analysis(analysis, token_stream(*(["NOUN"] * (MAX_INPUT_TOKENS + 1))))
        self.assertFalse(oversized["accepted"])
        self.assertIn("token limit", oversized["error"])
        self.assertEqual(len(oversized["trace"]), 1)

    def test_token_text_limit(self) -> None:
        result = parse_tokens(
            "S -> NOUN", [{"text": "x" * (MAX_TOKEN_TEXT_LENGTH + 1), "category": "NOUN"}]
        )
        self.assertFalse(result["accepted"])
        self.assertIn("text limit", result["error"])

    def test_trace_and_stack_limits_reject_instead_of_looping(self) -> None:
        with patch("compiler.parser.predictive.MAX_PARSE_STEPS", 3):
            result = parse_tokens("S -> NOUN VERB NUMBER", token_stream("NOUN", "VERB", "NUMBER"))
        self.assertFalse(result["accepted"])
        self.assertIn("trace limit", result["error"])
        self.assertEqual(len(result["trace"]), 3)
        with patch("compiler.parser.predictive.MAX_STACK_SYMBOLS", 3):
            result = parse_tokens("S -> NOUN VERB NUMBER", token_stream("NOUN", "VERB", "NUMBER"))
        self.assertFalse(result["accepted"])
        self.assertIn("stack limit", result["error"])

    def test_acceptance_can_use_the_last_allowed_trace_entry(self) -> None:
        with patch("compiler.parser.predictive.MAX_PARSE_STEPS", 3):
            result = parse_tokens("S -> NOUN", token_stream("NOUN"))
        self.assertTrue(result["accepted"])
        self.assertEqual(len(result["trace"]), 3)

    def test_defensive_no_progress_detection_for_a_corrupted_cached_table(self) -> None:
        analysis = analyze_grammar("S -> NOUN")
        analysis["table"]["S"]["NOUN"] = ["S"]
        result = parse_analysis(analysis, token_stream("NOUN"))
        self.assertFalse(result["accepted"])
        self.assertIn("no progress", result["error"])
        self.assertLessEqual(len(result["trace"]), 3)

    def test_default_grammar_is_ll1_with_real_lexer_flow(self) -> None:
        analysis = analyze_grammar(DEFAULT_GRAMMAR)
        self.assertTrue(analysis["is_ll1"])
        self.assertEqual(analysis["conflicts"], [])
        self.assertTrue(any("teaching starter" in warning for warning in analysis["warnings"]))
        self.assertTrue(any("limited coverage" in warning for warning in analysis["warnings"]))
        self.assertTrue(any("not covered" in warning for warning in analysis["warnings"]))
        for text in ("Je acheter argent.", "dey go quartier", "go", "le moto block.", "go argent money"):
            with self.subTest(text=text):
                tokens = [token._asdict() for token in analyze_sentence(text)["tokens"]]
                result = parse_analysis(analysis, tokens)
                self.assertTrue(result["accepted"], result["error"])
                self.assertEqual(result["consumed"], len(tokens))
        for text in ("Je buy phone.", "argent", "123", "go..", "yo"):
            with self.subTest(text=text):
                tokens = [token._asdict() for token in analyze_sentence(text)["tokens"]]
                self.assertFalse(parse_analysis(analysis, tokens)["accepted"])


if __name__ == "__main__":
    unittest.main()
