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

- [x] ~~Ambiente: instalar o uv e registrar o caveat da pasta sincronizada em nuvem~~
  - **uv 0.12.7** via `winget install --id=astral-sh.uv`, sobre o **Python 3.13.7** que já estava na máquina. O brief pedia 3.12; toda a stack roda em 3.13 sem asterisco, e instalar um segundo interpretador seria custo sem retorno.
  - **O caveat ficou registrado no `CLAUDE.md`, sem workaround.** A ideia original era apontar `UV_PROJECT_ENVIRONMENT` para fora da árvore, e foi descartada: a variável é global, e um caminho absoluto faria todos os projetos uv da máquina dividirem um venv só. Se o `uv sync` falhar de forma estranha, a primeira hipótese é a sincronização travando arquivo.
  - **Verificado:** `uv run python -V` devolveu `Python 3.13.7`.
- [x] ~~`git init` com branch `main`, `.gitattributes` e `.gitignore`~~
  - **`.gitignore`** cobre `.venv/`, os caches de ferramenta, `.env` e **`docs/learning/`**. **`.gitattributes`** com `* text=auto eol=lf`, para o repositório não guardar CRLF vindo do Windows.
  - **Verificado:** o commit inicial `12efd5d` levou 13 arquivos, e `.venv/`, `docs/learning/` e `.env` ficaram de fora.
- [x] ~~Repositório no GitHub com proteção da branch `main` exigindo o check do CI~~
  - **`wastecoder/python-url-shortener`**, público desde o primeiro commit. Merge restrito a **rebase** (`allow_merge_commit` e `allow_squash_merge` desligados), para o histórico de um-conceito-por-commit sobreviver na `main` em vez de virar uma linha só.
  - **`enforce_admins: true`, e sem exigência de review.** Review é impossível de satisfazer sozinho; e sem `enforce_admins` o dono do repositório passa por cima com um clique, o que tornaria "o CI barra o merge" uma frase decorativa.
  - **Ligada depois do primeiro run:** a proteção cobra o check pelo **nome exato**, e esse nome só vira fato depois que um run o reporta (`gh pr checks 1 --json name` devolveu `check`). Exigir um nome que nenhum workflow produz tranca todo PR até alguém desligar a proteção. Não é que o PR que traz o workflow deixe de rodar: em evento `pull_request` o GitHub usa o workflow **da branch do PR**, e foi assim que o PR #1 rodou o CI com a `main` ainda sem workflow nenhum.
  - **Verificado:** o PR #2, criado de propósito com o lint quebrado, recebeu `Pull request #2 is not mergeable: the base branch policy prohibits the merge` e foi fechado sem merge. Ele fica no repositório como prova.
  - **Fora deste item:** forçar com `gh pr merge --admin` não foi tentado. Se o `enforce_admins` não estivesse valendo, o commit quebrado entraria na `main` e viraria reversão. A garantia usada é a resposta da própria API ao configurar a proteção: `"enforce_admins": true`.
- [x] ~~`pyproject.toml` com uv~~
  - **Nenhum número de versão foi digitado à mão:** as constraints foram escritas pelo `uv add` e o `uv.lock` trava o que foi resolvido — fastapi 0.141.1, starlette 1.6.0, pydantic 2.13.5, sqlalchemy 2.0.52, alembic 1.19.1, psycopg 3.3.4, pytest 9.1.1, ruff 0.16.5, mypy 2.3.1, import-linter 2.14, testcontainers 4.15.0.
  - **Sem `pytest-asyncio`**, coerente com a decisão de manter o projeto síncrono: os testes de API vão usar `TestClient`.
  - **Verificado:** `uv sync --locked` verde no runner do GitHub, que é onde essa flag importa — ela falha se o lock estiver defasado em relação ao `pyproject.toml`, em vez de resolver de novo em silêncio.
