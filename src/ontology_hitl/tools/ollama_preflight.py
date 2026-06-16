"""Pre-flight Ollama model availability check.

Called once at agent initialisation so pipeline runs fail *immediately*
with a clear message instead of silently timing out 15 minutes later.

The check is intentionally lightweight:
- A single GET to ``/api/tags`` (lists pulled models) — fast, no inference.
- If the model is pulled but not loaded, that's fine; Ollama will load it
  on first inference.  We only hard-fail when the model isn't pulled at all.
- Results are cached per (url, model) pair so the HTTP call fires only once
  per process even when multiple agents share the same settings.
- Errors are *warnings* by default (``raise_on_failure=False``) so that
  unit tests and offline runs are not broken.  The runner scripts and
  BaseAgent set ``raise_on_failure=True`` for production use.
"""

from __future__ import annotations

from typing import NamedTuple

import structlog

logger = structlog.get_logger(__name__)

# Cache: (url, model) → ModelCheckResult — prevents repeated HTTP calls when
# OntologyEngineer, DomainExpert, Critic, Reasoner all call BaseAgent.__init__
_CHECKED: dict[tuple[str, str], "ModelCheckResult"] = {}


class ModelCheckResult(NamedTuple):
    ok: bool
    model: str
    ollama_url: str
    available_models: list[str]
    loaded_models: list[str]
    message: str


def check_ollama_model(
    ollama_url: str,
    model: str,
    *,
    timeout: float = 5.0,
    raise_on_failure: bool = False,
) -> ModelCheckResult:
    """Verify *model* is pulled on the Ollama instance at *ollama_url*.

    Results are cached per (url, model) pair — subsequent calls with the same
    arguments return immediately without any network I/O.

    Parameters
    ----------
    ollama_url:
        Base URL of the Ollama server, e.g. ``http://localhost:18134``.
    model:
        Model name to check, e.g. ``gemma4:e4b``.
    timeout:
        HTTP request timeout in seconds.
    raise_on_failure:
        When ``True``, raises ``RuntimeError`` if the model is unavailable.
        When ``False`` (default), logs a warning and returns the result.

    Returns
    -------
    ModelCheckResult
        Named tuple with ``ok``, ``model``, ``ollama_url``,
        ``available_models``, ``loaded_models``, and a human-readable
        ``message``.
    """
    cache_key = (ollama_url.rstrip("/"), model)
    if cache_key in _CHECKED:
        cached = _CHECKED[cache_key]
        if not cached.ok and raise_on_failure:
            raise RuntimeError(cached.message)
        return cached
    available: list[str] = []
    loaded: list[str] = []

    try:
        import httpx

        base = ollama_url.rstrip("/")

        # 1. Check pulled models (/api/tags)
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base}/api/tags")
            resp.raise_for_status()
            available = [m["name"] for m in resp.json().get("models", [])]

        # 2. Check loaded models (/api/ps) — best-effort
        try:
            with httpx.Client(timeout=timeout) as client:
                ps = client.get(f"{base}/api/ps")
                if ps.status_code == 200:
                    loaded = [m["name"] for m in ps.json().get("models", [])]
        except Exception:
            pass  # /api/ps is non-critical

    except Exception as exc:
        msg = (
            f"Ollama pre-flight failed: cannot reach {ollama_url} "
            f"({type(exc).__name__}: {exc}). "
            f"Is the container running?"
        )
        result = ModelCheckResult(
            ok=False, model=model, ollama_url=ollama_url,
            available_models=[], loaded_models=[], message=msg,
        )
        _CHECKED[cache_key] = result
        _handle_result(result, raise_on_failure)
        return result

    # Normalise: Ollama tags may include digest suffix (model:tag@sha256:…)
    def _base_name(n: str) -> str:
        return n.split("@")[0]

    available_base = [_base_name(n) for n in available]
    loaded_base = [_base_name(n) for n in loaded]

    if model not in available_base:
        # Build a helpful hint
        close = [n for n in available_base if model.split(":")[0] in n]
        hint = f" Available: {available_base}." + (
            f" Did you mean one of: {close}?" if close else ""
        )
        msg = (
            f"Model '{model}' is not pulled on {ollama_url}.{hint}\n"
            f"Fix: docker exec <container> ollama pull {model}"
        )
        result = ModelCheckResult(
            ok=False, model=model, ollama_url=ollama_url,
            available_models=available_base, loaded_models=loaded_base,
            message=msg,
        )
        _CHECKED[cache_key] = result
        _handle_result(result, raise_on_failure)
        return result

    hot = model in loaded_base
    msg = (
        f"Model '{model}' ready on {ollama_url} "
        f"({'loaded in VRAM' if hot else 'pulled, will load on first call'})."
    )
    result = ModelCheckResult(
        ok=True, model=model, ollama_url=ollama_url,
        available_models=available_base, loaded_models=loaded_base,
        message=msg,
    )
    _CHECKED[cache_key] = result
    logger.debug("ollama_preflight_ok", model=model, url=ollama_url, hot=hot)
    return result


def _handle_result(result: ModelCheckResult, raise_on_failure: bool) -> None:
    if not result.ok:
        logger.warning("ollama_preflight_failed", message=result.message)
        if raise_on_failure:
            raise RuntimeError(result.message)
