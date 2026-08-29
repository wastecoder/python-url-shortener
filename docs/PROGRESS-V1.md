# Progresso V1 — url-shortener (corte mínimo)

Roadmap em fases para construir o escopo mínimo: criar link, redirecionar, ler os metadados do
link, e nada mais. A sequência **constrói de dentro para fora** — domínio puro, depois casos de
uso, depois a API, e só então o banco — porque é essa ordem que a arquitetura hexagonal torna
possível, e porque é ela que produz a melhor demonstração do projeto: na Fase 4 o adaptador de
saída é trocado e o diff da camada web sai vazio.

O que ficou de fora de propósito está em [`PROGRESS-V2.md`](PROGRESS-V2.md).

**Se o tempo apertar, corte nesta ordem:** deduplicação (Fase 4), depois `GET /links/{code}`
(Fases 3 e 4). **Não corte:** os três testes com Testcontainers, o CI, e o README com a tabela de
decisões — funcionalidade não é o que está sendo avaliado neste projeto.

> **Como usar:** ao concluir um item, marque a caixa **e** risque o texto:
> `- [x] ~~item concluído~~`. Em seguida, **acrescente subitens em negrito descrevendo o que de
> fato foi feito** — decisões tomadas, nomes de módulos e classes, versões, e por quê. Todo item
> concluído deve ter:
>
> - um subitem **`Verificado:`** com a evidência concreta (o comando que rodou verde, a resposta
>   HTTP observada, o `git diff --stat` do commit);
> - quando útil, um subitem **`Fora deste item:`** dizendo o que ficou para depois, e
>   **`Caveats:`** para as armadilhas descobertas no caminho.
>
> Mantenha este arquivo em dia com a realidade. Um item marcado sem subitens não conta como
> concluído.

## Objetivos de aprendizado

O projeto existe para ensinar estes pontos. Marque quando você conseguir **explicar o item sem
consultar nada**. Esta lista é também o roteiro da entrevista.

- [ ] Layout `src/` e por que ele impede o import acidental do pacote não instalado (Fase 0)
- [ ] uv: `sync`, `run`, grupos de dependência, e o que o lock garante que o `requirements.txt` não garante (Fase 0)
- [ ] O que `mypy --strict` cobra que a anotação sozinha não cobra (Fase 0)
- [ ] Regra de dependência verificada por ferramenta e não por convenção — o que o `import-linter` prova (Fase 0)
- [ ] Dimensionamento do espaço de chave: `62^6` versus `62^7`, e por que 7 e não 6 (Fase 1)
- [ ] As duas famílias de geração de código — hash com resolução de colisão versus id convertido para base 62 — e o trade-off entre elas (Fase 1)
- [ ] Dataclass frozen versus Pydantic, e por que Pydantic não entra no domínio (Fase 1)
- [ ] Validação de destino como superfície de ataque: `file://`, `localhost`, IP de rede privada (Fase 1)
- [ ] `typing.Protocol` versus ABC, e por que Protocol é o que impede o adaptador de importar o `application` (Fase 2)
- [ ] Fake versus mock, e o caso concreto em que um mock faz o teste provar nada (Fases 2 e 5)
- [ ] Injeção por construtor sem framework de injeção de dependência (Fase 2)
- [ ] Por que este projeto é síncrono e não assíncrono, e qual é o erro clássico do FastAPI com `async def` (Fase 3)
- [ ] 301 versus 302, e o que o 301 custa em medição e em controle (Fase 3)
- [ ] Por que o default do `RedirectResponse` é 307 e por que 307 está errado aqui (Fase 3)
- [ ] Rota catch-all na raiz, ordem de registro, e a mesma questão vista pelo lado do gerador — os códigos reservados (Fases 1 e 3)
- [ ] Problem Details (RFC 7807), e por que 400 e 422 são coisas diferentes (Fase 3)
- [ ] Condição de corrida em check-then-act, e por que só a constraint fecha a janela (Fase 4)
- [ ] Por que o índice único é sobre `sha256(url)` e não sobre a URL — o limite de tamanho de entrada em btree (Fase 4)
- [ ] Por que a `UNIQUE` em `code` é rede de segurança e não mecanismo, e por que ainda assim ela fica (Fase 4)
- [ ] Escrita no caminho de leitura: contenção de linha, e por que `click` é append-only (Fase 4)
- [ ] Teste que verifica estado do banco versus teste que verifica retorno de função (Fase 5)
- [ ] `services:` do GitHub Actions versus container subido pelo próprio teste (Fase 5)
- [ ] Quais peças do desenho do Alex Xu foram tiradas e por quê — Snowflake, Redis, bloom filter, sharding (Fase 7)
- [ ] O que ficou de fora de propósito, e o que cada corte teria custado (Fase 7)

