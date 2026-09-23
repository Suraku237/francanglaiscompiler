from compiler.lexer import tokenizer
from compiler.lexer.learned import build_lexicon
from compiler.parser.service import analyze_grammar, parse_analysis

from . import coursework, coursework_store
from .schemas import AnalysisResult, TokenResult


def analyzer_state() -> dict:
    entries = coursework.read_corpus()
    stats = coursework.corpus_stats(entries)
    return {
        "grammar": coursework_store.load_project().grammar,
        "lexical_spec": coursework.lexical_spec(),
        "stats": {"total": stats["total"], "sentences": stats["sentences"]},
    }


def analyze(text: str, grammar_text: str) -> dict:
    entries = coursework.read_corpus()
    grammar = analyze_grammar(grammar_text)
    learned = build_lexicon(entries)
    result = tokenizer.analyze_sentence(text, learned)
    lexical = AnalysisResult(
        tokens=[TokenResult(text=token.text, category=token.category) for token in result["tokens"]],
        code_mixed_spans=result["code_mixed_spans"],
        verb_phrases=result["verb_phrases"],
    ).model_dump()
    return {
        "text": text,
        "lexical": {
            **lexical,
            "slang_expressions": tokenizer.find_slang_phrases(text),
            "statistics": coursework.token_statistics(lexical["tokens"]),
        },
        "grammar": grammar,
        "parse": parse_analysis(grammar, lexical["tokens"]),
        "corpus": coursework.parse_corpus(
            grammar, coursework.lexical_report(entries, learned_lexicon=learned),
        ),
    }
