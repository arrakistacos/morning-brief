#!/usr/bin/env python3
"""
quotes.py — Stoic line of the day. Salvaged from the old brief's email helper
and extended toward the virtues this strategy actually asks for: patience,
sitting on your hands, respecting the stop, and not arguing with the tape.

Deterministic per date, so a re-run of the same session shows the same line.
"""

from __future__ import annotations

import hashlib
from datetime import date

QUOTES: list[tuple[str, str]] = [
    ("The impediment to action advances action. What stands in the way becomes the way.",
     "Marcus Aurelius — Meditations"),
    ("You have power over your mind, not outside events. Realize this, and you will find strength.",
     "Marcus Aurelius — Meditations"),
    ("We suffer more often in imagination than in reality.", "Seneca — Letters"),
    ("He suffers more than necessary, who suffers before it is necessary.", "Seneca — Letters"),
    ("Luck is what happens when preparation meets opportunity.", "Seneca"),
    ("Make the best use of what is in your power, and take the rest as it happens.",
     "Epictetus — Discourses"),
    ("If it is not right, do not do it; if it is not true, do not say it.",
     "Marcus Aurelius — Meditations"),
    ("First say to yourself what you would be; and then do what you have to do.",
     "Epictetus — Discourses"),
    ("It is not the man who has too little, but the man who craves more, that is poor.",
     "Seneca — Letters"),
    ("No man is free who is not master of himself.", "Epictetus"),
    ("Receive without pride, let go without attachment.", "Marcus Aurelius — Meditations"),
    ("Begin at once to live, and count each separate day as a separate life.",
     "Seneca — Letters"),
    ("The best revenge is not to be like your enemy.", "Marcus Aurelius — Meditations"),
    ("Wealth consists not in having great possessions, but in having few wants.", "Epictetus"),
    ("Nothing happens to any man that he is not formed by nature to bear.",
     "Marcus Aurelius — Meditations"),
    ("Do not explain your philosophy. Embody it.", "Epictetus"),
    ("He who is brave is free.", "Seneca"),
    ("Confine yourself to the present.", "Marcus Aurelius — Meditations"),
    ("Difficulties strengthen the mind, as labor does the body.", "Seneca"),
    ("Attach yourself to what is spiritually superior, regardless of what other people think.",
     "Epictetus — Discourses"),
]


def quote_for(day: date) -> tuple[str, str]:
    idx = int(hashlib.md5(day.isoformat().encode()).hexdigest(), 16) % len(QUOTES)
    return QUOTES[idx]
