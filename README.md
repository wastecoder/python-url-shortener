# url-shortener

API que recebe uma URL longa, devolve um código curto de sete caracteres, e redireciona esse código
de volta ao destino registrando cada acesso.

Projeto de estudo e portfólio, escrito para praticar Python, FastAPI, PostgreSQL, Testcontainers e
CI — e para que cada decisão de desenho seja defensável, uma por uma.

> **Em construção.** O roadmap está em [`docs/PROGRESS-V1.md`](docs/PROGRESS-V1.md), e o que ficou
> de fora de propósito, em [`docs/PROGRESS-V2.md`](docs/PROGRESS-V2.md). Este README ganha o
> diagrama do fluxo, o passo a passo para subir e a seção de decisões na última fase.

## Escopo

Quatro rotas, e nada além delas:

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/links` | recebe a URL longa, devolve o código e a URL curta |
| `GET` | `/{code}` | redireciona com `302`, registrando o acesso |
| `GET` | `/links/{code}` | destino, data de criação e total de acessos |
| `GET` | `/health` | estado do serviço |

O que ficou de fora — expiração, alias customizado, estatísticas, autenticação, limite de taxa,
cache e fila — foi cortado de propósito, e cada corte tem uma justificativa registrada.

## Stack

Python 3.13 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic · PostgreSQL · pytest ·
Testcontainers · Docker · Ruff · mypy · import-linter · GitHub Actions

## Decisões

O porquê de cada escolha estrutural está em [`docs/adr/`](docs/adr/):

- [ADR-0001](docs/adr/0001-redirect-302.md) — o redirect é `302`, e não `301`
- [ADR-0002](docs/adr/0002-base62-sobre-a-sequence.md) — base 62 sobre a sequence, e não hash da URL
- [ADR-0003](docs/adr/0003-sem-fila.md) — sem fila, e o lugar exato onde ela entraria

## Como rodar

Ainda não há o que rodar. Chega na Fase 6 do roadmap, com um `docker compose up`.
