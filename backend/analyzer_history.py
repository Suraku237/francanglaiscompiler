from collections import Counter, defaultdict
from datetime import datetime, timezone

from data_collector import dataset

from . import analyzer, coursework_store
from .analyzer_models import AnalyzerTestRequest, OwnedTestSummary, RecordedTest, TestReport, TestSummary
from .collection import CollectionError
from .ownership import record_ownership
from .token_statistics import normalize_token


def record_test(request: AnalyzerTestRequest) -> RecordedTest:
    previous = coursework_store.load_analyzer_request(request.request_id)
    if previous is not None:
        if previous.text != request.text or previous.grammar_source != request.grammar:
            raise CollectionError(409, "This analyzer request identifier was already used for different input.")
        return previous

    grammar = analyzer.analyze_grammar(request.grammar)
    entries = dataset.load_all()
    learned = analyzer.build_lexicon(entries)
    result = analyzer.analyze_manual(request.text, grammar, learned)
    matches = [entry for entry in entries if entry["text"] == request.text]
    record = RecordedTest.model_validate({
        "id": coursework_store.analyzer_test_identifier(request.request_id),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "grammar_source": request.grammar,
        **result,
        "metadata": {
            "topics": sorted({entry["category"] for entry in matches if entry["category"].strip()}),
            "languages": sorted({entry.get("language", "unspecified") for entry in matches}),
            "matching_entries": len(matches),
        },
    })
    coursework_store.save_analyzer_request(request.request_id, record)
    return record


def get_test(test_id: str) -> RecordedTest:
    record = coursework_store.load_analyzer_test(test_id)
    if record is None:
        raise CollectionError(404, "Analyzer test not found.")
    return record


def _frequencies(counts: Counter[str]) -> list[dict]:
    return [{"token": token, "count": count} for token, count in sorted(
        counts.items(), key=lambda item: (-item[1], item[0]),
    )]


def test_report(offset: int, limit: int) -> TestReport:
    raw: Counter[str] = Counter()
    folded: Counter[str] = Counter()
    normalized: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    unknown_tests: Counter[str] = Counter()
    unknown_forms: dict[str, set[str]] = defaultdict(set)
    variants: dict[str, Counter[str]] = defaultdict(Counter)
    topics: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    summaries: list[OwnedTestSummary | TestSummary] = []
    total = accepted = 0
    # Only one complete snapshot is held at a time; the response contains a page of summaries.
    for record in coursework_store.iter_analyzer_tests():
        if offset <= total < offset + limit:
            summary = TestSummary(
                id=record.id, created_at=record.created_at, text=record.text,
                accepted=record.parse.accepted, token_count=len(record.lexical.tokens), error=record.parse.error,
            )
            ownership = record_ownership("analyzer_test", record.id)
            summaries.append(
                OwnedTestSummary(**summary.model_dump(), ownership=ownership) if ownership is not None else summary
            )
        total += 1
        accepted += record.parse.accepted
        topics.update(record.metadata.topics or ["Not recorded"])
        languages.update(record.metadata.languages or ["Not recorded"])
        seen_unknown = set()
        for token in record.lexical.tokens:
            text = token.text
            key = text.casefold()
            normalized_key = normalize_token(text)
            raw[text] += 1
            folded[key] += 1
            normalized[normalized_key] += 1
            categories[token.category] += 1
            variants[normalized_key][text] += 1
            if token.category == "UNKNOWN":
                unknown[key] += 1
                unknown_forms[key].add(text)
                seen_unknown.add(key)
        unknown_tests.update(seen_unknown)
    return TestReport.model_validate({
        "summary": {
            "total": total, "accepted": accepted, "rejected": total - accepted,
            "acceptance_rate": accepted * 100.0 / total if total else None,
        },
        "statistics": {
            "frequencies": _frequencies(folded),
            "category_counts": dict(sorted(categories.items())),
            "variations": [
                {
                    "normalized": key,
                    "forms": [{"text": form["token"], "count": form["count"]} for form in _frequencies(forms)],
                }
                for key, forms in sorted(variants.items()) if len(forms) > 1
            ],
            "unknown_tokens": _frequencies(unknown),
            "total_tokens": sum(raw.values()),
            "raw_frequencies": _frequencies(raw),
            "normalized_frequencies": _frequencies(normalized),
        },
        "unknown_review": [
            {**item, "tests": unknown_tests[item["token"]], "forms": sorted(unknown_forms[item["token"]])}
            for item in _frequencies(unknown)
        ],
        "topic_counts": dict(sorted(topics.items())),
        "language_counts": dict(sorted(languages.items())),
        "tests": summaries,
        "offset": offset,
        "limit": limit,
    })
