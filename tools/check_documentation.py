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
TS_NON_CODE = re.compile(
    r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`",
    re.DOTALL,
)
TS_CLASS_DECLARATION = re.compile(
    r"^\s*(?:(?:export|default|abstract)\s+)*class\s+([A-Za-z_$][\w$]*)"
    r"(?=\s*(?:[<{]|extends\b|implements\b))",
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
            factories = {
                alias.asname or alias.name
                for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "collections"
                for alias in node.names if alias.name == "namedtuple"
            }
            collections = {
                alias.asname or alias.name
                for node in tree.body if isinstance(node, ast.Import)
                for alias in node.names if alias.name == "collections"
            }
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.Call):
                    continue
                function = node.value.func
                is_factory = (
                    isinstance(function, ast.Name) and function.id in factories
                ) or (
                    isinstance(function, ast.Attribute) and function.attr == "namedtuple"
                    and isinstance(function.value, ast.Name) and function.value.id in collections
                )
                if is_factory:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    classes.update(f"{module}.{target.id}" for target in targets if isinstance(target, ast.Name))
    for source in (root / "frontend" / "src").rglob("*"):
        if source.suffix not in {".ts", ".tsx"} or source.name.endswith((".d.ts", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
            continue
        relative = source.relative_to(root)
        if set(relative.parts) & {"tests", "__tests__", "node_modules"}:
            continue
        text = TS_NON_CODE.sub(lambda match: "\n" * match[0].count("\n"), source.read_text(encoding="utf-8-sig"))
        module = ".".join(relative.with_suffix("").parts)
        classes.update(f"{module}.{name}" for name in TS_CLASS_DECLARATION.findall(text))
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


def check_sequence_activations(directory: Path) -> int:
    message = re.compile(r"^(\w+)\s*(--?>)\s*(\w+)\s*:")
    activation = re.compile(r"^(activate|deactivate)\s+(\w+)$")
    sources = sorted(directory.glob("sequence-*.puml"))
    for source in sources:
        lines: list[tuple[int, str]] = []
        block_end = ""
        for number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if block_end:
                if line == block_end:
                    block_end = ""
                continue
            if line.startswith("legend"):
                block_end = "endlegend"
            elif line.startswith("note ") and ":" not in line:
                block_end = "end note"
            elif line and not line.startswith("'"):
                lines.append((number, line))
        active: dict[str, int] = {}
        calls: list[tuple[str, str]] = []
        for index, (number, line) in enumerate(lines):
            state = activation.fullmatch(line)
            if state:
                action, name = state.groups()
                active[name] = active.get(name, 0) + (1 if action == "activate" else -1)
                if active[name] < 0:
                    raise ValueError(f"{source.name}:{number}: unbalanced activation for {name}.")
                continue
            arrow = message.match(line)
            if arrow is None:
                continue
            sender, style, receiver = arrow.groups()
            following = lines[index + 1][1] if index + 1 < len(lines) else ""
            if active.get(sender, 0) == 0:
                raise ValueError(f"{source.name}:{number}: sender {sender} has no activation.")
            if style == "->":
                if following != f"activate {receiver}":
                    raise ValueError(f"{source.name}:{number}: call needs receiver activation for {receiver}.")
                calls.append((sender, receiver))
            else:
                if not calls or calls.pop() != (receiver, sender):
                    raise ValueError(f"{source.name}:{number}: reply does not match the outstanding call.")
                if active.get(receiver, 0) == 0 or following != f"deactivate {sender}":
                    raise ValueError(f"{source.name}:{number}: reply must end the callee activation.")
        if calls or any(active.values()):
            raise ValueError(f"{source.name}: unfinished calls or activations.")
    return len(sources)


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
    atlas_source = (docs / "uml-atlas.tex").read_text(encoding="utf-8")
    sheets = re.findall(r"\\umlplate\{([\w-]+)\}", atlas_source)
    placements = re.findall(r"\\diagram\{([\w-]+)\}\{(\d+)\}", sdd_source)
    if len(sheets) != len(referenced) or set(sheets) != referenced or len(placements) != len(sheets):
        raise ValueError("The atlas must contain exactly one sheet per referenced diagram.")
    atlas = PdfReader(docs / "uml-atlas.pdf", strict=True)
    if len(atlas.pages) != len(sheets):
        raise ValueError("The compiled atlas does not have one page per UML sheet.")
    for name, page in placements:
        index = int(page) - 1
        if not 0 <= index < len(sheets) or sheets[index] != name:
            raise ValueError(f"Incorrect atlas page mapping for {name}.")
        embedded = {image_fingerprint(image.image) for image in atlas.pages[index].images if image.image is not None}
        if expected_images[name] not in embedded:
            raise ValueError(f"The atlas sheet for {name} is absent or stale.")
    atlas_problems = BUILD_PROBLEMS.findall((docs / ".build" / "uml-atlas.log").read_text(encoding="utf-8"))
    if atlas_problems:
        raise ValueError(f"The atlas build has layout errors: {atlas_problems[:5]}")
    results: dict[str, object] = {
        "production_classes": classes, "diagrams": len(referenced),
        "sequence_diagrams": check_sequence_activations(docs / "diagrams"),
        "atlas_pages": len(atlas.pages),
    }
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
