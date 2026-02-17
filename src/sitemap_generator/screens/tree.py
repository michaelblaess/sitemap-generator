"""Seitenbaum-Dialog fuer den Sitemap Generator.

Zeigt die gecrawlte Seitenstruktur als Baum an und ermoeglicht
den Export als Mermaid-Diagramm oder ASCII-Baum.
"""

from __future__ import annotations

from collections import defaultdict, deque
from urllib.parse import urlparse

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Tree

from ..models.crawl_result import CrawlResult, PageStatus


class TreeScreen(ModalScreen):
    """Modal-Dialog zur Anzeige der Seitenstruktur als Baum.

    Baut den Baum aus parent_url-Beziehungen auf (BFS)
    und bietet Mermaid- und ASCII-Export.
    """

    DEFAULT_CSS = """
    TreeScreen {
        align: center middle;
    }

    TreeScreen > Vertical {
        width: 120;
        height: 85%;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }

    TreeScreen #tree-title {
        height: 3;
        content-align: center middle;
        text-style: bold;
        background: $accent;
        color: $text;
        margin-bottom: 1;
    }

    TreeScreen #site-tree {
        height: 1fr;
    }

    TreeScreen #tree-footer {
        height: 1;
        content-align: center middle;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Schliessen"),
        Binding("q", "close", "Schliessen"),
        Binding("m", "copy_mermaid", "Mermaid kopieren"),
        Binding("a", "copy_ascii", "ASCII kopieren"),
        Binding("e", "expand_all", "Alles aufklappen"),
        Binding("c", "collapse_all", "Alles einklappen"),
    ]

    def __init__(
        self,
        results: list[CrawlResult],
        start_url: str,
        sitemap_urls: set[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._results = results
        self._start_url = start_url
        self._sitemap_urls: set[str] = sitemap_urls or set()
        self._url_to_result: dict[str, CrawlResult] = {}
        self._children: dict[str, list[str]] = defaultdict(list)
        self._root_url: str = ""

    def compose(self) -> ComposeResult:
        """Erstellt das Baum-Layout."""
        self._build_tree_data()

        with Vertical():
            yield Static("Seitenbaum", id="tree-title")
            yield Tree("Seiten", id="site-tree")
            yield Static(
                "m = Mermaid  |  a = ASCII  |  e = Aufklappen  |  c = Einklappen  |  ESC/q = Schliessen",
                id="tree-footer",
            )

    def on_mount(self) -> None:
        """Baut den Textual-Tree nach dem Mounten auf."""
        tree_widget = self.query_one("#site-tree", Tree)
        tree_widget.root.expand()

        if not self._root_url:
            tree_widget.root.set_label("Keine Daten")
            return

        root_result = self._url_to_result.get(self._root_url)
        root_label = self._make_label(self._root_url, root_result)
        tree_widget.root.set_label(root_label)
        tree_widget.root.data = self._root_url

        # BFS: Baum aufbauen
        visited: set[str] = {self._root_url}
        queue: deque[tuple] = deque()

        for child_url in self._children.get(self._root_url, []):
            if child_url not in visited:
                queue.append((tree_widget.root, child_url))
                visited.add(child_url)

        while queue:
            parent_node, url = queue.popleft()
            result = self._url_to_result.get(url)
            label = self._make_label(url, result)
            node = parent_node.add(label, data=url)

            for child_url in self._children.get(url, []):
                if child_url not in visited:
                    queue.append((node, child_url))
                    visited.add(child_url)

        # Erste Ebene aufklappen
        for child in tree_widget.root.children:
            child.expand()

        tree_widget.focus()

    def _build_tree_data(self) -> None:
        """Baut die Baumstruktur aus den Crawl-Ergebnissen auf."""
        for r in self._results:
            self._url_to_result[r.url] = r
            if r.parent_url:
                self._children[r.parent_url].append(r.url)

        # Root ermitteln: Start-URL oder URL ohne Parent
        if self._start_url in self._url_to_result:
            self._root_url = self._start_url
        else:
            # Fallback: URL ohne parent_url
            for r in self._results:
                if not r.parent_url:
                    self._root_url = r.url
                    break

    def _make_label(self, url: str, result: CrawlResult | None) -> Text:
        """Erstellt das Label fuer einen Baumknoten.

        Farbcodierung: 2xx gruen, 3xx gelb/dim, 4xx/5xx rot.
        Externe Redirects: komplett dim/grau.

        Args:
            url: Die URL des Knotens.
            result: Das CrawlResult oder None.

        Returns:
            Rich Text mit Status-Icon, HTTP-Code und URL-Pfad.
        """
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        if not result:
            return Text(f"? {path}")

        icon = result.status_icon
        code = result.http_status_code

        # Externe Redirects: komplett ausgegraut
        if result.is_external_redirect:
            label = Text(f"{icon} ", style="dim")
            label.append(f"[{code}]", style="dim")
            label.append(f" {path}", style="dim")
            label.append(" → (extern)", style="dim italic")
            return label

        # Interne Redirects: cyan
        if result.status == PageStatus.REDIRECT:
            label = Text(f"{icon} ")
            label.append(f"[{code}]", style="cyan")
            label.append(f" {path}")
            return label

        # Farbcodierung nach HTTP-Status
        if code >= 400:
            style = "bold red"
        elif code >= 200:
            style = "green"
        else:
            style = ""

        # Nicht in offizieller Sitemap: orange markiert (nur fuer 200er)
        not_in_sitemap = (
            self._sitemap_urls
            and code == 200
            and result.url not in self._sitemap_urls
        )

        label = Text(f"{icon} ")
        label.append(f"[{code}]", style=style)
        if not_in_sitemap:
            label.append(f" {path}", style="dark_orange")
        else:
            label.append(f" {path}")
        return label

    def _get_status_style(self, result: CrawlResult | None) -> str:
        """Gibt den Mermaid-Style fuer einen Knoten zurueck.

        Args:
            result: Das CrawlResult oder None.

        Returns:
            Mermaid-Style-String.
        """
        if not result:
            return ""

        code = result.http_status_code
        if 200 <= code < 300:
            return ":::ok"
        if 300 <= code < 400:
            return ":::redirect"
        if code >= 400:
            return ":::error"
        return ""

    def action_copy_mermaid(self) -> None:
        """Kopiert den Seitenbaum als Mermaid-Diagramm in die Zwischenablage."""
        if not self._root_url:
            self.app.notify("Kein Baum vorhanden.", severity="warning")
            return

        lines = ["graph TD"]
        node_ids: dict[str, str] = {}
        counter = 0

        # BFS: Alle Kanten sammeln
        visited: set[str] = {self._root_url}
        queue: deque[str] = deque([self._root_url])

        # Root-Knoten registrieren
        node_id = f"N{counter}"
        counter += 1
        root_path = self._get_path(self._root_url)
        node_ids[self._root_url] = node_id
        lines.append(f'    {node_id}["{root_path}"]')

        while queue:
            url = queue.popleft()
            parent_id = node_ids[url]

            for child_url in self._children.get(url, []):
                if child_url not in visited:
                    visited.add(child_url)
                    child_id = f"N{counter}"
                    counter += 1
                    child_path = self._get_path(child_url)
                    node_ids[child_url] = child_id
                    lines.append(f'    {parent_id} --> {child_id}["{child_path}"]')
                    queue.append(child_url)

        text = "\n".join(lines)
        self.app.copy_to_clipboard(text)
        self.app.notify(f"Mermaid-Diagramm kopiert ({counter} Knoten)")

    def action_copy_ascii(self) -> None:
        """Kopiert den Seitenbaum als ASCII-Baum in die Zwischenablage."""
        if not self._root_url:
            self.app.notify("Kein Baum vorhanden.", severity="warning")
            return

        lines: list[str] = []
        root_result = self._url_to_result.get(self._root_url)
        root_code = root_result.http_status_code if root_result else 0
        lines.append(f"[{root_code}] {self._root_url}")

        self._build_ascii_subtree(self._root_url, "", lines, set())

        text = "\n".join(lines)
        self.app.copy_to_clipboard(text)
        node_count = len(lines)
        self.app.notify(f"ASCII-Baum kopiert ({node_count} Knoten)")

    def _build_ascii_subtree(
        self,
        url: str,
        prefix: str,
        lines: list[str],
        visited: set[str],
    ) -> None:
        """Baut rekursiv den ASCII-Teilbaum auf.

        Args:
            url: Aktuelle URL.
            prefix: Einrueckung fuer die aktuelle Ebene.
            lines: Sammlung aller Zeilen.
            visited: Bereits besuchte URLs (Zykluserkennung).
        """
        visited.add(url)
        children = [
            c for c in self._children.get(url, [])
            if c not in visited
        ]

        for i, child_url in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = f"{prefix}    " if is_last else f"{prefix}│   "

            result = self._url_to_result.get(child_url)
            code = result.http_status_code if result else 0
            lines.append(f"{prefix}{connector}[{code}] {child_url}")

            self._build_ascii_subtree(child_url, child_prefix, lines, visited)

    def _get_path(self, url: str) -> str:
        """Extrahiert den Pfad (+Query) aus einer URL.

        Args:
            url: Die vollstaendige URL.

        Returns:
            Pfad-String (mit Query falls vorhanden).
        """
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        # Anfuehrungszeichen escapen fuer Mermaid
        return path.replace('"', '\\"')

    def action_expand_all(self) -> None:
        """Klappt alle Knoten im Baum auf."""
        tree_widget = self.query_one("#site-tree", Tree)
        tree_widget.root.expand_all()
        self.app.notify("Baum aufgeklappt")

    def action_collapse_all(self) -> None:
        """Klappt alle Knoten im Baum zu."""
        tree_widget = self.query_one("#site-tree", Tree)
        tree_widget.root.collapse_all()
        # Root wieder aufklappen damit man etwas sieht
        tree_widget.root.expand()
        self.app.notify("Baum eingeklappt")

    def action_close(self) -> None:
        """Schliesst den Dialog."""
        self.dismiss()
