"""
Runs the lexical analyzer over the collected dataset (or a small built-in
placeholder set if dataset.csv is still empty) and writes:
  - output/token_table.csv      : every token from every sentence, tagged
  - output/frequency_report.csv : token frequency counts, most common first
  - a printed summary to the console

Run from the project root:
    python compiler/run_lexer.py
"""

import os
import sys
import csv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data_collector"))
sys.path.insert(0, os.path.dirname(__file__))

import dataset  # from data_collector
from lexer import tokenizer, frequency
from lexer.learned import build_lexicon

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Placeholder sentences — used ONLY if dataset.csv is still empty, so the
# pipeline is runnable before real data collection is finished. REPLACE
# with your group's real collected statements as soon as you have them;
# these are not a substitute for the assignment's data collection step.
SAMPLE_SENTENCES = [
    ("Le taxi don refuse for carry me go quartier", "taxi/commuting"),
    ("Wetin dey happen with this internet, network don spoil again", "internet connectivity"),
    ("Courant don go since this morning, on doit chercher generator", "electricity supply"),
    ("Patron, baissez le prix small, je n'ai pas assez d'argent", "market bargaining"),
    ("La pluie don tombe trop, tout le quartier don flood", "rainy season"),
    ("Il n'y a plus d'essence for station, tout le monde dey queue", "fuel scarcity"),
    ("Boutique man say il va augmenter le prix demain", "roadside business"),
    ("Bendskin man, drop me for junction abeg", "bendskin communication"),
    ("Gendarme don bloquer la route pour checkpoint", "security checkpoint"),
    ("Etudiants dey wait for prof for salle B", "campus life"),
]


def load_dataset_texts():
    entries = dataset.load_all()
    if entries:
        return [(e["text"], e.get("category", "")) for e in entries if e.get("text")]
    print("dataset.csv is empty — using built-in placeholder sentences for now.")
    print("Replace these with your group's real collected data as soon as you have it.\n")
    return SAMPLE_SENTENCES


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    texts = load_dataset_texts()
    learned = build_lexicon(dataset.load_all())

    all_tokens = []
    token_rows = []
    code_mixed_count = 0
    verb_phrase_count = 0

    for text, category in texts:
        result = tokenizer.analyze_sentence(text, learned)
        all_tokens.extend(result["tokens"])
        for tok in result["tokens"]:
            token_rows.append({
                "sentence": text, "category": category,
                "token": tok.text, "token_category": tok.category,
            })
        code_mixed_count += len(result["code_mixed_spans"])
        verb_phrase_count += len(result["verb_phrases"])

    # --- token table ---
    token_table_path = os.path.join(OUTPUT_DIR, "token_table.csv")
    with open(token_table_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sentence", "category", "token", "token_category"])
        writer.writeheader()
        writer.writerows(token_rows)

    # --- frequency report ---
    by_text, by_category = frequency.compute_frequencies(all_tokens)
    freq_path = os.path.join(OUTPUT_DIR, "frequency_report.csv")
    with open(freq_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["token", "count"])
        for tok, count in by_text.most_common():
            writer.writerow([tok, count])

    # --- console summary ---
    print(f"Sentences analyzed: {len(texts)}")
    print(f"Total tokens: {len(all_tokens)}")
    print(f"Code-mixed spans detected: {code_mixed_count}")
    print(f"Known verb phrases detected: {verb_phrase_count}\n")
    print("Tokens by category:")
    for cat, count in by_category.most_common():
        print(f"  {cat:<24} {count}")
    print("\nTop 15 most frequent tokens:")
    for tok, count in by_text.most_common(15):
        print(f"  {tok:<20} {count}")
    print(f"\nWrote: {token_table_path}")
    print(f"Wrote: {freq_path}")


if __name__ == "__main__":
    main()