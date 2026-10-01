"""Language mirroring: detect the user's language per turn; set TTS language from KB's reply script."""

from __future__ import annotations

import re

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.sarvam.tts import SarvamTTSService

# Hindi verbs/auxiliaries: one of these means the sentence itself is Hindi, not an English sentence
# with a stray Devanagari word (STT sometimes writes "KB" as "के भी").
HINDI_VERBS = re.compile(r"(?<![\u0900-\u0963\u0966-\u097F])(है|हैं|था|थी|थे|हूँ|हूं|हो|रहा|रही|रहे|गया|गई|गए|करो|कर|दो|दीजिए|नहीं|हाँ|हां|चाहिए|जाएगा)(?![\u0900-\u0963\u0966-\u097F])")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
HINGLISH = {
    "hai", "hain", "nahi", "nahin", "kar", "karo", "kiya", "raha", "rahi", "rahe", "se", "pe", "par", "bhi", "aa",
    "kya", "haan", "ha", "ho", "kab", "mein", "ki", "ka", "ko", "bas", "abhi", "phir", "bahut", "wala", "wali",
    "diya", "dena", "do", "theek", "thik", "chal", "ruk", "jayega", "hoga", "mera", "meri", "aur", "kuch", "koi",
    "lagta", "lag", "gaya", "gayi", "liya", "chahiye", "batao", "dikhao", "kaun", "kaunse", "sab",
    "ke", "baad", "pehle", "yeh", "woh", "kuchh", "acha", "accha", "haa", "hua", "hui", "kijiye", "dijiye",
}  # fmt: skip


def detect(text: str) -> str:
    """'hi' for Hindi (Devanagari) or Hinglish (romanized), else 'en'."""
    if HINDI_VERBS.search(text or ""):
        return "hi"
    dev = len(DEVANAGARI.findall(text or ""))
    latin = len(re.findall(r"[A-Za-z]", text or ""))
    # STT sometimes writes a stray word ("KB" -> "के भी") in Devanagari inside English speech.
    if dev and dev / (dev + latin) >= 0.25:
        return "hi"
    words = re.findall(r"[a-z]+", (text or "").lower())
    hits = sum(w in HINGLISH for w in words)
    return "hi" if hits >= 2 or (words and hits / len(words) > 0.25) else "en"


def looks_hindi(value: str) -> bool:
    """Strict check for tool-argument values: Devanagari, or clearly romanized Hindi (2+ Hindi words)."""
    if DEVANAGARI.search(value or ""):
        return True
    words = re.findall(r"[a-z]+", (value or "").lower())
    return sum(w in HINGLISH for w in words) >= 2


class ReplyLanguage(FrameProcessor):
    """Between LLM and TTS: switch Bulbul's language to match each reply's script.

    Holds the first few tokens of a reply until the script is clear (any
    Devanagari, or 12+ Latin letters), pushes a settings update only when the
    language changes, then releases the held tokens. TTS aggregates sentences
    anyway, so the hold costs nothing audible.
    """

    def __init__(self, initial: str = "en-IN") -> None:
        super().__init__()
        self.current = initial
        self._held: list[tuple[Frame, FrameDirection]] = []
        self._text = ""
        self._decided = True

    async def _decide(self, want: str) -> None:
        self._decided = True
        if want != self.current:
            self.current = want
            await self.push_frame(TTSUpdateSettingsFrame(delta=SarvamTTSService.Settings(language=want)))
        held, self._held = self._held, []
        for f, d in held:
            await self.push_frame(f, d)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            self._decided, self._text, self._held = True, "", []
        elif isinstance(frame, LLMFullResponseStartFrame):
            self._decided, self._text, self._held = False, "", []
        elif isinstance(frame, LLMTextFrame) and not self._decided:
            self._held.append((frame, direction))
            self._text += frame.text
            if DEVANAGARI.search(self._text):
                await self._decide("hi-IN")
            elif len(re.findall(r"[A-Za-z]", self._text)) >= 12:
                await self._decide("en-IN")
            return
        elif isinstance(frame, LLMFullResponseEndFrame) and not self._decided:
            await self._decide("hi-IN" if DEVANAGARI.search(self._text) else "en-IN")
        await self.push_frame(frame, direction)
