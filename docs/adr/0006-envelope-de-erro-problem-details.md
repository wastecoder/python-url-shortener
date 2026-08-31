# ADR-0006: Todo erro da API sai no mesmo envelope Problem Details

## Status

Aceito.

## Contexto

O `CLAUDE.md` já fixava o formato de erro — Problem Details (RFC 7807), `application/problem+json`
— e uma tabela de quatro situações:

| Situação | Status | `type` |
|---|---|---|
| Destino recusado pela política do domínio | `400` | `invalid-target-url` |
| Corpo malformado (Pydantic) | `422` | `validation-error` |
| Código desconhecido | `404` | `link-not-found` |
| Qualquer coisa não tratada | `500` | `internal-error` |

Ao implementar, duas perguntas que a tabela não responde apareceram, e as duas mudam o que um
cliente vê.

**Primeira: o que é o campo `type` no fio.** A RFC 7807 diz que ele é uma *referência de URI*. A
tabela escreve slugs. Slug puro, URN e URL absoluta são três respostas defensáveis e diferentes.

**Segunda: os erros que este projeto não levanta.** As quatro linhas cobrem o que o *nosso* código
levanta. O framework levanta outros antes de qualquer controller rodar: `POST /health` é `405`, e um
caminho que rota nenhuma casa é `404`. Sem tratamento, os dois saem como
`{"detail": "Method Not Allowed"}` em `application/json` — e a frase "todo erro da API sai no mesmo
envelope", que o item da fase escreve com todas as letras, fica falsa a um `curl` de distância.

## Decisão

**1. `type` carrega o slug exatamente como a tabela escreve**: `"type": "invalid-target-url"`.

**2. Um quinto membro no `ProblemType`, `http-error`**, e um handler para `HTTPException` do
Starlette. Ele responde com o status que o framework escolheu, `title` igual à frase do status, e
repassa `exc.headers` — o que preserva o `Allow` que um `405` é inútil sem.

**3. `ProblemType` é um `StrEnum` de slugs, e o status *não* mora nele.** O pareamento
erro→status fica nos cinco handlers, uma linha cada.

**4. Cinco handlers, e os dois últimos existem para fechar a afirmação:** `InvalidTargetUrlError`,
`LinkNotFoundError`, `RequestValidationError` (substituindo o handler default do FastAPI),
`HTTPException` e `Exception`.

**5. O corpo é um modelo Pydantic**, `ProblemResponse`, serializado com `exclude_none=True`.
Membros da RFC: `type`, `title`, `status`, `detail`, `instance`. Membros de extensão: `reason`
(o motivo de recusa, legível por máquina) e `errors` (a lista de campos recusados).

## Justificativa

**Por que o slug puro.** A RFC permite referência relativa, então o slug é legal. As outras duas
opções custam mais do que entregam: uma URL absoluta apontando para o repositório é dereferenciável
e, por isso mesmo, é uma promessa de manter quatro páginas de documentação vivas e um host fixado
dentro do código; uma URN (`urn:problem-type:invalid-target-url`) é estável e absoluta, mas é um
namespace que ninguém registrou — absoluta de fachada. O slug é o que o contrato escreve, é o que o
cliente compara, e não vira link morto. O custo está nas consequências.

**Por que um membro novo em vez de `about:blank`.** A RFC prescreve `about:blank` quando o problema
não tem nome próprio além do status, e teria funcionado. `http-error` foi preferido porque a
taxonomia deste projeto é lida por um humano antes de ser lida por um cliente: um `type` que diz
"em branco" obriga quem lê a saber a RFC para entender que aquilo é o caso genérico. O nome também
separa o que precisa ficar separado — `internal-error` é a API **falhando** e `http-error` é a API
**recusando**, e só o primeiro é bug.

**Por que o status não mora no enum.** Porque `http-error` não tem um. Ele cobre uma família —
`405`, `404`, e qualquer outro que o roteador produza — e o status vem da exceção. Uma coluna de
status no enum daria a esse membro um buraco ou uma mentira, e a docstring do pacote `handler` já
dizia a forma certa desde a Fase 0: *"`ProblemType` is the taxonomy and the handlers are the
mapping"*.

