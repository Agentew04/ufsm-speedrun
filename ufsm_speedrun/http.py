"""Cliente HTTP do projeto (webservice SIE + páginas HTML do portal).

Regras embutidas (docs/ufsm-api.md §12):
  * 1 request por vez, intervalo mínimo entre chamadas de rede;
  * cache em disco — chamada repetida não vai na rede;
  * retry com backoff exponencial em 429/5xx/timeout/erro de rede;
  * toda request e response é gravada em data/raw/.
"""

from __future__ import annotations

import json
import random
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from . import config, endpoints
from .recorder import Recorder, build_envelope, utc_now


class UfsmApiError(RuntimeError):
    """O webservice respondeu 200 mas com envelope {"error": true}."""


class UfsmHttpError(RuntimeError):
    """Falha de rede/HTTP depois de esgotar as tentativas."""


@dataclass
class Stats:
    network_calls: int = 0
    cache_hits: int = 0
    bytes_downloaded: int = 0
    retries: int = 0
    errors: int = 0

    def summary(self) -> str:
        return (f"rede={self.network_calls} cache={self.cache_hits} "
                f"retries={self.retries} erros={self.errors} "
                f"baixado={self.bytes_downloaded / 1024 / 1024:.1f} MB")


@dataclass
class Result:
    data: Any
    meta: dict[str, Any]
    from_cache: bool
    stats: Stats = field(repr=False, default_factory=Stats)


def page_slug(url: str) -> str:
    """Nome de pasta legível para uma página: .../santa-maria/x/informacoes-do-curriculo
    -> 'cursos_graduacao_santa-maria_x_informacoes-do-curriculo'."""
    path = urlparse(url).path.strip("/")
    slug = re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")
    return (slug or "root")[:90]


class UfsmClient:
    def __init__(
        self,
        recorder: Recorder | None = None,
        *,
        min_interval: float = config.MIN_INTERVAL,
        timeout: int = config.TIMEOUT,
        max_attempts: int = config.MAX_ATTEMPTS,
        refresh: bool = False,
        verbose: bool = True,
    ) -> None:
        self.recorder = recorder or Recorder()
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.refresh = refresh
        self.verbose = verbose
        self.stats = Stats()
        self._last_call_at: float | None = None

    # ------------------------------------------------------------------ utils
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def _wait_turn(self) -> None:
        """Respeita o intervalo mínimo entre chamadas de rede."""
        if self._last_call_at is None:
            return
        elapsed = time.monotonic() - self._last_call_at
        remaining = self.min_interval + random.uniform(0.0, 0.35) - elapsed
        if remaining > 0:
            time.sleep(remaining)

    # -------------------------------------------------------------- atalhos
    def call(self, endpoint: str, params: dict[str, Any] | None = None,
             *, json_body: bool = False) -> Result:
        """POST no webservice do SIE."""
        return self.fetch("POST", endpoints.url_for(endpoint), params or {},
                          endpoint=endpoint, json_body=json_body)

    def get_page(self, url: str) -> Result:
        """GET em uma página HTML do portal (sem header do SIE)."""
        return self.fetch("GET", url, {}, endpoint=page_slug(url),
                          send_app_id=False, parse_json=False)

    # ------------------------------------------------------------------- core
    def fetch(
        self,
        method: str,
        url: str,
        params: dict[str, Any],
        *,
        endpoint: str,
        json_body: bool = False,
        send_app_id: bool = True,
        parse_json: bool = True,
    ) -> Result:
        method = method.upper()
        key = Recorder.key_for(method, url, params)

        # ---------------------------------------------------- cache em disco
        if not self.refresh:
            envelope = self.recorder.load(endpoint, key)
            if envelope is not None:
                self.stats.cache_hits += 1
                self.recorder.append_log({
                    "ts": utc_now(), "endpoint": endpoint, "key": key,
                    "method": method, "url": url, "params": params,
                    "from_cache": True, "status": envelope["response"]["status"],
                    "bytes": envelope["response"]["bytes"], "elapsed_ms": 0,
                })
                cached_body = envelope["response"]["body"]
                data = json.loads(cached_body) if parse_json else cached_body
                return Result(data, envelope["meta"], True, self.stats)

        # ------------------------------------------------- cabeçalhos e corpo
        request_headers = {
            "Accept": "application/json" if send_app_id else "text/html,application/xhtml+xml",
            "User-Agent": config.USER_AGENT,
        }
        if send_app_id:
            request_headers.update(config.APP_ID_HEADERS)

        data: bytes | None = None
        if method == "POST":
            if json_body:
                data = json.dumps(params, ensure_ascii=False).encode("utf-8")
                request_headers["Content-Type"] = "application/json"
            else:
                data = urllib.parse.urlencode(params).encode("utf-8")
                request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        # ------------------------------------------------- chamada de verdade
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._wait_turn()
            started = time.monotonic()
            try:
                req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    status = resp.status
                    resp_headers = {k: v for k, v in resp.headers.items()}
                    charset = resp.headers.get_content_charset()

                body = raw.decode(charset or "utf-8", "replace")
                self._last_call_at = time.monotonic()
                self.stats.network_calls += 1
                self.stats.bytes_downloaded += len(raw)

                envelope = build_envelope(
                    method=method, url=url, params=params, request_headers=request_headers,
                    status=status, response_headers=resp_headers, body=body,
                    endpoint=endpoint, key=key, elapsed_ms=elapsed_ms, attempts=attempt,
                )
                path = self.recorder.save(endpoint, key, envelope)
                self.recorder.append_log({
                    "ts": utc_now(), "endpoint": endpoint, "key": key, "method": method,
                    "url": url, "params": params, "from_cache": False, "status": status,
                    "bytes": len(raw), "elapsed_ms": elapsed_ms, "attempts": attempt,
                    "raw_file": str(path.relative_to(config.DATA_DIR)),
                    "body_sha256": envelope["response"]["body_sha256"],
                })

                self._log(f"  [{self.stats.network_calls:>3}] {endpoint[:52]:<52} "
                          f"-> {status} {len(raw)/1024:.0f} KB {elapsed_ms} ms")

                if parse_json:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict) and parsed.get("error") is True:
                        raise UfsmApiError(parsed.get("mensagem") or "erro não especificado")
                else:
                    parsed = body
                return Result(parsed, envelope["meta"], False, self.stats)

            except urllib.error.HTTPError as exc:  # 4xx/5xx
                self._last_call_at = time.monotonic()
                last_error = exc
                self.stats.errors += 1
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.max_attempts:
                    wait = config.BACKOFF_BASE * (2 ** (attempt - 1))
                    self.stats.retries += 1
                    self._log(f"  [{endpoint}] HTTP {exc.code}, tentativa {attempt}/"
                              f"{self.max_attempts}, aguardando {wait:.0f}s")
                    time.sleep(wait)
                    continue
                raise UfsmHttpError(f"HTTP {exc.code} em {url}") from exc

            except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
                self._last_call_at = time.monotonic()
                last_error = exc
                self.stats.errors += 1
                if attempt < self.max_attempts:
                    wait = config.BACKOFF_BASE * (2 ** (attempt - 1))
                    self.stats.retries += 1
                    self._log(f"  [{endpoint}] falha de rede ({exc}), tentativa {attempt}/"
                              f"{self.max_attempts}, aguardando {wait:.0f}s")
                    time.sleep(wait)
                    continue
                raise UfsmHttpError(f"falha de rede em {url}: {exc}") from exc

        raise UfsmHttpError(f"desisti de {url}: {last_error}")
