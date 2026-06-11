"""Terminal image rendering.

Three backends are supported, in decreasing order of fidelity:

* ``kitty`` — base64 PNG via the Kitty graphics protocol (Kitty, Ghostty,
  recent WezTerm).
* ``sixel`` — bitmap sixel via the pure-Python ``sixel`` package (foot,
  WezTerm, mlterm, Konsole, iTerm2, xterm ``-ti vt340``, mintty, ...).
* ``256`` — xterm 256-color ANSI half blocks (``U+2580``). Universal floor.

``render_image_auto`` / ``render_image_from_url_auto`` pick a backend based on
either an explicit user choice (``sixel`` / ``kitty`` / ``256``) or — when the
choice is ``auto`` — the result of :func:`detect_graphics_backend`, which
probes the terminal once and caches the answer for the rest of the process.

The cache exists so the probe can safely run before prompt_toolkit takes over
stdin/stdout. Running DA1 from inside a prompt_toolkit ``Application`` would
collide with its own cursor-position queries.
"""
import base64
import io
import os
import select
import sys
import zlib

import requests

from ._kitty_diacritics import ROWCOLUMN_DIACRITICS

# Imported here so tests can monkeypatch them as
# ``nekofedi.image.termios.tcgetattr`` etc. ``termios`` / ``tty`` are
# Unix-only; on Windows they raise ImportError here, which is fine — the
# DA1 probe below catches every exception and returns ``"none"``.
try:
    import termios  # type: ignore
    import tty  # type: ignore
except ImportError:  # pragma: no cover - Windows / non-Unix
    termios = None  # type: ignore
    tty = None  # type: ignore


HALF_BLOCK = "\u2580"  # U+2580 UPPER HALF BLOCK
RESET = "\x1b[0m"

# Rough assumption for sixel pixel-width derivation from terminal columns.
# 10 px/cell is a typical monospace cell at the usual desktop font size.
CELL_PIXEL_WIDTH = 10

# Kitty graphics protocol constants.
_KITTY_CHUNK_SIZE = 4096  # base64 payload bytes per APC segment
_APC_PREFIX = "\x1b_G"
_APC_SUFFIX = "\x1b\\"

# tmux DCS passthrough wrapper. Inside tmux the terminal never sees raw APC
# escapes — tmux swallows them — so Kitty graphics silently fail. Wrapping a
# sequence in ``ESC P tmux ; <payload> ESC \`` with every inner ESC doubled
# lets tmux forward the bytes verbatim to the outer terminal. This is what
# image.nvim does, which is why images show there but not here.
#
# Crucially, each APC *chunk* is wrapped in its own passthrough rather than
# wrapping the whole multi-chunk sequence at once: tmux caps the length of a
# single passthrough string, so one giant DCS is truncated and the image
# silently fails for anything larger than a tiny single-chunk PNG. Per-chunk
# wrapping keeps every DCS under ~4 KB, which is what kitty's own icat does.
# (The exact cap is tmux's INPUT_BUF_LIMIT and varies across tmux versions.)
# Requires ``set -g allow-passthrough on`` in the user's tmux config.
_TMUX_PT_PREFIX = "\x1bPtmux;"
_TMUX_PT_SUFFIX = "\x1b\\"

# Kitty Unicode placeholder (virtual placement) support. Under tmux a plain
# ``a=T`` placement is invisible to tmux: it doesn't scroll with the text and
# tmux never clears it, so the image stays pinned over the UI. Instead we
# create a *virtual* placement (``U=1``) and "stamp" it onto real text cells
# made of the placeholder char U+10EEEE, whose row/column are encoded with
# combining diacritics and whose image id is encoded in the cell foreground
# colour. Those cells are ordinary text, so tmux scrolls and clears them
# normally and the image rides along. See:
#   https://sw.kovidgoyal.net/kitty/graphics-protocol/#unicode-placeholders
_KITTY_PLACEHOLDER = "\U0010eeee"
# Terminal cells are ~twice as tall as wide; a square image spanning N columns
# needs ~N/2 rows to keep its aspect (matches the 256-colour half-block ratio).
_CELL_ASPECT = 2

# Sixel detection timeout (seconds) — modern terminals respond in <10 ms,
# 200 ms leaves headroom for SSH over slow links without being user-visible.
_SIXEL_PROBE_TIMEOUT = 0.2


# ---------------------------------------------------------------------------
# Backend detection (cached)
# ---------------------------------------------------------------------------

