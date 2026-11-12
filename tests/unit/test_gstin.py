import random

import pytest

from matcher import gstin

# Publicly cited sample GSTINs that pass the GSTN checksum.
VALID = ["27AAPFU0939F1ZV", "29AAGCB7383J1Z4"]


@pytest.mark.parametrize("g", VALID)
def test_known_valid(g):
    assert gstin.is_valid(g)


def test_one_char_typo_fails_checksum():
    g = "27AAPFU0939F1ZV"
    for i in range(14):
        alt = "A" if g[i] != "A" else "B"
        typo = g[:i] + alt + g[i + 1 :]
        assert not gstin.is_valid(typo), typo


def test_cleans_case_and_spaces():
    assert gstin.is_valid(" 27aapfu0939f1zv ")
    assert gstin.clean(" 27aa pfu0939f1zv") == "27AAPFU0939F1ZV"


@pytest.mark.parametrize("bad", ["", "27AAPFU0939F1Z", "27AAPFU0939F1XV", "AAAAPFU0939F1ZV", None])
def test_bad_format(bad):
    assert not gstin.is_valid(bad)


def test_pan_and_state():
    assert gstin.pan("27AAPFU0939F1ZV") == "AAPFU0939F"
    assert gstin.state_code("27AAPFU0939F1ZV") == "27"


def test_generate_is_valid_and_reproducible():
    a = [gstin.generate(random.Random(7)) for _ in range(3)]
    assert len(set(a)) == 1
    rng = random.Random(1)
    for _ in range(500):
        assert gstin.is_valid(gstin.generate(rng))
    same_pan = gstin.generate(rng, state="29", pan_="AAPFU0939F")
    assert gstin.pan(same_pan) == "AAPFU0939F" and same_pan.startswith("29")
