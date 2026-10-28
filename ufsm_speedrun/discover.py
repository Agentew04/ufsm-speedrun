"""Fase 1 — descoberta de cursos e versões de currículo.

Não busca nada do webservice: lê apenas HTML de duas páginas por curso.

    https://www.ufsm.br/graduacao                          -> lista dos cursos
    .../cursos/graduacao/<campus>/<slug>/informacoes-do-curriculo
                                                          -> IDs de curso + versões

O HTML da página de currículo já traz o JSON completo de cada versão dentro do
atributo `data-versao` de cada <option> (ver docs/ufsm-api.md §9).
"""

from __future__ import annotations

import html as htmlmod
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from . import config
from .http import UfsmClient
from .recorder import utc_now

CAMPUS_LABEL = {
    "santa-maria": "Santa Maria",
    "cachoeira-do-sul": "Cachoeira do Sul",
    "frederico-westphalen": "Frederico Westphalen",
    "palmeira-das-missoes": "Palmeira das Missões",
    "educacao-a-distancia": "EaD",
}

# prioridade de escolha da versão "vigente" para análise
PRIORIDADE_SITUACAO = ("C", "A", "I")


@dataclass(frozen=True)
class CursoRef:
    """Um link de curso da página /graduacao."""

    campus_slug: str
    slug: str
    url: str
    nome_lista: str

    @property
    def campus(self) -> str:
        return CAMPUS_LABEL.get(self.campus_slug, self.campus_slug)


@dataclass
class Discovery:
    refs: list[CursoRef] = field(default_factory=list)
    versoes: dict[int, dict] = field(default_factory=dict)  # id -> JSON VersaoCurso
    erros: list[str] = field(default_factory=list)


# --------------------------------------------------------------------- parsing
def parse_course_list(html: str) -> list[CursoRef]:
    """Extrai os links de curso de #lista_cursos (href sem aspas, cuidado)."""
    soup = BeautifulSoup(html, "html.parser")
    refs: dict[str, CursoRef] = {}
    for a in soup.select("#lista_cursos a[href]"):
        href = (a.get("href") or "").strip()
        m = re.match(r"^/cursos/graduacao/([^/]+)/([^/]+)/?$", href)
        if not m:
            continue
        campus_slug, slug = m.group(1), m.group(2)
        url = f"{config.SITE_URL}{href.rstrip('/')}/"
        if url in refs:
            continue
        refs[url] = CursoRef(
            campus_slug=campus_slug,
            slug=slug,
            url=url,
            nome_lista=(a.get("title") or a.get_text(strip=True) or "").strip(),
        )
    return list(refs.values())


def parse_curriculum_page(html: str) -> list[dict]:
    """Extrai os JSONs de versão embutidos em <option data-versao='...'>."""
    versoes: dict[int, dict] = {}

    soup = BeautifulSoup(html, "html.parser")
    for opt in soup.select("option[data-versao]"):
        blob = opt.get("data-versao") or ""
        try:
            versao = json.loads(htmlmod.unescape(blob))
        except json.JSONDecodeError:
            continue
        if isinstance(versao, dict) and "id" in versao:
            versoes[versao["id"]] = versao

    # fallback: regex no HTML cru, caso o parser tenha engolido o atributo
    if not versoes:
        for blob in re.findall(r"data-versao='([^']+)'", html):
            try:
                versao = json.loads(htmlmod.unescape(blob))
            except json.JSONDecodeError:
                continue
            if isinstance(versao, dict) and "id" in versao:
                versoes[versao["id"]] = versao

    return list(versoes.values())


# ------------------------------------------------------------------ coleta
def discover(client: UfsmClient, *, limit: int | None = None) -> Discovery:
    resultado = Discovery()

    pagina = client.get_page(f"{config.SITE_URL}/graduacao")
    resultado.refs = parse_course_list(pagina.data)
    if not resultado.refs:
        raise RuntimeError("nenhum curso encontrado em #lista_cursos — o layout mudou?")

    alvos = resultado.refs[:limit] if limit else resultado.refs
    print(f"\n{len(alvos)} páginas de currículo para visitar "
          f"({len(resultado.refs)} cursos na lista)\n", flush=True)

    for i, ref in enumerate(alvos, 1):
        url = f"{ref.url}informacoes-do-curriculo"
        try:
            resp = client.get_page(url)
            versoes = parse_curriculum_page(resp.data)
        except Exception as exc:  # noqa: BLE001 - segue o baile, registra e continua
            resultado.erros.append(f"{url}: {exc}")
            print(f"  !! falhou {ref.slug}: {exc}", flush=True)
            continue

        if not versoes:
            resultado.erros.append(f"{url}: nenhuma versão encontrada")
            print(f"  !! sem versões {ref.slug}", flush=True)
            continue

        for versao in versoes:
            versao["_origem"] = {
                "campus": ref.campus,
                "campus_slug": ref.campus_slug,
                "slug": ref.slug,
                "nome_lista": ref.nome_lista,
            }
            resultado.versoes[versao["id"]] = versao

        if client.verbose:
            print(f"  {i:>3}/{len(alvos)} {ref.campus_slug}/{ref.slug} "
                  f"-> {len(versoes)} versão(ões)", flush=True)

    return resultado


