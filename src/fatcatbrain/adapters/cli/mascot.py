"""The fat cat mascot as a presentation adapter.

The mascot is deliberately *not* part of the domain. It only turns domain facts
into playful strings, so it can be swapped or muted without touching logic.

The cat changes face depending on the situation, which makes it feel alive.
"""

from __future__ import annotations

from fatcatbrain.domain.models import MemoryCandidate, MemoryItem

# ASCII cat faces, one per mood. The trailing backslash on some faces is escaped.
FACE_CURIOUS = "/ᐠ｡ꞈ｡ᐟ\\"        # sniffing / found something / project detected
FACE_IDLE = "/ᐠ - ˕ -マ"          # sleepy / nothing to do
FACE_HAPPY = "/ᐠ≽^•⩊•^≼マ"        # success
FACE_SUSPICIOUS = "/ᐠಠ_ಠᐟ\\"      # sensitive / needs review / discarded
FACE_WORKING = "/ᐠ•ꞈ•ᐟ\\"        # thinking


def _say(face: str, message: str) -> str:
    return f"{face}  {message}"


class MascotRenderer:
    """Renders cat-flavoured messages for CLI output."""

    def greeting(self) -> str:
        return _say(FACE_CURIOUS, "fatcatbrain at your service.")

    def ask(self, text: str) -> str:
        return _say(FACE_CURIOUS, text)

    def info(self, text: str) -> str:
        return _say(FACE_WORKING, text)

    def happy(self, text: str) -> str:
        return _say(FACE_HAPPY, text)

    def confused(self, text: str) -> str:
        return _say(FACE_SUSPICIOUS, text)

    def brain_prompt(self) -> str:
        return _say(
            FACE_CURIOUS,
            "Dump your thoughts. I'll sniff out useful context.\n"
            "   Type as many lines as you like; press Enter on an empty line to finish.",
        )

    def paste_prompt(self) -> str:
        return _say(
            FACE_CURIOUS,
            "Paste your text, then press CTRL+D on an empty line to finish\n"
            "   (CTRL+Z then Enter on Windows).",
        )

    def thinking(self) -> str:
        return _say(FACE_WORKING, "Sniffing out useful context...")

    def listening(self, source: str, review_cmd: str) -> str:
        return _say(
            FACE_WORKING,
            f"Ears up. Listening to {source}.\n"
            f"   I'll keep running here - this terminal stays busy.\n"
            f"   Review in another terminal with: {review_cmd}\n"
            f"   Press CTRL+C here to stop.",
        )

    def stopped_listening(self) -> str:
        return _say(FACE_IDLE, "Ears down. Stopped listening.")

    def candidates_found(self, count: int) -> str:
        if count == 0:
            return _say(FACE_IDLE, "Hmm, nothing shiny in there. Nothing saved.")
        noun = "shiny thought" if count == 1 else "shiny thoughts"
        return _say(FACE_CURIOUS, f"I found {count} {noun}.")

    def inbox_empty(self) -> str:
        return _say(FACE_IDLE, "No pending memories. Cat is sleeping.")

    def inbox_intro(self, count: int) -> str:
        noun = "thought" if count == 1 else "thoughts"
        return _say(FACE_CURIOUS, f"{count} {noun} waiting for your review.")

    def candidate_intro(self, candidate: MemoryCandidate) -> str:
        """A mood line shown before a candidate, reflecting its nature."""

        if candidate.sensitivity == "high":
            return _say(
                FACE_SUSPICIOUS, "This may be sensitive. Review before saving."
            )
        if candidate.project_id:
            return _say(FACE_CURIOUS, f"This belongs to: {candidate.project_id}")
        return _say(FACE_CURIOUS, f"Hmm... this smells like a {candidate.memory_type}.")

    def candidate_found(self, candidate: MemoryCandidate) -> str:
        return _say(FACE_CURIOUS, f"I found a shiny thought: {candidate.content}")

    def saved(self, item: MemoryItem) -> str:
        return _say(
            FACE_HAPPY,
            f"Saved. Delicious context. ({item.memory_type}, scope: {item.scope})",
        )

    def already_known(self, item: MemoryItem) -> str:
        return _say(
            FACE_IDLE,
            f"Already in my belly - skipped the duplicate. "
            f"({item.memory_type}, scope: {item.scope})",
        )

    def discarded(self) -> str:
        return _say(FACE_SUSPICIOUS, "Tossed it. Gone for good.")

    def review_done(self) -> str:
        return _say(FACE_IDLE, "All reviewed. Nap time.")
