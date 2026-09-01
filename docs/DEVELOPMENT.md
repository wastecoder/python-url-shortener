# Desenvolvimento

Como pôr isto para rodar na sua máquina, quais comandos existem e onde no código está cada coisa
que você pode querer mudar.

> A **arquitetura** está em [`ARCHITECTURE.md`](ARCHITECTURE.md); o **contrato HTTP** em
> [`API.md`](API.md); a **estratégia de teste** em [`TESTS.md`](TESTS.md). Aqui não há justificativa
> de decisão — isso mora nos [ADRs](README.md#adrs).

- [1. Pré-requisitos](#1-pré-requisitos)
- [2. Subir o ambiente](#2-subir-o-ambiente)
- [3. Comandos](#3-comandos)
- [4. URLs úteis](#4-urls-úteis)
- [5. Configuração](#5-configuração)
- [6. Migrations](#6-migrations)
- [7. A imagem](#7-a-imagem)
- [8. O pipeline](#8-o-pipeline)
- [9. Onde achar as coisas no código](#9-onde-achar-as-coisas-no-código)
- [10. Convenções](#10-convenções)
- [11. Referências](#11-referências)

## 1. Pré-requisitos

| Caminho | O que precisa |
|---|---|
| **Rodar** | Docker com Compose. E mais nada — nem Python instalado, nem `.env`, nem migration na mão |
| **Desenvolver** | [uv](https://docs.astral.sh/uv/) e Docker. O Python 3.13 é provisionado pelo próprio uv, a partir do `.python-version` |

O `uv` gerencia o interpretador, a virtualenv e as dependências. **Nunca ative a `.venv` à mão e
nunca chame `pip` diretamente** — `uv run` cuida da ativação.

## 2. Subir o ambiente

### 2.1 Com Docker, que é o caminho padrão

```bash
docker compose up
```

Sobem três serviços, **nesta ordem**, e a ordem é o mecanismo:

| Serviço | O que faz | Espera por |
|---|---|---|
| `postgres` | PostgreSQL `18.6-alpine`, volume nomeado | — |
| `migrate` | A mesma imagem da API com `alembic upgrade head`. Roda e sai | `postgres: service_healthy` |
| `api` | `uvicorn` na porta 8000 | `postgres: service_healthy` **e** `migrate: service_completed_successfully` |

A segunda condição é sobre **código de saída**, e não sobre tempo: uma migration que falha impede a
API de subir, em vez de deixá-la responder `500` sobre um schema que não existe.
[ADR-0009](adr/0009-migracao-e-passo-de-deploy.md).

```bash
docker compose up -d --wait     # espera tudo ficar saudavel; sai com 1 se algo falhar
docker compose ps -a            # migrate deve aparecer como Exited (0)
docker compose logs migrate     # a revisao que rodou
docker compose down -v          # derruba tudo, inclusive o volume do banco
```

O `--wait` é o que torna isso verificável num script: com a migration quebrada, o comando sai com
código **1**.

### 2.2 Sem Docker, para desenvolver

```bash
cp .env.example .env                             # DATABASE_URL e BASE_URL, sem default
uv sync                                          # dependencias
docker compose up -d postgres                    # so o banco
uv run alembic upgrade head                      # o schema
uv run uvicorn url_shortener.main:app --reload   # a API, na 8000
```

**O `cp` é a primeira linha e não é opcional.** `Settings` não tem default para nenhuma das duas
variáveis, e tanto o Alembic quanto a aplicação leem o mesmo objeto. Sem `.env`, os dois param com um
`ValidationError` do Pydantic em vez de rodarem contra o banco errado — que é o comportamento
desejado, e a razão de o caminho com Docker acima não precisar de arquivo nenhum: lá as duas
variáveis vêm do `compose.yml`.

## 3. Comandos

| Tarefa | Comando |
|---|---|
| Instalar / sincronizar dependências | `uv sync` |
| Acrescentar dependência | `uv add <pkg>` — de desenvolvimento: `uv add --dev <pkg>` |
| Rodar a API local | `uv run uvicorn url_shortener.main:app --reload` |
| Testes rápidos (sem Docker) | `uv run pytest` |
| Testes de integração (precisa de Docker) | `uv run pytest -m integration` |
| Tudo | `uv run pytest -m ""` |
| Cobertura | `uv run pytest --cov=src/url_shortener --cov-report=term-missing` |
| Lint | `uv run ruff check .` — corrigir: `uv run ruff check --fix .` |
| Formatação | `uv run ruff format .` |
| Tipos | `uv run mypy` |
| Contratos de arquitetura | `uv run lint-imports` |
| Aplicar migrations | `uv run alembic upgrade head` |
| Nova migration | `uv run alembic revision --autogenerate -m "<mensagem>"` |
| Ambiente completo | `docker compose up -d` — derrubar: `docker compose down -v` |

Duas armadilhas nessa tabela:

- **`uv run mypy`, nunca `uv run mypy src`.** Um caminho explícito sobrescreve o `files` do
  `pyproject.toml` e derruba `tests` e `migrations` da checagem em silêncio — e é em `tests/fakes.py`
  que a conformidade estrutural com as portas é declarada. Uma declaração que nenhum verificador lê
  não prova nada.
- **`ruff format` também processa Markdown**, formatando os blocos de código Python dentro dele.
  Então `ruff format --check .` no CI cobre os trechos do `README.md` e dos documentos daqui, e não
  só `src/` e `tests/` — um exemplo mal formatado num documento deixa o pipeline vermelho.
  `docs/learning/` fica de fora porque está no `.gitignore`.

### Antes de abrir um PR

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
uv run pytest -m ""
uv run coverage report --fail-under=100
```

### Caveat conhecido — a pasta sincronizada em nuvem

Este repositório vive dentro de uma pasta sincronizada. A `.venv/` guarda dezenas de milhares de
arquivos pequenos, então o cliente de sincronização é lento sobre ela e ocasionalmente tranca um
arquivo no meio de uma escrita — o que aparece como uma falha do `uv sync` que **parece** um bug do
uv. Se o uv começar a se comportar de forma estranha, pause a sincronização e tente de novo antes de
depurar qualquer outra coisa.

O `UV_PROJECT_ENVIRONMENT` **não** é usado como contorno: é variável global, então apontá-la para um
caminho absoluto faria todos os projetos uv da máquina compartilharem um ambiente só.

## 4. URLs úteis

| Recurso | URL |
|---|---|
| Swagger UI — **a interface deste projeto** | <http://localhost:8000/docs> |
| ReDoc | <http://localhost:8000/redoc> |
| Documento OpenAPI | <http://localhost:8000/openapi.json> |
| Health | <http://localhost:8000/health> |
| PostgreSQL | `localhost:5432`, banco/usuário/senha `url_shortener` |

```bash
docker compose exec postgres psql -U url_shortener -d url_shortener
```

## 5. Configuração

Duas variáveis, ambas obrigatórias, ambas sem default:

| Variável | Para quê | Valor no `.env.example` |
|---|---|---|
| `DATABASE_URL` | DSN do PostgreSQL usado pelo SQLAlchemy | `postgresql+psycopg://url_shortener:url_shortener@localhost:5432/url_shortener` |
| `BASE_URL` | Origem pública de onde as URLs curtas são montadas, sem barra no fim | `http://localhost:8000` |

Valores vêm de variáveis de ambiente reais primeiro, e de um `.env` local depois. O modelo usa
`extra="forbid"`, então uma chave desconhecida no `.env` é erro.

O esquema do DSN é `postgresql+psycopg://` — SQLAlchemy 2.0 com **psycopg 3**, não `psycopg2`.

Dentro do `compose.yml` a DSN aponta para o host `postgres` (o nome do serviço), e não para
`localhost`. Por isso o compose **não** usa `env_file: .env`: o `.env` de quem seguiu o
`.env.example` aponta para `localhost:5432`, que dentro de um container é o próprio container.

## 6. Migrations

O schema vem **só** de migrations Alembic — nunca de `Base.metadata.create_all()`, nem nos testes. O
`create_all` não aparece em lugar nenhum do projeto.

```bash
uv run alembic upgrade head                             # aplicar
uv run alembic revision --autogenerate -m "<mensagem>"  # gerar a partir dos modelos
uv run alembic current                                  # em que revisao o banco esta
uv run alembic history                                  # o que existe
```

**Ao acrescentar uma entidade nova, acrescente-a também a `adapter/persistence/entity/__init__.py`.**
O `migrations/env.py` importa aquele pacote para popular o `Base.metadata`; uma entidade fora do
`__init__` é uma tabela que o `--autogenerate` propõe **derrubar**.

Toda revisão gerada precisa ser lida antes de ser commitada: o `--autogenerate` compara metadados e
não sabe o que você quis dizer. Existe um teste de integração que roda `alembic check` contra o
`Base.metadata` — ele pega o schema divergindo dos modelos, mas não pega uma migration que faz a
coisa errada de forma consistente.

**Reverter é comando na mão** (`uv run alembic downgrade -1`), e não existe serviço de `downgrade` no
compose. Com uma revisão só isso é adequado; na décima vira dívida.

## 7. A imagem

```bash
docker build -t url-shortener:0.1.0 .
docker run --rm url-shortener:0.1.0 id     # uid=10001(app)
```

Multi-stage, dois estágios, e **os dois com o mesmo `FROM`** (`python:3.13-slim-bookworm`). O uv
entra como binário copiado de uma tag fixa (`ghcr.io/astral-sh/uv:0.12.7`), e não como imagem base —
porque uma virtualenv guarda o **caminho absoluto** do interpretador que a criou, e um builder e um
runtime com Pythons diferentes produzem uma `.venv` que copia limpo e depois não sobe.

Pontos que valem saber ao mexer:

- **`--no-editable` no segundo `uv sync`** é o que permite o estágio final não carregar `src/`. No
  modo padrão a venv guardaria um ponteiro para `/app/src`, que não existe na imagem final, e a
  falha chegaria como `ImportError` no start do container.
- **`--locked` nos dois `uv sync`** transforma um `uv.lock` desatualizado em erro de build, em vez de
  numa imagem construída a partir de uma resolução que ninguém revisou.
- **O `COPY` do runtime não usa `--chown`.** Os arquivos ficam de `root` e o usuário `app` tem
  exatamente o que usa: ler e executar, sem poder reescrever o código que executa.
- **A porta `8000` aparece duas vezes** — no `CMD` e no `HEALTHCHECK` — porque o `HEALTHCHECK` não
  enxerga a porta do `CMD`. Mudar uma exige mudar a outra.
- **Sem `--workers`.** Um container é um processo; quantos deles rodam é contagem de réplica, e isso
  pertence a quem escalona containers, não à imagem.

## 8. O pipeline

GitHub Actions, em todo pull request e em todo push para `main`. **Três jobs, sem `needs:` entre
eles** — um erro de lint e um redirect quebrado são fatos independentes, e um PR que tem os dois deve
ser informado dos dois de uma vez.

| Job | O que roda |
|---|---|
| `check` | `ruff check` · `ruff format --check` · `mypy` · `lint-imports` · testes unitários · gate de cobertura de `domain` + `application` |
| `integration` | Toda a suíte contra um PostgreSQL de verdade (Testcontainers) · gate de cobertura da árvore inteira |
| `image` | Constrói a imagem, sobe os três serviços com `up -d --wait` e exercita `POST /links` → `GET /{code}` → `GET /links/{code}` pela porta publicada |

**Os dois primeiros rodam o código; o terceiro roda o artefato.** Um `docker build` sozinho provaria
que a imagem compila — não que a migration rodou antes do servidor, não que o usuário não-root
consegue ler o que precisa, e não que o `BASE_URL` chega na resposta.

**Não há bloco `services:` em lugar nenhum do workflow**, de propósito: o `ubuntu-latest` já roda um
daemon Docker, e o Testcontainers sobe, migra e joga fora o próprio PostgreSQL de dentro da sessão de
teste.

A branch `main` é protegida e exige o check do CI — **e não exige review**, que é impossível de
satisfazer sozinho. O merge é restrito a **rebase**, para o histórico de um-conceito-por-commit
sobreviver em vez de virar uma linha só. O `enforce_admins` está ligado: sem ele, o dono do
repositório passaria por cima com um clique e "o CI barra o merge" seria frase decorativa.

## 9. Onde achar as coisas no código

| Quero mudar… | Vá em |
|---|---|
| O alfabeto, o comprimento do código | `domain/service/base62.py` |
| O que é aceito como destino | `domain/service/url_policy.py` |
| A chave da deduplicação | `domain/service/url_hash.py` |
| As invariantes de `Link` / `Click` | `domain/model/` |
| O fluxo da deduplicação | `application/usecase/create_link_use_case.py` |
| O que o redirect registra | `application/usecase/resolve_link_use_case.py` |
| O que a API aceita e devolve | `adapter/web/dto/` |
| Uma rota, um status, um header | `adapter/web/*_controller.py` |
| O mapeamento erro → status | `adapter/web/handler/problem_details.py` |
| A taxonomia de `type` | `adapter/web/handler/problem_type.py` |
| O SQL | `adapter/persistence/*_repository_impl.py` |
| Colunas e constraints | `adapter/persistence/entity/` + `migrations/versions/` |
| A engine, o pool, o timeout | `adapter/persistence/database/session.py` |
| A ligação porta → implementação | `adapter/config/dependencies.py` |
| A fronteira da transação | `adapter/config/dependencies.py`, em `get_session` |
| Uma configuração nova | `adapter/config/settings.py` **e** `.env.example` **e** `compose.yml` |
| A ordem de registro das rotas | `main.py`, em `create_app` |
| O que o OpenAPI mostra | `main.py`, em `_describe_errors_accurately` |
| Os contratos de dependência | `.importlinter` — e mexer aqui exige um ADR |

## 10. Convenções

### Idioma

**Código em inglês** — módulos, classes, funções, variáveis, tabelas, colunas, comentários, logs,
mensagens de commit, nomes de branch, títulos de PR. **Documentação em português** — tudo sob `docs/`
e o `README.md` da raiz.

### Commits

Conventional Commits, estritamente: `<tipo>(<escopo opcional>): <resumo imperativo em minúsculas>`.

Tipos aceitos: `feat`, `fix`, `refactor`, `test`, `docs`, `build`, `ci`, `chore`, `perf`, `style`.

O escopo acompanha o layout (`domain`, `application`, `web`, `persistence`, `config`, `db`, `deps`)
ou a ferramenta de que o commit trata (`adr`, `progress`, `github`, `docker`, `compose`, `alembic`,
`uv`, `lint`, `mypy`).

```text
feat(domain): add base62 encoding with fixed-length 7 output
fix(web): register the catch-all redirect route after /links and /health
test(integration): assert the redirect records a row in click
docs(adr): record why the redirect is 302 and not 301
```

**Um conceito por commit**, porque o que é revisado é o diff e não o arquivo pronto. Nunca um commit
gigante: o histórico é parte do que está sendo avaliado.

**Trailer de coautoria é proibido** — nenhum `Co-Authored-By:`, de ninguém, e nenhum "Generated
with". A autoria de todo commit é exclusivamente do usuário.

### Branches e pull requests

Nada entra direto na `main`. Uma branch e um PR **por fase** do
[`PROGRESS-V1.md`](PROGRESS-V1.md), nomeada `phase-N-<slug>` em inglês (`phase-0-foundation`,
`phase-4-persistence`). Fora do roadmap, `feat/<slug>` ou `fix/<slug>`.

## 11. Referências

- [ARCHITECTURE.md](ARCHITECTURE.md) — por que o código está organizado assim.
- [API.md](API.md) — o que a API responde, com exemplos em `curl`.
- [TESTS.md](TESTS.md) — como escrever e rodar testes, e os dois gates.
- [SECURITY.md](SECURITY.md) — a configuração e a imagem pelo ângulo da segurança.
- [PROGRESS-V1.md](PROGRESS-V1.md) — o roadmap e o registro do que cada fase construiu.
- ADRs: [0007](adr/0007-fronteira-da-transacao.md) ·
  [0008](adr/0008-health-responde-503-no-mesmo-envelope.md) ·
  [0009](adr/0009-migracao-e-passo-de-deploy.md)
