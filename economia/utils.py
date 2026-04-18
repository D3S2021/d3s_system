from decimal import Decimal, InvalidOperation
import re


def safe_int(v, default: int = 0) -> int:
    """
    Convierte cadenas como '2 025', '2,025', '2.025' → 2025.
    Quita todo lo que no sea dígito.
    """
    if v is None:
        return default
    s = str(v).replace("\u00A0", " ")
    digits = re.sub(r"[^0-9]", "", s)
    return int(digits) if digits else default


def to_decimal(x) -> Decimal:
    """Convierte a Decimal tolerando None/str con separadores argentinos o internacionales."""
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    s = str(x).strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")
