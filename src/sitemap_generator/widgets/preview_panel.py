"""Vorschau-Panel - zeigt einen Seiten-Screenshot im Terminal.

Nutzt ein Terminal-Grafik-Protokoll (TGP/Sixel) wenn das Terminal es
unterstuetzt, sonst Unicode-Half-Blocks als Fallback. Angelehnt an die
Cover-Darstellung in retro-amp.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from ..i18n import t

logger = logging.getLogger(__name__)

_UPPER_HALF_BLOCK = "▀"


def _select_graphics_backend() -> str | None:
    """Ermittelt das beste Terminal-Grafik-Protokoll anhand des Terminals.

    Returns:
        "tgp" (Kitty-Protokoll), "sixel" oder None (kein Grafik-Protokoll,
        Fallback auf Half-Blocks).
    """
    term = os.environ.get("TERM", "").lower()
    term_program = os.environ.get("TERM_PROGRAM", "").lower()

    if os.environ.get("KITTY_WINDOW_ID"):
        return "tgp"
    if "kitty" in term or "ghostty" in term:
        return "tgp"
    if term_program in ("wezterm", "ghostty"):
        return "tgp"
    if os.environ.get("KONSOLE_VERSION"):
        return "tgp"

    if os.environ.get("WT_SESSION"):
        return "sixel"
    if term in ("foot", "xterm", "mlterm", "mintty") or "foot" in term:
        return "sixel"
    if term_program in ("mintty", "iterm.app"):
        return "sixel"

    return None


def _load_graphics_widget_class(backend: str) -> type[Widget] | None:
    """Laedt die passende textual-image-Widget-Klasse.

    Args:
        backend:
            "tgp" oder "sixel".

    Returns:
        Die Widget-Klasse oder None, wenn textual-image nicht verfuegbar ist.
    """
    try:
        if backend == "tgp":
            from textual_image.widget import TGPImage

            return TGPImage
        if backend == "sixel":
            from textual_image.widget import SixelImage

            return SixelImage
    except ImportError:
        logger.debug("textual-image nicht installiert, kein Grafik-Rendering")
        return None
    return None


def _render_half_blocks(image_data: bytes, max_width: int, max_height: int) -> list[Text]:
    """Rendert Bilddaten als Unicode-Half-Block-Zeilen.

    Jedes Terminal-Zeichen kodiert 2 vertikale Pixel via Vorder-/Hintergrund.

    Args:
        image_data: PNG-Bilddaten.
        max_width: Maximale Breite in Terminal-Zeichen.
        max_height: Maximale Hoehe in Terminal-Zeilen.

    Returns:
        Liste der gerenderten Zeilen.
    """
    try:
        from PIL import Image as PILImage
    except ImportError:
        return [Text(t("preview.error"), style="dim")]

    try:
        img = PILImage.open(io.BytesIO(image_data)).convert("RGB")
    except Exception:
        return [Text(t("preview.error"), style="dim")]

    orig_w, orig_h = img.size
    if orig_w <= 0 or orig_h <= 0:
        return []

    pixel_h = max_height * 2
    scale = min(max_width / orig_w, pixel_h / orig_h)
    new_w = max(1, int(orig_w * scale))
    new_h = max(2, int(orig_h * scale))
    if new_h % 2 != 0:
        new_h += 1

    img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)

    lines: list[Text] = []
    for y in range(0, new_h, 2):
        line = Text()
        for x in range(new_w):
            # getpixel liefert auf einem RGB-Bild ein (r, g, b)-Tupel;
            # Rich akzeptiert dessen Repr direkt als rgb(r, g, b).
            top = img.getpixel((x, y))
            bottom = img.getpixel((x, y + 1))
            line.append(_UPPER_HALF_BLOCK, style=f"rgb{top} on rgb{bottom}")
        lines.append(line)
    return lines


class PreviewPanel(Widget):
    """Zeigt einen Seiten-Screenshot als Terminal-Grafik oder Half-Blocks."""

    DEFAULT_CSS = """
    PreviewPanel {
        width: 100%;
        height: 100%;
    }
    PreviewPanel #preview-scroll {
        height: 100%;
        align-horizontal: center;
        padding: 0 1;
    }
    PreviewPanel #preview-status {
        color: $text-muted;
        height: auto;
    }
    PreviewPanel #preview-content {
        color: $text;
    }
    PreviewPanel .graphics-image {
        width: auto;
        height: 1fr;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._graphics_widget_cls: type[Widget] | None = None
        backend = _select_graphics_backend()
        if backend is not None:
            self._graphics_widget_cls = _load_graphics_widget_class(backend)
        self._loading_timer: Any = None
        self._loading_step: int = 0

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="preview-scroll"):
            yield Static("", id="preview-status")
            if self._graphics_widget_cls is not None:
                yield self._graphics_widget_cls(id="preview-content", classes="graphics-image")
            else:
                yield Static("", id="preview-content")

    def on_mount(self) -> None:
        """Zeigt den Auswahl-Hinweis beim Start."""
        self._set_status(t("preview.select"))

    def _set_status(self, text: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#preview-status", Static).update(text)

    def _clear_graphics_image(self) -> None:
        if self._graphics_widget_cls is None:
            return
        with contextlib.suppress(Exception):
            widget = self.query_one("#preview-content", self._graphics_widget_cls)
            widget.image = None  # type: ignore[attr-defined]

    def show_loading(self) -> None:
        """Zeigt den Ladezustand an — mit wachsender Punkt-Animation."""
        self._loading_step = 0
        self._set_status(t("preview.loading"))
        if self._graphics_widget_cls is not None:
            self._clear_graphics_image()
        else:
            with contextlib.suppress(Exception):
                self.query_one("#preview-content", Static).update("")
        # Animation starten — Punkte zaehlen bis 3, dann wieder von vorne.
        if self._loading_timer is not None:
            with contextlib.suppress(Exception):
                self._loading_timer.stop()
        self._loading_timer = self.set_interval(0.4, self._tick_loading)

    def _tick_loading(self) -> None:
        """Aktualisiert die Lade-Animation um einen Punkt."""
        self._loading_step = (self._loading_step + 1) % 4
        dots = "." * self._loading_step
        self._set_status(t("preview.loading") + dots)

    def _stop_loading_animation(self) -> None:
        if self._loading_timer is not None:
            with contextlib.suppress(Exception):
                self._loading_timer.stop()
            self._loading_timer = None

    def show_preview(self, image_data: bytes | None) -> None:
        """Rendert den Screenshot oder zeigt einen Fallback-Text.

        Args:
            image_data: PNG-Bilddaten oder None.
        """
        self._stop_loading_animation()
        if self._graphics_widget_cls is not None:
            self._show_graphics(image_data)
        else:
            self._show_halfblock(image_data)

    def _show_graphics(self, image_data: bytes | None) -> None:
        """Zeigt den Screenshot ueber ein textual-image-Widget (TGP/Sixel)."""
        if not image_data:
            self._set_status(t("preview.none"))
            self._clear_graphics_image()
            return
        try:
            from PIL import Image as PILImage

            pil_img = PILImage.open(io.BytesIO(image_data)).convert("RGB")
            assert self._graphics_widget_cls is not None
            widget = self.query_one("#preview-content", self._graphics_widget_cls)
            widget.image = pil_img  # type: ignore[attr-defined]
            self._set_status("")
        except Exception:
            logger.debug("Grafik-Vorschau fehlgeschlagen", exc_info=True)
            self._set_status(t("preview.error"))

    def _show_halfblock(self, image_data: bytes | None) -> None:
        """Zeigt den Screenshot ueber Unicode-Half-Blocks in einem Static."""
        content = self.query_one("#preview-content", Static)
        if not image_data:
            self._set_status(t("preview.none"))
            content.update("")
            return
        try:
            scroll = self.query_one("#preview-scroll")
            max_width = max(20, scroll.size.width - 2)
            max_height = max(8, scroll.size.height - 2)
        except Exception:
            max_width, max_height = 60, 20
        lines = _render_half_blocks(image_data, max_width, max_height)
        if lines:
            self._set_status("")
            content.update(Text("\n").join(lines))
        else:
            self._set_status(t("preview.none"))
            content.update("")

    def clear(self) -> None:
        """Leert das Panel."""
        self._set_status(t("preview.select"))
        if self._graphics_widget_cls is not None:
            self._clear_graphics_image()
        else:
            with contextlib.suppress(Exception):
                self.query_one("#preview-content", Static).update("")