# One of ``None`` (not yet detected), ``"kitty"``, ``"sixel"``, or ``"none"``.
_BACKEND_CACHE = None


def _reset_backend_cache_for_tests():
    """Reset the module-level backend cache. Test-only helper."""
    global _BACKEND_CACHE
    _BACKEND_CACHE = None


def _detect_kitty_from_env():
    """Return ``True`` if the environment advertises Kitty-protocol support.

    Kitty itself always exports ``KITTY_WINDOW_ID``. Ghostty and recent
    WezTerm advertise via ``TERM_PROGRAM``.
    """
    if os.environ.get("KITTY_WINDOW_ID"):
        return True
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program == "ghostty":
        return True
    if term_program == "WezTerm":
        return True
    return False


def _probe_sixel_da1():
    """Send a DA1 query and check whether the reply advertises sixel.

    Returns ``True`` only when the terminal's Primary Device Attributes
    response contains ``4`` as an explicit token (``Ps = 4 => Sixel
    graphics`` per xterm ctlseqs).

    Returns ``False`` on any failure — missing tty, timeout, termios error,
    unusual stdin, anything. Never raises.
    """
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        term = os.environ.get("TERM", "")
        if term.startswith("screen") or term.startswith("tmux"):
            # tmux/screen need passthrough + compile flags; default off.
            return False

        if termios is None or tty is None:
            return False
        fd = sys.stdin.fileno()
        old_attrs = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            sys.stdout.write("\x1b[c")
            sys.stdout.flush()
            buf = ""
            deadline_parts = select.select([sys.stdin], [], [], _SIXEL_PROBE_TIMEOUT)
            if not deadline_parts[0]:
                return False
            while True:
                ch = sys.stdin.read(1)
                if not ch:
                    break
                buf += ch
                if ch == "c":
                    break
                # Safety: stop waiting after another short slice.
                more = select.select([sys.stdin], [], [], _SIXEL_PROBE_TIMEOUT)
                if not more[0]:
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)

        # Expected shape: ESC [ ? p1 ; p2 ; ... ; pn c
        if not buf:
            return False
        payload = buf
        if payload.startswith("\x1b[?"):
            payload = payload[3:]
        elif payload.startswith("\x1b["):
            payload = payload[2:]
        if payload.endswith("c"):
            payload = payload[:-1]
        tokens = payload.split(";")
        return "4" in tokens
    except Exception:
        return False


def detect_graphics_backend():
    """Detect the best available terminal graphics backend.

    Returns one of ``"kitty"``, ``"sixel"``, or ``"none"``. The first call
    performs the detection and caches the result; subsequent calls return
    the cached answer for the rest of the process lifetime.

    The caller is expected to invoke this once during startup — ideally
    before prompt_toolkit takes over the terminal — so the DA1 probe
    doesn't collide with prompt_toolkit's own cursor-position queries.
    """
    global _BACKEND_CACHE
    if _BACKEND_CACHE is not None:
        return _BACKEND_CACHE
    if _detect_kitty_from_env():
        _BACKEND_CACHE = "kitty"
        return _BACKEND_CACHE
    if _probe_sixel_da1():
        _BACKEND_CACHE = "sixel"
        return _BACKEND_CACHE
    _BACKEND_CACHE = "none"
    return _BACKEND_CACHE


# ---------------------------------------------------------------------------
# 256-color half-block renderer (existing — unchanged behaviour)
# ---------------------------------------------------------------------------


def rgb_to_256(r, g, b):
    """Map an 8-bit RGB triple to the nearest xterm 256-color index."""
    if r == g == b:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + round((r - 8) / 247 * 24)
    return (
        16
        + 36 * round(r / 255 * 5)
        + 6 * round(g / 255 * 5)
        + round(b / 255 * 5)
    )


def _resize_for_terminal(image, max_width):
    """Resize ``image`` so its width is at most ``max_width``, preserving aspect.

    Height is not halved here — ``render_image_256`` iterates two source rows per
    output line, so the final visual aspect matches the source on a terminal
    with roughly 2:1 cell height.
    """
    from PIL import Image  # lazy import

    w, h = image.size
    if w <= max_width:
        return image
    ratio = max_width / w
    new_w = max_width
    new_h = max(1, int(round(h * ratio)))
    return image.resize((new_w, new_h), Image.LANCZOS)


