"""Seitenbaum als eingebettetes Widget (frueher: Modal TreeScreen).

Baut den Baum aus den `parent_url`-Beziehungen der CrawlResults. Der Filter
der UrlTable wird auf den Baum mit angewendet — passende Knoten plus ihre
Vorfahren bleiben sichtbar, der Rest verschwindet.
"""

from __future__ import annotations

import contextlib
from collections import defaultdict, deque
from urllib.parse import quote, unquote, urlparse, urlunparse

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree

from ..i18n import t
from ..models.crawl_result import CrawlResult, PageStatus


def _canon(url: str) -> str:
    """Kanonische Form einer URL fuer Set-Vergleiche.

    Lowercases scheme/netloc, normalisiert Percent-Encoding und entfernt das
    Fragment. Wird sowohl fuer Eintraege in ``_known_urls`` als auch fuer
    Redirect-Targets benutzt, damit eine httpx-Antwort-URL und eine ueber
    den Link-Extraktor entdeckte URL auch dann als gleich erkannt werden,
    wenn das Encoding minimal abweicht.
    """
    try:
        p = urlparse(url)
    except Exception:
        return url
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    path = quote(unquote(p.path), safe="/:@!$&'*+,;=-._~") or "/"
    query = quote(unquote(p.query), safe="/:@!$&'*+,;=-._~?=")
    return urlunparse((scheme, netloc, path, p.params, query, ""))


