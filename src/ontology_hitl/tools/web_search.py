"""Limited, safe web search for the DomainExpert agent.

Design constraints
------------------
* **No API key required** — uses DuckDuckGo Lite HTML search and the
  public Wikipedia REST API.
* **Allowlist-restricted** — only retrieves content from a curated
  list of trusted domain/encyclopedic sources to prevent prompt injection
  from arbitrary web pages.
* **Rate-limited** — maximum ``max_queries`` calls per review call
  (default 3) and a hard per-request ``timeout`` (default 5 s).
* **Truncated output** — each result is capped at ``max_chars``
  characters (default 500) so the LLM context stays bounded.
* **Fail-safe** — any network error or unexpected response silently
  returns an empty result; it never raises.

Intended use
------------
The DomainExpert calls :meth:`DomainWebSearch.search_for_concept`
for a handful of proposed ontology terms it cannot ground from
the local document corpus. The returned :class:`WebSearchResult`
snippets are injected as an extra evidence block in the review prompt.

Security note
-------------
Results are plain-text snippets extracted from trusted sources only.
HTML tags are stripped. URLs are validated against the allowlist before
any content is fetched. This prevents SSRF to internal services and
limits prompt-injection surface.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Sequence

import structlog

logger = structlog.get_logger(__name__)

# ── Allowlist ───────────────────────────────────────────────────────────────
# Only these domains are trusted for content retrieval.
# DuckDuckGo/Wikipedia result URLs are checked against this list before fetch.
_ALLOWED_DOMAINS: frozenset[str] = frozenset(
    [
        "en.wikipedia.org",
        "www.wikidata.org",
        "www.w3.org",
        "schema.org",
        "dbpedia.org",
        "purl.org",
        "ontologyportal.org",         # SUMO
        "geneontology.org",
        "obofoundry.org",
        "bioportal.bioontology.org",
        "lov.linkeddata.es",
        "bartoc.org",
        "iate.europa.eu",             # EU terminology
    ]
)

# ── Blocked patterns (even on allowlisted domains) ────────────────────────────
# Prevents the agent from "peeking" at the actual ontologies it is trying to
# reproduce (no ground-truth leakage) and blocks raw OWL/RDF file downloads
# that could inject structured ontology content into agent prompts.
#
# Rule 1 — file extensions:  any URL whose path ends with one of these is
#   rejected before a network request is made.
_BLOCKED_EXTENSIONS: frozenset[str] = frozenset([
    ".rdf", ".owl", ".ttl", ".n3", ".nt", ".nq",
    ".jsonld", ".ofn", ".omn", ".obo", ".owx",
])

# Rule 2 — W3C Technical Report path prefixes for reproduction targets:
#   www.w3.org/TR/owl-guide  → Wine OWL 1.0 guide (contains wine.rdf)
#   www.w3.org/TR/owl-time   → OWL-Time (reproduction target)
#   www.w3.org/TR/prov-o     → PROV-O (reproduction target)
#   www.w3.org/TR/prov-*     → PROV family (primer, constraints, …)
_BLOCKED_W3C_TR_PATHS: frozenset[str] = frozenset([
    "/tr/owl-guide",
    "/tr/owl-time",
    "/tr/prov-o",
    "/tr/prov-primer",
    "/tr/prov-constraints",
    "/tr/prov-n",
    "/tr/prov-dm",
    "/tr/prov-sem",
    "/tr/prov-aq",
    "/tr/prov-xml",
    "/tr/prov-links",
])

# Maximum snippet length returned per result
_DEFAULT_MAX_CHARS = 500
# Maximum number of web requests per DomainExpert review call
_DEFAULT_MAX_QUERIES = 3
# Per-request timeout in seconds
_DEFAULT_TIMEOUT = 5


# ── Result type ─────────────────────────────────────────────────────────────


@dataclass
class WebSearchResult:
    """A single retrieved evidence snippet."""

    query: str
    source: str           # URL
    title: str
    snippet: str          # Plain-text, stripped, truncated
    from_cache: bool = False

    def to_prompt_block(self) -> str:
        return f"[Web: {self.title}]\n{self.snippet}\n(source: {self.source})"


# ── HTML stripping ───────────────────────────────────────────────────────────


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from *text*."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _is_allowed_url(url: str) -> bool:
    """Return True only if *url* is on the trusted allowlist and not blocked.

    Checks (in order):
    1. Domain must be in :data:`_ALLOWED_DOMAINS`.
    2. File extension must not be in :data:`_BLOCKED_EXTENSIONS` (no raw
       ontology files — prevents ground-truth leakage for reproduction runs).
    3. For ``www.w3.org``, the path must not match a W3C TR reproduction-target
       path listed in :data:`_BLOCKED_W3C_TR_PATHS`.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()

        # Rule 0: domain allowlist
        if not any(host == d or host.endswith("." + d) for d in _ALLOWED_DOMAINS):
            return False

        # Rule 1: block raw ontology file extensions
        if any(path.endswith(ext) for ext in _BLOCKED_EXTENSIONS):
            logger.debug("web_search_blocked_extension", url=url)
            return False

        # Rule 2: block W3C TR paths for reproduction targets
        if host in ("www.w3.org", "w3.org"):
            if any(path.startswith(prefix) for prefix in _BLOCKED_W3C_TR_PATHS):
                logger.debug("web_search_blocked_w3c_tr", url=url)
                return False

        return True
    except Exception:
        return False


