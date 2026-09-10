from __future__ import annotations

import re
from fractions import Fraction


class AnswerCheckError(ValueError):
    pass


_SPACES = re.compile(r"\s+")
_AND_SPLIT = re.compile(r"\s*(?:,|;|/|\bи\b|\band\b)\s*", re.IGNORECASE)


def _normalize_text(raw: str) -> str:
    text = raw.strip().lower().replace("ё", "е")
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace(",", ".")
    text = _SPACES.sub(" ", text)
    return text


def _parse_number(token: str) -> Fraction:
    token = token.strip().lower().replace(" ", "")
    token = token.replace("−", "-")
    if not token:
        raise AnswerCheckError("empty")
    if token.startswith("x="):
        token = token[2:]
    mixed = re.fullmatch(r"(-?\d+)[_.](\d+)/(\d+)", token)
    if mixed:
        whole, num, den = mixed.groups()
        sign = -1 if whole.startswith("-") else 1
        return sign * (abs(int(whole)) + Fraction(int(num), int(den)))
    if "/" in token:
        left, right = token.split("/", 1)
        return Fraction(left) / Fraction(right)
    if re.fullmatch(r"-?\d+(\.\d+)?", token):
        return Fraction(token)
    raise AnswerCheckError(token)


def _parse_number_list(raw: str) -> set[Fraction]:
    text = _normalize_text(raw)
    text = re.sub(r"^[xа-яa-z=\s:]+", "", text)
    parts = [p for p in _AND_SPLIT.split(text) if p]
    if not parts:
        raise AnswerCheckError("empty list")
    return {_parse_number(part) for part in parts}


def check_answer(answer_type: str, expected: str, submitted: str) -> bool:
    kind = answer_type.strip().lower()
    try:
        if kind in {"number", "fraction"}:
            return _parse_number(_normalize_text(submitted)) == _parse_number(
                _normalize_text(expected)
            )
        if kind == "numbers":
            return _parse_number_list(submitted) == _parse_number_list(expected)
        if kind in {"text", "choice"}:
            return _normalize_text(submitted) == _normalize_text(expected)
    except (AnswerCheckError, ValueError, ZeroDivisionError):
        return False
    return _normalize_text(submitted) == _normalize_text(expected)
