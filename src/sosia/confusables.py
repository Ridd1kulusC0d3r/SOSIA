"""Tabelas de caracteres confundíveis.

Duas famílias, tratadas de forma diferente (ver UTS #39):

* ASCII_LOOKALIKES: trocas que continuam válidas em handles (0/o, 1/l, rn/m ...).
* UNICODE_TO_ASCII: Cirílico/Grego/etc. -> ASCII. Usado para *skeleton* (comparação)
  e para variantes de nome de exibição. Skeleton NÃO é normalização do identificador
  nem prova de intenção maliciosa — é só um sinal de semelhança visual.
"""

from __future__ import annotations

# Escapes explícitos para o arquivo ser legível/auditável em qualquer editor.
UNICODE_TO_ASCII: dict[str, str] = {
    # Cirílico minúsculo
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "і": "i", "ј": "j", "ѕ": "s",
    "ԁ": "d", "һ": "h", "ѵ": "v", "ӏ": "l", "ԛ": "q",
    "ԝ": "w",
    # Cirílico maiúsculo
    "А": "a", "В": "b", "Е": "e", "К": "k", "М": "m",
    "Н": "h", "О": "o", "Р": "p", "С": "c", "Т": "t",
    "Х": "x",
    # Grego
    "ο": "o", "α": "a", "ν": "v", "ρ": "p", "ι": "i",
    "Ο": "o", "Α": "a", "Β": "b", "Ε": "e", "Ζ": "z",
    "Η": "h", "Ι": "i", "Κ": "k", "Μ": "m", "Ν": "n",
    "Ρ": "p", "Τ": "t", "Χ": "x", "Υ": "y",
    # Latinos exóticos / símbolos
    "ı": "i", "ɡ": "g", "ᴏ": "o", "ℓ": "l", "ⅼ": "l",
    # Armênio
    "ո": "n", "ս": "u", "օ": "o",
}

# char -> sequências ASCII visualmente próximas (válidas em handles)
ASCII_LOOKALIKES: dict[str, list[str]] = {
    "a": ["4"], "b": ["6", "8"], "e": ["3"], "g": ["9", "q"], "i": ["1", "l", "j"],
    "l": ["1", "i"], "o": ["0"], "s": ["5"], "t": ["7"], "z": ["2"], "q": ["g"],
    "u": ["v"], "v": ["u"],
    # sequências
    "m": ["rn"], "w": ["vv"], "d": ["cl"], "h": ["ln"],
}

# Para o skeleton: sequências -> letra e símbolo -> letra.
FOLD_MULTI: list[tuple[str, str]] = [("rn", "m"), ("vv", "w"), ("cl", "d")]
FOLD_SINGLE: dict[str, str] = {
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "6": "b", "7": "t",
    "8": "b", "9": "g", "2": "z", "i": "l", "|": "l", "!": "l", "$": "s", "@": "a",
}

# char ASCII -> lookalikes Unicode (invertido; usado só para nomes de exibição)
ASCII_TO_UNICODE: dict[str, list[str]] = {}
for _u, _a in UNICODE_TO_ASCII.items():
    if _u.islower() or not _u.isalpha():
        ASCII_TO_UNICODE.setdefault(_a, []).append(_u)