- [x] ~~Configuração de ferramenta num arquivo só~~
  - **Tudo no `pyproject.toml`:** ruff com `line-length = 100` e as regras `E,F,I,UP,B,SIM,C4,RUF`; mypy `strict` sobre `src`; pytest com o marker `integration` registrado e `addopts = -m 'not integration' --strict-markers --import-mode=importlib`; coverage com `branch = true`.
  - **`--import-mode=importlib`** dispensa `__init__.py` nas pastas de teste e elimina a colisão de nome que apareceria quando existirem `tests/unit/test_link.py` e `tests/integration/test_link.py`.
  - **Caveat:** o plugin `pydantic.mypy` **não é opcional**. Sem ele, `mypy --strict` acusa um falso `Missing named argument "database_url" for "Settings"`, porque o Pydantic v2 usa `@dataclass_transform` e o mypy sintetiza um `__init__` com todos os campos obrigatórios. Há um comentário no arquivo dizendo isso, porque removê-lo quebra o build de um jeito que não faz sentido nenhum.
- [x] ~~Esqueleto hexagonal completo, com docstring de camada por pacote~~
  - **22 pacotes**, cada `__init__.py` documentando a responsabilidade da camada e a regra de dependência dela. É o equivalente dos 21 `package-info.java` do `imagepipe`, e foi escolhido em vez de `.gitkeep` pela mesma razão: é importável, sobrevive ao Git e dá ao import-linter um módulo real em que ancorar os contratos.
  - **`inbound`/`outbound` em vez de `in`/`out`:** `in` é palavra reservada, e `application.port.in` é erro de sintaxe **no import**, não na criação — a pasta nasceria sem reclamação e explodiria só quando alguém tentasse importá-la.
  - **Decisão deliberadamente contrária à do `imagepipe`:** lá os pacotes de terceiro nível só nascem junto da primeira classe, porque ficariam meses vazios. Aqui todos estarão preenchidos até a Fase 4, e ver o mapa inteiro vale mais que descobri-lo aos poucos.
  - **Verificado:** `uv run mypy src` devolveu `Success: no issues found in 23 source files`.
- [x] ~~`.importlinter` com os três contratos~~
  - **`Contracts: 3 kept, 0 broken` — e isso, sozinho, não valia nada.** O relatório dizia `Analyzed 22 files, 0 dependencies`: sem nenhum import entre pacotes, os contratos passavam por vacuidade.
  - **Os dois tipos foram provados:** `import fastapi` dentro de `domain/__init__.py` quebra *The domain imports no framework* e sai com 1; `import url_shortener.adapter` no mesmo arquivo quebra *The dependency arrow points inward* e sai com 1. Ambos revertidos em seguida.
  - **Caveats:** `include_external_packages = True` é obrigatório para os contratos `forbidden` enxergarem pacotes de terceiros.
- [x] ~~`adapter/config/settings.py` com pydantic-settings e `.env.example`~~
  - **Nenhum campo tem default**, de propósito: `DATABASE_URL` ou `BASE_URL` faltando derruba o boot com mensagem clara, em vez de a aplicação subir feliz contra o banco errado. **`extra="forbid"`** transforma uma variável digitada errada no `.env` em erro em vez de silêncio. **`@lru_cache`** em `get_settings`, para o ambiente ser lido uma vez só.
  - **Verificado:** dois testes — um lendo do ambiente, outro afirmando que a construção falha quando `BASE_URL` some.
- [x] ~~CI magra em `.github/workflows/ci.yml`~~
  - **Seis passos, sem Docker, quinze segundos:** `uv sync --locked`, `ruff check`, `ruff format --check`, `mypy src`, `lint-imports`, `pytest`.
  - **Caveat:** `astral-sh/setup-uv@v10` **não resolve**. A action parou de publicar tag flutuante de major depois da `v7`; da `v8` em diante só existem tags exatas, e o primeiro run morreu em `Unable to resolve action` antes de qualquer passo. Corrigido pinando `@v10.0.1` — que é a prática melhor de qualquer forma. `actions/checkout@v7` continua publicando a tag de major.
  - **Caveat:** `ruff format` também processa **Markdown**, formatando os blocos de Python dentro dele. Um exemplo mal formatado no README ou num ADR derruba o pipeline; `docs/learning/` escapa porque está no `.gitignore`.
  - **Verificado:** run `33280203590` verde nos seis passos.
