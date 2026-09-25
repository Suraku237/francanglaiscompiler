"""Exact supplied transcriptions; regression fixtures do not certify their provenance."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusCase:
    text: str
    categories: tuple[str, ...]
    accepted: bool
    reason: str


CORPUS_CASES = (
    CorpusCase(
        "J'ai n'est pas tchop depuis bayar",
        ("VERB", "VERB", "FRENCH_FUNCTION_WORD", "NOUN", "FRENCH_FUNCTION_WORD", "ADVERB"),
        True, "Contracted verbs, a function-word nominal group and a temporal adverbial group; not corrected French.",
    ),
    CorpusCase(
        "je suis kass je go nang",
        ("FRENCH_FUNCTION_WORD", "VERB", "ADJECTIVE", "FRENCH_FUNCTION_WORD", "VERB", "VERB"),
        True, "Pronominal clause with an adjective, followed by a juxtaposed clause with serial verbs.",
    ),
    CorpusCase(
        "je suis back du school le sharp man",
        ("FRENCH_FUNCTION_WORD", "VERB", "AMBIGUOUS", "FRENCH_FUNCTION_WORD", "NOUN",
         "FRENCH_FUNCTION_WORD", "ADVERB", "AMBIGUOUS"),
        True, "Ambiguous complement, school nominal group and a marked adverb-plus-ambiguous group.",
    ),
    CorpusCase(
        "j'ai mban gars je yabat",
        ("VERB", "VERB", "PIDGIN_MARKER", "FRENCH_FUNCTION_WORD", "VERB"),
        True, "Contracted auxiliary and verb, discourse marker, then a juxtaposed pronominal clause.",
    ),
    CorpusCase(
        "elles yamo flop le kongossa",
        ("FRENCH_FUNCTION_WORD", "VERB", "ADVERB", "FRENCH_FUNCTION_WORD", "AMBIGUOUS"),
        True, "Pronominal clause with an adverb and an introduced ambiguous complement.",
    ),
    CorpusCase(
        "go au piol shoua mes kako",
        ("VERB", "FRENCH_FUNCTION_WORD", "NOUN", "VERB", "FRENCH_FUNCTION_WORD", "NOUN"),
        True, "Two juxtaposed verb-initial phrases with introduced nominal complements.",
    ),
    CorpusCase(
        "pere ca me chop je suis kass",
        ("NOUN", "FRENCH_FUNCTION_WORD", "AMBIGUOUS", "PIDGIN_MARKER",
         "FRENCH_FUNCTION_WORD", "VERB", "ADJECTIVE"),
        True, "Nominal address, pronominal/Pidgin pattern, then a pronominal clause and adjective.",
    ),
    CorpusCase(
        "Ont a cote la light depuis le shap",
        ("VERB", "ENGLISH_FUNCTION_WORD", "VERB", "FRENCH_FUNCTION_WORD", "NOUN",
         "FRENCH_FUNCTION_WORD", "FRENCH_FUNCTION_WORD", "ADVERB"),
        True, "Observed verb-link-verb categories, nominal complement and a two-marker adverbial group.",
    ),
    CorpusCase(
        "shiba le price pere je n'ais pas flop les do",
        ("VERB", "FRENCH_FUNCTION_WORD", "NOUN", "NOUN", "FRENCH_FUNCTION_WORD", "UNKNOWN",
         "FRENCH_FUNCTION_WORD", "ADVERB", "FRENCH_FUNCTION_WORD", "ENGLISH_FUNCTION_WORD"),
        False, "The original n'ais is UNKNOWN. No silent correction to n'ai is made.",
    ),
    CorpusCase(
        "mon combi came au school alli day a pied",
        ("FRENCH_FUNCTION_WORD", "NOUN", "VERB", "FRENCH_FUNCTION_WORD", "NOUN", "UNKNOWN",
         "NOUN", "ENGLISH_FUNCTION_WORD", "NOUN"),
        False, "The original alli is UNKNOWN. Its intended form and usage require human review.",
    ),
    CorpusCase(
        "je falla le taco depuis bayar",
        ("FRENCH_FUNCTION_WORD", "VERB", "FRENCH_FUNCTION_WORD", "NOUN", "FRENCH_FUNCTION_WORD", "ADVERB"),
        True, "Pronominal clause, introduced nominal complement and temporal adverbial group.",
    ),
    CorpusCase(
        "les talk free le francais",
        ("FRENCH_FUNCTION_WORD", "VERB", "AMBIGUOUS", "FRENCH_FUNCTION_WORD", "NOUN"),
        True, "Function-word-led clause with an ambiguous complement and an introduced nominal group.",
    ),
)
