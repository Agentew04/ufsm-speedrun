"""Cliente HTTP para o webservice do SIE.

Regras embutidas (docs/ufsm-api.md §12):
  * 1 request por vez, intervalo mínimo entre chamadas de rede;
  * cache em disco — chamada repetida não vai na rede;
  * retry com backoff exponencial em 429/5xx/timeout/erro de rede;
  * toda request e response é gravada em data/raw/.
"""

from __future__ import annotations

import json
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

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

    # ------------------------------------------------------------------- call
    def call(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        json_body: bool = False,
        method: str = "POST",
    ) -> Result:
        params = params or {}
        url = endpoints.url_for(endpoint)
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
                self._log(f"  [cache] {endpoint} {params}")
                return Result(json.loads(envelope["response"]["body"]), envelope["meta"], True, self.stats)

        # ------------------------------------------------- chamada de verdade
        request_headers = {
            **config.APP_ID_HEADERS,
            "Accept": "application/json",
            "User-Agent": config.USER_AGENT,
        }
        if json_body:
            data = json.dumps(params, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        else:
            data = urllib.parse.urlencode(params).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

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

                size_kb = len(raw) / 1024
                self._log(f"  [{self.stats.network_calls:>3}] {endpoint} {params} "
                          f"-> {status} {size_kb:.0f} KB {elapsed_ms} ms")

                data_json = json.loads(body)
                if isinstance(data_json, dict) and data_json.get("error") is True:
                    raise UfsmApiError(data_json.get("mensagem") or "erro não especificado")
                return Result(data_json, envelope["meta"], False, self.stats)

            except urllib.error.HTTPError as exc:  # 4xx/5xx
                self._last_call_at = time.monotonic()
                status = exc.code
                last_error = exc
                self.stats.errors += 1
                if status in (429, 500, 502, 503, 504) and attempt < self.max_attempts:
                    wait = config.BACKOFF_BASE * (2 ** (attempt - 1))
                    self.stats.retries += 1
                    self._log(f"  [{endpoint}] HTTP {status}, tentativa {attempt}/{self.max_attempts}, "
                              f"aguardando {wait:.0f}s")
                    time.sleep(wait)
                    continue
                raise UfsmHttpError(f"HTTP {status} em {endpoint} {params}") from exc

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
                raise UfsmHttpError(f"falha de rede em {endpoint} {params}: {exc}") from exc

        raise UfsmHttpError(f"desisti de {endpoint} {params}: {last_error}")
