"""User-reviewed vocal substitutions for the synthesis copy only."""
import re

LAUGHTER = re.compile(r'(^|(?<=[.!?…])\s+)(?:teehee|giggles?)(?:[.!?…]+(?=\s|$)|(?=\s*$))', re.I)
GASP = re.compile(r'(^|(?<=[.!?…])\s+)(?P<cue>gasp)(?:[.!?…]+(?=\s|$)|(?=\s*(?:\.{2,}|…|$)))', re.I)
QUOTED = re.compile(r'''"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’|(?<!\w)'(?:[^'\n]|(?<=\w)'(?=\w))*'(?!\w)''')


def breeze_text(text):
    text = LAUGHTER.sub(lambda match: match[1] + '(giggles)', text)
    quotes = [(m.start(), m.end()) for m in QUOTED.finditer(text)]

    def gasp(match):
        if any(start <= match.start('cue') < end for start, end in quotes):
            return match[0]
        return match[1] + '(gasp)'

    return GASP.sub(gasp, text)
