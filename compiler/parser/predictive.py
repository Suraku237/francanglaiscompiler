"""A bounded LL(1) stack machine; UNKNOWN is never a wildcard."""

from typing import Any

from .grammar import END, EPSILON, TERMINAL_SET

MAX_INPUT_TOKENS = 256
MAX_TOKEN_TEXT_LENGTH = 1_000
MAX_PARSE_STEPS = 2_000
MAX_STACK_SYMBOLS = 1_024


def parse_analysis(analysis: dict[str, Any], tokens: list[dict[str, str]]) -> dict[str, Any]:
    """Parse using an unmodified result of analyze_grammar, without recalculating it.

    Trace snapshots precede their action; the rightmost stack element is its top.
    ``remaining`` contains categories followed by the end marker, never raw words.
    """
    stack = [END, analysis["start_symbol"]]
    categories: list[str] = []
    position = 0
    trace: list[dict[str, Any]] = []

    def record(action: str) -> None:
        trace.append({
            "stack": stack.copy(),
            "remaining": categories[position:] + [END],
            "action": action,
        })

    def reject(error: str) -> dict[str, Any]:
        record("Reject: " + error)
        return {"accepted": False, "error": error, "trace": trace, "consumed": position}

    if not isinstance(tokens, list):
        return reject("Tokens must be a list of dictionaries containing text and category strings.")
    if len(tokens) > MAX_INPUT_TOKENS:
        return reject(f"Input exceeds the {MAX_INPUT_TOKENS}-token limit.")
    for index, token in enumerate(tokens):
        if not isinstance(token, dict) or not isinstance(token.get("text"), str):
            return reject(f"Token {index + 1} must contain a string 'text' field.")
        category = token.get("category")
        if not isinstance(category, str) or category not in TERMINAL_SET:
            return reject(f"Token {index + 1} must contain a valid lexer 'category'.")
        if len(token["text"]) > MAX_TOKEN_TEXT_LENGTH:
            return reject(f"Token {index + 1} exceeds the {MAX_TOKEN_TEXT_LENGTH}-character text limit.")
        categories.append(category)

    if analysis["conflicts"]:
        conflict = analysis["conflicts"][0]
        return reject(
            f"Grammar is not LL(1): table conflict at "
            f"({conflict['nonterminal']}, {conflict['terminal']}). "
            "No conflicting production was selected."
        )
    if not analysis["is_ll1"]:
        return reject("Grammar is not LL(1): unresolved left recursion prevents predictive parsing.")

    table = analysis["table"]
    visited: set[tuple[tuple[str, ...], int]] = set()
    while stack:
        lookahead = categories[position] if position < len(categories) else END
        top = stack[-1]
        if top == END:
            if lookahead != END:
                return reject(f"Unexpected trailing token {lookahead}; expected end of input.")
            record("Accept: input fully consumed.")
            return {"accepted": True, "error": None, "trace": trace, "consumed": position}
        if len(trace) >= MAX_PARSE_STEPS - 1:
            return reject(f"Predictive parse trace limit of {MAX_PARSE_STEPS} steps reached.")
        configuration = (tuple(stack), position)
        if configuration in visited:
            return reject("Predictive parsing made no progress: a repeated stack/input configuration.")
        visited.add(configuration)
        if top in TERMINAL_SET:
            if top != lookahead:
                return reject(f"Expected {top}, found {lookahead} at token {position + 1}.")
            record(f"Match {top}")
            stack.pop()
            position += 1
            continue
        row = table.get(top, {})
        if lookahead not in row:
            expected = ", ".join(sorted(row)) or "no valid lookahead"
            return reject(
                f"No production for {top} with lookahead {lookahead} "
                f"at token {position + 1}; expected: {expected}."
            )
        production = row[lookahead]
        if len(stack) - 1 + len(production) > MAX_STACK_SYMBOLS:
            return reject(f"Predictive parser stack limit of {MAX_STACK_SYMBOLS} symbols reached.")
        record(f"Apply {top} -> {' '.join(production) if production else EPSILON}")
        stack.pop()
        stack.extend(reversed(production))
    return reject("Predictive parser stack ended without matching the end marker.")