- [x] ~~Os três ADRs em `docs/adr/`~~
  - **Escritos antes do código e antes desta fase, junto do commit inicial**, porque são decisões já tomadas e que não vão mudar: `0001-redirect-302`, `0002-base62-sobre-a-sequence` e `0003-sem-fila`. Formato do ShopFlow: Status, Contexto, Decisão, Alternativas consideradas e Consequências, separando as positivas dos custos.
- **Critério:** ~~os cinco comandos verdes num repositório sem regra de negócio, um pull request que não consegue ser mergeado com o check vermelho, e o `lint-imports` provado não-vacuoso.~~ **Atendido.** PR #1 verde e mergeado por rebase; PR #2, quebrado de propósito, recusado pela política da branch e fechado sem merge; os dois contratos vistos quebrando e voltando.
- **Documento de aprendizado:** `docs/learning/fase-0-fundacao.md`, com o exercício em `docs/learning/exercicio_fase_0.py`.

## Fase 1 — Domínio puro

- [x] ~~`domain/service/base62.py`: `encode(id) -> str` sobre o alfabeto `0-9a-zA-Z`, com padding à esquerda até **exatamente 7 caracteres**, e `decode(code) -> int`. Funções puras, sem estado e sem I/O~~
  - **Quatro constantes, todas públicas e anotadas com `Final[...]`:** `ALPHABET` (`0-9a-zA-Z`, nessa ordem — é ela que fixa que `encode(10)` é `000000a` e não `000000A`), `BASE = len(ALPHABET)` derivado e nunca o literal 62, `CODE_LENGTH = 7` e `MAX_ID = BASE**CODE_LENGTH - 1` (`3_521_614_606_207`). O mapa reverso `_DIGIT_VALUES` é privado e construído a partir do próprio alfabeto, então os dois não podem discordar.
  - **`encode` recusa id negativo e id que não cabe em sete caracteres.** Devolver oito caracteres em silêncio quebraria a invariante que torna as rotas da API ingeráveis, e um id negativo só pode vir de bug — nenhuma sequence produz um. `encode(0)` é `0000000` e é aceito: `encode` é função numérica pura, e recusar o 0 seria enfiar regra de negócio no módulo errado.
  - **`decode` é estrito, e a ordem das checagens importa:** comprimento primeiro, alfabeto depois. Invertido, `decode("")` devolveria 0 e inventaria um id. Estrito também é o que dá a bijeção nos dois sentidos — um `decode("1") == 1` leniente teria `encode` devolvendo `0000001`, e um link passaria a ter dois nomes.
  - **Erro é `ValueError` da stdlib, nunca uma subclasse de `DomainError`.** A taxonomia de erro do projeto é fechada e cada entrada dela vira uma linha da tabela de Problem Details; falha aqui é bug (id negativo, ou a sequence além de 3,5e12), que é a linha do 500. Criar uma classe de domínio obrigaria a inventar uma linha para uma situação que nenhum cliente consegue causar.
  - **Caveat — `Final` sem subscrito desliga a checagem:** `int.__pow__` é tipado como devolvendo `Any`, então `MAX_ID = BASE**CODE_LENGTH - 1` sem `Final[int]` é inferido como `Any` e toda comparação contra ele deixa de ser verificada. Confirmado com `reveal_type` neste repositório: sem anotação e com `Final` pelado, `Any`; com `Final[int]`, `int`.
  - **Verificado:** 83 testes em `tests/unit/test_base62.py`. A tabela `KNOWN_CODES` (`0 -> 0000000`, `10 -> 000000a`, `36 -> 000000A`, `62 -> 0000010`, `56_800_235_583 -> 0ZZZZZZ`, `3_521_614_606_207 -> ZZZZZZZ`) é usada quatro vezes: valor literal, padding e alfabeto, `decode(encode(n)) == n` e `encode(decode(c)) == c`.
