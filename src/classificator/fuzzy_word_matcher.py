from __future__ import annotations

MAX_EDIT_DISTANCE = 2
DIACRITICS_MAP = str.maketrans(
    {
        "ă": "a",
        "Ă": "A",
        "â": "a",
        "Â": "A",
        "î": "i",
        "Î": "I",
        "ș": "s",
        "Ș": "S",
        "ț": "t",
        "Ț": "T",
        "ş": "s",
        "Ş": "S",
        "ţ": "t",
        "Ţ": "T",
    }
)


def normalize(text: str) -> str:
    return text.translate(DIACRITICS_MAP).lower()


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ch_a in enumerate(a, start=1):
        curr = [i]
        for j, ch_b in enumerate(b, start=1):
            cost = 0 if ch_a == ch_b else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def matches(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    norm_expected = normalize(expected)
    norm_actual = normalize(actual)
    if norm_expected == norm_actual:
        return True
    if abs(len(norm_expected) - len(norm_actual)) > MAX_EDIT_DISTANCE:
        return False
    return levenshtein(norm_expected, norm_actual) <= MAX_EDIT_DISTANCE
