"""Minimal English morphology used by the translator.

Dictionary glosses are citation forms (``to chop`` -> ``eat``). To build a natural
English sentence the translator needs the third person singular, the past tense, the
past participle, the gerund and the plural, so this module supplies them with an
irregular table plus the usual spelling rules.
"""

from __future__ import annotations

import re

#: base -> (past, past participle)
IRREGULAR_VERBS: dict[str, tuple[str, str]] = {
    "be": ("was", "been"),
    "have": ("had", "had"),
    "do": ("did", "done"),
    "go": ("went", "gone"),
    "come": ("came", "come"),
    "get": ("got", "got"),
    "give": ("gave", "given"),
    "take": ("took", "taken"),
    "make": ("made", "made"),
    "say": ("said", "said"),
    "tell": ("told", "told"),
    "see": ("saw", "seen"),
    "know": ("knew", "known"),
    "think": ("thought", "thought"),
    "feel": ("felt", "felt"),
    "hear": ("heard", "heard"),
    "find": ("found", "found"),
    "lose": ("lost", "lost"),
    "keep": ("kept", "kept"),
    "leave": ("left", "left"),
    "bring": ("brought", "brought"),
    "buy": ("bought", "bought"),
    "sell": ("sold", "sold"),
    "pay": ("paid", "paid"),
    "send": ("sent", "sent"),
    "spend": ("spent", "spent"),
    "sit": ("sat", "sat"),
    "stand": ("stood", "stood"),
    "sleep": ("slept", "slept"),
    "eat": ("ate", "eaten"),
    "drink": ("drank", "drunk"),
    "run": ("ran", "run"),
    "drive": ("drove", "driven"),
    "break": ("broke", "broken"),
    "speak": ("spoke", "spoken"),
    "write": ("wrote", "written"),
    "read": ("read", "read"),
    "teach": ("taught", "taught"),
    "catch": ("caught", "caught"),
    "fight": ("fought", "fought"),
    "steal": ("stole", "stolen"),
    "understand": ("understood", "understood"),
    "forget": ("forgot", "forgotten"),
    "build": ("built", "built"),
    "cut": ("cut", "cut"),
    "put": ("put", "put"),
    "let": ("let", "let"),
    "begin": ("began", "begun"),
    "wear": ("wore", "worn"),
    "win": ("won", "won"),
    "meet": ("met", "met"),
    "hold": ("held", "held"),
    "hurt": ("hurt", "hurt"),
    "cost": ("cost", "cost"),
    "sing": ("sang", "sung"),
    "become": ("became", "become"),
    "fall": ("fell", "fallen"),
    "grow": ("grew", "grown"),
    "hide": ("hid", "hidden"),
    "rise": ("rose", "risen"),
    "shine": ("shone", "shone"),
    "blow": ("blew", "blown"),
    "wake": ("woke", "woken"),
    "choose": ("chose", "chosen"),
    "shut": ("shut", "shut"),
    "set": ("set", "set"),
    "beat": ("beat", "beaten"),
}

IRREGULAR_PLURALS: dict[str, str] = {
    "child": "children",
    "man": "men",
    "woman": "women",
    "person": "people",
    "foot": "feet",
    "tooth": "teeth",
    "goose": "geese",
    "mouse": "mice",
    "wife": "wives",
    "knife": "knives",
    "life": "lives",
    "leaf": "leaves",
    "thief": "thieves",
    "loaf": "loaves",
}

UNCOUNTABLE = {
    "money", "water", "food", "rain", "time", "trouble", "work", "news",
    "electricity", "power", "fuel", "petrol", "traffic", "rice", "salt", "oil",
    "bread", "meat", "fish", "hunger", "gossip", "noise", "luck", "shame",
    "respect", "sense", "poverty", "blood", "dirt", "help", "information",
    "network", "data", "credit", "wine", "beer", "milk", "air", "fire", "light",
    "advice", "business", "transport", "people", "children", "hair", "sugar",
    "home", "school", "church", "town", "prison", "hospital",
}

_VOWELS = "aeiou"
_SIBILANT = re.compile(r"(s|x|z|ch|sh)$")


def _split_head(phrase: str) -> tuple[str, str]:
    """``look for`` -> ``('look', ' for')`` so only the head word inflects."""
    head, sep, tail = phrase.partition(" ")
    return head, (sep + tail if sep else "")


def third_person(verb: str) -> str:
    head, tail = _split_head(verb)
    if head == "be":
        return "is" + tail
    if head == "have":
        return "has" + tail
    if head in {"can", "must", "will", "shall", "may", "might", "could", "would", "should"}:
        return head + tail
    if head.endswith("y") and head[-2:-1] not in _VOWELS:
        return head[:-1] + "ies" + tail
    if _SIBILANT.search(head) or head.endswith("o"):
        return head + "es" + tail
    return head + "s" + tail


def past(verb: str) -> str:
    head, tail = _split_head(verb)
    if head in IRREGULAR_VERBS:
        return IRREGULAR_VERBS[head][0] + tail
    if head in {"can", "will", "must", "shall"}:
        return {"can": "could", "will": "would", "must": "must", "shall": "should"}[head] + tail
    return _regular_ed(head) + tail


def participle(verb: str) -> str:
    head, tail = _split_head(verb)
    if head in IRREGULAR_VERBS:
        return IRREGULAR_VERBS[head][1] + tail
    return _regular_ed(head) + tail


def gerund(verb: str) -> str:
    head, tail = _split_head(verb)
    if head.endswith("ie"):
        return head[:-2] + "ying" + tail
    if head.endswith("e") and len(head) > 2 and not head.endswith("ee"):
        return head[:-1] + "ing" + tail
    return _double_final(head) + "ing" + tail


def plural(noun: str) -> str:
    head, tail = _split_head(noun)
    if head in UNCOUNTABLE:
        return noun
    if head in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[head] + tail
    if head.endswith("y") and head[-2:-1] not in _VOWELS:
        return head[:-1] + "ies" + tail
    if _SIBILANT.search(head):
        return head + "es" + tail
    return head + "s" + tail


def article_for(noun: str) -> str:
    """``a`` or ``an`` according to the following sound (spelling approximation)."""
    return "an" if noun[:1].lower() in _VOWELS else "a"


def _regular_ed(head: str) -> str:
    if head.endswith("e"):
        return head + "d"
    if head.endswith("y") and head[-2:-1] not in _VOWELS:
        return head[:-1] + "ied"
    return _double_final(head) + "ed"


def _double_final(head: str) -> str:
    """Double a final consonant after a single stressed short vowel: ``stop`` -> ``stopp``.

    Only one-syllable stems qualify, which keeps ``enter`` and ``open`` intact.
    """
    if len(re.findall(r"[aeiou]+", head)) != 1:
        return head
    if (
        len(head) >= 3
        and head[-1] not in _VOWELS + "wxy"
        and head[-2] in _VOWELS
        and head[-3] not in _VOWELS
    ):
        return head + head[-1]
    return head