## Fase 0 — Fundação do repositório

- [ ] Ambiente: instalar o uv e registrar o caveat da pasta sincronizada em nuvem — o `.venv` tem dezenas de milhares de arquivos pequenos, e a sincronização pode travar escrita no meio, o que aparece como falha inventada do `uv sync`. Não se resolve com `UV_PROJECT_ENVIRONMENT`, que é variável global e faria todos os projetos uv da máquina dividirem um venv só
- [ ] `git init` com branch `main`, `.gitattributes` (`* text=auto eol=lf`), `.gitignore` (`.venv/`, `__pycache__/`, `.env`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `htmlcov/` e **`docs/learning/`**)
- [ ] Repositório no GitHub com **proteção da branch `main` exigindo o check do CI** — e sem exigência de review, que é impossível de satisfazer sozinho. Sem a proteção, "o merge é barrado quando o pipeline falha" é uma frase que ninguém consegue verificar
- [ ] `pyproject.toml` com uv: Python 3.13; runtime `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `pydantic-settings`; grupo `dev` com `pytest`, `pytest-cov`, `httpx`, `testcontainers[postgres]`, `ruff`, `mypy`, `import-linter`. Versões travadas no `uv.lock`. Nada de `pytest-asyncio`: o projeto é síncrono por decisão
- [ ] Configuração de ferramenta num arquivo só, o `pyproject.toml`: ruff (lint e format), mypy em modo strict, pytest com o marker `integration` registrado e `addopts = -m "not integration"`, coverage
- [ ] Esqueleto hexagonal completo em `src/url_shortener/`, com um `__init__.py` por pacote contendo a docstring da responsabilidade da camada — escolhido em vez de `.gitkeep` porque é importável, sobrevive ao Git e serve de âncora para o `import-linter`
- [ ] `.importlinter` com os três contratos: as camadas (`adapter` acima de `application` acima de `domain`) e os dois `forbidden` (nem `domain` nem `application` podem importar `fastapi`, `starlette`, `sqlalchemy`, `pydantic` ou `alembic`)
- [ ] `adapter/config/settings.py` com pydantic-settings (`DATABASE_URL`, `BASE_URL`) e `.env.example` versionado, com o `.env` fora do Git
- [ ] CI magra em `.github/workflows/ci.yml`: `ruff check`, `ruff format --check`, `mypy src`, `lint-imports`, `pytest`. Não precisa de Docker, roda em segundos, e barra merge desde o primeiro pull request. Os jobs de integração e de imagem entram nas Fases 5 e 6, quando existir o que rodar
- [ ] Os três ADRs em `docs/adr/`: `0001` o redirect é 302 e não 301; `0002` base 62 sobre a sequence em vez de hash da URL; `0003` sem fila, e o lugar exato onde ela entraria. São decisões **já tomadas** e que não vão mudar — escrevê-las antes do código não gera retrabalho e tira peso da Fase 7
- **Critério:** os cinco comandos verdes num repositório que ainda não tem uma linha de regra de negócio, e um pull request de verdade que **não consegue ser mergeado enquanto o check estiver vermelho**. O `lint-imports` precisa ser provado **não-vacuoso**: inserir de propósito um `import fastapi` no `domain` e ver o comando reprovar, depois remover.
- **Documento de aprendizado:** `docs/learning/fase-0-fundacao.md`

## Fase 1 — Domínio puro

- [ ] `domain/service/base62.py`: `encode(id) -> str` sobre o alfabeto `0-9a-zA-Z`, com padding à esquerda até **exatamente 7 caracteres**, e `decode(code) -> int`. Funções puras, sem estado e sem I/O
- [ ] `domain/service/url_policy.py`: aceita apenas `http` e `https`; recusa `localhost`, loopback, rede privada, link-local, faixas reservadas e URL com credencial embutida; expõe a lista de códigos reservados (`docs`, `redoc`, `openapi.json`, `health`, `links`) como rede de segurança para a Fase de alias do V2, já que com 7 caracteres fixos nenhuma delas pode ser gerada
- [ ] `domain/model/`: `Link`, `Click` e `ShortCode` como dataclasses frozen, validando as invariantes no `__post_init__`
- [ ] `domain/exception/`: `DomainError` como base; `InvalidTargetUrlError` (carrega o motivo da recusa), `LinkNotFoundError` (carrega o code), `ReservedCodeError`. Nenhuma delas sabe o que é status HTTP — quem traduz é o handler da Fase 3
- [ ] Testes unitários escritos antes do código: `base62` com `parametrize` em 0, 1, 61, 62, um id grande, o round-trip `decode(encode(n)) == n` e o padding em 7; `url_policy` com um caso por ramo de recusa
- **Critério:** `uv run pytest` verde sem Docker e sem banco. `grep -rE "fastapi|sqlalchemy|pydantic|starlette" src/url_shortener/domain` não retorna nada, e o `import-linter` chega à mesma conclusão sozinho.
- **Documento de aprendizado:** `docs/learning/fase-1-dominio.md`

## Fase 2 — Portas, casos de uso e viewmodels

- [ ] `application/port/outbound/`: `LinkRepository` (`next_id`, `find_by_code`, `find_by_url_hash`, `save`), `ClickRepository` (`record`, `count_by_link`) e `Clock` (`now`), todos como `Protocol`
- [ ] `application/port/inbound/`: `CreateLinkUseCase`, `ResolveLinkUseCase` e `GetLinkDetailsUseCase`, também `Protocol`
- [ ] `application/viewmodel/`: `CreateLinkCommand`, `LinkResult` e `RedirectResult` como dataclasses frozen. É a fronteira de saída — o objeto de domínio não atravessa para o adaptador
- [ ] `application/usecase/`: os três `*Impl`, recebendo as portas por construtor. A ordem dentro do `CreateLinkUseCaseImpl` é deliberada e vai documentada em subitem: validar o destino antes de qualquer efeito, calcular o hash, procurar, só então pedir o `next_id`, converter para base 62 e salvar
- [ ] `tests/fakes.py`: `InMemoryLinkRepository`, `InMemoryClickRepository` e `FixedClock` implementando as Protocols. **Fakes, não mocks** — um mock aqui faria o teste afirmar que uma chamada aconteceu em vez de afirmar o resultado
- [ ] Testes unitários dos três casos de uso contra os fakes, cobrindo também o caminho de deduplicação
- **Critério:** os três casos de uso verdes sem nada de infraestrutura de pé, e `lint-imports` provando que `application` não importa `fastapi`, `sqlalchemy` nem `pydantic`.
- **Documento de aprendizado:** `docs/learning/fase-2-portas-e-use-cases.md`

## Fase 3 — Adaptador web, ainda em memória

- [ ] `adapter/web/dto/request/` e `dto/response/`: modelos Pydantic v2. São a fronteira HTTP e não entram para dentro; quem cruza a camada é o `viewmodel`
- [ ] `adapter/web/link_controller.py` (`POST /links` e `GET /links/{code}`), `health_controller.py` (`GET /health`) e `redirect_controller.py` (`GET /{code}`)
- [ ] `POST /links` devolve `201` com header `Location` quando cria, e `200` quando a URL já existia. O chamador distingue os dois casos
- [ ] `GET /{code}` com `RedirectResponse(url, status_code=302)`. O default do Starlette é `307`, que preserva o método e não é o que um link curto significa
- [ ] `adapter/web/handler/`: o enum `ProblemType` e os handlers RFC 7807, **substituindo** também o handler default de `RequestValidationError` para que todo erro da API saia no mesmo envelope `application/problem+json`
- [ ] `adapter/config/dependencies.py`: a fiação por `Depends`, num lugar só. Os controllers dependem das portas `inbound`, nunca dos `*Impl`
- [ ] `adapter/config/clock.py` com `SystemClock`
- [ ] `main.py`: registra os exception handlers, depois os routers, com o `redirect_controller` **por último** — o catch-all na raiz engole `/links`, `/health` e `/docs` se vier antes
- [ ] Testes de API com `httpx.AsyncClient` sobre `ASGITransport`, sobrescrevendo as dependências pelos fakes da Fase 2. Rápidos, sem Docker, e ficam no conjunto de testes unitários
- **Critério:** `uv run uvicorn url_shortener.main:app --reload` sobe; `/docs` lista as quatro rotas **e continua acessível**, que é a prova de que o catch-all não engoliu nada; `GET /{code}` de um código conhecido devolve `302` com `Location`; um corpo inválido devolve `application/problem+json`. O passeio manual com `curl` e as respostas observadas ficam registrados em subitem.
- **Documento de aprendizado:** `docs/learning/fase-3-adapter-web.md`

## Fase 4 — Persistência em PostgreSQL

- [ ] `compose.yml` com o serviço `postgres`, imagem pinada por versão (nunca `latest`) e volume nomeado
- [ ] Alembic inicializado em `migrations/`, com a primeira migration criando `link` (`id BIGSERIAL`, `code TEXT UNIQUE NOT NULL`, `url TEXT NOT NULL`, `url_hash CHAR(64) UNIQUE NOT NULL`, `created_at TIMESTAMPTZ NOT NULL`) e `click` (`id`, `link_id` com chave estrangeira, `occurred_at`, `user_agent`, `referer`, `ip INET`), mais o índice em `click(link_id)`
- [ ] `adapter/persistence/entity/` com os modelos SQLAlchemy 2.0 (`Mapped` e `mapped_column`), `mapper/` com a conversão entidade-domínio nos dois sentidos, e `database/session.py` com engine e sessão
- [ ] `link_repository_impl.py`: `next_id` lendo `nextval` da sequence **antes** do insert — é isso que permite calcular o código no domínio puro e inserir com `code NOT NULL` num único statement — e o insert com `ON CONFLICT (url_hash) DO NOTHING`
- [ ] O fluxo de deduplicação em quatro passos, com o `SELECT` de reentrada no passo 4 para o caso de perder a corrida. **Nunca** check-then-insert: entre o `SELECT` que não achou e o `INSERT`, outra requisição insere
- [ ] `click_repository_impl.py`: `INSERT` append-only e `count_by_link` por `COUNT`. Nenhum contador dentro de `link`
- [ ] Trocar os fakes pelas implementações reais em `dependencies.py`
- **Critério:** `docker compose up -d postgres`, `uv run alembic upgrade head`, e o mesmo passeio manual da Fase 3 funcionando contra o Postgres — **com diff vazio na camada `web`**. Esse diff vazio é a demonstração mais barata e mais convincente da arquitetura que este projeto produz: registre o `git diff --stat` do commit em subitem.
- **Documento de aprendizado:** `docs/learning/fase-4-persistencia.md`

## Fase 5 — Testes de integração com Testcontainers

- [ ] `tests/conftest.py`: `PostgresContainer` com escopo de sessão, `alembic upgrade head` aplicado contra ele, e o client HTTP apontando para a aplicação com as dependências reais. Os testes rodam a mesma migration que a produção roda
- [ ] Teste 1, criar e seguir: `POST /links`, depois `GET /{code}`, afirmando `302` e o `Location`. É o caminho feliz de ponta a ponta
- [ ] Teste 2, deduplicação: `POST` da mesma URL duas vezes, afirmando que o código devolvido é o mesmo **e** que existe exatamente uma linha em `link`
- [ ] Teste 3, o clique foi registrado: `GET /{code}` e depois uma linha em `click`. Prova o efeito colateral, não o retorno da função
- [ ] `tests/mothers.py` com Object Mother: classe final, construtor privado, factories estáticas de cenário, sem builders
- [ ] Gate de cobertura no CI (`--cov-fail-under`), mais exigente sobre `domain/` do que sobre `adapter/` — um número único deixaria passar adaptador coberto com domínio furado, que é o inverso do que interessa
- [ ] O CI ganha o job de integração. O `ubuntu-latest` já tem Docker, então o workflow **não** declara `services:`: o teste sobe o próprio container
- **Critério:** `uv run pytest -m integration` verde local e no CI, e um pull request com teste vermelho fica bloqueado. Provar a não-vacuidade do gate de cobertura removendo uma **classe de teste inteira** e vendo o CI reprovar — com Object Mother, remover um teste isolado costuma não provar nada, porque as camadas de cima exercitam os mesmos objetos reais.
- **Documento de aprendizado:** `docs/learning/fase-5-testcontainers.md`

## Fase 6 — Docker

- [ ] Dockerfile multi-stage: estágio de build com uv instalando as dependências em camada própria, estágio final slim, usuário não-root
- [ ] `compose.yml` completo, com `api` e `postgres`, aplicando a migration antes de o servidor subir
- [ ] O CI ganha o `docker build`
- **Critério:** num clone limpo, `docker compose up` e o fluxo `POST /links` seguido de `GET /{code}` funciona com um comando só, sem nenhum passo manual.
- **Documento de aprendizado:** `docs/learning/fase-6-docker.md`

## Fase 7 — Documentação e acabamento

- [ ] `README.md` em português: o problema em três frases, o diagrama do fluxo em Mermaid, `docker compose up`, a **seção de decisões** e a **tabela do que ficou de fora** com a resposta pronta para cada corte. Essa tabela é a parte do repositório que um entrevistador técnico lê primeiro
- [ ] Revisar os três ADRs escritos na Fase 0 contra o que foi de fato construído, e acrescentar um quarto se alguma decisão estrutural tiver mudado no caminho
- [ ] Revisão do histórico: mensagens legíveis, nenhum commit gigante, nenhum trailer de co-autoria
- [ ] Marcar em `Objetivos de aprendizado` tudo que você já explica sem consultar, e listar honestamente o que faltou
- **Critério:** um clone limpo sobe com um comando, e o README responde sozinho as seis coisas que sustentam o projeto: Testcontainers verificando estado do banco, a constraint fechando a corrida da deduplicação, 302 versus 301, `click` append-only, as peças do desenho do Xu que saíram, e a tabela de cortes com a justificativa de cada um.
- **Documento de aprendizado:** `docs/learning/fase-7-documentacao.md`

## Extras, se sobrar tempo

Em ordem de valor, do maior para o menor:

- [ ] **O teste de concorrência.** Duas requisições simultâneas com a mesma URL longa, afirmando que exatamente um link foi criado. É impossível de escrever com mock, porque o que está sob teste é o comportamento do banco sob concorrência — é o argumento inteiro do projeto num teste só
- [ ] Ensaiar as respostas dos `Objetivos de aprendizado` em voz alta, sem consultar
- [ ] A permutação multiplicativa que fecha a enumerabilidade — está descrita em [`PROGRESS-V2.md`](PROGRESS-V2.md), e só entra aqui se as Fases 0 a 7 estiverem inteiras