class PageTree(Widget):
    """Eingebetteter Seitenbaum.

    Wird im "Baumansicht / Struktur"-Tab der `UrlTable` angezeigt.
    Verlorenen Modal-Funktionen wie Mermaid-/ASCII-Export sind als Methoden
    erhalten und koennen spaeter ueber ein Kontextmenue freigeschaltet werden.
    """

    DEFAULT_CSS = """
    PageTree {
        height: 1fr;
    }
    PageTree #site-tree {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._results: list[CrawlResult] = []
        self._start_url: str = ""
        self._sitemap_urls: set[str] = set()
        self._filter_text: str = ""
        self._url_to_result: dict[str, CrawlResult] = {}
        self._children: dict[str, list[str]] = defaultdict(list)
        self._parent_of: dict[str, str] = {}
        self._root_url: str = ""
        self._dirty: bool = False  # Daten geaendert, aber noch nicht gerendert

    def compose(self) -> ComposeResult:
        yield Tree(t("tree.root_label"), id="site-tree")

    def on_mount(self) -> None:
        # Falls set_data() vor dem Mount aufgerufen wurde: jetzt rendern.
        if self._dirty:
            self._rebuild()

    # --- Public API --------------------------------------------------

    def set_data(
        self,
        results: list[CrawlResult],
        start_url: str,
        sitemap_urls: set[str] | None = None,
    ) -> None:
        """Setzt die zugrundeliegenden Daten und baut den Baum neu auf.

        Args:
            results:
                Alle gecrawlten Ergebnisse.
            start_url:
                Start-URL des Crawls (Wurzel des Baums).
            sitemap_urls:
                Optional: URLs aus der offiziellen sitemap.xml — wird zur
                Markierung von "nicht-in-sitemap"-Knoten verwendet.
        """
        self._results = results
        self._start_url = start_url
        self._sitemap_urls = sitemap_urls or set()
        self._dirty = True
        if self.is_mounted:
            # Auf den naechsten Refresh-Tick verschieben — sonst kann
            # `query_one("#site-tree", Tree)` waehrend Layout-Phasen
            # fehlschlagen und die Aktualisierung still verloren gehen.
            self.call_after_refresh(self._rebuild)

    def apply_filter(self, filter_text: str) -> None:
        """Filtert den Baum nach demselben Text wie die URL-Tabelle.

        Args:
            filter_text:
                Suchbegriff (Substring auf URL / Status / HTTP-Code).
                Leerer Text zeigt den vollstaendigen Baum.
        """
        new_filter = filter_text or ""
        if new_filter == self._filter_text:
            return
        self._filter_text = new_filter
        self._dirty = True
        if self.is_mounted:
            self.call_after_refresh(self._rebuild)

    def clear(self) -> None:
        """Leert den Baum."""
        self._results = []
        self._url_to_result = {}
        self._children = defaultdict(list)
        self._parent_of = {}
        self._root_url = ""
        self._dirty = True
        if self.is_mounted:
            self._rebuild()

    # --- Daten-Aufbau ------------------------------------------------

    def _build_data(self) -> None:
        """Baut die parent->children-Lookup-Strukturen aus den Results."""
        self._url_to_result = {}
        self._children = defaultdict(list)
        self._parent_of = {}
        for r in self._results:
            self._url_to_result[r.url] = r
            if r.parent_url:
                self._children[r.parent_url].append(r.url)
                self._parent_of[r.url] = r.parent_url
        # Geschwister alphabetisch sortieren — vorher war die Reihenfolge
        # vom Crawl-Abschluss diktiert und damit zufaellig.
        for parent in self._children:
            self._children[parent].sort()
        # Wurzel ermitteln in 3 Stufen — soll auch dann eine Wurzel finden,
        # wenn start_url und result.url leicht unterschiedlich normalisiert
        # sind (Encoding, Trailing-Slash).
        start_c = _canon(self._start_url) if self._start_url else ""
        self._root_url = ""
        if self._start_url in self._url_to_result:
            self._root_url = self._start_url
        elif start_c:
            for u in self._url_to_result:
                if _canon(u) == start_c:
                    self._root_url = u
                    break
        if not self._root_url:
            for r in self._results:
                if not r.parent_url:
                    self._root_url = r.url
                    break
        if not self._root_url and self._results:
            # Letzte Rettung: einfach das erste Ergebnis nehmen, damit der
            # Baum etwas anzeigt statt "Keine Daten".
            self._root_url = self._results[0].url

    def _is_dup_redirect(self, url: str) -> bool:
        """Interner Redirect, dessen Ziel sowieso schon im Baum vorhanden ist.

        Gleicher Filter wie in der URL-Tabelle — z.B. /kontakt -> /kontakt/ —
        damit derselbe Knoten nicht doppelt erscheint.
        """
        result = self._url_to_result.get(url)
        if result is None or result.status != PageStatus.REDIRECT:
            return False
        target = (result.redirect_url or "").split("#", 1)[0]
        if not target or target == url:
            return False
        target_c = _canon(target)
        return any(_canon(u) == target_c for u in self._url_to_result)

    def _matches_filter(self, url: str) -> bool:
        """Substring-Match auf URL / Statuscode / Status-Name."""
        if not self._filter_text:
            return True
        search = self._filter_text.lower()
        if search in url.lower():
            return True
        r = self._url_to_result.get(url)
        if r is not None:
            if search in str(r.http_status_code):
                return True
            if search in r.status.value.lower():
                return True
        return False

    def _visible_urls(self) -> set[str]:
        """URLs, die unter dem aktuellen Filter im Baum erscheinen sollen.

        Match = Knoten selbst + alle Vorfahren bis zur Wurzel (sonst koennten
        passende Knoten ohne erkennbaren Pfad im Baum erscheinen).
        """
        if not self._filter_text:
            # Auch ohne Text-Filter: Duplikat-Redirects nicht zeigen.
            visible_all = {u for u in self._url_to_result if not self._is_dup_redirect(u)}
            if self._root_url:
                visible_all.add(self._root_url)
            return visible_all
        visible: set[str] = set()
        for url in self._url_to_result:
            if self._is_dup_redirect(url):
                continue
            if not self._matches_filter(url):
                continue
            cur: str | None = url
            while cur is not None and cur not in visible:
                visible.add(cur)
                cur = self._parent_of.get(cur)
        if visible and self._root_url:
            visible.add(self._root_url)
        return visible

    def _rebuild(self) -> None:
        """Rendert den Tree neu — nur aufrufen wenn gemountet."""
        try:
            tree = self.query_one("#site-tree", Tree)
        except Exception:
            return
        self._dirty = False
        self._build_data()
        tree.reset(t("tree.root_label"))

        if not self._root_url or not self._results:
            tree.root.set_label(t("tree.no_data"))
            tree.root.expand()
            return

        visible = self._visible_urls()
        if self._root_url not in visible:
            tree.root.set_label(t("tree.no_data"))
            tree.root.expand()
            return

        root_result = self._url_to_result.get(self._root_url)
        tree.root.set_label(self._make_label(self._root_url, root_result))
        tree.root.data = self._root_url
        tree.root.expand()

        visited: set[str] = {self._root_url}
        queue: deque[tuple] = deque()
        for child in self._children.get(self._root_url, []):
            if child in visible and child not in visited:
                queue.append((tree.root, child))
                visited.add(child)
        while queue:
            parent_node, url = queue.popleft()
            r = self._url_to_result.get(url)
            # Hat dieser Knoten ueberhaupt sichtbare Kinder? Sonst kein
            # Expand-Dreieck am Eintrag.
            visible_children = [c for c in self._children.get(url, []) if c in visible and c not in visited]
            node = parent_node.add(
                self._make_label(url, r),
                data=url,
                allow_expand=bool(visible_children),
            )
            for child in visible_children:
                queue.append((node, child))
                visited.add(child)

        # Erste Ebene aufklappen — bei aktivem Filter alles aufklappen.
        if self._filter_text:
            tree.root.expand_all()
        else:
            for child in tree.root.children:
                child.expand()

    def _make_label(self, url: str, result: CrawlResult | None) -> Text:
        """Baut das Knoten-Label mit Farbcodierung (gleiche Logik wie zuvor im Modal)."""
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        if not result:
            return Text(f"? {path}")

        icon = result.status_icon
        code = result.http_status_code

        if result.is_external_redirect:
            label = Text(f"{icon} ", style="dim")
            label.append(f"[{code}]", style="dim")
            label.append(f" {path}", style="dim")
            label.append(" -> (extern)", style="dim italic")
            return label

        if result.status == PageStatus.REDIRECT:
            label = Text(f"{icon} ")
            label.append(f"[{code}]", style="cyan")
            label.append(f" {path}")
            return label

        if code >= 400:
            style = "bold red"
        elif code >= 200:
            style = "green"
        else:
            style = ""

        not_in_sitemap = self._sitemap_urls and code == 200 and result.url not in self._sitemap_urls

        label = Text(f"{icon} ")
        label.append(f"[{code}]", style=style)
        if not_in_sitemap:
            label.append(f" {path}", style="dark_orange")
        else:
            label.append(f" {path}")
        return label

    # --- Auswahl im Baum -> Detail-Panel der App ----------------------

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Reicht eine markierte URL als UrlTable.UrlHighlighted weiter.

        So zeigt das rechte Detail-Panel beim Durchnavigieren im Baum
        dieselben Informationen wie beim Cursor-Wechsel in der Tabelle.
        """
        url = getattr(event.node, "data", None)
        if not isinstance(url, str):
            return
        result = self._url_to_result.get(url)
        if result is None:
            return
        # Lazy-Import, damit page_tree nicht zyklisch von url_table abhaengt.
        from .url_table import UrlTable

        self.post_message(UrlTable.UrlHighlighted(result))

    # --- Bequeme Aktionen --------------------------------------------

    def expand_all(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#site-tree", Tree).root.expand_all()

    def collapse_all(self) -> None:
        with contextlib.suppress(Exception):
            tree = self.query_one("#site-tree", Tree)
            tree.root.collapse_all()
            tree.root.expand()