- [x] ~~`domain/service/url_policy.py`: aceita apenas `http` e `https`; recusa `localhost`, loopback, rede privada, link-local, faixas reservadas e URL com credencial embutida; expõe a lista de códigos reservados (`docs`, `redoc`, `openapi.json`, `health`, `links`) como rede de segurança para a Fase de alias do V2, já que com 7 caracteres fixos nenhuma delas pode ser gerada~~
  - **`validate_target_url(url) -> None`**, que levanta `InvalidTargetUrlError` ou não diz nada. **Não normaliza absolutamente nada:** a URL é guardada, hasheada e redirecionada exatamente como chegou, senão a linha do banco deixaria de conter o que o chamador mandou.
  - **A ordem das onze checagens é semântica, não estética.** Comprimento (2048) antes de tudo, porque `urlsplit` é `lru_cache` e uma string gigante ficaria presa num cache global só por ter sido olhada. Caracteres de controle **na string crua**, porque `urlsplit` apaga `\t`, `\r` e `\n` de qualquer posição — validar depois de parsear é validar uma URL diferente da que vai ser guardada. `urlsplit` e a leitura de `parts.port` dentro do mesmo `try`, porque as duas levantam `ValueError` e sem isso uma URL forjada vira 500 em vez de 400.
  - **Rota pública é `is_global and not is_multicast`, e não uma lista de faixas.** `is_private` deixaria passar o CGNAT `100.64/10`, que não é privado nem global — medido nesta máquina. Multicast é a única faixa que o `is_global` ainda chama de global, então sai na mão.
  - **`rstrip(".")` e não `removesuffix(".")`:** o ponto final é o rótulo raiz do DNS e faz o `ipaddress` recusar `127.0.0.1.`, que então passaria como nome. Com `removesuffix`, `127.0.0.1..` continuava passando; tem uma linha de teste só para essa diferença.
  - **O host é validado como host antes de qualquer coisa confiar nele.** O parser da stdlib segue a RFC 3986 e todo navegador segue o WHATWG, e os dois discordam sobre a barra invertida: `http://127.0.0.1\` tem host `127.0.0.1\` aqui e host `127.0.0.1` no navegador. Em vez de caçar cada grafia, tudo que não é um hostname (rótulos de `[a-z0-9_]`, sem hífen nas pontas) é recusado. O último rótulo ainda precisa ser um TLD plausível — letras ou `xn--` —, o que também derruba `127.1`, `0177.0.0.1` e `0x7f.0x0.0x0.0x1`, três formas que o `ipaddress` não lê e o navegador resolve para 127.0.0.1.
  - **Um IPv6 pode carregar um IPv4 dentro, em quatro grafias**, e o `is_global` só enxerga duas. `_embedded_ipv4` desembrulha `::ffff:a.b.c.d`, `::a.b.c.d`, 6to4 e o prefixo NAT64 `64:ff9b::/96` e faz a mesma pergunta ao endereço de dentro; `fec0::/10` (site-local, depreciado) sai à parte.
  - **`RESERVED_CODES` é `frozenset` e `is_reserved_code` só devolve `bool`.** Nada levanta `ReservedCodeError` no V1, de propósito: a fase pede a lista exposta e a classe existindo, não um chamador. Uma função que ninguém chama e que *parece* viva é pior do que uma exceção que ainda não tem quem a levante.
  - **Verificado:** 104 testes em `tests/unit/test_url_policy.py`, um por ramo de recusa mais os controles de aceitação que dão sentido a eles (`172.32.0.1` logo fora do `172.16/12`, `[::ffff:8.8.8.8]`, `example.com.`, punycode, `localhost.example.com`, `127.0.0.1.example.com`). Fora da suíte, uma matriz de 21 recusas e 14 aceitações rodada contra o módulo: zero divergências.
  - **Fora deste item:** resolução de nome. A política decide só pela string, o que deixa em aberto o nome que resolve para endereço interno e o DNS rebinding — está registrado como item da Fase 8 do [`PROGRESS-V2.md`](PROGRESS-V2.md). Também ficou de fora `domain/service/url_hash.py`, que é da Fase 2.
  - **Caveats:** `MAX_TARGET_URL_LENGTH = 2048` e a recusa de host não-ASCII (mande punycode) são **acréscimos** ao que a fase pediu, e estão aqui porque fecham grafia ambígua, não porque a lista mandava. O literal IPvFuture `http://[v1.x]/` não é recusado pelo parser: vira o nome `v1.x`, que é aceito como público — inofensivo, porque não resolve para lugar nenhum.
