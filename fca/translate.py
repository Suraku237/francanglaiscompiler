"""Transfer-based translation from Pidgin / Camfranglais into English.

The strategy is the classical three-stage transfer model, simplified:

1. **Lexical transfer** - every token is replaced by its English equivalent, taken from
   the dictionary gloss (or from ``data/translation_overrides.json`` where the gloss
   describes a word instead of translating it).
2. **Structural transfer** - the parts of the sentence that do *not* map word-for-word
   are rewritten: the tense/mood/aspect markers ``bin don di go fit mus`` become an
   English auxiliary chain, the zero copula is filled in, pronouns take subject or
   object case, and post-nominal ``dem`` becomes an English plural.
3. **Generation** - the English words are inflected, given articles, capitalised and
   punctuated.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import morphology as morph
from .lexicon import DATA_DIR, Lexicon, load_lexicon, normalize
from .lexer import Lexer
from .tokens import Cat, Lang, Token

# -- pronoun tables ------------------------------------------------------
# (subject form, object form, person, number)

_PIDGIN_PRONOUNS = {
    "a": ("I", "me", 1, "sg"),
    "mi": ("I", "me", 1, "sg"),
    "yu": ("you", "you", 2, "sg"),
    "i": ("he", "him", 3, "sg"),
    "yi": ("he", "him", 3, "sg"),
    "e": ("it", "it", 3, "sg"),
    "am": ("it", "it", 3, "sg"),
    "wi": ("we", "us", 1, "pl"),
    "wuna": ("you", "you", 2, "pl"),
    "dem": ("they", "them", 3, "pl"),
    "ol man": ("everybody", "everybody", 3, "sg"),
    "ol ting": ("everything", "everything", 3, "sg"),
    "notin": ("nothing", "nothing", 3, "sg"),
    "nobodi": ("nobody", "nobody", 3, "sg"),
}

_FRENCH_PRONOUNS = {
    "je": ("I", "me", 1, "sg"),
    "j'": ("I", "me", 1, "sg"),
    "moi": ("I", "me", 1, "sg"),
    "me": ("I", "me", 1, "sg"),
    "tu": ("you", "you", 2, "sg"),
    "toi": ("you", "you", 2, "sg"),
    "te": ("you", "you", 2, "sg"),
    "il": ("he", "him", 3, "sg"),
    "lui": ("he", "him", 3, "sg"),
    "elle": ("she", "her", 3, "sg"),
    "on": ("we", "us", 1, "pl"),
    "nous": ("we", "us", 1, "pl"),
    "vous": ("you", "you", 2, "pl"),
    "ils": ("they", "them", 3, "pl"),
    "elles": ("they", "them", 3, "pl"),
    "eux": ("they", "them", 3, "pl"),
    "ca": ("that", "that", 3, "sg"),
    "cela": ("that", "that", 3, "sg"),
    "ceci": ("this", "this", 3, "sg"),
}

_ENGLISH_PRONOUNS = {
    "i": ("I", "me", 1, "sg"),
    "me": ("I", "me", 1, "sg"),
    "you": ("you", "you", 2, "sg"),
    "he": ("he", "him", 3, "sg"),
    "him": ("he", "him", 3, "sg"),
    "she": ("she", "her", 3, "sg"),
    "her": ("she", "her", 3, "sg"),
    "it": ("it", "it", 3, "sg"),
    "we": ("we", "us", 1, "pl"),
    "us": ("we", "us", 1, "pl"),
    "they": ("they", "them", 3, "pl"),
    "them": ("they", "them", 3, "pl"),
}

_POSSESSIVES = {
    "ma": "my", "ya": "your", "wi own": "our", "yu own": "your",
    "mon": "my", "mes": "my", "ton": "your", "ta": "your",
    "son": "his", "sa": "her", "notre": "our", "votre": "your", "leur": "their",
}

#: Tense / mood / aspect markers mapped onto abstract features.
_TMA = {
    "bin": "PAST", "don": "PERF", "di": "PROG", "go": "FUT", "fit": "CAN", "mus": "MUST",
    "va": "FUT", "vais": "FUT", "vas": "FUT", "vont": "FUT", "allons": "FUT", "allez": "FUT",
    "ai": "PERF", "as": "PERF", "a": "PERF", "ont": "PERF", "avons": "PERF", "avez": "PERF",
    "peut": "CAN", "peux": "CAN", "pouvons": "CAN", "peuvent": "CAN",
    "faut": "MUST", "doit": "MUST", "dois": "MUST",
    "will": "FUT", "shall": "FUT", "would": "FUT", "going to": "FUT", "about to": "FUT",
    "can": "CAN", "could": "CAN", "may": "MAY", "might": "MAY",
    "must": "MUST", "should": "MUST",
    "have": "PERF", "has": "PERF", "had": "PASTPERF",
    "did": "PAST", "used to": "PAST", "do": "", "does": "",
}

_PAST_COPULAS = {"was", "were", "etait", "bin"}
_FUTURE_COPULAS = {"sera"}
_DROP = {"pas", "ne", "oh", "deh", "dey", "la"}
_AUXILIARIES = {
    "is", "are", "am", "was", "were", "will", "can", "could", "must", "may",
    "might", "have", "has", "had", "do", "does", "did", "would", "should",
}
#: Verbs of motion take ``to`` before a bare destination in English.
_MOTION = {"go", "come", "return", "walk", "run", "travel", "move", "drive", "climb"}


@dataclass
class Translation:
    source: str
    english: str
    tokens: list[Token] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.english


class Translator:
    """Rule-based Pidgin/Camfranglais -> English transfer engine."""

    def __init__(self, lexicon: Lexicon | None = None, lexer: Lexer | None = None):
        self.lex = lexicon or (lexer.lex if lexer else load_lexicon())
        self.lexer = lexer or Lexer(self.lex)
        data = json.loads((DATA_DIR / "translation_overrides.json").read_text(encoding="utf-8"))
        self.overrides = {normalize(k): v for k, v in data["gloss"].items()}
        self.preps = data["prepositions"]
        self.place_preps = data["place_prepositions"]
        self.place_nouns = set(data["place_nouns"])
        self.determiners = data["determiners"]

    # -- public API ------------------------------------------------------

    def translate(self, text: str) -> Translation:
        tokens = self.lexer.tokenize(text)
        return self.translate_tokens(tokens, text)

    def translate_word(self, word: str) -> list[tuple[str, str, str]]:
        """Look one item up. Returns ``(language, category, english)`` per reading."""
        key = normalize(word)
        readings: list[tuple[str, str, str]] = []
        for entry in self.lex.lookup(key):
            english = "; ".join(entry.senses) or self.overrides.get(key) or entry.head
            readings.append((entry.lang.value, entry.cat.value, english))
        if not readings and self.lex.is_english(key):
            readings.append(("ENGLISH", self.lex.english_cat(key).value, key))
        return readings

    def translate_tokens(self, tokens: list[Token], source: str = "") -> Translation:
        notes: list[str] = []
        chunks: list[str] = []
        capitalise = True
        for segment, closer in _segments(tokens):
            text = self._translate_segment(segment, closer, notes)
            if text:
                chunks.append(_finish(text, closer, capitalise))
                capitalise = closer in {"", ".", "!", "?"}
            elif closer and chunks:
                chunks[-1] = _retrofit(chunks[-1], closer)
        english = " ".join(c for c in chunks if c)
        return Translation(source or _surface(tokens), english, tokens, notes)

    # -- segment translation ----------------------------------------------

    def _translate_segment(self, seg: list[Token], closer: str, notes: list[str]) -> str:
        out: list[str] = []
        subject: tuple[str, str, int, str] | None = None
        verb_done = False
        det_pending = False
        article_at = -1
        first_group: tuple[int, dict, tuple | None] | None = None
        hortative = False
        wh_subject = False
        has_qword = False
        subject_at = -1
        last_verb = ""
        copula_at = -1
        negated = False
        skip = set()
        i = 0

        while i < len(seg):
            if i in skip:
                i += 1
                continue
            tok = seg[i]

            if tok.cat is Cat.PLUR:
                i += 1
                continue

            if tok.cat is Cat.CONJ:
                out.append(self._english_of(tok))
                subject, verb_done, wh_subject = None, False, False
                copula_at, article_at, last_verb, subject_at = -1, -1, "", -1
                i += 1
                continue

            if tok.cat is Cat.MAKE:
                out.append("let")
                hortative = True
                i += 1
                continue

            if tok.cat is Cat.NEG:
                negated = True

            if tok.cat in {Cat.NEG, Cat.TMA, Cat.VERB, Cat.COP}:
                start = len(out)
                group, i = self._read_verb_group(seg, i)
                # A serial 'go' after another verb is a directional, not a verb:
                # 'carry me go Mvog-Ada' = 'take me to Mvog-Ada'.
                if verb_done and group["head"] == "go" and not group["markers"]:
                    out.append("to")
                    last_verb = ""
                    det_pending = False
                    continue
                rendered = self._render_verb_group(group, None if hortative else subject)
                # 'taxi no dey' - a clause-final copula needs an English complement.
                if group["copula"] and i >= len(seg) and not has_qword:
                    rendered.append("there")
                out.extend(rendered)
                if first_group is None:
                    first_group = (start, group, subject)
                last_verb = group["head"]
                verb_done = True
                hortative = False
                det_pending = False
                continue

            word = self._english_of(tok)

            if tok.cat is Cat.PRON:
                person = self._pronoun(tok)
                if person:
                    prev = seg[i - 1] if i else None
                    nxt = seg[i + 1] if i + 1 < len(seg) else None
                    # 'na tu kolo a get' - a pronoun right after a noun and right
                    # before a verb opens a new (cleft or relative) clause.
                    new_clause = (
                        prev is not None
                        and prev.cat in {Cat.NOUN, Cat.PLUR, Cat.NUM}
                        and nxt is not None
                        and nxt.cat in {Cat.VERB, Cat.TMA, Cat.NEG}
                    )
                    if hortative:
                        out.append(person[1])
                        subject = person
                    elif (subject is None and not verb_done) or new_clause:
                        subject = person
                        subject_at = len(out)
                        out.append(person[0])
                    else:
                        out.append(_negative_concord(person[1]) if negated else person[1])
                    i += 1
                    continue

            if tok.cat is Cat.QWORD and subject is None:
                has_qword = True
                out.append(word)
                nxt = seg[i + 1] if i + 1 < len(seg) else None
                # 'wetin di hapen' - the question word is the subject.
                # 'wetin yu di chop' - it is not; the subject follows.
                if nxt is None or nxt.cat in {Cat.VERB, Cat.TMA, Cat.NEG, Cat.COP}:
                    subject = (word, word, 3, "sg")
                    subject_at = len(out) - 1
                    wh_subject = True
                i += 1
                continue

            if (
                tok.cat in {Cat.ADJ, Cat.PREP, Cat.ADV}
                and subject
                and not verb_done
                and not (wh_subject and tok.cat is Cat.PREP)
            ):
                copula_at = len(out)
                out.append(_be(subject[2], subject[3], False))
                verb_done = True
                notes.append("inserted copula: this variety allows a zero copula")

            if tok.cat is Cat.ADJ and copula_at >= 0 and len(out) > copula_at + 1:
                out.insert(copula_at + 1, word)
                det_pending = False
                i += 1
                continue

            if tok.cat is Cat.ADJ:
                out.append(word)
                i += 1  # an attributive adjective does not close the noun phrase
                continue

            if tok.cat is Cat.PREP:
                nxt = seg[i + 1] if i + 1 < len(seg) else None
                out.append(self._preposition(tok, nxt))
                last_verb = ""
                det_pending = False
                i += 1
                continue

            if tok.cat in {Cat.DET, Cat.POSS, Cat.NUM}:
                article_at = len(out)
                out.append(
                    _POSSESSIVES.get(tok.norm)
                    or (self.determiners.get(tok.norm) if tok.cat is Cat.DET else None)
                    or word
                )
                det_pending = True
                i += 1
                continue

            if tok.cat is Cat.NOUN or (tok.cat is Cat.UNKNOWN and word):
                plural = _is_plural_marked(seg, i)
                if plural:
                    skip.add(i + 1)
                noun = _strip_article(word)[0]
                if plural:
                    noun = morph.plural(noun)
                vocative = len(seg) == 1 and closer in {",", "!", ""}
                if last_verb in _MOTION and self._is_place(tok):
                    out.append("to")
                    last_verb = ""
                np_start = article_at if det_pending else len(out)
                if not det_pending and not vocative and not _bare(noun, plural):
                    article_at = len(out)
                    out.append("the")
                out.append(noun)
                if subject is None and not verb_done:
                    subject = (noun, noun, 3, "pl" if plural else "sg")
                    subject_at = np_start
                det_pending = False
                i += 1
                continue

            if tok.cat is Cat.PART:
                self._apply_particle(tok, out, article_at)
                det_pending = False
                i += 1
                continue

            if word:
                out.append(word)
            det_pending = False
            i += 1

        if first_group and not wh_subject and (closer == "?" or has_qword):
            if self._invert(out, first_group, subject_at):
                notes.append("inverted the auxiliary: English marks questions by inversion")
        return " ".join(w for w in out if w)

    def _invert(self, out: list[str], first_group, subject_at: int) -> bool:
        """Move the auxiliary in front of the subject, adding do-support if needed."""
        start, group, subject = first_group
        if subject_at < 0 or subject_at >= start or start >= len(out):
            return False
        head = out[start]
        if head in _AUXILIARIES:
            out.pop(start)
            out.insert(subject_at, head)
            return True
        person, number = (subject[2], subject[3]) if subject else (2, "sg")
        past = group["past"] or "PAST" in group["markers"]
        do = "did" if past else ("does" if (person == 3 and number == "sg") else "do")
        out[start] = group["head"] or head
        out.insert(subject_at, do)
        return True

    # -- verb group --------------------------------------------------------

    def _read_verb_group(self, seg: list[Token], i: int) -> tuple[dict, int]:
        group = {
            "neg": False, "markers": [], "head": "",
            "copula": False, "past": False, "inflect": True,
        }
        while i < len(seg):
            tok = seg[i]
            if tok.cat is Cat.NEG:
                group["neg"] = True
                i += 1
                continue
            if tok.cat is Cat.TMA:
                feature = _TMA.get(tok.norm, "")
                if feature:
                    group["markers"].append(feature)
                i += 1
                continue
            if tok.cat is Cat.COP:
                # 'dey/dei' immediately before a verb is the progressive marker,
                # not the copula: 'i dey sell' = 'he is selling'.
                nxt = seg[i + 1] if i + 1 < len(seg) else None
                if tok.norm in {"dei", "dey", "de"} and nxt is not None and nxt.cat is Cat.VERB:
                    group["markers"].append("PROG")
                    i += 1
                    continue
                group["copula"] = True
                group["head"] = "be"
                if tok.norm in _PAST_COPULAS:
                    group["past"] = True
                if tok.norm in _FUTURE_COPULAS:
                    group["markers"].append("FUT")
                if tok.norm in {"c'est", "ce n'est pas"}:
                    group["dummy_subject"] = "it"
                i += 1
                break
            if tok.cat is Cat.VERB:
                group["head"] = self._english_of(tok) or tok.norm
                group["inflect"] = tok.lang is not Lang.UNKNOWN
                if tok.lang is Lang.ENGLISH and normalize(tok.surface).endswith("ed"):
                    group["past"] = True
                i += 1
                break
            break
        return group, i

    def _render_verb_group(self, group: dict, subject) -> list[str]:
        markers = group["markers"]
        person, number = (subject[2], subject[3]) if subject else (2, "sg")
        past = group["past"] or "PAST" in markers or "PASTPERF" in markers
        perfect = "PERF" in markers or "PASTPERF" in markers
        progressive = "PROG" in markers
        future = "FUT" in markers
        modal = next((m.lower() for m in markers if m in {"CAN", "MUST", "MAY"}), "")
        main = group["head"] or ("be" if group["copula"] else "")
        words: list[str] = []
        if group["copula"] and subject is None and not group.get("dummy_subject"):
            group["dummy_subject"] = "it"
        if group.get("dummy_subject"):
            words.append(group["dummy_subject"])
            person, number = 3, "sg"

        chain: list[str] = []
        if modal:
            chain.append(modal)
        elif future:
            chain.append("will")
        if perfect:
            chain.append("have")
        if progressive:
            chain.append("be")

        if not main:
            tail = chain or [_be(person, number, past)]
            if group["neg"]:
                tail = tail[:1] + ["not"] + tail[1:]
            return words + tail

        if not chain:
            words.extend(_simple_verb(main, person, number, past, group["neg"], group["inflect"]))
            return words

        finite = chain[0]
        if finite in {"can", "must", "may", "will"}:
            words.append(morph.past(finite) if past and finite != "must" else finite)
        elif finite == "be":
            words.append(_be(person, number, past))
        elif past:
            words.append("had" if finite == "have" else _be(person, number, True))
        else:
            words.append(
                morph.third_person(finite) if (person == 3 and number == "sg") else finite
            )
        if group["neg"]:
            words.append("not")

        previous = finite
        tail = chain[1:] + [main]
        for k, nxt in enumerate(tail):
            is_main = k == len(tail) - 1
            keep_raw = is_main and not group["inflect"]
            words.append(nxt if keep_raw else _dependent_form(previous, nxt))
            previous = nxt
        return words

    # -- lexical helpers ---------------------------------------------------

    def _english_of(self, tok: Token) -> str:
        if tok.norm in self.overrides:
            return self.overrides[tok.norm]
        if tok.norm in _DROP:
            return ""
        if tok.cat is Cat.DET and tok.norm in self.determiners:
            return self.determiners[tok.norm]
        if tok.lang is Lang.UNKNOWN:
            return tok.surface
        if tok.lang is Lang.ENGLISH or not tok.gloss:
            return tok.norm
        for entry in self.lex.lookup(tok.norm):
            if entry.lang is tok.lang and entry.cat is tok.cat:
                return _decapitalise(entry.head, tok.cat)
        entries = self.lex.lookup(tok.norm)
        return _decapitalise(entries[0].head, tok.cat) if entries else tok.norm

    def _pronoun(self, tok: Token):
        table = {
            Lang.PIDGIN: _PIDGIN_PRONOUNS,
            Lang.CAMFRANGLAIS: _PIDGIN_PRONOUNS,
            Lang.FRENCH: _FRENCH_PRONOUNS,
            Lang.ENGLISH: _ENGLISH_PRONOUNS,
        }.get(tok.lang, _ENGLISH_PRONOUNS)
        return table.get(tok.norm) or _ENGLISH_PRONOUNS.get(tok.norm)

    def _preposition(self, tok: Token, nxt: Token | None) -> str:
        if tok.norm in self.preps:
            if nxt is not None and self._is_place(nxt):
                return self.place_preps[tok.norm]
            return self.preps[tok.norm]
        return self._english_of(tok)

    def _is_place(self, tok: Token) -> bool:
        section = tok.section.lower()
        if "place" in section or "home" in section or "transport" in section:
            return True
        head = _strip_article(self._english_of(tok))[0]
        return head.split()[0] in self.place_nouns if head else False

    def _apply_particle(self, tok: Token, out: list[str], article_at: int) -> None:
        word = self._english_of(tok)
        if tok.norm == "la" and article_at >= 0:
            out[article_at] = "that"
            return
        if not word:
            return
        if word == "even" and out:
            out.insert(len(out) - 1, "even")
            return
        out.append(word)


# -- module-level helpers -------------------------------------------------


def _segments(tokens: list[Token]):
    """Split the token stream into clauses, keeping the closing punctuation."""
    segment: list[Token] = []
    for tok in tokens:
        if tok.cat is Cat.PUNCT:
            yield segment, tok.surface
            segment = []
        else:
            segment.append(tok)
    if segment:
        yield segment, ""


def _surface(tokens: list[Token]) -> str:
    return " ".join(t.surface for t in tokens)


def _be(person: int, number: str, past: bool) -> str:
    if past:
        return "was" if (number == "sg" and person in (1, 3)) else "were"
    if person == 1 and number == "sg":
        return "am"
    if person == 3 and number == "sg":
        return "is"
    return "are"


def _simple_verb(
    main: str, person: int, number: str, past: bool, neg: bool, inflect: bool = True
) -> list[str]:
    if main == "be":
        be = _be(person, number, past)
        return [be, "not"] if neg else [be]
    if neg:
        do = "did" if past else ("does" if (person == 3 and number == "sg") else "do")
        return [do, "not", main]
    if not inflect:
        return [main]
    if past:
        return [morph.past(main)]
    if person == 3 and number == "sg":
        return [morph.third_person(main)]
    return [main]


def _dependent_form(previous: str, word: str) -> str:
    if previous in {"can", "must", "may", "will"}:
        return word
    if previous == "have":
        return morph.participle(word)
    if previous == "be":
        return morph.gerund(word)
    return word


def _is_plural_marked(seg: list[Token], i: int) -> bool:
    nxt = seg[i + 1] if i + 1 < len(seg) else None
    return bool(nxt and nxt.cat is Cat.PLUR)


def _negative_concord(word: str) -> str:
    """Pidgin stacks negatives; English does not. 'no ... notin' -> 'not anything'."""
    return {"nothing": "anything", "nobody": "anybody", "nowhere": "anywhere"}.get(word, word)


def _decapitalise(word: str, cat: Cat) -> str:
    """Dictionary glosses are capitalised; only genuine proper nouns should stay so."""
    if cat is Cat.NOUN or not word:
        return word
    return word[0].lower() + word[1:]


def _starts_with_qword(seg: list[Token]) -> bool:
    return bool(seg) and seg[0].cat in {Cat.QWORD, Cat.INTERJ}


def _strip_article(word: str) -> tuple[str, bool]:
    match = re.match(r"^(a|an|the)\s+(.*)$", word)
    return (match.group(2), True) if match else (word, False)


def _bare(noun: str, plural: bool) -> bool:
    """True when English would use no article at all."""
    head = noun.split()[0] if noun else ""
    return plural or head in morph.UNCOUNTABLE or noun[:1].isupper()


def _finish(text: str, closer: str, capitalise: bool = True) -> str:
    text = re.sub(r"\ba (?=[aeiouAEIOU])", "an ", text)
    text = re.sub(r"\s+([,;:])", r"\1", text).strip()
    if not text:
        return ""
    if capitalise:
        text = text[0].upper() + text[1:]
    text = re.sub(r"\bi\b", "I", text)
    if closer in {".", "!", "?"}:
        return text + closer
    if closer == ",":
        return text + ","
    return text + "."


def _retrofit(chunk: str, closer: str) -> str:
    return chunk[:-1] + closer if chunk and chunk[-1] in ".!?," else chunk


def translate(text: str, translator: Translator | None = None) -> Translation:
    return (translator or Translator()).translate(text)
