import re
import threading

VOICES = {
    "British Male — Ryan":    "en-GB-RyanNeural",
    "British Female — Sonia": "en-GB-SoniaNeural",
    "American Male — Guy":    "en-US-GuyNeural",
    "American Female — Jenny":"en-US-JennyNeural",
    "Irish Male — Connor":    "en-IE-ConnorNeural",
    "Australian Male — William": "en-AU-WilliamNeural",
}

DEFAULT_VOICE = "en-GB-RyanNeural"


def clean_for_speech(text: str) -> str:
    text = re.sub(r"\[STATE_UPDATE\].*?\[/STATE_UPDATE\]", "", text, flags=re.DOTALL)
    text = re.sub(r"🎲.*", "", text)
    text = re.sub(r"⚔️.*", "", text)
    text = re.sub(r"🔮.*", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"#+\s+", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"[✅❤️💙✨💰🎒📜📍🌤️🎉🏃💔💚🗣️]", "", text)
    text = re.sub(r"---+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def synthesize(text: str, voice: str = DEFAULT_VOICE) -> bytes | None:
    """Generate MP3 audio bytes via edge-tts. Returns None on any failure."""
    clean = clean_for_speech(text)
    if not clean:
        return None

    result: list[bytes | None] = [None]

    async def _run():
        try:
            import edge_tts
            communicate = edge_tts.Communicate(clean, voice)
            buf = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
            result[0] = buf
        except Exception:
            result[0] = None

    def _thread():
        import asyncio
        asyncio.run(_run())

    t = threading.Thread(target=_thread, daemon=True)
    t.start()
    t.join(timeout=25)
    return result[0]
