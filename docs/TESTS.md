# Testes

Como este projeto é testado e o que é preciso fazer para acrescentar um teste: a separação entre as
duas naturezas de teste e como ela é imposta, o padrão de fixture, o estilo obrigatório, e os dois
gates que reprovam o build.

> A **arquitetura** que estes testes exercitam está em [`ARCHITECTURE.md`](ARCHITECTURE.md); o
> **contrato HTTP** que eles afirmam está em [`API.md`](API.md); os **comandos** estão em
> [`DEVELOPMENT.md`](DEVELOPMENT.md).

- [1. Estratégia](#1-estratégia)
- [2. Estrutura de pastas](#2-estrutura-de-pastas)
- [3. Como a separação é imposta](#3-como-a-separação-é-imposta)
- [4. Estilo de teste](#4-estilo-de-teste)
- [5. Object Mother](#5-object-mother)
- [6. Fakes, e não mocks](#6-fakes-e-não-mocks)
- [7. Testes de integração com Testcontainers](#7-testes-de-integração-com-testcontainers)
- [8. Os testes que carregam o projeto](#8-os-testes-que-carregam-o-projeto)
- [9. Os dois gates de cobertura](#9-os-dois-gates-de-cobertura)
- [10. Como adicionar um teste](#10-como-adicionar-um-teste)
- [11. Referências](#11-referências)

## 1. Estratégia

Duas naturezas de teste, e só duas.

| Natureza | O que exercita | Precisa de Docker | Comando |
|---|---|---|---|
| Unitário | Domínio, casos de uso, adaptador web e wiring, com os portos de saída trocados por *fakes* | Não | `uv run pytest` |
| Integração | A aplicação inteira contra um PostgreSQL de verdade, sem nada substituído | Sim | `uv run pytest -m integration` |

Os números, porque citar "505 testes" sem dizer de qual deles se fala induz a erro:

- **505 itens coletados** ao todo.
- **484 unitários**, escritos como **235 funções** em **31 arquivos**.
- **21 de integração**, escritos como **21 funções** em **6 arquivos**.
- A diferença entre 235 funções e 484 itens é inteiramente `@pytest.mark.parametrize`.

Não existe um terceiro nível. Com um serviço só, **integração já é o topo**; inventar um "ponta a
ponta" acima dele seria renomear a mesma coisa.

## 2. Estrutura de pastas

```text
tests/
├─ fakes.py                    stand-ins em memoria dos portos de saida
├─ mothers.py                  Object Mothers: cenarios nomeados
├─ unit/                       sem Docker, sem banco, sem rede
│  ├─ conftest.py              o app real com quatro providers trocados
│  └─ test_*.py                31 arquivos
└─ integration/                Testcontainers
   ├─ conftest.py              um container por sessao, migrado com Alembic
   └─ test_*.py                6 arquivos
```

**Não existe `tests/conftest.py` na raiz.** As fixtures moram só nos dois `conftest.py` das
subpastas, e os dois são imagens espelhadas de propósito: o unitário troca quatro portos e não abre
socket nenhum; o de integração **não troca nada**.

**Também não existe `tests/__init__.py`**, e isso não é esquecimento: o `--import-mode=importlib` do
pytest dispensa o arquivo. A consequência é que o `mypy` precisa ser avisado de quais diretórios são
raízes de pacote — daí `mypy_path = ["src", "."]` e `explicit_package_bases = true` no
`pyproject.toml`. Sem as duas linhas ele mapeia o mesmo arquivo para dois nomes de módulo e para
antes de checar qualquer coisa.

## 3. Como a separação é imposta

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not integration' --strict-markers --import-mode=importlib"
markers = ["integration: precisa de um Docker rodando (Testcontainers)"]
```

O `addopts` desmarca a integração **por default**, então um `uv run pytest` pelado é sempre rápido e
sempre rodável sem Docker. Todo arquivo de integração carrega `pytestmark = pytest.mark.integration`
no nível do módulo, e o `--strict-markers` faz um marcador com erro de digitação virar erro em vez
de virar um teste que nunca roda.

Para rodar tudo: `uv run pytest -m ""`.

Os dois `conftest.py` combinam onde importa:

| | `tests/unit/` | `tests/integration/` |
|---|---|---|
| Providers sobrescritos | `get_link_repository`, `get_click_repository`, `get_clock`, `get_health_probe` | **nenhum** |
| Settings | entregues a `create_app(settings=...)`, com `_env_file=None` | idem, com a DSN do container |
| `BASE_URL` | `https://sho.rt` | `https://sho.rt` |
| Peer do cliente | `203.0.113.7:51234` | idem |
| Escopo do app | por teste | por teste |

**O que o conftest unitário sobrescreve é deliberadamente estreito:** os três portos de saída — os
dois repositórios e o relógio — mais o `HealthProbe`, que **não** é porto de saída, porque mora em
`adapter/web/` ([ADR-0008](adr/0008-health-responde-503-no-mesmo-envelope.md)). Nem as settings, nem
os casos de uso. Todo teste unitário roda o `CreateLinkUseCaseImpl` de verdade, o
fluxo de deduplicação de verdade e o wiring de verdade do `dependencies.py`. E como o FastAPI
resolve *overrides* através de sub-dependências, trocar a folha basta — é por isso que **nenhum
desses testes abre conexão** apesar de a aplicação estar ligada ao PostgreSQL: `get_session` fica
*abaixo* dos repositórios que foram trocados, então nunca chega a ser resolvido.

O `app` é reconstruído a cada teste porque `dependency_overrides` é estado no objeto do app;
compartilhar um app vazaria os *fakes* de um teste para o seguinte.

Os dois clientes usam `follow_redirects=False`, e o motivo **não é a rede** — isso é o que os
docstrings diziam até a Fase 5 medir. O test client despacha tudo pelo seu único transporte ASGI,
qualquer que seja o host, então o salto nunca sai do processo e nenhum nome é resolvido. Ele
**reentra nesta mesma aplicação**, casa com o catch-all `GET /{code}`, responde `404`, e enterra o
`302` e o `Location` em `response.history` — onde as asserções que os nomeiam não os enxergam.

O `client=(...)` fixa o endereço do peer, que é o que o controlador do redirect lê para preencher
`Click.ip`. O default do test client é a string literal `testclient`, que não parseia como endereço:
sem isso, todo clique da suíte gravaria `None` e a coluna `INET` nunca seria exercitada.

## 4. Estilo de teste

- Arquivos `test_*.py`, funções `test_<comportamento>`. Os nomes são frases, não abreviações:
  `test_the_loser_of_the_race_is_refused_without_raising_and_reads_the_winner`.
- **Toda função de teste carrega um docstring em Given / When / Then** — o equivalente ao
  `@DisplayName` do lado Java. Muitas carregam parágrafos adicionais depois, explicando por que
  aquele teste existe e o que ele deixaria passar se fosse escrito de outro jeito.
- **A conformidade com as portas de entrada é afirmada pela anotação de retorno.** Cada arquivo de
  caso de uso constrói o sujeito por um helper `_use_case(...)` anotado com a porta, e é o tipo de
  retorno que serve de asserção — lido pelo `mypy`, não em runtime.

## 5. Object Mother

Fixtures de cenário em `tests/mothers.py`: três classes `@final` de fábricas estáticas, cada uma com
construtor privado que levanta `TypeError`. **Sem builders.**

| Mother | Fábricas |
|---|---|
| `TargetUrlMother` | `accepted()`, `another_accepted()`, `refused()` |
| `LinkMother` | `first()`, `with_id(id, *, url=None)`, `pointing_at(url)`, `with_a_mixed_case_code()` |
| `ClickMother` | `on(link)`, `on_link_id(id)`, `fully_described(link)` |

`LinkMother.with_id` deriva o código por `ShortCode.from_id`, e não o escreve à mão — assim nenhum
teste concorda com o codificador por construção.

Existem um `MIXED_CASE_ID` e um `MIXED_CASE_CODE` (`"hBxM5A3"`) porque o id óbvio, `1`, codifica para
`0000001`: **só dígitos**, e toda asserção sobre código sobreviveria a um mapper ou repositório que
passasse tudo para maiúscula ou minúscula.

As mothers **não cobrem tudo**, de propósito: `test_link.py` e `test_click.py` constroem os sujeitos
à mão, porque o que eles testam são as recusas do próprio construtor — uma mother ali esconderia a
coisa sob teste.

## 6. Fakes, e não mocks

`tests/fakes.py` traz `InMemoryLinkRepository`, `InMemoryClickRepository`, `StubHealthProbe` e
`FixedClock`.

**A diferença deixa de ser acadêmica no teste de deduplicação:** faça `POST` da mesma URL duas vezes
e a pergunta é *quantos links existem*, não *quantas vezes `save` foi chamado*. Um mock responde a
segunda pergunta e chama isso de prova.

`InMemoryLinkRepository` mantém dois índices de busca — por digest e por código — e um contador
monotônico. O `save` devolve `False` quando o digest já está tomado, espelhando o
`ON CONFLICT (url_hash) DO NOTHING`. O índice único sobre `code` **não é modelado**, de propósito:
uma colisão de código não pode acontecer ali, então o ramo seria código morto que o gate de
cobertura depois teria que ser instruído a ignorar.

O método `insert_before_next_save(rival, *, url_hash)` insere um escritor concorrente exatamente na
janela da corrida — sem threads, sem sleeps e sem nada para ficar instável. Ele **dispara uma vez e
se limpa**, porque uma corrida é um momento e não uma condição; e o `False` cai da regra de unicidade
do próprio store, e não de uma flag (uma flag só testaria a flag).

**Nada aqui herda de uma porta.** A conformidade é estrutural e é provada por quatro atribuições
anotadas dentro de um `if TYPE_CHECKING:` — nunca executadas, lidas pelo `mypy`. É por isso que o
`pyproject.toml` aponta o `mypy` para `tests` além de `src`: uma declaração de conformidade que
nenhum verificador lê não prova nada.

`@runtime_checkable` com `isinstance` foi explicitamente recusado: ele compara nomes de método e
nada sobre assinaturas, então aceitaria um `save` que devolve string.

## 7. Testes de integração com Testcontainers

```python
POSTGRES_IMAGE = "postgres:18.6-alpine"

with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as container:
    dsn = container.get_connection_url()
    command.upgrade(alembic_config(dsn), "head")
    yield dsn
```

Um container por **sessão**, migrado uma vez. Quatro decisões dentro dessas quatro linhas:

- **A imagem é a mesma do `compose.yml`, caractere por caractere.** Nada na suíte depende de um
  recurso recente do PostgreSQL — o que está fixado é **paridade com a coisa que é publicada**, e não
  uma versão.
- **`driver="psycopg"` não é opcional.** O `PostgresContainer` assume `psycopg2` por default, que
  este projeto não tem como dependência, e a falha chegaria como erro de import de dentro do
  SQLAlchemy.
- **O schema vem das mesmas migrations que a produção roda.** Nunca `create_all()`, nem aqui.
- **A `Config` do Alembic é construída vazia em memória, e não lida do `alembic.ini`.** O
  `migrations/env.py` chama `fileConfig`, que assume `disable_existing_loggers=True` — ler o arquivo
  desligaria o logger do `DatabaseProbe` pelo resto da sessão de teste, e um dos testes de `/health`
  afirma justamente sobre o que foi logado.

As asserções leem o banco por uma **segunda engine**, `NullPool`, separada de toda engine que a
aplicação constrói — assim elas observam estado **commitado**, de fora da transação da requisição.

Uma fixture `autouse` roda `TRUNCATE link, click RESTART IDENTITY` **antes** de cada teste, e não
depois, para que um teste comece de um estado conhecido mesmo quando o anterior falhou no meio. As
duas tabelas são listadas e **não há `CASCADE`**: hoje ele não acrescentaria nada, e amanhã
truncaria em silêncio qualquer tabela que alguém acrescentasse sem listar aqui. Por causa do
`RESTART IDENTITY`, os testes afirmam o código exato `0000001` em vez de comparar dois códigos entre
si.

**Não se faz mock de repositório em teste de integração.** O ponto inteiro é verificar *estado do
banco*, e não valor de retorno.

## 8. Os testes que carregam o projeto

### Os três da fundação

1. **Encurtar e seguir** — `test_a_shortened_url_is_stored_and_redirects_back_to_itself`: `POST
   /links`, depois `GET /{code}`, afirmando `302` e o `Location`.
2. **Deduplicação** — `test_the_same_url_twice_answers_one_code_and_leaves_one_row`: o mesmo `POST`
   duas vezes, afirmando o mesmo código **e** que existe exatamente uma linha em `link`.
3. **O redirect registrou o acesso** —
   `test_following_a_link_appends_one_fully_described_row_to_click`.

### A deduplicação é provada em três níveis, e nenhum basta sozinho

| Teste | O que ele prova | O que ele não prova |
|---|---|---|
| Sequencial | O mesmo código volta e existe uma linha | Nada sobre concorrência |
| **Corrida determinística** | O ramo perdedor roda **em toda execução**: duas `Session` reais, a janela aberta à mão, `save` devolve `False` — e não `IntegrityError` — e a releitura devolve o vencedor | Não há contenção de verdade |
| **Oito requisições simultâneas** | A invariante sob contenção real: um `201`, sete `200`, um código, **uma linha** | Num escalonamento infeliz, todas poderiam pegar o caminho rápido |

O teste concorrente solta as oito de uma vez com `threading.Barrier(8)` dentro de um
`ThreadPoolExecutor` — num laço, a primeira terminaria antes de a última começar, o que não é corrida
nenhuma. E ele tem uma quinta asserção que é o que **impede o teste de passar por vacuidade**:

```python
assert _ids_spent(database) > 1
```

Mais de um id gasto da sequence significa que mais de uma requisição passou do `SELECT` e entrou na
janela que só o índice único fecha. Sem ela, as outras quatro asserções continuariam verdes num teste
em que nada correu.

`RACERS = 8` é limitado dos dois lados: o pool da engine tem cinco conexões mais dez de overflow,
então qualquer coisa acima de quinze pararia de medir o banco e passaria a medir o `pool_timeout`; e
menos que um punhado é uma corrida pequena demais para valer o nome.

A corrida determinística **depende do `READ COMMITTED` fixado na engine**: sob `REPEATABLE READ` o
`INSERT` perdedor levantaria `SerializationFailure` e o passo seguinte nunca rodaria.

### Os três que exercitam a borda

- **A transação que falha no `COMMIT`.** Um `UNIQUE (link_id) DEFERRABLE INITIALLY DEFERRED` posto em
  `click` por uma fixture faz o `INSERT` passar e a violação aparecer **só no `COMMIT`** — o momento
  exato de que a [ADR-0007](adr/0007-fronteira-da-transacao.md) trata. O segundo redirect responde
  **`500`, e não `302`**, em `application/problem+json`, sem `Location`, e `click` fica com uma linha
  só. O PostgreSQL só adia `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` e `EXCLUDE` — por isso é constraint
  de unicidade e não `CHECK`. Um segundo teste afirma que a conexão volta usável, para que um commit
  falho continue sendo uma requisição falha e não uma indisponibilidade.
- **`/health` com o pool esgotado.** As quinze conexões do pool de requisições são retiradas à mão
  (`pool.size() + pool._max_overflow`, afirmado como **15**) e o endpoint responde `200` na hora,
  porque o probe roda numa engine `NullPool` que não tem fila para esperar. É a
  [ADR-0008](adr/0008-health-responde-503-no-mesmo-envelope.md) como fato observável.
- **As migrations conferidas por máquina.** `alembic check` contra o `Base.metadata`, a revisão do
  container comparada com o head que o repositório declara, e a existência de `ix_click_link_id` — o
  índice de que o `COUNT` depende.

## 9. Os dois gates de cobertura

Os gates vivem **só no CI**; não há `--cov-fail-under` no `addopts`. São dois, e não uma média:

| Gate | Escopo | Limite | Negociável |
|---|---|---|---|
| Do domínio e da aplicação | `src/url_shortener/domain/*`, `src/url_shortener/application/*` | **100** | Não |
| Da árvore inteira | tudo em `src/url_shortener` | **100** | Em um PR que explique por quê |

**Por que dois e não uma média.** `domain` e `application` são onde as decisões deste projeto moram,
e são inteiramente alcançáveis sem banco nenhum de pé — então um buraco ali nunca é "a infraestrutura
não estava no ar", é uma regra que ninguém testou. Um número único sobre a árvore toda deixaria um
adaptador bem testado pagar por um domínio sem teste, que é exatamente o inverso.

**100 sem folga.** Quando uma linha é genuinamente inalcançável ela recebe `# pragma: no cover` e um
comentário dizendo por quê — o que põe a exceção no diff, onde um revisor a vê, em vez de escondê-la
dentro de um limiar que ninguém revisita.

O job de integração roda `uv run pytest -m "" --cov`, as duas suítes num processo só, e a combinação
é necessária: **nenhuma das duas alcança o gate sozinha.** A rodada unitária perde exatamente os doze
statements que não conseguem executar sem uma sessão de verdade — `get_session` e os dois
repositórios — e nada mais; a de integração perde todo caminho de erro que os testes unitários
dirigem com *fakes*.

**Cobertura de linha é um instrumento fraco, e o registro deste projeto diz isso na cara.** Um módulo
pode ser apagado sem mover o número quando dois testes diferentes passam pelas mesmas linhas. **O
gate pega uma camada ficar sem teste, não um cenário sumir.** Para cenário, o que serve são os testes
da seção anterior. Teste de mutação sobre `domain/` — que é o instrumento certo para essa pergunta —
está em [`PROGRESS-V2.md`](PROGRESS-V2.md).

**O workflow não declara `services:` em lugar nenhum**, de propósito: o `ubuntu-latest` já roda um
daemon Docker, e o Testcontainers sobe, migra e joga fora o próprio PostgreSQL de dentro da sessão de
teste. O container é declarado pelo código que precisa dele, na versão que esse código fixa, e nada
no CI precisa ser mantido em dia com o `compose.yml` à mão.

## 10. Como adicionar um teste

1. **Escolha a natureza.** Se a pergunta é sobre *estado do banco* ou sobre o comportamento do
   PostgreSQL, é integração. Se é sobre uma regra, um status ou um corpo, é unitário — e roda em
   milissegundos.
2. **Ponha o arquivo em `tests/unit/` ou `tests/integration/`.** Se for de integração, acrescente
   `pytestmark = pytest.mark.integration` no topo do módulo.
3. **Escreva o docstring em Given / When / Then antes do corpo.** Se ele não sair, o teste ainda não
   sabe o que afirma.
4. **Use as mothers** para os sujeitos, a menos que o que esteja sob teste seja a construção deles.
5. **Não faça mock do repositório num teste de integração.** Leia o banco pela fixture `database`.
6. **Rode os dois gates antes de commitar** — e note o `--cov`: sem ele a rodada não grava dado
   nenhum, e o `coverage report` seguinte responde `No data to report.` ou, pior, julga um
   `.coverage` velho de outra rodada.

   ```bash
   uv run pytest -m "" --cov --cov-report=
   uv run coverage report --include="src/url_shortener/domain/*,src/url_shortener/application/*" --fail-under=100
   uv run coverage report --fail-under=100
   ```

## 11. Referências

- [ARCHITECTURE.md](ARCHITECTURE.md) — as camadas e os fluxos que estes testes exercitam.
- [API.md](API.md) — o contrato que os testes de borda afirmam.
- [DEVELOPMENT.md](DEVELOPMENT.md) — os comandos, e o pipeline que roda tudo isto.
- [PROGRESS-V2.md](PROGRESS-V2.md) — teste de mutação e teste de carga, cortados de propósito.
- ADRs: [0002](adr/0002-base62-sobre-a-sequence.md) · [0007](adr/0007-fronteira-da-transacao.md) ·
  [0008](adr/0008-health-responde-503-no-mesmo-envelope.md) ·
  [0009](adr/0009-migracao-e-passo-de-deploy.md)
