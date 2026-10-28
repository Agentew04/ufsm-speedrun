"""Configuração central do projeto.

Tudo que é caminho/constante mora aqui, com override por variável de ambiente.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("UFSM_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = Path(os.environ.get("UFSM_DB_PATH", DATA_DIR / "ufsm.db"))
REQUESTS_LOG = LOG_DIR / "requests.jsonl"

# --- SIE webservice ---------------------------------------------------------
BASE_URL = "https://portal.ufsm.br/webservice/ws/site"
SITE_URL = "https://www.ufsm.br"

# Header obrigatório. Sem ele o webservice responde 200 com
# {"error": true, "codigo": 500, "mensagem": "Acesso não autorizado"}.
APP_ID_HEADERS = {"X-UFSM-Application-ID": "SiteWS"}

USER_AGENT = "ufsm-speedrun/0.1 (projeto academico UFSM)"

# --- Política de acesso (ver docs/ufsm-api.md §12) --------------------------
MIN_INTERVAL = 1.75      # segundos entre requests de rede (sem paralelismo)
TIMEOUT = 120            # segundos
MAX_ATTEMPTS = 4         # tentativas por request em caso de 429/5xx/timeout
BACKOFF_BASE = 1.0       # 1, 2, 4, 8 s