# ------------------------------------------------------------------ persistência
def _ano(numero: str) -> int:
    """Extrai o ano de `numero`, que nem sempre é numérico.

    Exemplos reais: "2024", "92", "2021/2", "2020.2", ".", "INATIV".
    """
    m = re.search(r"(\d{4})", str(numero or ""))
    return int(m.group(1)) if m else -1


def escolher_versao(versoes: list[dict]) -> dict | None:
    """Corrente; se não houver, a Ativa mais recente; senão a Inativa mais recente."""
    for codigo in PRIORIDADE_SITUACAO:
        candidatas = [v for v in versoes if (v.get("situacao") or {}).get("codigo") == codigo]
        if candidatas:
            return max(candidatas, key=lambda v: _ano(v.get("numero", "")))
    return max(versoes, key=lambda v: _ano(v.get("numero", ""))) if versoes else None


def persist(conn: sqlite3.Connection, discovery: Discovery) -> dict:
    por_curso: dict[int, list[dict]] = defaultdict(list)
    for versao in discovery.versoes.values():
        por_curso[versao["curso"]["id"]].append(versao)

    for curso_id, versoes in por_curso.items():
        curso = versoes[0]["curso"]
        origem = versoes[0].get("_origem") or {}

        conn.execute(
            """
            INSERT INTO curso (id, codigo, nome, nome_lista, nome_unificado, grau, modalidade,
                               turno, nivel_item, classificacao, area_conhecimento,
                               unidade_sigla, codigo_emec, url, campus, campus_slug, slug)
            VALUES (:id, :codigo, :nome, :nome_lista, :nome_unificado, :grau, :modalidade,
                    :turno, :nivel, :classificacao, :area, :unidade, :emec, :url,
                    :campus, :campus_slug, :slug)
            ON CONFLICT(id) DO UPDATE SET
                codigo = excluded.codigo, nome = excluded.nome,
                nome_lista = excluded.nome_lista, nome_unificado = excluded.nome_unificado,
                grau = excluded.grau, modalidade = excluded.modalidade,
                turno = excluded.turno, nivel_item = excluded.nivel_item,
                classificacao = excluded.classificacao,
                area_conhecimento = excluded.area_conhecimento,
                unidade_sigla = excluded.unidade_sigla, codigo_emec = excluded.codigo_emec,
                url = excluded.url, campus = excluded.campus,
                campus_slug = excluded.campus_slug, slug = excluded.slug
            """,
            {
                "id": curso_id,
                "codigo": curso.get("codigo"),
                "nome": curso.get("descricao") or "",
                "nome_lista": origem.get("nome_lista"),
                "nome_unificado": curso.get("nomeUnificado"),
                "grau": curso.get("grau"),
                "modalidade": (curso.get("modalidade") or {}).get("descricao"),
                "turno": (curso.get("turno") or {}).get("descricao"),
                "nivel": (curso.get("nivel") or {}).get("item"),
                "classificacao": (curso.get("classificacao") or {}).get("descricao"),
                "area": (curso.get("areaConhecimento") or {}).get("descricao"),
                "unidade": (curso.get("unidade") or {}).get("sigla"),
                "emec": curso.get("codigoEmec"),
                "url": (curso.get("url") or "").strip() or None,
                "campus": origem.get("campus"),
                "campus_slug": origem.get("campus_slug"),
                "slug": origem.get("slug"),
            },
        )

        for versao in versoes:
            conn.execute(
                """
                INSERT INTO versao_curriculo
                    (id, curso_id, numero, ano, situacao_codigo, situacao, ch_total,
                     ch_extensao, ch_min_periodo, ch_max_periodo, periodo_ideal,
                     periodo_minimo, periodo_maximo, tipo_periodo_item, tipo_periodo,
                     trancamentos_totais, trancamentos_parciais)
                VALUES (:id, :curso_id, :numero, :ano, :situacao_codigo, :situacao, :ch_total,
                        :ch_extensao, :ch_min_periodo, :ch_max_periodo, :periodo_ideal,
                        :periodo_minimo, :periodo_maximo, :tipo_periodo_item, :tipo_periodo,
                        :tranc_totais, :tranc_parciais)
                ON CONFLICT(id) DO UPDATE SET
                    numero = excluded.numero, ano = excluded.ano,
                    situacao_codigo = excluded.situacao_codigo, situacao = excluded.situacao,
                    ch_total = excluded.ch_total, ch_extensao = excluded.ch_extensao,
                    ch_min_periodo = excluded.ch_min_periodo,
                    ch_max_periodo = excluded.ch_max_periodo,
                    periodo_ideal = excluded.periodo_ideal,
                    periodo_minimo = excluded.periodo_minimo,
                    periodo_maximo = excluded.periodo_maximo,
                    tipo_periodo_item = excluded.tipo_periodo_item,
                    tipo_periodo = excluded.tipo_periodo,
                    trancamentos_totais = excluded.trancamentos_totais,
                    trancamentos_parciais = excluded.trancamentos_parciais
                """,
                {
                    "id": versao["id"],
                    "curso_id": curso_id,
                    "numero": str(versao.get("numero") or ""),
                    "ano": _ano(versao.get("numero", "")),
                    "situacao_codigo": (versao.get("situacao") or {}).get("codigo"),
                    "situacao": (versao.get("situacao") or {}).get("descricao"),
                    "ch_total": versao.get("cargaHorariaTotal"),
                    "ch_extensao": versao.get("cargaHorariaExtensao"),
                    "ch_min_periodo": versao.get("cargaHorariaMinima"),
                    "ch_max_periodo": versao.get("cargaHorariaMaxima"),
                    "periodo_ideal": versao.get("periodoIdeal"),
                    "periodo_minimo": versao.get("periodoMinimo"),
                    "periodo_maximo": versao.get("periodoMaximo"),
                    "tipo_periodo_item": (versao.get("tipoPeriodo") or {}).get("item"),
                    "tipo_periodo": ((versao.get("tipoPeriodo") or {}).get("descricao") or "").strip(),
                    "tranc_totais": versao.get("trancamentosTotais"),
                    "tranc_parciais": versao.get("trancamentosParciais"),
                },
            )

        # versão vigente para análise
        escolhida = escolher_versao(versoes)
        if escolhida:
            conn.execute(
                "UPDATE versao_curriculo SET selecionada = 0 WHERE curso_id = ?", (curso_id,)
            )
            conn.execute(
                "UPDATE versao_curriculo SET selecionada = 1 WHERE id = ?", (escolhida["id"],)
            )

    conn.commit()
    return por_curso