- [x] ~~`domain/model/`: `Link`, `Click` e `ShortCode` como dataclasses frozen, validando as invariantes no `__post_init__`~~
  - **Um tipo público por módulo:** `short_code.py`, `link.py`, `click.py`. Todos `frozen=True, slots=True`; `Link` e `Click` também `kw_only=True`, que é o que impede trocar `user_agent` por `referer` — dois `str | None` vizinhos — sem ninguém perceber. Em `ShortCode`, que tem um campo só, `kw_only` seria ruído.
  - **`ShortCode.from_id(link_id)` é o único ponto onde modelo e serviço se encontram**, e a seta é `model -> service`, nunca o contrário. É por causa dele que a Fase 2 não vai precisar importar `base62` em lugar nenhum: o caso de uso pede o código de um id.
  - **`Link.id` é obrigatório e `Click` não tem `id`.** A assimetria é a decisão: o id do link vem do `nextval` **antes** do insert e é o que gera o código, então um link sem id não existe; o clique é append-only e a única pergunta que se faz a ele é um `COUNT` por link, então um campo que ninguém lê só criaria mais um opcional.
  - **`Link` não carrega `url_hash`.** O hash é chave de índice de tamanho fixo — assunto de persistência — e é calculado **antes** de qualquer `Link` existir, no `SELECT` que decide se é preciso criar um. Guardar aqui seria uma segunda cópia do mesmo fato, com um `__post_init__` recalculando sha256 para conferir se as duas concordam. Consequência já fixada para a Fase 2: `LinkRepository.find_by_url_hash` recebe `str`, não um objeto.
  - **Violação de invariante levanta `ValueError`, nunca `DomainError`.** Um modelo malformado é bug de quem construiu; regra de negócio quebrada é coisa que a API precisa explicar. Se fossem a mesma família, um `except` só engoliria as duas.
  - **A regra de fuso é `utcoffset() is None`, uma condição só.** `datetime.utcoffset()` já devolve `None` exatamente quando não há `tzinfo` ou quando o `tzinfo` não sabe o próprio deslocamento — testar `tzinfo is None` junto seria um ramo inalcançável. Um instante com deslocamento `-03:00` é aceito e compara igual ao gêmeo em UTC: a regra é "nomeia um instante sem ambiguidade", não "está rotulado UTC".
  - **Verificado:** 22 testes de `ShortCode`, 11 de `Link` e 9 de `Click`, incluindo `dataclasses.replace` revalidando as invariantes na cópia, `FrozenInstanceError` na atribuição, o `tzinfo` que não sabe o próprio deslocamento, e a lista de campos afirmada nome a nome — é o teste que trava a ausência de `url_hash` e a ausência de `Click.id`.
  - **Caveats:** `Click.ip` é objeto `IPv4Address | IPv6Address`, não texto. Na Fase 4 o `INET` do SQLAlchemy é `TypeEngine[str]`, então o mapper provavelmente precisa de `str(click.ip)` na escrita e `ip_address(row.ip)` na leitura — é linha de mapper, não mudança de modelo, e fica registrado aqui para não ser redescoberto como "bug do modelo".
