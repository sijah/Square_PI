#!/usr/bin/env python3
# Script-aware font selection for user metadata (track titles, artists, playlist
# names). Chrome stays on the bundled DejaVu faces -- see screens.py.
#
# Why this module exists: Pillow has no font fallback. Hand it a string containing
# Malayalam and DejaVu will draw .notdef boxes, silently. And no redistributable
# font covers Devanagari + Malayalam + Tamil together, so a single "content font"
# was not an option once all three were in scope.
#
# Correct Indic rendering additionally needs Pillow built against libraqm (HarfBuzz
# + FriBidi), which reorders pre-base vowel signs and forms conjuncts. Without it
# the glyphs are drawn in codepoint order, which is wrong in a way that still looks
# plausible -- the failure mode is a panel that appears to work. shaping_available()
# reports it so the caller can log the truth once at startup rather than leave it to
# be discovered by someone who can read the script.
#
# Verified on hardware 2026-07-26: Pillow 12.3.0 on the Pi reports raqm True.
import glob
import os

from PIL import ImageFont, features

# Unicode blocks, in the order we test them. Latin (and anything else) falls through
# to the bundled DejaVu, which is also what keeps digits and punctuation looking the
# same whichever script they sit next to.
_BLOCKS = (
    ("deva", 0x0900, 0x097F),
    ("mlym", 0x0D00, 0x0D7F),
    ("taml", 0x0B80, 0x0BFF),
)

# Debian ships these under two different packages with different naming, and a
# Pi may have either. First existing path wins; an env var overrides for testing on
# a dev box that has neither.
_CANDIDATES = {
    "deva": (
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
        "/usr/share/fonts/truetype/fonts-deva-extra/Samyak-Devanagari.ttf",
    ),
    "mlym": (
        "/usr/share/fonts/truetype/noto/NotoSansMalayalam-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-malayalam/Lohit-Malayalam.ttf",
        "/usr/share/fonts/truetype/malayalam/Rachana.ttf",
    ),
    "taml": (
        "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
        "/usr/share/fonts/truetype/samyak/Samyak-Tamil.ttf",
    ),
}
# Bold cuts are optional: Noto ships them, Lohit generally does not. A missing bold
# falls back to the regular cut rather than to a Latin face, because the wrong
# weight is a cosmetic problem and .notdef boxes are not.
_BOLD_CANDIDATES = {
    "deva": ("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",),
    "mlym": ("/usr/share/fonts/truetype/noto/NotoSansMalayalam-Bold.ttf",),
    "taml": ("/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",),
}
# SQUAREPI_FONT_DEVA / _MLYM / _TAML point at a file directly. Used by the headless
# tests, which run on a box with no Debian font packages at all.
_ENV = {"deva": "SQUAREPI_FONT_DEVA", "mlym": "SQUAREPI_FONT_MLYM",
        "taml": "SQUAREPI_FONT_TAML"}

# Last resort: search by name. Debian has moved Noto's files between directories and
# naming conventions across releases (plain, /hinted/, unhinted variants), so an
# exact-path list is a guess that silently degrades to boxes when it's wrong. A glob
# finds the font wherever the package actually put it, and also picks up anything the
# user installed by hand. Done once per script and cached.
_FONT_DIRS = ("/usr/share/fonts", "/usr/local/share/fonts",
              os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts"))
_GLOBS = {
    "deva": ("NotoSansDevanagari-*", "Lohit-Devanagari*", "*Devanagari*"),
    "mlym": ("NotoSansMalayalam-*", "Lohit-Malayalam*", "*Malayalam*"),
    "taml": ("NotoSansTamil-*", "Lohit-Tamil*", "*Tamil*"),
}
# Faces that would be wrong for body text even though the name matches the script.
_REJECT = ("italic", "thin", "light", "black", "extra", "semi", "condensed",
           "medium", "ui-")


def _search(tag, bold):
    """Find a face for `tag` by filename. Prefers the requested weight, then Regular,
    and refuses display weights that would be unreadable at 15px on this panel."""
    hits = []
    for root in _FONT_DIRS:
        if not os.path.isdir(root):
            continue
        for pattern in _GLOBS.get(tag, ()):
            for ext in ("ttf", "otf"):
                hits.extend(glob.glob(os.path.join(root, "**", f"{pattern}.{ext}"),
                                      recursive=True))
        if hits:
            break        # a match in an earlier root wins over a later one
    if not hits:
        return None

    def rank(path):
        name = os.path.basename(path).lower()
        penalty = sum(4 for bad in _REJECT if bad in name)
        if bold:
            return penalty + (0 if "bold" in name else 2)
        return penalty + (0 if "regular" in name else (3 if "bold" in name else 1))

    return sorted(hits, key=lambda p: (rank(p), len(p)))[0]

_path_cache = {}
_font_cache = {}


def shaping_available():
    """Whether Pillow can shape complex scripts. False means Indic text will render
    incorrectly no matter which font is installed."""
    return bool(features.check("raqm"))


def script_of(ch):
    """Script tag for one character, or None for Latin/digits/punctuation/anything
    we have no dedicated font for."""
    cp = ord(ch)
    for tag, lo, hi in _BLOCKS:
        if lo <= cp <= hi:
            return tag
    return None


def font_path(tag, bold=False):
    """Resolved path for a script, or None if nothing suitable is installed."""
    key = (tag, bold)
    if key not in _path_cache:
        override = os.environ.get(_ENV.get(tag, ""))
        options = []
        if override:
            options.append(override)
        if bold:
            options.extend(_BOLD_CANDIDATES.get(tag, ()))
        options.extend(_CANDIDATES.get(tag, ()))
        found = next((p for p in options if os.path.exists(p)), None)
        if found is None:
            found = _search(tag, bold)
        if found is None and bold:
            # No bold cut for this script (Lohit ships none). The regular face is the
            # right fallback: the wrong weight is cosmetic, .notdef boxes are not.
            found = font_path(tag, bold=False)
        _path_cache[key] = found
    return _path_cache[key]


def font_for(tag, size, bold=False):
    """Font for a script at a size, or None to mean "use the caller's Latin font"."""
    if tag is None:
        return None
    path = font_path(tag, bold)
    if path is None:
        return None
    key = (path, size)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except OSError:
            # Present but unreadable (a truncated package, a bad symlink). Treat it
            # as absent: boxes are better than a crashed display service.
            _font_cache[key] = None
    return _font_cache[key]


def runs(text):
    """Split text into (script_tag_or_None, substring) runs of consecutive
    same-script characters.

    Splitting on script boundaries is safe for shaping -- no shaping rule spans two
    scripts -- while splitting *within* a script would break conjunct formation, so
    each run is handed to the shaper whole.
    """
    out = []
    for ch in text:
        tag = script_of(ch)
        # Spaces and punctuation join the run they follow, so "ചലനം (Remastered)"
        # doesn't fragment into six runs and lose its kerning.
        if tag is None and out and ch in " \t.,;:!?-()[]'\"/&":
            out[-1] = (out[-1][0], out[-1][1] + ch)
        elif out and out[-1][0] == tag:
            out[-1] = (tag, out[-1][1] + ch)
        else:
            out.append((tag, ch))
    return out


def missing_scripts(text):
    """Script tags present in `text` that have no font installed. For a one-time log
    line at startup, so a boxes-instead-of-glyphs panel has an explanation."""
    return sorted({tag for tag, _ in runs(text)
                   if tag is not None and font_for(tag, 12) is None})


def has_complex(text):
    """True if any character needs a script font. Cheap enough for the render loop,
    and lets the Latin path stay exactly as it was."""
    return any(script_of(ch) for ch in text)
