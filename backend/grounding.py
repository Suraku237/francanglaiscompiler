"""Deterministic collection/reference retrieval, never sentence synthesis or training."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from heapq import heappush, heapreplace
from typing import Literal, cast

from compiler.lexer.tokenizer import normalize_text, tokenize

from .schemas import (
    Coverage, DatasetLanguage, DictionaryEntry, Evidence, EvidenceSource,
    Origin, TranslationContent, TranslationLanguage,
)

MAX_CANDIDATES = 64
MAX_EVIDENCE = 8
MAX_EVIDENCE_CHARACTERS = 12000
MAX_FIELD_CHARACTERS = 4000
STOPWORDS = frozenset(
    "a an the is are was were be of to in on for and or with it this that me my "
    "please explain translate translation meaning example another what does mean "
    "le la les un une des de du et ou est en pour dans ce cette avec "
    "traduire traduction expliquer exemple signifie".split()
)


def terms(text: str) -> list[str]:
    return [token for token in tokenize(normalize_text(text)) if any(c.isalnum() for c in token)]


def aligned_value(entry: Evidence, language: TranslationLanguage) -> str:
    if language == "fr":
        return entry.french_gloss
    if language == "en":
        return entry.english_gloss
    return entry.text if entry.language == language else ""


def source_values(entry: Evidence, language: TranslationLanguage) -> list[str]:
    value = aligned_value(entry, language)
    if entry.source == "dictionary" and entry.language == language:
        return list(dict.fromkeys([value, *entry.aliases]))
    return [value]


def source_evidence(
    entries: list[dict[str, str]], references: list[DictionaryEntry],
) -> Iterator[Evidence]:
    for entry in entries:
        if (
            entry.get("review_status") == "approved"
            and entry.get("language") in ("francanglais", "pidgin")
            and entry.get("id") and entry.get("text", "").strip()
        ):
            yield Evidence(
                id=entry["id"], text=entry["text"], language=cast(DatasetLanguage, entry["language"]),
                french_gloss=entry.get("french_gloss", ""), english_gloss=entry.get("english_gloss", ""),
                match_type="token",
            )
    for entry in references:
        yield Evidence(
            id=entry.id, text=entry.text, language=entry.language,
            french_gloss="", english_gloss=entry.english_gloss, match_type="token",
            source="dictionary", source_document=entry.source_document,
            source_line=entry.source_line, aliases=entry.aliases,
        )


def evidence_json(evidence: list[Evidence]) -> str:
    return json.dumps([item.model_dump() for item in evidence], ensure_ascii=False, separators=(",", ":"))


def ai_origin(evidence: list[Evidence]) -> Origin:
    if any(item.source == "dictionary" for item in evidence):
        return "ai_with_sources"
    return "ai_with_dataset" if evidence else "ai"


@dataclass
class Grounding:
    evidence: list[Evidence] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    exact_translation: str | None = None
    exact_sources: set[EvidenceSource] = field(default_factory=set)
    ambiguous: bool = False


def _contains(haystack: list[str], needle: list[str]) -> bool:
    return bool(needle) and any(
        haystack[index:index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def retrieve(
    entries: list[dict[str, str]],
    text: str,
    source_language: TranslationLanguage,
    target_language: TranslationLanguage,
    *,
    references: list[DictionaryEntry] | None = None,
    recent_user_messages: list[str] | None = None,
    chat: bool = False,
) -> Grounding:
    queries = [text, *reversed((recent_user_messages or [])[-2:])]
    query_terms = [terms(query) for query in queries]
    query_normalized = [normalize_text(query) for query in queries]
    requested_terms = list(dict.fromkeys(query_terms[0]))
    local_languages = {source_language, target_language} & {"francanglais", "pidgin"}
    candidates: list[tuple[tuple[int, int, int], int, Evidence, set[str]]] = []
    exact_targets: dict[str, str] = {}
    missing_exact_target = False
    omitted = False
    matched_count = 0
    for index, entry in enumerate(source_evidence(entries, references or [])):
        if local_languages and entry.language not in local_languages:
            continue
        sources = source_values(entry, source_language)
        target = aligned_value(entry, target_language)
        exact = any(source.strip() and normalize_text(source) == query_normalized[0] for source in sources)
        if exact:
            if target.strip() and len(target) <= MAX_FIELD_CHARACTERS:
                if len(exact_targets) < 2:
                    exact_targets.setdefault(normalize_text(target), target)
            elif entry.source == "dataset":
                # An English-only reference must not veto a reviewed French alignment.
                missing_exact_target = True
        fields = sources
        if chat:
            fields = [entry.text, *entry.aliases, entry.french_gloss, entry.english_gloss]
        if any(len(value) > MAX_FIELD_CHARACTERS for value in (entry.text, entry.french_gloss, entry.english_gloss)):
            if exact:
                omitted = True
            continue
        score = (0, 0, 0)
        matched: set[str] = set()
        match_type: Literal["exact", "phrase", "token"] = "token"
        for query_index, (query, normalized) in enumerate(zip(query_terms, query_normalized)):
            for value in fields:
                value_terms = terms(value)
                if not value_terms:
                    continue
                overlap = set(query) & set(value_terms)
                if normalize_text(value) == normalized:
                    rank, kind = 3, "exact"
                elif len(value_terms) > 1 and _contains(query, value_terms):
                    rank, kind = 2, "phrase"
                elif overlap - STOPWORDS:
                    rank, kind = 1, "token"
                else:
                    continue
                next_score = (rank, -query_index, len(overlap - STOPWORDS))
                if next_score > score:
                    score = next_score
                    match_type = kind
                # Coverage describes overlap with supplied examples, not known lexical categories.
                matched.update(set(requested_terms) & set(value_terms))
        if not score[0]:
            continue
        evidence = entry.model_copy(update={"match_type": match_type})
        candidate = (score, -index, evidence, matched)
        matched_count += 1
        if len(candidates) < MAX_CANDIDATES:
            heappush(candidates, candidate)
        elif candidate[:2] > candidates[0][:2]:
            heapreplace(candidates, candidate)
    result = Grounding(ambiguous=len(exact_targets) > 1 or (bool(exact_targets) and missing_exact_target))
    covered: set[str] = set()
    seen_ids: set[str] = set()
    for _, _, item, matched in sorted(candidates, key=lambda row: row[:2], reverse=True):
        if item.id in seen_ids:
            continue
        if (
            len(result.evidence) >= MAX_EVIDENCE
            or len(evidence_json([*result.evidence, item])) > MAX_EVIDENCE_CHARACTERS
        ):
            omitted = True
            continue
        result.evidence.append(item)
        seen_ids.add(item.id)
        covered.update(matched)
    if matched_count > len(result.evidence) or omitted:
        result.coverage.warnings.append("Relevant examples were limited by the evidence budget; coverage may be incomplete.")
    result.coverage.matched_terms = [word for word in requested_terms if word in covered]
    result.coverage.unmatched_terms = [word for word in requested_terms if word not in covered]
    if result.ambiguous:
        result.coverage.warnings.append("Ambiguous local alignment: full-entry matches have conflicting or missing target glosses.")
    elif len(exact_targets) == 1 and any(item.match_type == "exact" for item in result.evidence):
        translation = next(iter(exact_targets.values()))
        # Only an actual supplied full-entry alignment may produce a local answer.
        result.exact_sources = {
            item.source
            for item in result.evidence
            if any(normalize_text(value) == query_normalized[0] for value in source_values(item, source_language))
            and aligned_value(item, target_language) == translation
        }
        if result.exact_sources:
            result.exact_translation = translation
    if result.exact_translation is None:
        result.coverage.warnings.append(
            "No unambiguous full-entry translation from the enabled local sources. "
            "Token/phrase evidence is not a complete sentence translation."
        )
    return result


def without_local_sources(text: str) -> Grounding:
    return Grounding(coverage=Coverage(
        unmatched_terms=list(dict.fromkeys(terms(text))),
        warnings=["Collection and dictionary use are disabled; any translation is an unverified AI suggestion."],
    ))


def local_translation(result: Grounding, explanation_language: str) -> TranslationContent:
    if result.exact_translation is None:
        raise ValueError("No complete local translation is available.")
    french = explanation_language == "fr"
    if "dictionary" in result.exact_sources:
        return TranslationContent(
            translation=result.exact_translation,
            explanation=(
                "Sens repris des sources locales citées, dont le dictionnaire de référence, sans IA."
                if french else "Meaning copied from the cited local sources, including the reference dictionary, without AI."
            ),
            vocabulary=[],
            note=(
                "Les sens et variantes du dictionnaire sont conservés. Ce n'est pas une observation de terrain "
                "ni une traduction mot à mot de phrase; aucune adaptation du ton."
                if french else "Dictionary meanings and alternatives are preserved. This is not collected fieldwork "
                "or word-for-word sentence translation; no tone adaptation."
            ),
        )
    return TranslationContent(
        translation=result.exact_translation,
        explanation=(
            "Traduction reprise d'un alignement complet approuvé dans le jeu de données, sans IA."
            if french else "Translation copied from an approved full-entry dataset alignment, without AI."
        ),
        vocabulary=[],
        note=(
            "Le registre du texte collecté est conservé; aucune adaptation automatique du ton."
            if french else "The collected wording and register are preserved; no automatic tone adaptation."
        ),
    )