def render_image_256(image_bytes, max_width=76):
    """Render raw image bytes as ANSI 256-color half-block text.

    Returns a terminal-ready string; the caller writes it to stdout.
    """
    from PIL import Image  # lazy import

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = _resize_for_terminal(img, max_width)
    pixels = img.load()
    w, h = img.size

    lines = []
    for y in range(0, h, 2):
        buf = []
        last_fg = None
        last_bg = None
        for x in range(w):
            top = pixels[x, y]
            bottom = pixels[x, y + 1] if y + 1 < h else (0, 0, 0)
            fg = rgb_to_256(*top)
            bg = rgb_to_256(*bottom)
            if fg != last_fg:
                buf.append(f"\x1b[38;5;{fg}m")
                last_fg = fg
            if bg != last_bg:
                buf.append(f"\x1b[48;5;{bg}m")
                last_bg = bg
            buf.append(HALF_BLOCK)
        buf.append(RESET)
        buf.append("\n")
        lines.append("".join(buf))
    return "".join(lines)


def render_image_256_from_url(url, max_width=76):
    """Fetch ``url`` and render it via :func:`render_image_256`."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return render_image_256(resp.content, max_width=max_width)


# ---------------------------------------------------------------------------
# Sixel renderer (via the pure-Python `sixel` package)
# ---------------------------------------------------------------------------


def render_image_sixel(image_bytes, max_pixel_width):
    """Render raw image bytes as a sixel escape sequence string.

    Uses :class:`sixel.converter.SixelConverter` from the ``sixel`` PyPI
    package. Pillow is used implicitly by that package; we don't import
    it here.
    """
    from sixel import converter  # lazy import

    c = converter.SixelConverter(io.BytesIO(image_bytes), w=max_pixel_width)
    return c.getvalue()


def render_image_sixel_from_url(url, max_pixel_width):
    """Fetch ``url`` and render it via :func:`render_image_sixel`."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return render_image_sixel(resp.content, max_pixel_width=max_pixel_width)


# ---------------------------------------------------------------------------
# Kitty graphics protocol renderer
# ---------------------------------------------------------------------------


def _to_png_with_size(image_bytes):
    """Normalize arbitrary image bytes to ``(png_bytes, width, height)``.

    The Kitty graphics protocol accepts PNG directly (``f=100``). We always
    re-encode via Pillow so the input can be JPEG / WebP / ...
    """
    from PIL import Image  # lazy import

    img = Image.open(io.BytesIO(image_bytes))
    width, height = img.size
    # Kitty accepts RGBA PNG just fine; convert only if unusual mode.
    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        img = img.convert("RGBA")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue(), width, height


def _in_tmux():
    """Return ``True`` when running inside a tmux (or screen) session."""
    if os.environ.get("TMUX"):
        return True
    term = os.environ.get("TERM", "")
    return term.startswith("tmux") or term.startswith("screen")


def _wrap_tmux_passthrough(seq):
    """Wrap an escape sequence so tmux forwards it to the outer terminal.

    Every inner ESC must be doubled per the DCS passthrough convention.
    """
    return _TMUX_PT_PREFIX + seq.replace("\x1b", "\x1b\x1b") + _TMUX_PT_SUFFIX


def _apc_transmit_chunks(payload, first_header, in_tmux):
    """Chunk a base64 ``payload`` into Kitty APC ``_G`` transmit segments.

    The first segment carries ``first_header``; subsequent segments carry only
    the continuation flag. ``m=1`` on all but the last (``m=0``). When
    ``in_tmux`` each segment is individually wrapped in a tmux DCS passthrough
    — see ``_TMUX_PT_PREFIX`` for why wrapping is per-chunk.
    """
    chunks = [
        payload[i : i + _KITTY_CHUNK_SIZE]
        for i in range(0, len(payload), _KITTY_CHUNK_SIZE)
    ]
    if not chunks:
        return ""
    parts = []
    for idx, chunk in enumerate(chunks):
        m_flag = "0" if idx == len(chunks) - 1 else "1"
        header = f"{first_header},m={m_flag}" if idx == 0 else f"m={m_flag}"
        apc = f"{_APC_PREFIX}{header};{chunk}{_APC_SUFFIX}"
        if in_tmux:
            apc = _wrap_tmux_passthrough(apc)
        parts.append(apc)
    return "".join(parts)


