# Francanglais Mini Compiler

A project to recognize **Francanglais** (Camfranglais) — the French/English
(and Pidgin) code-mixed language spoken in Cameroon — by matching input
against a collected dataset and predicting new/unseen Francanglais words
from French + English blending patterns.

## Phase 1 — Dataset Collection (this drop)

`data_collector/app.py` is a CustomTkinter desktop app for building the
dataset yourself.

**Setup**
```bash
cd francanglais_compiler
pip install -r requirements.txt
cd data_collector
python app.py
```

**What it captures per entry**, into `data_collector/dataset.csv`:
- `text` — the Francanglais word / phrase / sentence
- `entry_type` — word, phrase, or sentence
- `french_gloss`, `english_gloss` — standard-language meaning
- `category` — greeting, slang, market/money, school/campus, etc.
- `notes` — free-text context (region, register, usage note)
- `audio_filename` — optional; either recorded live (mic) or attached
  from an existing audio file, saved into `data_collector/audio/`
- `contributor`, `timestamp`

Live recording needs `sounddevice`/`soundfile` and a working mic
backend (PortAudio). If that's not available on your machine, the
"Attach file..." button works with zero extra setup — just point it
at a `.wav`/`.mp3` you already have.

Aim for enough breadth per category (not just volume) — the classifier
and predictor in Phase 2 will lean on `category`, `french_gloss`, and
`english_gloss` as much as on the raw text.

## Phase 2 — Compiler Pipeline (next)

Planned under `compiler/`, built once the dataset has a reasonable
size (roughly 150–300+ entries is a workable starting point):

1. **Lexer** — tokenizes input text into words/morphemes.
2. **Classifier** — for each token: exact/fuzzy match against the
   dataset (edit distance) to tag it French / English / Pidgin /
   known-Francanglais / unknown.
3. **Predictor** — for unknown tokens, a rule-based + statistical
   model trained on the dataset's known French↔English blending
   patterns (e.g. French verb stem + English "-ing"/"-er" morphology,
   common Camfranglais affixes) to guess whether a novel word
   plausibly *is* Francanglais, and what it likely means.
4. **Sentence-level check** — recognizes typical Francanglais
   code-switch structure (which parts of a sentence swap language)
   rather than requiring a fixed grammar.
5. *(Stretch)* **Audio front-end** — speech-to-text (e.g. an offline
   engine like Vosk) transcribes recorded audio, then feeds the same
   text pipeline above.

I'll build this against the actual shape of your collected data once
you've gathered a first batch — the predictor design in particular
should be tuned to whatever patterns show up.