**Por que o corpo é reconstruído campo a campo no 422.** `RequestValidationError.errors()` devolve
entradas com `input` e `ctx`. `input` é o payload do próprio chamador ecoado de volta; `ctx` carrega
valores que nem sempre sobrevivem a JSON. Três campos — `field`, `message`, `type` — é o que um
cliente precisa para saber qual campo errou e por quê. Tem um teste que manda
`{"url": {"secret": "do-not-echo-me"}}` e afirma que a string não aparece na resposta.

**Por que o 500 não diz nada.** Mensagem de exceção, caminho de arquivo e erro de driver numa
resposta é como detalhe interno vaza para quem está sondando. O traceback vai para o log — e a
forma de mandá-lo para lá tem uma armadilha registrada: o Starlette roda um handler **síncrono**
via `run_in_threadpool`, então ele executa em outra thread que a do `except`, o `sys.exc_info()`
está vazio e `logger.exception` escreve `NoneType: None` no lugar do traceback. O handler passa
`exc_info=exc` explicitamente, e existe um teste afirmando que o traceback está mesmo no log.

## Alternativas consideradas

- **`urn:problem-type:<slug>`.** Não adotada: absoluta e estável, mas num namespace que ninguém
  registrou, e mais longa para o cliente comparar sem ganhar nada verificável.
- **URL `https://` para uma página de documentação.** Não adotada: fixa o host do repositório dentro
  do código e promete manter páginas que este projeto não tem. Continua sendo a escolha certa no dia
  em que a documentação de erro existir.
- **`about:blank` para os erros do framework.** Não adotada, embora seja o que a RFC prescreve: veja
  acima. É a alternativa mais defensável das três e a decisão aqui é de legibilidade, não de
  conformidade.
- **Não tratar `HTTPException` e ficar nas quatro linhas da tabela.** Não adotada: menos código, ao
  custo de a afirmação central do item da fase ser falsa.
- **Um `ProblemResponse` por tipo de erro, com herança.** Não adotada: daria um schema mais preciso
  no OpenAPI e três classes a mais para descrever um envelope que é um só. `exclude_none=True`
  resolve a mesma coisa, e um membro de extensão é opcional por definição na RFC.

## Consequências

**Positivas:**

- Um cliente escreve um parser de erro só, e ele funciona para as cinco situações — inclusive para
  as que o framework produz.
- O `405` continua carregando `Allow`, porque `exc.headers` é repassado. Um `405` sem `Allow` é um
  erro que não diz o que fazer a seguir.
- `400` e `422` seguem significando coisas diferentes, e o handler de validação substituído é o que
  impede o erro mais comum da API de ser o único que não se parece com os outros.
- `reason` dá ao cliente um valor para ramificar sem casar texto em inglês, sem inflar a taxonomia
  de status: os nove motivos de recusa vão todos para um `type` e um status.

**Negativas / custos:**

- **O `type` é uma referência relativa**, então resolvê-lo contra a URI da requisição dá
  `/invalid-target-url` — um caminho com a forma exata dos que a rota catch-all atende. Nada
  dereferencia esse valor na prática, e nenhum cliente deveria, mas o incômodo é real e é o preço de
  ser fiel à tabela do contrato. Trocar por uma URL absoluta é uma constante e uma ADR.
- O OpenAPI gerado anuncia `application/json` para os corpos de erro, e não `application/problem+json`.
  O FastAPI deriva o media type das respostas de erro da classe de resposta da **rota**, e forçar o
  correto exigiria escrever o bloco `content` à mão em cada rota, com o schema inline em vez de
  `$ref`. É cosmético e está registrado como caveat no `PROGRESS-V1.md`.
- Cinco handlers registrados à mão em `register_exception_handlers`, cada um com um
  `# type: ignore[arg-type]` na linha de registro — o Starlette tipa handler como
  `Callable[[Request, Exception], Response]` e, por contravariância, uma assinatura precisa não é
  atribuível a isso. A imprecisão fica na linha de registro, comentada, e não dentro do handler,
  onde o checador está fazendo trabalho útil.
