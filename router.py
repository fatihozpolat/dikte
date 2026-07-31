"""Deciding whether the words themselves are wanted, or something done with them.

Two things can be meant by talking to an assistant, and they need opposite
treatment. "Write this down: we agreed three things today" wants the sentence,
tidied and pasted where the cursor is. "Put that in my calendar on Thursday"
wants the calendar changed and a sentence back about it. Everything hangs on
telling those apart, and getting it wrong is loud in both directions: a note
that never arrives, or an agent asked to carry out a diary entry.

It is a table of openings rather than a question put to a model. Three reasons,
in order of how much they matter:

  * It is instant. A model call here would put a second in front of every
    command, including the ones that are only going to be pasted.
  * It is inspectable. When it gets something wrong the reason is a line that
    can be read, and the fix is a line that can be added.
  * It cannot fail in a new way on a Tuesday.

Only the opening is looked at. "Yaz" at the front of a sentence is an
instruction; "sonra sana yazarım" in the middle of one is not, and a matcher
that went hunting through the whole command would find the second and paste a
message meant for the agent.
"""

import re
import unicodedata

DICTATE = "dictate"
ASK = "ask"

# What somebody says when they want the words. Longest first, so "not al" is
# tried before "not" would be, and each is matched only at the start.
#
# Turkish and English together in one table on purpose: people switch between
# them mid-sentence, and a command in the wrong list is a command that silently
# goes to the agent.
DICTATE_OPENINGS = (
    "metne dok", "metne cevir", "yaziya dok", "yaziya cevir",
    "not al", "not et", "not tut", "notuma ekle",
    "dikte et", "dikte",
    "yazar misin", "yazi ver", "yazdir", "yaz",
    "sunu yaz", "bunu yaz",
    "take a note", "make a note", "note this", "note down",
    "write this down", "write down", "write this", "write",
    "type this out", "type this", "type it", "type",
    "transcribe this", "transcribe", "dictate this", "dictate",
)

# What sits between the instruction and the thing to be written: a colon, a
# comma, "şunu", "ki". Taken off so the note does not begin with punctuation.
_JOINERS = ("sunu", "bunu", "ki", "diye", "that", "this")
_EDGE = re.compile(r"^[\s:,;.\-–—]+|[\s:,;\-–—]+$")


def fold(text):
    """Lower case and strip the accents, so matching is not spelling-sensitive.

    Turkish is the reason this is not str.lower(). The dotted and dotless i are
    different letters, a transcriber picks between them by ear, and "Yazı" and
    "yazi" have to be the same word here or half the openings never match.
    """
    text = (text or "").replace("İ", "i").replace("I", "ı")
    lowered = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(c for c in lowered if not unicodedata.combining(c))
    for source, target in (("ı", "i"), ("ş", "s"), ("ğ", "g"),
                           ("ç", "c"), ("ö", "o"), ("ü", "u")):
        stripped = stripped.replace(source, target)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", stripped)).strip()


def _openings(extra=""):
    """The table, with anything the user added to it."""
    custom = [fold(line) for line in (extra or "").splitlines() if line.strip()]
    table = [fold(entry) for entry in DICTATE_OPENINGS] + custom
    return sorted({entry for entry in table if entry}, key=len, reverse=True)


def route(text, extra=""):
    """(what was meant, what to do it with).

    For a dictation the second value is what should be written, which is empty
    when the instruction was given on its own — "write this down" and then a
    pause, meaning the note is still to come.
    """
    said = (text or "").strip()
    if not said:
        return ASK, ""
    folded = fold(said)
    for opening in _openings(extra):
        if folded == opening:
            return DICTATE, ""
        if folded.startswith(opening + " "):
            return DICTATE, _rest(said, opening)
    return ASK, said


def _rest(said, opening):
    """What is left of the sentence once the instruction has been taken off.

    Counted in words rather than characters: the folded form has lost the
    accents and can be a different length from what was actually said, so an
    offset taken from one does not point at the same place in the other.
    """
    words = said.split()
    taken = len(opening.split())
    rest = words[taken:]
    while rest and fold(rest[0]) in _JOINERS:
        rest = rest[1:]
    return _EDGE.sub("", " ".join(rest))


def looks_like_dictation(text, extra=""):
    return route(text, extra)[0] == DICTATE
