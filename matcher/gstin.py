"""GSTIN checks. Layout: 2-digit state code, 10-char PAN, entity no, 'Z', check char."""
import random
import re
import string

CHARSET = string.digits + string.ascii_uppercase  # value of a char = its index (base 36)
_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def clean(gstin: str) -> str:
    return re.sub(r"\s+", "", gstin or "").upper()


def check_char(first14: str) -> str:
    """GSTN check char: weights alternate 1,2; products fold to quotient + remainder."""
    total = 0
    for i, ch in enumerate(first14):
        product = CHARSET.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return CHARSET[(36 - total % 36) % 36]


def is_valid(gstin: str) -> bool:
    g = clean(gstin)
    return bool(_PATTERN.match(g)) and check_char(g[:14]) == g[14]


def pan(gstin: str) -> str:
    return clean(gstin)[2:12]


def state_code(gstin: str) -> str:
    return clean(gstin)[:2]


def generate(rng: random.Random, state: str | None = None, pan_: str | None = None) -> str:
    """A random GSTIN that passes is_valid. Used by datagen."""
    state = state or f"{rng.randint(1, 37):02d}"
    if pan_ is None:
        letters = string.ascii_uppercase
        pan_ = (
            "".join(rng.choices(letters, k=3)) + rng.choice("CPHFATBLJG") + rng.choice(letters)
            + f"{rng.randint(0, 9999):04d}" + rng.choice(letters)
        )
    body = f"{state}{pan_}{rng.choice('123456789')}Z"
    return body + check_char(body)
