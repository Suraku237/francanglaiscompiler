"""A constrained category-level grammar derived from the group's supplied corpus."""

GRAMMAR = """# Yaounde collected-sentence grammar; original wording is never corrected.
# Category acceptance is not a claim of standard French or authentic fieldwork.
# UNKNOWN is deliberately excluded; n'ais and alli still need human review.
Utterance -> Clause | Clause PUNCTUATION
Clause -> FRENCH_FUNCTION_WORD SubjectTail | Nominal BareSubjectTail | VERB PredicateTail
SubjectTail -> VERB PredicateTail | Nominal VERB PredicateTail | AMBIGUOUS PIDGIN_MARKER ComplementTail
BareSubjectTail -> VERB PredicateTail | FRENCH_FUNCTION_WORD SubjectTail
PredicateTail -> VERB PredicateTail | ENGLISH_FUNCTION_WORD VERB PredicateTail | ADJECTIVE ComplementTail | AMBIGUOUS ComplementTail | ADVERB AdverbTail | Nominal ComplementTail | FRENCH_FUNCTION_WORD LinkedPhrase | PIDGIN_MARKER ComplementTail | epsilon
LinkedPhrase -> VERB PredicateTail | Nominal ComplementTail | AMBIGUOUS ComplementTail | ADVERB AdverbTail | FRENCH_FUNCTION_WORD ModifiedNominal
ModifiedNominal -> Nominal ComplementTail | AMBIGUOUS ComplementTail | ADVERB AdverbTail
AdverbTail -> Nominal ComplementTail | AMBIGUOUS ComplementTail | FRENCH_FUNCTION_WORD LinkedPhrase | VERB PredicateTail | epsilon
ComplementTail -> FRENCH_FUNCTION_WORD LinkedPhrase | VERB PredicateTail | epsilon
Nominal -> Nominal NOUN | NOUN
"""

RATIONALE = (
    "The 12 supplied transcriptions motivate reusable category structures rather than "
    "a list of accepted sentences. Clause accepts a French-function-word subject, "
    "a nominal subject or vocative, or a verb-initial imperative/contracted auxiliary. "
    "SubjectTail covers je suis, mon combi came, and the ca me chop pronominal/Pidgin pattern. "
    "PredicateTail covers auxiliary/serial verbs (j'ai mban, go nang), a function-word "
    "verb link (the observed Ont a cote categories), and nominal, adjectival, adverbial "
    "or ambiguous complements. LinkedPhrase distinguishes a following subject-plus-verb "
    "from an introduced nominal/adverbial group, for example je go, au piol, depuis bayar "
    "and depuis le shap. ComplementTail permits observed juxtaposed clauses and imperatives, "
    "such as je suis kass je go nang and go au piol shoua mes kako. AdverbTail supports "
    "flop le kongossa and the sharp man category pattern. Nominal models noun clusters; "
    "its natural left recursion is removed by the existing transformation algorithm. "
    "Utterance has an optional single punctuation token; its shared Clause prefix is "
    "left-factored. FIRST/FOLLOW and the LL(1) table are calculated from the resulting "
    "grammar, not hard-coded. Empty input, noun-only fragments, dangling function words, "
    "unsupported category orders and UNKNOWN tokens are rejected."
)

LIMITATIONS = (
    "This is a small CFG of lexer categories, not a full grammar of Camfranglais. "
    "FRENCH_FUNCTION_WORD merges pronouns, determiners and prepositions; "
    "PIDGIN_MARKER includes both discourse words and chop; AMBIGUOUS retains conflicting "
    "supplied parts of speech. The existing a/do/tchop classifications are not overwritten "
    "to force a parse. Thus Ont a cote or J'ai n'est may fit category rules without being "
    "standard French, and some other meaningful statements will fall outside the grammar. "
    "AMBIGUOUS is allowed only in specified subject/complement positions, never as a wildcard. "
    "No spelling is repaired and UNKNOWN is not an allowed terminal: n'ais and alli remain "
    "unresolved, so their original sentences reject. A lexical or CFG verdict cannot "
    "establish meaning, pronunciation, speaker identity, consent or fieldwork authenticity."
)