# ── DomainWebSearch ──────────────────────────────────────────────────────────


class DomainWebSearch:
    """Fetch grounding evidence for ontology concepts from trusted web sources.

    Parameters
    ----------
    max_queries:
        Hard cap on how many HTTP requests may be made per :meth:`batch_search`
        call. Prevents runaway queries during a single review.
    max_chars:
        Maximum characters returned per snippet.
    timeout:
        Per-request HTTP timeout in seconds.
    extra_allowed_domains:
        Additional domain names to allow (e.g. a project-specific wiki).
    """

    def __init__(
        self,
        max_queries: int = _DEFAULT_MAX_QUERIES,
        max_chars: int = _DEFAULT_MAX_CHARS,
        timeout: float = _DEFAULT_TIMEOUT,
        extra_allowed_domains: Sequence[str] = (),
    ) -> None:
        self.max_queries = max_queries
        self.max_chars = max_chars
        self.timeout = timeout
        self._allowed = _ALLOWED_DOMAINS | frozenset(extra_allowed_domains)
        self._cache: dict[str, WebSearchResult | None] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def search_for_concept(self, concept: str) -> WebSearchResult | None:
        """Search for a single ontology *concept* and return the best snippet.

        Tries Wikipedia summary API first; falls back to DuckDuckGo Lite.
        Returns ``None`` on any error or if no allowed-domain result is found.
        """
        key = concept.lower().strip()
        if key in self._cache:
            r = self._cache[key]
            if r is not None:
                r = WebSearchResult(
                    query=r.query, source=r.source, title=r.title,
                    snippet=r.snippet, from_cache=True,
                )
            return r

        result = self._wikipedia_summary(concept) or self._ddg_search(concept)
        self._cache[key] = result
        return result

    def batch_search(self, concepts: list[str]) -> list[WebSearchResult]:
        """Search for multiple concepts, respecting the ``max_queries`` cap.

        Concepts are deduped and limited to ``max_queries`` items.
        Already-cached hits do not count against the cap.
        """
        seen: set[str] = set()
        results: list[WebSearchResult] = []
        network_calls = 0

        for concept in concepts:
            key = concept.lower().strip()
            if key in seen or not key:
                continue
            seen.add(key)

            cached = self._cache.get(key, _SENTINEL)
            if cached is not _SENTINEL:
                if cached is not None:
                    results.append(cached)  # type: ignore[arg-type]
                continue

            if network_calls >= self.max_queries:
                logger.debug("web_search_cap_reached", cap=self.max_queries)
                break

            r = self._wikipedia_summary(concept) or self._ddg_search(concept)
            self._cache[key] = r
            network_calls += 1
            if r:
                results.append(r)

        return results

    def format_for_prompt(self, results: list[WebSearchResult]) -> str:
        """Format a list of results as a compact prompt evidence block."""
        if not results:
            return ""
        lines = ["=== Web Evidence (limited, trusted sources only) ==="]
        for r in results:
            lines.append(r.to_prompt_block())
        return "\n\n".join(lines)

    # ── Backend: Wikipedia REST summary ──────────────────────────────────────

    def _wikipedia_summary(self, concept: str) -> WebSearchResult | None:
        """Fetch the Wikipedia article summary for *concept* (no API key)."""
        try:
            import httpx

            title = concept.replace(" ", "_")
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "OntologyExtender/1.0"})
            if resp.status_code != 200:
                return None
            data = resp.json()
            extract = _strip_html(data.get("extract", ""))[: self.max_chars]
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", url)
            if not extract:
                return None
            logger.debug("web_search_wikipedia_hit", concept=concept)
            return WebSearchResult(
                query=concept,
                source=page_url,
                title=data.get("title", concept),
                snippet=extract,
            )
        except Exception as exc:
            logger.debug("web_search_wikipedia_error", concept=concept, error=str(exc))
            return None

    # ── Backend: DuckDuckGo Lite HTML (no API key) ────────────────────────────

    def _ddg_search(self, concept: str) -> WebSearchResult | None:
        """Scrape DuckDuckGo Lite for *concept* and return the first
        allowlisted result.

        DuckDuckGo Lite is a plain-HTML endpoint that doesn't require
        JavaScript or API keys. We extract only <a> + adjacent text from
        the result list and filter by the domain allowlist.
        """
        try:
            import httpx

            params = {"q": concept, "kl": "en-us"}
            url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode(params)
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "OntologyExtender/1.0"})
            if resp.status_code != 200:
                return None

            # Extract result links and snippets with a minimal regex
            # DDG Lite HTML: <a class="result-link" href="...">Title</a> … snippet text
            hits = re.findall(
                r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>.*?<td[^>]*>(.*?)</td>',
                resp.text,
                re.DOTALL,
            )
            for href, title_html, snippet_html in hits:
                if not _is_allowed_url(href):
                    continue
                title = _strip_html(title_html)
                snippet = _strip_html(snippet_html)[: self.max_chars]
                if not snippet:
                    continue
                logger.debug("web_search_ddg_hit", concept=concept, url=href)
                return WebSearchResult(
                    query=concept, source=href, title=title, snippet=snippet
                )
        except Exception as exc:
            logger.debug("web_search_ddg_error", concept=concept, error=str(exc))
        return None


# Sentinel for cache miss (distinct from cached None)
_SENTINEL = object()