- [x] ~~`domain/exception/`: `DomainError` como base; `InvalidTargetUrlError` (carrega o motivo da recusa), `LinkNotFoundError` (carrega o code), `ReservedCodeError`. Nenhuma delas sabe o que é status HTTP — quem traduz é o handler da Fase 3~~
  - **`DomainError(Exception)`, e explicitamente não `ValueError`.** Se herdasse de `ValueError`, o `except ValueError` que a Fase 2 vai usar para transformar um code inválido em `LinkNotFoundError` engoliria também as regras de negócio, e o 404 responderia coisa que merecia 400. Tem um teste afirmando `not issubclass(DomainError, ValueError)`.
  - **`self.message` tipado, e não `args[0]`:** `BaseException.args` é `tuple[Any, ...]`, então um handler que devolvesse `error.args[0]` de uma função `-> str` quebraria no `mypy --strict`.
  - **`RejectionReason(StrEnum)` mora em `domain/exception/rejection_reason.py`, módulo próprio.** Se morasse dentro de `url_policy`, a exceção importaria o serviço e o serviço importaria a exceção — ciclo. Os valores são escritos à mão e hifenizados porque `auto()` num `StrEnum` devolve o nome do membro em minúsculas com underscore, e o formato de fio desta API é hifenizado.
  - **Nove motivos, uma linha só na tabela de erro.** `URL_TOO_LONG`, `FORBIDDEN_CHARACTER`, `MALFORMED_URL`, `MISSING_SCHEME`, `UNSUPPORTED_SCHEME`, `MISSING_HOST`, `CREDENTIALS_IN_URL`, `NON_PUBLIC_HOST` e `NON_PUBLIC_ADDRESS` mapeiam todos para `invalid-target-url` e 400 na Fase 3; o motivo viaja no corpo como campo de extensão. Ele é taxonomia de máquina, não uma segunda taxonomia de status.
  - **`LinkNotFoundError.code` e `ReservedCodeError.code` são `str`, nunca `ShortCode`.** O redirect é catch-all na raiz, então o valor que a exceção carrega quase nunca é um código válido — tipar como `ShortCode` tornaria irrepresentável justamente o caso que interessa, e apontaria `domain.exception` para `domain.model`.
  - **Verificado:** 24 testes em `tests/unit/test_domain_errors.py`, incluindo a asserção parametrizada de que nenhuma exceção tem `status`, `status_code`, `http_status` ou `problem_type`, e a de que os nove valores são únicos — lida por `__members__`, porque iterar o enum esconde alias e faria a asserção nunca poder falhar.
  - **Fora deste item:** as exceções não sobrevivem a `copy.copy` nem a `pickle`, porque a assinatura do `__init__` não bate com `args`. Um `__reduce__` de duas linhas resolveria; num app síncrono de um processo só, nada copia exceção, então fica como limite conhecido em vez de código sem chamador.
