# Grammar


## Raw grammar as first drafted

```
Start -> Utterance
Utterance -> Utterance CONJ Utterance | Utterance PUNCT Utterance | Openers Clause
Openers -> Openers INTERJ | Openers PART | eps
Clause -> NP Predicate | NP | QWORD NP Predicate | QWORD Predicate | MAKE Clause | COP Comp | VG | eps
Predicate -> COP Comp | COP | VG | ADJ Args | PP Args | ADV Args
Comp -> ADJ Args | Args
VG -> NEG VG | TMA VG | VERB Args
Args -> Args NP | Args PP | Args ADV | Args PART | eps
PP -> PREP NP
NP -> PRON | DET AdjList NHead | DET AdjList | POSS AdjList NHead | NUM AdjList NHead | NHead
NHead -> NOUN | UNKNOWN
AdjList -> AdjList ADJ | AdjList NUM | eps
```

## After left-recursion removal

- removed immediate left recursion on Utterance (new symbol Utterance')
- removed immediate left recursion on Openers (new symbol Openers')
- removed immediate left recursion on Args (new symbol Args')
- removed immediate left recursion on AdjList (new symbol AdjList')
- substituted PP into Args'
- substituted NP into Args'
- substituted NHead into Args'

```
Start -> Utterance
Utterance -> Openers Clause Utterance'
Openers -> Openers'
Clause -> NP Predicate | NP | QWORD NP Predicate | QWORD Predicate | MAKE Clause | COP Comp | VG | eps
Predicate -> COP Comp | COP | VG | ADJ Args | PP Args | ADV Args
Comp -> ADJ Args | Args
VG -> NEG VG | TMA VG | VERB Args
Args -> Args'
PP -> PREP NP
NP -> PRON | DET AdjList NHead | DET AdjList | POSS AdjList NHead | NUM AdjList NHead | NHead
NHead -> NOUN | UNKNOWN
AdjList -> AdjList'
Utterance' -> CONJ Utterance Utterance' | PUNCT Utterance Utterance' | eps
Openers' -> INTERJ Openers' | PART Openers' | eps
Args' -> PRON Args' | DET AdjList NHead Args' | DET AdjList Args' | POSS AdjList NHead Args' | NUM AdjList NHead Args' | NOUN Args' | UNKNOWN Args' | PREP NP Args' | ADV Args' | PART Args' | eps
AdjList' -> ADJ AdjList' | NUM AdjList' | eps
```

## After left factoring

- factored Clause: common prefix 'NP' -> Clause'
- factored Predicate: common prefix 'COP' -> Predicate'
- factored NP: common prefix 'DET AdjList' -> NP'
- factored Args': common prefix 'DET AdjList' -> Args''
- factored Clause: common prefix 'QWORD' -> Clause''

```
Start -> Utterance
Utterance -> Openers Clause Utterance'
Openers -> Openers'
Clause -> MAKE Clause | COP Comp | VG | eps | NP Clause' | QWORD Clause''
Predicate -> VG | ADJ Args | PP Args | ADV Args | COP Predicate'
Comp -> ADJ Args | Args
VG -> NEG VG | TMA VG | VERB Args
Args -> Args'
PP -> PREP NP
NP -> PRON | POSS AdjList NHead | NUM AdjList NHead | NHead | DET AdjList NP'
NHead -> NOUN | UNKNOWN
AdjList -> AdjList'
Utterance' -> CONJ Utterance Utterance' | PUNCT Utterance Utterance' | eps
Openers' -> INTERJ Openers' | PART Openers' | eps
Args' -> PRON Args' | POSS AdjList NHead Args' | NUM AdjList NHead Args' | NOUN Args' | UNKNOWN Args' | PREP NP Args' | ADV Args' | PART Args' | eps | DET AdjList Args''
AdjList' -> ADJ AdjList' | NUM AdjList' | eps
Clause' -> Predicate | eps
Predicate' -> Comp | eps
NP' -> NHead | eps
Args'' -> NHead Args' | Args'
Clause'' -> NP Predicate | Predicate
```

## Final LL(1) grammar used by the parser

```
Start -> Utterance
Utterance -> Openers Clause Rest
Openers -> INTERJ Openers | PART Openers | eps
Rest -> CONJ Utterance | PUNCT Utterance | eps
Clause -> QWORD QClause | MAKE Clause | NP Predicate | VG | eps
QClause -> NP Predicate | Predicate
Predicate -> VG | ADJ Args | PP Args | ADV Args | eps
Comp -> Args
VG -> NEG VG | TMA VG | VERB Args | COP Comp
Args -> NP Args | PP Args | ADV Args | ADJ Args | PART Args | VG | eps
PP -> PREP NP
NP -> PRON | DET AdjList NHead | POSS AdjList NHead | NUM AdjList NHead | NHead
NHead -> NOUN Plur | UNKNOWN Plur
Plur -> PLUR | eps
AdjList -> ADJ AdjList | NUM AdjList | eps
```