# --------------------------------------------------------------------- relatório
def relatorio(conn: sqlite3.Connection, discovery: Discovery, por_curso: dict) -> None:
    cursos = conn.execute("SELECT COUNT(*) FROM curso").fetchone()[0]
    versoes = conn.execute("SELECT COUNT(*) FROM versao_curriculo").fetchone()[0]
    selecionadas = conn.execute(
        "SELECT COUNT(*) FROM versao_curriculo WHERE selecionada = 1"
    ).fetchone()[0]

    print("\n" + "=" * 72)
    print("RELATÓRIO — FASE 1")
    print("=" * 72)
    print(f"  links em /graduacao ........ {len(discovery.refs)}")
    print(f"  cursos no banco ............ {cursos}")
    print(f"  versões no banco ........... {versoes}")
    print(f"  versões selecionadas ....... {selecionadas}")

    print("\n  por campus:")
    for campus, n in conn.execute(
        "SELECT campus, COUNT(*) FROM curso GROUP BY campus ORDER BY COUNT(*) DESC"
    ):
        print(f"    {campus or '(sem campus)':<24} {n:>3} cursos")

    print("\n  situações das versões:")
    for situacao, n in conn.execute(
        "SELECT situacao, COUNT(*) FROM versao_curriculo GROUP BY situacao ORDER BY COUNT(*) DESC"
    ):
        print(f"    {situacao or '(sem situação)':<24} {n:>3}")

    fallback = conn.execute(
        """
        SELECT c.nome, v.numero, v.situacao
        FROM versao_curriculo v JOIN curso c ON c.id = v.curso_id
        WHERE v.selecionada = 1 AND v.situacao_codigo IS NOT 'C'
        ORDER BY c.nome
        """
    ).fetchall()
    print(f"\n  selecionadas SEM situação 'Corrente' (fallback): {len(fallback)}")
    for row in fallback:
        print(f"    - {row[0][:48]:<48} {row[1]} ({row[2]})")

    sem_versao = [c for c, vs in por_curso.items() if not vs]
    if sem_versao:
        print(f"\n  ATENÇÃO: {len(sem_versao)} cursos sem versão")

    if discovery.erros:
        print(f"\n  erros de coleta: {len(discovery.erros)}")
        for erro in discovery.erros[:10]:
            print(f"    - {erro}")

    top = conn.execute(
        """
        SELECT c.nome, COUNT(*) AS n
        FROM versao_curriculo v JOIN curso c ON c.id = v.curso_id
        GROUP BY c.id ORDER BY n DESC LIMIT 5
        """
    ).fetchall()
    print("\n  cursos com mais versões (histórico):")
    for nome, n in top:
        print(f"    {nome[:52]:<52} {n}")
    print()
