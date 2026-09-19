"""Check production-class coverage, rendered figures and the published PDFs."""

import argparse
import ast
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PyPdfError

ROOT = Path(__file__).resolve().parents[1]
CLASS_DECLARATION = re.compile(
    r'^\s*(?:abstract\s+)?class\s+(?:"([^"]+)"|([A-Za-z_][\w.]*))',
    re.MULTILINE,
)
BUILD_PROBLEMS = re.compile(
    r"^!|LaTeX Error|LaTeX Warning|undefined references|Missing character:|"
    r"(?:Overfull|Underfull) \\[hv]box",
    re.MULTILINE,
)


def application_classes(root: Path) -> set[str]:
    classes: set[str] = set()
    for package in ("backend", "compiler", "data_collector"):
        for source in (root / package).rglob("*.py"):
            relative = source.relative_to(root)
            if set(relative.parts) & {"tests", "__pycache__", ".venv", "venv", "node_modules"}:
                continue
            if package == "data_collector" and relative.parts[1] in {"audio", "coursework"}:
                continue
            parts = list(relative.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            module = ".".join(parts)
            tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
            classes.update(f"{module}.{node.name}" for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    return classes


def declared_classes(source: str) -> set[str]:
    source = re.sub(r"/'.*?'/", "", source, flags=re.DOTALL)
    names = set()
    for match in CLASS_DECLARATION.finditer(source):
        name = match.group(1) or match.group(2)
        names.add(name.split("\\n", 1)[0].split(".")[-1])
    return names


def check_class_coverage(root: Path) -> int:
    directory = root / "docs" / "diagrams"
    inventory = json.loads((directory / "class-coverage.json").read_text(encoding="utf-8"))
    if not isinstance(inventory, dict):
        raise ValueError("The class-coverage inventory must map qualified classes to diagram lists.")
    expected = application_classes(root)
    if set(inventory) != expected:
        raise ValueError(
            f"Class inventory mismatch; missing={sorted(expected - set(inventory))}, "
            f"obsolete={sorted(set(inventory) - expected)}."
        )
    diagrams: dict[str, set[str]] = {}
    for qualified, views in inventory.items():
        if not isinstance(views, list) or not views:
            raise ValueError(f"No class diagram is recorded for {qualified}.")
        for name in views:
            if not isinstance(name, str) or re.fullmatch(r"[\w-]+(?:\.puml)?", name) is None:
                raise ValueError(f"Invalid diagram basename for {qualified}.")
            stem = name.removesuffix(".puml")
            if stem not in diagrams:
                diagrams[stem] = declared_classes((directory / f"{stem}.puml").read_text(encoding="utf-8"))
            if qualified.rsplit(".", 1)[1] not in diagrams[stem]:
                raise ValueError(f"{qualified} is not declared as a class in {stem}.puml.")
    return len(expected)


def image_fingerprint(image: Image.Image) -> str:
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    normalized = Image.alpha_composite(background, rgba).convert("RGB")
    digest = hashlib.sha256(f"{normalized.width}x{normalized.height}:RGB:".encode("ascii"))
    digest.update(normalized.tobytes())
    return digest.hexdigest()


def verify_documents(root: Path) -> dict[str, object]:
    docs = root / "docs"
    classes = check_class_coverage(root)
    sdd_source = (docs / "sdd.tex").read_text(encoding="utf-8")
    referenced = set(re.findall(r"\\diagram\{([\w-]+)\}", sdd_source))
    sources = {path.stem for path in (docs / "diagrams").glob("*.puml")}
    if not referenced or referenced != sources:
        raise ValueError(
            f"Diagram/source reference mismatch; unused sources={sorted(sources - referenced)}, "
            f"missing sources={sorted(referenced - sources)}."
        )
    expected_images = {}
    for name in sorted(referenced):
        with Image.open(docs / "diagrams" / f"{name}.png") as image:
            expected_images[name] = image_fingerprint(image)
    results: dict[str, object] = {"production_classes": classes, "diagrams": len(referenced)}
    for stem, title in (
        ("srs", "Software Requirements Specification"),
        ("sdd", "Software Design Description"),
    ):
        reader = PdfReader(docs / f"{stem}.pdf", strict=True)
        text = " ".join(unicodedata.normalize(
            "NFKC", "\n".join(page.extract_text() or "" for page in reader.pages),
        ).split())
        if title not in text or not reader.pages:
            raise ValueError(f"The published {stem.upper()} is empty or has an unexpected title.")
        if "??" in text:
            raise ValueError(f"The published {stem.upper()} contains unresolved-reference markers.")
        log = docs / ".build" / f"{stem}.log"
        problems = BUILD_PROBLEMS.findall(log.read_text(encoding="utf-8", errors="replace"))
        if problems:
            raise ValueError(f"The {stem.upper()} build log contains layout/reference errors: {problems[:5]}")
        results[f"{stem}_pages"] = len(reader.pages)
        if stem == "sdd":
            embedded = {
                image_fingerprint(image.image)
                for page in reader.pages for image in page.images
                if image.image is not None
            }
            missing = [name for name, digest in expected_images.items() if digest not in embedded]
            if missing:
                raise ValueError(f"Current rendered diagrams are absent or stale in the SDD PDF: {missing}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = verify_documents(args.root)
    except (OSError, ValueError, SyntaxError, PyPdfError) as exc:
        parser.exit(1, f"Documentation verification failed: {exc}\n")
    print(json.dumps({"verified": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
