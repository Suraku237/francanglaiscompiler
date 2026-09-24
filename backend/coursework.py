from collections import Counter
from collections.abc import Mapping

from compiler.lexer import lexicon, tokenizer
from compiler.lexer.learned import build_lexicon
from compiler.lexer.reference import CSV_PATH, load_classified_lexicon, reference_verb_phrases
from compiler.parser.service import analyze_grammar, parse_analysis
from data_collector import dataset

from .coursework_models import ProjectProfile
from .coursework_store import list_screenshots, load_project
from .token_statistics import token_statistics

BRIEF = {
    "title": "Lexical and syntactic analysis of informal urban communication in Yaounde",
    "course": "CS4110 - Compiler Construction, Summer 2026, SET A",
    "due": "2026-09-29",
    "group_size": 3,
    "statement_target": [10, 15],
    "report_pages": [25, 30],
    "presentation_minutes": 10,
    "per_student_minutes": 3,
}
MAX_CORPUS_ENTRIES = 500
MAX_CORPUS_CHARACTERS = 100000


def lexical_spec() -> dict:
    return {
        "token_pattern": tokenizer.TOKEN_SPLIT_RE.pattern,
        "regex_rules": [
            {"category": category, "pattern": pattern}
            for category, pattern in lexicon.TOKEN_REGEX_RULES
        ] + [
            {"category": "ENGLISH_VERB_LIKE", "pattern": r"(?:ing|ed)$"},
            {"category": "FRENCH_VERB_LIKE", "pattern": r"(?=.{4,}$).*(?:er|ir|re)$"},
        ],
        "verb_phrases": [*lexicon.VERB_PHRASES, *reference_verb_phrases()],
        "slang_phrases": lexicon.SLANG_PHRASES,
        "classification_order": [
            "NUMBER", "PUNCTUATION", "SLANG", "PIDGIN_MARKER", "NOUN", "VERB",
            "FRENCH_FUNCTION_WORD", "ENGLISH_FUNCTION_WORD",
            "CSV_REFERENCE",
            "ENGLISH_VERB_LIKE", "FRENCH_VERB_LIKE", "UNKNOWN",
        ],
        "limitations": [
            "After structural regex rules, approved language-labeled Word annotations override static lists; conflicting labels are ignored.",
            f"Existing explicit word classifications take priority over the {len(load_classified_lexicon())} rows in {CSV_PATH.name}.",
            "CSV aliases fill vocabulary gaps before morphological guesses; raw spelling and supplied meanings remain unchanged.",
            "AMBIGUOUS means the supplied reference gives a new word multiple categories; context is not guessed.",
            "Multiword references do not assign their meaning or category to each component word. Supplied verb phrases are annotated separately.",
            "Morphological labels ending in _LIKE are guesses, not confirmed parts of speech.",
            "Code-mixed spans are inferred transitions, not proof of a speaker's language.",
            "Variation groups compare spelling/case/accents only, not semantic equivalence.",
            "The CFG consumes lexical categories. Acceptance means grammar fit, not correct or authentic speech.",
        ],
    }


def read_corpus() -> list[dict[str, str]]:
    entries = dataset.load_all()
    if len(entries) > MAX_CORPUS_ENTRIES or sum(len(entry["text"]) for entry in entries) > MAX_CORPUS_CHARACTERS:
        raise ValueError("The coursework analyzer supports at most 500 entries and 100000 text characters.")
    if any(len(entry["text"]) > 4000 for entry in entries):
        raise ValueError("A collected expression exceeds 4000 characters. Shorten or split it before analysis.")
    return entries


def tokens_for(text: str) -> list[dict[str, str]]:
    learned = build_lexicon(dataset.load_all())
    return [{"text": token.text, "category": token.category} for token in tokenizer.analyze_sentence(text, learned)["tokens"]]


def corpus_stats(entries: list[dict[str, str]]) -> dict:
    sentences = [entry for entry in entries if entry["entry_type"].casefold() == "sentence"]
    topic_counts = dict(Counter(entry["category"] for entry in sentences))
    return {
        "total": len(entries),
        "sentences": len(sentences),
        "topic_counts": topic_counts,
        "missing_topics": [topic for topic in dataset.CATEGORIES if topic != "Other" and not topic_counts.get(topic)],
    }


def lexical_report(
    entries: list[dict[str, str]], *, learned_lexicon: Mapping[str, str] | None = None,
) -> dict:
    statements = []
    learned = build_lexicon(entries) if learned_lexicon is None else learned_lexicon
    for entry in entries:
        result = tokenizer.analyze_sentence(entry["text"], learned)
        statements.append({
            "id": entry["id"], "text": entry["text"], "category": entry["category"],
            "tokens": [{"text": token.text, "category": token.category} for token in result["tokens"]],
            "code_mixed_spans": result["code_mixed_spans"],
            "verb_phrases": result["verb_phrases"],
            "slang_expressions": tokenizer.find_slang_phrases(entry["text"]),
        })
    return {
        "statements": statements,
        **token_statistics(token for statement in statements for token in statement["tokens"]),
    }


