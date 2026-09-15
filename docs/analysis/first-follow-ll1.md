# FIRST, FOLLOW and the LL(1) parsing table

## FIRST / FOLLOW

| non-terminal | nullable | FIRST | FOLLOW |
|---|---|---|---|
| Start | yes | CONJ COP DET INTERJ MAKE NEG NOUN NUM PART POSS PRON PUNCT QWORD TMA UNKNOWN VERB | $ |
| Utterance | yes | CONJ COP DET INTERJ MAKE NEG NOUN NUM PART POSS PRON PUNCT QWORD TMA UNKNOWN VERB | $ |
| Openers | yes | INTERJ PART | $ CONJ COP DET MAKE NEG NOUN NUM POSS PRON PUNCT QWORD TMA UNKNOWN VERB |
| Rest | yes | CONJ PUNCT | $ |
| Clause | yes | COP DET MAKE NEG NOUN NUM POSS PRON QWORD TMA UNKNOWN VERB | $ CONJ PUNCT |
| QClause | yes | ADJ ADV COP DET NEG NOUN NUM POSS PREP PRON TMA UNKNOWN VERB | $ CONJ PUNCT |
| Predicate | yes | ADJ ADV COP NEG PREP TMA VERB | $ CONJ PUNCT |
| Comp | yes | ADJ ADV COP DET NEG NOUN NUM PART POSS PREP PRON TMA UNKNOWN VERB | $ CONJ PUNCT |
| VG | no | COP NEG TMA VERB | $ CONJ PUNCT |
| Args | yes | ADJ ADV COP DET NEG NOUN NUM PART POSS PREP PRON TMA UNKNOWN VERB | $ CONJ PUNCT |
| PP | no | PREP | $ ADJ ADV CONJ COP DET NEG NOUN NUM PART POSS PREP PRON PUNCT TMA UNKNOWN VERB |
| NP | no | DET NOUN NUM POSS PRON UNKNOWN | $ ADJ ADV CONJ COP DET NEG NOUN NUM PART POSS PREP PRON PUNCT TMA UNKNOWN VERB |
| NHead | no | NOUN UNKNOWN | $ ADJ ADV CONJ COP DET NEG NOUN NUM PART POSS PREP PRON PUNCT TMA UNKNOWN VERB |
| Plur | yes | PLUR | $ ADJ ADV CONJ COP DET NEG NOUN NUM PART POSS PREP PRON PUNCT TMA UNKNOWN VERB |
| AdjList | yes | ADJ NUM | NOUN UNKNOWN |

## LL(1) table M[A, a]

| M[A,a] | $ | ADJ | ADV | CONJ | COP | DET | INTERJ | MAKE | NEG | NOUN | NUM | PART | PLUR | POSS | PREP | PRON | PUNCT | QWORD | TMA | UNKNOWN | VERB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Start | Utterance |  |  | Utterance | Utterance | Utterance | Utterance | Utterance | Utterance | Utterance | Utterance | Utterance |  | Utterance |  | Utterance | Utterance | Utterance | Utterance | Utterance | Utterance |
| Utterance | Openers Clause Rest |  |  | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest |  | Openers Clause Rest |  | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest | Openers Clause Rest |
| Openers | eps |  |  | eps | eps | eps | INTERJ Openers | eps | eps | eps | eps | PART Openers |  | eps |  | eps | eps | eps | eps | eps | eps |
| Rest | eps |  |  | CONJ Utterance |  |  |  |  |  |  |  |  |  |  |  |  | PUNCT Utterance |  |  |  |  |
| Clause | eps |  |  | eps | VG | NP Predicate |  | MAKE Clause | VG | NP Predicate | NP Predicate |  |  | NP Predicate |  | NP Predicate | eps | QWORD QClause | VG | NP Predicate | VG |
| QClause | Predicate | Predicate | Predicate | Predicate | Predicate | NP Predicate |  |  | Predicate | NP Predicate | NP Predicate |  |  | NP Predicate | Predicate | NP Predicate | Predicate |  | Predicate | NP Predicate | Predicate |
| Predicate | eps | ADJ Args | ADV Args | eps | VG |  |  |  | VG |  |  |  |  |  | PP Args |  | eps |  | VG |  | VG |
| Comp | Args | Args | Args | Args | Args | Args |  |  | Args | Args | Args | Args |  | Args | Args | Args | Args |  | Args | Args | Args |
| VG |  |  |  |  | COP Comp |  |  |  | NEG VG |  |  |  |  |  |  |  |  |  | TMA VG |  | VERB Args |
| Args | eps | ADJ Args | ADV Args | eps | VG | NP Args |  |  | VG | NP Args | NP Args | PART Args |  | NP Args | PP Args | NP Args | eps |  | VG | NP Args | VG |
| PP |  |  |  |  |  |  |  |  |  |  |  |  |  |  | PREP NP |  |  |  |  |  |  |
| NP |  |  |  |  |  | DET AdjList NHead |  |  |  | NHead | NUM AdjList NHead |  |  | POSS AdjList NHead |  | PRON |  |  |  | NHead |  |
| NHead |  |  |  |  |  |  |  |  |  | NOUN Plur |  |  |  |  |  |  |  |  |  | UNKNOWN Plur |  |
| Plur | eps | eps | eps | eps | eps | eps |  |  | eps | eps | eps | eps | PLUR | eps | eps | eps | eps |  | eps | eps | eps |
| AdjList |  | ADJ AdjList |  |  |  |  |  |  |  | eps | NUM AdjList |  |  |  |  |  |  |  |  | eps |  |

Conflicts: 0

