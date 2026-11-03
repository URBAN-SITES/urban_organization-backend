import re
import unicodedata


def make_identifier(name: str) -> str:
    """Short uppercase key from a project name: "Desenvolvimento" -> "DES",
    "Marketing Digital" -> "MD"; falls back to "PRJ"."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", plain)
    if not words:
        return "PRJ"
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(word[0] for word in words[:4]).upper()
