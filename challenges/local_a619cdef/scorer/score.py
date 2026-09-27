"""Conservative abc challenge-rubric scorer; executed by the owned sandbox.

The H1 Bohrium Job used the same deterministic 64-bit primality witnesses and
100-digit Decimal quality calculation. Larger claims fail without a numeric
score here, rather than turning an unverified result into a false zero.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import zipfile
from decimal import Decimal, localcontext
from pathlib import Path

_MR_BASES = (2, 325, 9375, 28178, 450775, 9780504, 1795265022)
_RECORD_C, _RECORD_RAD = 6436343, 15042
_SECOND_C, _SECOND_RAD = 4375, 210


class Unverified(ValueError):
    """The local scorer cannot establish a numeric scientific result."""


class Invalid(ValueError):
    """A claim definitively violates a stated challenge check."""


def _decimal_int(value: object, label: str, limit: int) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise Invalid(f"{label}: expected decimal string")
    if len(value) > limit:
        raise Invalid(f"{label}: challenge digit limit exceeded")
    if len(value) > 4300:
        raise Unverified(f"{label}: local conversion limit exceeded")
    number = int(value)
    if number < 1:
        raise Invalid(f"{label}: must be positive")
    return number


def _prime64(number: int) -> bool:
    if number < 2:
        return False
    for prime in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if number % prime == 0:
            return number == prime
    remainder = number - 1
    halves = 0
    while remainder % 2 == 0:
        remainder //= 2
        halves += 1
    for witness in _MR_BASES:
        witness %= number
        if not witness:
            continue
        residue = pow(witness, remainder, number)
        if residue in (1, number - 1):
            continue
        for _ in range(halves - 1):
            residue = pow(residue, 2, number)
            if residue == number - 1:
                break
        else:
            return False
    return True


def _factors(claim: object, number: int, label: str) -> set[int]:
    if not isinstance(claim, dict):
        raise Invalid(f"{label}: factorization must be an object")
    product = 1
    bases: set[int] = set()
    for raw_base, exponent in claim.items():
        base = _decimal_int(raw_base, f"{label} base", 10000)
        if base < 2:
            raise Invalid(f"{label}: base is not prime")
        if base >= 2**64:
            raise Unverified(f"{label}: primality beyond deterministic 64-bit scope")
        if not _prime64(base):
            raise Invalid(f"{label}: composite claimed base")
        if type(exponent) is not int or exponent < 1:
            raise Invalid(f"{label}: exponent must be a positive integer")
        if base in bases:
            raise Invalid(f"{label}: duplicate prime base")
        bases.add(base)
        if exponent * (base.bit_length() - 1) > number.bit_length() + 1:
            raise Invalid(f"{label}: factor product exceeds number")
        product *= pow(base, exponent)
        if product > number:
            raise Invalid(f"{label}: factor product exceeds number")
    if product != number:
        raise Invalid(f"{label}: factor product mismatch")
    return bases


def _quality(c: int, radical: int) -> Decimal:
    if radical <= 1:
        raise Invalid("radical must exceed one")
    with localcontext() as context:
        context.prec = 100
        return +(Decimal(c).ln() / Decimal(radical).ln())


def _strictly_above(c: int, radical: int, threshold_c: int,
                    threshold_radical: int, quality: Decimal) -> bool:
    if c == threshold_c and radical == threshold_radical:
        return False
    boundary = _quality(threshold_c, threshold_radical)
    if abs(quality - boundary) <= Decimal("1e-50"):
        raise Unverified("quality too close to threshold at local precision")
    return quality > boundary


def evaluate(triple: object, scorer_version: str) -> dict:
    try:
        if not isinstance(triple, dict):
            raise Invalid("triple must be an object")
        a = _decimal_int(triple.get("a"), "a", 100000)
        b = _decimal_int(triple.get("b"), "b", 100000)
        c = _decimal_int(triple.get("c"), "c", 100000)
        if a + b != c:
            raise Invalid("a + b != c")
        if math.gcd(a, b) != 1:
            raise Invalid("gcd(a,b) != 1")
        bases: set[int] = set()
        for name, value in (("a", a), ("b", b), ("c", c)):
            bases.update(_factors(triple.get(name + "_factorization"), value, name))
        radical = math.prod(bases)
        quality = _quality(c, radical)
        if _strictly_above(c, radical, _RECORD_C, _RECORD_RAD, quality):
            score = 100
        elif _strictly_above(c, radical, _SECOND_C, _SECOND_RAD, quality):
            score = 20
        elif abs(quality - Decimal("1.40")) <= Decimal("1e-50"):
            raise Unverified("quality too close to 1.40 at local precision")
        elif quality > Decimal("1.40"):
            score = 10
        elif radical < c:
            score = 5
        else:
            score = 0
        return {"score": score,
                "components": {"valid_triple": True, "radical": str(radical),
                               "quality": str(quality), "rubric_tier": score},
                "confidence": "medium",
                "notes": "Challenge rubric only; platform currently uses generic ARM scoring. "
                         "Claimed prime bases were deterministically checked below 2^64.",
                "scorer_version": scorer_version}
    except Invalid as exc:
        return {"score": 0, "components": {"valid_triple": False,
                                           "reason": str(exc)},
                "confidence": "high", "notes": "Definitive challenge-check failure",
                "scorer_version": scorer_version}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: score.py science_package.zip")
    version = os.environ["CS_SCORER_VERSION"]
    with zipfile.ZipFile(Path(sys.argv[1])) as archive:
        info = archive.getinfo("outputs/triple.json")
        if info.file_size > 1_000_000:
            raise Unverified("triple.json exceeds local scorer input limit")
        triple = json.loads(archive.read(info))
    print(json.dumps(evaluate(triple, version), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
