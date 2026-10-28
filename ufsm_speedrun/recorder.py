"""Gravação de tudo que passa pela rede.

Objetivo: permitir (a) auditoria, (b) cache local, (c) reconstruir o banco sem
refazer o crawl.

Layout em disco:

    data/
      raw/<endpoint_slug>/<request_key>.json   <- envelope request+response
      logs/requests.jsonl                      <- auditoria append-only (sem corpo)

O arquivo em `raw/` é a fonte da verdade: contém exatamente o que foi pedido e o
que voltou. Qualquer ETL futuro lê apenas esses arquivos.

Os arquivos são imutáveis por chave: a mesma requisição sempre cai no mesmo
caminho. `--refresh` sobrescreve.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, endpoints

RAW_SCHEMA = "ufsm-sie-raw/1"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Recorder:
    raw_dir: Path = config.RAW_DIR
    log_path: Path = config.REQUESTS_LOG

    # ------------------------------------------------------------------ chave
    @staticmethod
    def key_for(method: str, url: str, params: dict[str, Any] | None,
                json_body: dict[str, Any] | None = None) -> str:
        """Chave estável da requisição (independente da ordem dos params)."""
        payload = {
            "method": method.upper(),
            "url": url,
            "params": params or {},
            "json_body": json_body or {},
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return _sha256(canonical)[:16]

    # ------------------------------------------------------------- caminhos
    def raw_path(self, endpoint: str, key: str) -> Path:
        return self.raw_dir / endpoints.slug_for(endpoint) / f"{key}.json"

    # ---------------------------------------------------------------- cache
    def load(self, endpoint: str, key: str) -> dict[str, Any] | None:
        path = self.raw_path(endpoint, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # arquivo corrompido: trata como ausente e refaz
            return None

    def save(self, endpoint: str, key: str, envelope: dict[str, Any]) -> Path:
        path = self.raw_path(endpoint, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # atômico: nunca deixa arquivo pela metade
        return path

    # ------------------------------------------------------------------ log
    def append_log(self, entry: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    # ---------------------------------------------------------- estatísticas
    def count_raw(self) -> int:
        if not self.raw_dir.exists():
            return 0
        return sum(1 for _ in self.raw_dir.rglob("*.json"))

    def count_log(self) -> int:
        if not self.log_path.exists():
            return 0
        with self.log_path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)


def build_envelope(*, method: str, url: str, params: dict[str, Any] | None,
                   request_headers: dict[str, str], status: int,
                   response_headers: dict[str, str], body: str,
                   endpoint: str, key: str, elapsed_ms: int, attempts: int) -> dict[str, Any]:
    return {
        "schema": RAW_SCHEMA,
        "request": {
            "method": method.upper(),
            "url": url,
            "params": params or {},
            "headers": request_headers,
        },
        "response": {
            "status": status,
            "headers": response_headers,
            "encoding": "utf-8",
            "bytes": len(body.encode("utf-8")),
            "body_sha256": _sha256(body),
            "body": body,
        },
        "meta": {
            "endpoint": endpoint,
            "key": key,
            "fetched_at": utc_now(),
            "elapsed_ms": elapsed_ms,
            "attempts": attempts,
            "ok": 200 <= status < 300,
            "from_cache": False,
        },
    }