- [x] ~~Testes unitários escritos antes do código: `base62` com `parametrize` em 0, 1, 61, 62, um id grande, o round-trip `decode(encode(n)) == n` e o padding em 7; `url_policy` com um caso por ramo de recusa~~
  - **256 testes, todos sem Docker e sem banco**, em 0,5 s. O ciclo foi teste vermelho, implementação, verde, e só então o commit com os dois juntos — nunca um commit só de teste, porque a `main` é mergeada por rebase e um commit intermediário vermelho entraria no histórico em silêncio e quebraria o `git bisect`.
  - **Todo teste tem docstring em Given / When / Then** e assinatura `-> None`; nenhum mock, nenhum marcador, nenhum `async`. Os motivos de recusa são afirmados com `is RejectionReason.X`, não contra o texto da mensagem.
  - **A suíte foi medida por mutação, não por leitura.** Rodando mutantes contra uma cópia do repositório, sobreviveram seis: `frozen` do `Click`, a constante de comprimento máximo, a regra de que `ShortCode` não normaliza, o ramo do `tzinfo` sem deslocamento, a unicidade dos motivos e a metade morta da checagem de credencial. Os cinco primeiros viraram teste; o sexto virou simplificação — `parts.password` não pode ser lido sem `parts.username`, então a segunda metade da condição era ramo inalcançável e saiu.
  - **Verificado:** `uv run pytest` → `256 passed`. Os treze commits de código anteriores a este foram rodados um a um, cada um em seu próprio worktree: **13 verdes, 0 vermelhos**, com `ruff check` limpo em todos.
- **Critério:** ~~`uv run pytest` verde sem Docker e sem banco. `grep -rE "fastapi|sqlalchemy|pydantic|starlette" src/url_shortener/domain` não retorna nada, e o `import-linter` chega à mesma conclusão sozinho.~~ **Atendido.** `uv run pytest` → `256 passed`; `uv run mypy src` → `Success: no issues found in 33 source files`; `uv run ruff check .` e `ruff format --check .` limpos; o `grep` sai com 1 e sem saída. O `lint-imports` deixou de ser vacuoso: a Fase 0 registrava `Analyzed 22 files, 0 dependencies`, e agora são **`Analyzed 43 files, 24 dependencies. Contracts: 3 kept, 0 broken.`** — é a primeira fase em que existem arestas de verdade dentro do domínio para os contratos julgarem. `git diff --stat main..HEAD`: 19 arquivos, 1.548 inserções.
  - **Caveat sobre o próprio critério:** o `grep` só passa porque as docstrings escrevem os nomes capitalizados (`FastAPI`, `SQLAlchemy`, `Pydantic`, `Starlette`). Um `pydantic` em minúsculas em prosa faria o critério de aceitação da fase *parecer* falhar. O `-i` acha a docstring de `domain/__init__.py`; o `import-linter` é quem responde a pergunta de verdade.
  - **Revisão:** o diff passou por uma revisão adversarial em cinco lentes (segurança, correção, aderência ao spec, qualidade de teste por mutação, tipagem), com dois céticos independentes por achado. Vinte achados sobreviveram; foram corrigidos os de segurança (barra invertida, host percent-encoded, octeto hexadecimal, as quatro formas de IPv6 com IPv4 dentro), o `py.typed` ausente — sem ele, `mypy` sobre `tests/` enxerga o domínio inteiro como `Any` — e os seis buracos de teste. Ficaram registrados como limite consciente: cópia/pickle de exceção, `Link` aceitar id e code que não se correspondem (verificar isso acoplaria o modelo ao base62 e quebraria na permutação da Fase 8 do V2), `Click` não ter identidade própria, e `encode` não checar tipo em tempo de execução.
- **Documento de aprendizado:** `docs/learning/fase-1-dominio.md`, com o exercício em `docs/learning/exercicio_fase_1.py`.

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
- [ ] Testes de API com `fastapi.testclient.TestClient`, sobrescrevendo as dependências pelos fakes da Fase 2. Rápidos, sem Docker, e ficam no conjunto de testes unitários. **Era `httpx.AsyncClient` sobre `ASGITransport`, e estava errado:** aquilo exige teste `async def` e `pytest-asyncio`, os dois proibidos pela regra síncrona do `CLAUDE.md`, que é o documento que manda. Corrigido na Fase 2, que é a fase em que o modelo síncrono virou assinatura em toda porta — deixar para a Fase 3 seria descobrir a contradição com o `uv add --dev pytest-asyncio` à mão
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
