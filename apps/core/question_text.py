"""Operate on question wording without rewriting quoted filter literals."""
import re

_QUOTED = re.compile(r"""('(?:''|[^'])*'|"(?:""|[^"])*"|‘[^’]*’|“[^”]*”)""")


def unquoted_question(text: str) -> str:
    return _QUOTED.sub(" ", text)


def replace_outside_literals(text: str, pattern: str, replacement: str) -> str:
    return "".join(segment if index % 2 else re.sub(pattern, replacement, segment, flags=re.I)
                   for index, segment in enumerate(_QUOTED.split(text)))
