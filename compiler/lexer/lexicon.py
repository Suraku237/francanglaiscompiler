"""
Word lists and regex patterns used by the lexical analyzer.

IMPORTANT: this is a STARTING lexicon based on common, well-documented
Camfranglais / Cameroonian Pidgin patterns. The classifier's accuracy
depends entirely on how complete these lists are for the SPECIFIC
speech your group actually collects — grow these sets from your own
dataset.csv (especially NOUN_LEXICON, VERB_LEXICON, SLANG_WORDS,
VERB_PHRASES) before writing up frequency results in the report.
"""

# --- Regex-recognizable token categories (structural, not lexicon-based) ---
# Checked first, in order, against the raw token text.

TERMINAL_CATEGORIES = (
    "NUMBER", "PUNCTUATION", "SLANG", "PIDGIN_MARKER", "NOUN", "VERB",
    "FRENCH_FUNCTION_WORD", "ENGLISH_FUNCTION_WORD",
    "ENGLISH_VERB_LIKE", "FRENCH_VERB_LIKE", "UNKNOWN",
)

TOKEN_REGEX_RULES = [
    ("NUMBER",      r"^\d+(?:[.,]\d+)?$"),
    ("PUNCTUATION", r"^[.,!?;:\"()]+$"),
]

# Combining diacritical-mark blocks, retained with a preceding letter.
COMBINING_MARKS = r"\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f"

# --- Function words (closed-class, small enough to enumerate exhaustively) ---

FRENCH_FUNCTION_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "mais",
    "donc", "car", "ne", "pas", "que", "qui", "avec", "pour", "sur", "dans",
    "il", "elle", "on", "je", "tu", "nous", "vous", "ils", "elles", "mon",
    "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "ce", "cette",
    "il-y-a", "y", "en", "au", "aux",
}

ENGLISH_FUNCTION_WORDS = {
    "the", "a", "an", "and", "or", "but", "so", "because", "not", "that",
    "who", "with", "for", "on", "in", "he", "she", "we", "i", "you", "they",
    "my", "your", "his", "her", "our", "their", "is", "are", "was", "were",
    "do", "does", "did", "of", "to", "at",
}

PIDGIN_MARKERS = {
    "dey", "don", "na", "abeg", "wetin", "nawa", "sabi", "waka", "chop",
    "wahala", "kombi", "gars", "small", "sef", "sabi",
}

# --- Content-word lexicons (open-class — the ones most worth growing) ---

NOUN_LEXICON = {
    "tchop", "quartier", "bendskin", "moto", "marche", "marché", "taxi",
    "go-slow", "electricite", "électricité", "internet", "reseau", "réseau",
    "essence", "carburant", "pluie", "campus", "checkpoint", "gendarme",
    "argent", "money", "wahala", "prof", "salle", "junction", "station",
    "boutique", "generator", "générateur",
}

VERB_LEXICON = {
    "drop", "hala", "dey", "go", "come", "waka", "sabi", "spoil", "block",
    "attendre", "payer", "acheter", "vendre", "chercher", "courir", "veux",
    "bloquer", "augmenter", "refuser", "refuse", "tomber", "flood",
}

SLANG_WORDS = {
    "hmmm", "garrr", "zero-zero", "zéro-zéro", "wanda", "ekiee",
    "yo", "eh", "voila", "voilà", "chai", "haba", "sha",
}

# --- Multi-word verb phrases / idioms (matched against the whole sentence,
#     since they don't classify sensibly one token at a time) ---

VERB_PHRASES = [
    r"\bdrop\s+me\b",
    rf"\bhala\s+me\b(?:\s+[\w{COMBINING_MARKS}]+){{0,3}}\s+money\b",
    r"\bdey\s+for\s+front\b",
    r"\bdon\s+spoil\b",
    r"\bdon\s+refuse\b",
    r"\bcome\s+down\b",
    r"\bmove\s+small\b",
]

SLANG_PHRASES = [r"\bje\s+wanda\b"]