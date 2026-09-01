# url-shortener

API que recebe uma URL longa, devolve um código curto de sete caracteres, e redireciona esse código
de volta ao destino registrando cada acesso.

Projeto de estudo e portfólio, escrito para praticar Python, FastAPI, PostgreSQL, Testcontainers e
CI — e para que cada decisão de desenho seja defensável, uma por uma.

> **Em construção.** O roadmap está em [`docs/PROGRESS-V1.md`](docs/PROGRESS-V1.md), e o que ficou
> de fora de propósito, em [`docs/PROGRESS-V2.md`](docs/PROGRESS-V2.md). Este README ganha o
> diagrama do fluxo e a tabela do que ficou de fora na última fase.

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
- [ADR-0004](docs/adr/0004-fronteira-sem-objeto-de-dominio.md) — a fronteira da aplicação não carrega objeto de domínio
- [ADR-0005](docs/adr/0005-corpo-de-requisicao-sem-httpurl.md) — o corpo do `POST /links` carrega uma string, e não um `HttpUrl`
- [ADR-0006](docs/adr/0006-envelope-de-erro-problem-details.md) — todo erro da API sai no mesmo envelope Problem Details
- [ADR-0007](docs/adr/0007-fronteira-da-transacao.md) — a transação commita antes de a resposta ser enviada
- [ADR-0008](docs/adr/0008-health-responde-503-no-mesmo-envelope.md) — o `/health` responde `503` no mesmo envelope
- [ADR-0009](docs/adr/0009-migracao-e-passo-de-deploy.md) — a migração é um passo do deploy, e não do startup

## Como rodar

Precisa de Docker, e de mais nada — nem Python instalado, nem `.env`, nem migration na mão.

```bash
docker compose up
```

Sobem três coisas, nesta ordem: o PostgreSQL, um serviço que aplica as migrations e sai, e a API na
porta 8000. A API só é iniciada depois de a migration ter saído com sucesso, então uma migration que
falha impede o servidor de subir em vez de deixá-lo responder sobre um schema que não existe
([ADR-0009](docs/adr/0009-migracao-e-passo-de-deploy.md)).

A documentação interativa fica em <http://localhost:8000/docs>, e é a interface deste projeto: não
há front-end porque não é preciso um.

O fluxo inteiro, de fora:

```bash
# cria o link -- 201 Created, e o Location aponta para os metadados
curl -sS -X POST localhost:8000/links -H 'content-type: application/json' \
     -d '{"url": "https://www.example.com/a/very/long/path"}'

# segue o código -- 302 Found, Location: https://www.example.com/a/very/long/path
curl -i localhost:8000/0000001

# o que ficou registrado, inclusive o total de acessos
curl -sS localhost:8000/links/0000001
```

Para derrubar tudo, incluindo o volume do banco: `docker compose down -v`.

### Sem Docker, para desenvolver

```bash
cp .env.example .env                             # DATABASE_URL e BASE_URL, sem default
uv sync                                          # dependências
docker compose up -d postgres                    # só o banco
uv run alembic upgrade head                      # o schema
uv run uvicorn url_shortener.main:app --reload   # a API, na 8000
uv run pytest                                    # suíte rápida; -m integration para a de Docker
```

O `cp` é a primeira linha e não é opcional: `Settings` não tem default para nenhuma das duas
variáveis, e tanto o Alembic quanto a aplicação leem o mesmo objeto. Sem `.env`, os dois param com
um `ValidationError` do pydantic em vez de rodarem contra o banco errado — que é o comportamento
desejado, e a razão de o caminho com Docker acima não precisar de arquivo nenhum: lá as duas
variáveis vêm do `compose.yml`.