def requirements(profile: ProjectProfile, entries: list[dict[str, str]], grammar: dict | None = None) -> list[dict]:
    stats = corpus_stats(entries)
    grammar = analyze_grammar(profile.grammar) if grammar is None else grammar
    has_data = stats["sentences"] > 0
    members_ready = all(profile.group_members)
    count_ready = 10 <= stats["sentences"] <= 15
    evidence = members_ready and count_ready and profile.manual_transcription_confirmed and bool(profile.collection_method)
    grammar_ready = grammar["is_ll1"] and bool(profile.grammar_rationale)

    def item(key: str, title: str, marks: int, ready: bool, detail: str, section: str) -> dict:
        return {"id": key, "title": title, "marks": marks, "status": "ready" if ready else "needs_input",
                "detail": detail, "section": section}

    result = [
        item("data", "Group of three and 10-15 real manual transcriptions", 10, evidence,
             f"{stats['sentences']} sentence entries; {sum(bool(name) for name in profile.group_members)} members. "
             "Record the collection method and confirm authenticity yourself; software cannot verify fieldwork.", "Evidence"),
        item("topics", "Review coverage of the suggested everyday topics", 0, not stats["missing_topics"],
             "The brief suggests these topic areas; it does not require one statement per topic. "
             "Not yet represented: " + (", ".join(stats["missing_topics"]) or "none"), "Evidence"),
        item("lexical", "Nouns, verbs, slang and code-mixed expressions", 10, has_data,
             "Token tables and multiword expressions use your saved entries only. Inspect UNKNOWN labels.", "Lexical analysis"),
        item("frequency", "Custom regex lexer, frequency and observed variation", 10, has_data,
             "Python regex specification, corpus frequencies, category counts and spelling-variation candidates are available.", "Lexical analysis"),
        item("recursion", "Construct CFG and remove left recursion", 5, bool(profile.grammar_rationale),
             "Save a rationale tying your grammar to observed statements; inspect calculated transformation steps.", "Grammar"),
        item("factoring", "Left-factor the grammar", 5, bool(profile.grammar_rationale),
             "Common prefixes are transformed with before/after rules; unchanged stages are explained.", "Grammar"),
        item("sets", "Compute FIRST and FOLLOW sets", 5, True,
             "Sets are calculated to a fixed point, including epsilon and the end marker.", "Grammar"),
        item("table", "Build an LL(1) parsing table", 5, grammar["is_ll1"],
             "The LL(1) path is implemented; LR/SLR is an alternative, not an additional requirement. "
             f"Current table conflicts: {len(grammar['conflicts'])}.", "Grammar"),
        item("parser", "Implement a table-driven parser", 5, grammar_ready,
             "Parser uses the transformed grammar; conflicting tables are not arbitrarily resolved.", "Parser"),
        item("token-input", "Parse tokenized input", 2, True,
             "The original Python lexer supplies a category for every token, including unknown symbols.", "Parser"),
        item("tests", "Show accept/reject for your own collected sentences", 3, has_data and grammar["is_ll1"],
             "Run corpus analysis to see every saved entry and its trace. A rejection is a grammar limitation, not a judgment of speech.", "Parser"),
        item("screenshots", "Screenshots of the working analyzer", 0, bool(list_screenshots()),
             f"{len(list_screenshots())} local screenshots attached. Upload genuine captures of your runs.", "Deliverables"),
        item("report", "25-30 page report, at most 30 pages", 5, False,
             "Export includes a 25-section printable report draft. Add original discussion/evidence, inspect print preview and verify final pagination.", "Deliverables"),
        item("source", "Lexer, parser and own-data regression cases", 0, has_data,
             "The ZIP contains actual Python sources and generated cases from your saved corpus, not invented field observations.", "Deliverables"),
        item("presentation", "Ten-minute PowerPoint and demonstration", 5, False,
             "Export includes editable slides with timing notes: three minutes per member plus a one-minute shared wrap-up. Rehearse and personalize.", "Deliverables"),
    ]
    for row in result:
        if row["id"] in ("topics", "report", "presentation"):
            row["status"] = "review"
    return result


def coursework_state() -> dict:
    profile = load_project()
    entries = read_corpus()
    return {
        "project": profile.model_dump(), "brief": BRIEF,
        "requirements": requirements(profile, entries),
        "lexical_spec": lexical_spec(), "stats": corpus_stats(entries),
        "screenshots": list_screenshots(),
    }


def parse_corpus(grammar: dict, lexical: dict) -> dict:
    tests = []
    for statement in lexical["statements"]:
        parsed = parse_analysis(grammar, statement["tokens"])
        tests.append({"id": statement["id"], "text": statement["text"], **parsed})
    accepted = sum(test["accepted"] for test in tests)
    return {
        "lexical": lexical, "tests": tests,
        "summary": {"accepted": accepted, "rejected": len(tests) - accepted, "total": len(tests)},
    }


def analyze_coursework(grammar_text: str, *, entries: list[dict[str, str]] | None = None) -> dict:
    entries = read_corpus() if entries is None else entries
    grammar = analyze_grammar(grammar_text)
    corpus = parse_corpus(grammar, lexical_report(entries))
    profile = load_project().model_copy(update={"grammar": grammar_text})
    return {
        "grammar": grammar, **corpus,
        "requirements": requirements(profile, entries, grammar),
    }
