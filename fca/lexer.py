"""Scanner: turns raw Yaoundé speech into a stream of categorised tokens.

Three things happen here that a textbook scanner does not have to do:

1. **Longest-match phrase lookup.** ``no wahala`` and ``c'est comment`` are single
   lexical items, so the scanner tries the longest dictionary key first.
2. **Language tagging.** Every token carries the language it was recognised from, which
   is what makes mixture detection possible downstream.
3. **Category disambiguation.** ``chop`` is both a noun and a verb, ``go`` is both a
   verb and a future marker. The scanner resolves these from the surrounding
   categories - the classic "lexer hack".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .lexicon import Entry, Lexicon, load_lexicon, normalize
from .tokens import Cat, Lang, Token

_WORD = re.compile(r"[A-Za-zÀ-ÿ]+(?:['\u2019-][A-Za-zÀ-ÿ]+)*|\d+(?:[.,]\d+)?|[^\sA-Za-zÀ-ÿ\d]")
_PUNCT_CAT = {".", "!", "?", ",", ";", ":", "...", "\u2026"}
#: French elision: the clitic in 'j'ai', 'l'argent', 'qu'on' is a word of its own.
_ELISION = re.compile(r"^([A-Za-zÀ-ÿ]{1,3}['\u2019])(.+)$")

#: Language preference when a word exists in more than one dictionary.
_LANG_PRIORITY = (Lang.CAMFRANGLAIS, Lang.FRENCH, Lang.ENGLISH)


#: The second half of French 'ne ... pas' carries no negation of its own.
_NEG_TAIL = {"pas", "plus", "jamais"}


@dataclass
class RawToken:
    surface: str
    norm: str
    line: int
    col: int
    hint: Lang | None = None


def scan_raw(text: str) -> list[RawToken]:
    """Split the input into words, numbers and punctuation with positions."""
    raw: list[RawToken] = []
    for line_no, line in enumerate(text.splitlines() or [""], start=1):
        for match in _WORD.finditer(line):
            surface = match.group(0)
            raw.append(
                RawToken(
                    surface=surface,
                    norm=normalize(surface) or surface,
                    line=line_no,
                    col=match.start() + 1,
                )
            )
    return raw


class Lexer:
    """Maximal-munch scanner over the combined lexicon."""

    def __init__(self, lexicon: Lexicon | None = None, prefer: Lang | None = None):
        self.lex = lexicon or load_lexicon()
        self.prefer = prefer
        self.candidate_overrides = _candidate_map(self.lex)

    # -- public API -----------------------------------------------------

    def tokenize(self, text: str) -> list[Token]:
        raw = self._split_elisions(scan_raw(text))
        tokens = self._match_phrases(raw)
        self._resolve_categories(tokens)
        for i, tok in enumerate(tokens):
            tok.index = i
        return tokens

    def _split_elisions(self, raw: list[RawToken]) -> list[RawToken]:
        """Break ``j'ai`` into ``j'`` + ``ai``, unless the whole form is itself an entry."""
        out: list[RawToken] = []
        for token in raw:
            match = _ELISION.match(token.surface)
            if not match or token.norm in self.lex:
                out.append(token)
                continue
            head, tail = match.group(1), match.group(2)
            if normalize(head) not in self.lex:
                out.append(token)
                continue
            # Both halves are French, which settles the reading of the clitic's partner.
            out.append(RawToken(head, normalize(head), token.line, token.col, Lang.FRENCH))
            out.append(
                RawToken(tail, normalize(tail), token.line, token.col + len(head), Lang.FRENCH)
            )
        return out

    # -- stage 1: maximal munch ------------------------------------------

    def _match_phrases(self, raw: list[RawToken]) -> list[Token]:
        tokens: list[Token] = []
        i = 0
        while i < len(raw):
            span = min(self.lex.max_words, len(raw) - i)
            matched = False
            for n in range(span, 0, -1):
                key = " ".join(r.norm for r in raw[i : i + n])
                entries = self.lex.lookup(key)
                if not entries:
                    continue
                surface = " ".join(r.surface for r in raw[i : i + n])
                tokens.append(self._from_entries(key, surface, entries, raw[i], n))
                i += n
                matched = True
                break
            if not matched:
                tokens.append(self._inflected_or_fallback(raw[i]))
                i += 1
        return tokens

    def _inflected_or_fallback(self, raw: RawToken) -> Token:
        """Try the French plural and feminine forms before giving up on a word."""
        for stem, plural in ((raw.norm[:-1], True), (raw.norm[:-1], False)):
            if len(raw.norm) < 4:
                break
            if plural and not raw.norm.endswith("s"):
                continue
            if not plural and not raw.norm.endswith("e"):
                continue
            entries = self.lex.lookup(stem)
            if entries:
                token = self._from_entries(stem, raw.surface, entries, raw, 1)
                token.norm = stem
                token.plural = plural
                return token
        return self._fallback(raw)

    def _from_entries(
        self, key: str, surface: str, entries: list[Entry], pos: RawToken, words: int
    ) -> Token:
        langs = tuple(dict.fromkeys(e.lang for e in entries))
        if self.lex.is_english(key):
            langs = langs + (Lang.ENGLISH,)
        lang = self._pick_language(entries, key, pos.hint)
        same = [e for e in entries if e.lang is lang] or entries
        cats = self.candidate_overrides.get(key) or tuple(
            dict.fromkeys(e.cat for e in same)
        )
        chosen = same[0]
        return Token(
            surface=surface,
            norm=key,
            cat=cats[0],
            lang=lang,
            gloss=chosen.gloss,
            line=pos.line,
            col=pos.col,
            words=words,
            candidates=cats,
            langs=langs,
            section=chosen.section,
            origin=chosen.origin,
        )

    def _pick_language(self, entries: list[Entry], key: str, hint: Lang | None = None) -> Lang:
        available = {e.lang for e in entries}
        if hint in available:
            return hint
        if self.prefer and self.prefer in available:
            return self.prefer
        # A French-only entry that is also an ordinary English word (taxi, me, note)
        # is far more likely to be the English one in this corpus.
        if available == {Lang.FRENCH} and key in self.lex.english:
            return Lang.FRENCH if self.prefer is Lang.FRENCH else Lang.ENGLISH
        for lang in _LANG_PRIORITY:
            if lang in available:
                return lang
        return entries[0].lang

    def _fallback(self, raw: RawToken) -> Token:
        """Words absent from every dictionary: punctuation, numerals, English, unknown."""
        surface, key = raw.surface, raw.norm
        base = dict(surface=surface, norm=key, line=raw.line, col=raw.col)

        if surface in _PUNCT_CAT or not key:
            return Token(**base, cat=Cat.PUNCT, lang=Lang.PUNCT, gloss=surface)
        if surface.replace(",", "").replace(".", "").isdigit():
            return Token(**base, cat=Cat.NUM, lang=Lang.ENGLISH, gloss=surface)
        if self.lex.is_english(key):
            cats = self.lex.english_cats(key)
            return Token(
                **base,
                cat=cats[0],
                lang=Lang.ENGLISH,
                gloss=key,
                candidates=cats if len(cats) > 1 else (),
                langs=(Lang.ENGLISH,),
            )

        stem, cat = self._morphological_guess(key)
        if stem:
            return Token(**base, cat=cat, lang=Lang.ENGLISH, gloss=stem, langs=(Lang.ENGLISH,))

        return Token(
            **base,
            cat=Cat.NOUN,
            lang=Lang.UNKNOWN,
            gloss="",
            candidates=(Cat.NOUN, Cat.VERB),
            guessed=True,
        )

    def _morphological_guess(self, key: str) -> tuple[str, Cat]:
        """Recognise inflected English: ``taxis``, ``bargaining``, ``charged``."""
        for suffix, cat in (("ing", Cat.VERB), ("ed", Cat.VERB), ("es", Cat.NOUN), ("s", Cat.NOUN)):
            if not key.endswith(suffix) or len(key) <= len(suffix) + 2:
                continue
            stem = key[: -len(suffix)]
            for candidate in (stem, stem + "e", stem[:-1] if stem[-1:] == stem[-2:-1] else stem):
                if self.lex.is_english(candidate):
                    return candidate, cat
        return "", Cat.UNKNOWN

    # -- stage 2: category disambiguation ---------------------------------

    def _resolve_categories(self, tokens: list[Token]) -> None:
        for i, tok in enumerate(tokens):
            cats = tok.candidates
            if len(cats) < 2:
                continue
            prev = tokens[i - 1] if i and tokens[i - 1].cat is not Cat.PUNCT else None
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            tok.cat = self._decide(cats, prev, nxt, tok.guessed)
            tok.gloss = self._gloss_for(tok)
        self._mark_negation_tails(tokens)

    @staticmethod
    def _mark_negation_tails(tokens: list[Token]) -> None:
        """In 'ne ... pas' only 'ne' negates; 'pas' is left as a particle."""
        for i, tok in enumerate(tokens):
            if tok.norm not in _NEG_TAIL or tok.cat is not Cat.NEG:
                continue
            prev = tokens[i - 1] if i else None
            if prev is not None and prev.cat in {Cat.VERB, Cat.COP, Cat.TMA}:
                tok.cat = Cat.PART

    @staticmethod
    def _decide(cats: tuple, prev: Token | None, nxt: Token | None, guessed: bool = False) -> Cat:
        has = cats.__contains__
        nxt_cats = set(nxt.candidates) | {nxt.cat} if nxt else set()
        nominal_next = bool(nxt_cats & {Cat.NOUN, Cat.ADJ, Cat.UNKNOWN})
        # A preposition can be followed by anything that opens a noun phrase.
        phrase_next = bool(
            nxt_cats & {Cat.NOUN, Cat.ADJ, Cat.UNKNOWN, Cat.NUM, Cat.DET, Cat.POSS, Cat.PRON}
        )
        # A guessed word is weak evidence, so it cannot on its own turn the word in
        # front of it into a tense marker.
        verb_next = nxt is not None and not nxt.guessed and Cat.VERB in nxt_cats
        # 'go di chop': a marker may be followed by another marker rather than the verb.
        verbal_next = verb_next or (nxt is not None and Cat.TMA in nxt_cats)
        after_subject = prev is not None and prev.cat in {Cat.PRON, Cat.TMA, Cat.NEG}

        if prev and prev.cat in {Cat.DET, Cat.POSS, Cat.NUM, Cat.PREP, Cat.ADJ} and has(Cat.NOUN):
            return Cat.NOUN
        if has(Cat.TMA) and after_subject and verbal_next:
            return Cat.TMA
        if prev and prev.cat in {Cat.VERB, Cat.COP, Cat.PREP} and has(Cat.DET):
            return Cat.DET
        # 'a' is both the perfect auxiliary and the preposition 'to'.
        if has(Cat.PREP) and phrase_next and not verb_next:
            return Cat.PREP
        # Utterance-initial 'di' is the article, not the continuous marker.
        if has(Cat.TMA) and prev is not None and verb_next:
            return Cat.TMA
        if has(Cat.DET) and nominal_next and not (nxt is not None and nxt.guessed):
            return Cat.DET
        if prev and prev.cat in {Cat.TMA, Cat.NEG} and has(Cat.VERB):
            return Cat.VERB
        if prev and prev.cat is Cat.PRON and has(Cat.VERB):
            return Cat.VERB
        if nxt and nxt.cat in {Cat.COP, Cat.TMA} and has(Cat.NOUN):
            return Cat.NOUN
        if prev is None and not guessed and has(Cat.VERB):
            return Cat.VERB
        if prev and prev.cat is Cat.COP:
            for cat in (Cat.VERB, Cat.ADJ, Cat.NOUN):
                if has(cat):
                    return cat
        return cats[0]

    def _gloss_for(self, tok: Token) -> str:
        for entry in self.lex.lookup(tok.norm):
            if entry.lang is tok.lang and entry.cat is tok.cat:
                return entry.gloss
        for entry in self.lex.lookup(tok.norm):
            if entry.lang is tok.lang:
                return entry.gloss
        return tok.gloss


def _candidate_map(lex: Lexicon) -> dict[str, tuple[Cat, ...]]:
    import json

    from .lexicon import DATA_DIR

    data = json.loads((DATA_DIR / "pos_overrides.json").read_text(encoding="utf-8"))
    return {
        normalize(term): tuple(Cat(c) for c in cats)
        for term, cats in data.get("candidates", {}).items()
    }


def tokenize(text: str, lexicon: Lexicon | None = None, prefer: Lang | None = None) -> list[Token]:
    """Convenience wrapper for one-off scans."""
    return Lexer(lexicon, prefer).tokenize(text)