def _placeholder_grid(image_id, rows, cols):
    """Build the Unicode-placeholder cell grid that stamps a virtual placement.

    Each cell is the placeholder char with the row/column encoded as combining
    diacritics; the image id is carried by the cell foreground colour. Only the
    first cell of each row needs explicit diacritics — the terminal advances the
    column for bare placeholder cells and inherits the row from the left.
    """
    r = (image_id >> 16) & 0xFF
    g = (image_id >> 8) & 0xFF
    b = image_id & 0xFF
    fg = f"\x1b[38;2;{r};{g};{b}m"
    col0 = chr(ROWCOLUMN_DIACRITICS[0])
    lines = []
    for row in range(rows):
        first = _KITTY_PLACEHOLDER + chr(ROWCOLUMN_DIACRITICS[row]) + col0
        rest = _KITTY_PLACEHOLDER * (cols - 1)
        lines.append(f"{fg}{first}{rest}\x1b[39m")
    return "\n".join(lines) + "\n"


def _render_kitty_unicode(png, width, height, max_cols):
    """Render via a Kitty *virtual* placement + Unicode placeholders (tmux-safe).

    Unlike a plain ``a=T`` placement, the image is anchored to real text cells,
    so tmux scrolls and clears it like ordinary text instead of leaving it
    pinned over the UI.
    """
    payload = base64.standard_b64encode(png).decode("ascii")
    if not payload:
        return ""
    limit = len(ROWCOLUMN_DIACRITICS)
    cols = max(1, min(max_cols, limit))
    rows = max(1, min(round(cols * height / (_CELL_ASPECT * width)), limit))
    # Deterministic 24-bit id (encodes into the RGB foreground; nonzero).
    image_id = (zlib.crc32(png) & 0xFFFFFF) or 1
    header = f"a=T,U=1,i={image_id},f=100,q=2,c={cols},r={rows}"
    transmit = _apc_transmit_chunks(payload, header, in_tmux=True)
    return transmit + _placeholder_grid(image_id, rows, cols)


def render_image_kitty(image_bytes, max_cols):
    """Render ``image_bytes`` as a Kitty graphics protocol escape string.

    Outside tmux the image is transmitted-and-displayed directly (``a=T``):
    the PNG base64 is chunked into APC ``_G`` segments (``m=1`` until the last
    ``m=0``); the first carries ``a=T,f=100,q=2,c=<max_cols>``. ``q=2``
    suppresses the terminal's OK/error replies, which would otherwise land in
    stdin and be read as stray input by the next prompt.

    Inside tmux a plain ``a=T`` placement is unmanaged by tmux — it never
    scrolls or clears and stays pinned over the UI. So we switch to a virtual
    placement addressed by Unicode placeholders (:func:`_render_kitty_unicode`),
    which rides along with the surrounding text.
    """
    png, width, height = _to_png_with_size(image_bytes)
    if _in_tmux():
        return _render_kitty_unicode(png, width, height, max_cols)
    payload = base64.standard_b64encode(png).decode("ascii")
    body = _apc_transmit_chunks(payload, f"a=T,f=100,q=2,c={max_cols}", in_tmux=False)
    return body + "\n" if body else ""


def render_image_kitty_from_url(url, max_cols):
    """Fetch ``url`` and render it via :func:`render_image_kitty`."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return render_image_kitty(resp.content, max_cols=max_cols)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _resolve_backend(backend):
    """Resolve an explicit or ``"auto"`` backend choice to a concrete one.

    Returns one of ``"kitty"``, ``"sixel"``, ``"256"``. Any unknown value
    (including ``None``) degrades to ``"256"`` so a miswritten config can
    never break the preview command.
    """
    if backend == "sixel":
        return "sixel"
    if backend == "kitty":
        return "kitty"
    if backend == "256":
        return "256"
    if backend == "auto":
        detected = detect_graphics_backend()
        if detected in ("kitty", "sixel"):
            return detected
        return "256"
    return "256"


def render_image_auto(image_bytes, *, max_cols, backend):
    """Render ``image_bytes`` using the best backend allowed by ``backend``.

    ``max_cols`` is the caller's desired width in terminal cells. For the
    sixel backend the cell count is multiplied by ``CELL_PIXEL_WIDTH`` to
    obtain a reasonable pixel cap.
    """
    choice = _resolve_backend(backend)
    if choice == "kitty":
        return render_image_kitty(image_bytes, max_cols=max_cols)
    if choice == "sixel":
        return render_image_sixel(
            image_bytes, max_pixel_width=max(64, max_cols * CELL_PIXEL_WIDTH)
        )
    return render_image_256(image_bytes, max_width=max_cols)


def render_image_from_url_auto(url, *, max_cols, backend):
    """Fetch ``url`` and render it via :func:`render_image_auto`."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return render_image_auto(resp.content, max_cols=max_cols, backend=backend)
