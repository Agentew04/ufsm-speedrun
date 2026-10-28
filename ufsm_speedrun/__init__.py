"""ufsm-speedrun: mapeamento das rotas de graduação da UFSM.

Fases:
    0  esqueleto: cliente HTTP polido + log/cache em disco + esquema SQLite
    1  descoberta de cursos e versões de currículo
    2  crawl das árvores curriculares
    3  pré-requisitos e equivalências
    4  ementas (catálogo global de disciplinas)
    5  validação e ETL para o banco
    6  equivalência heurística + otimizador de rota + dashboard web
"""

__version__ = "0.1.0"
