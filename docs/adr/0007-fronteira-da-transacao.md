# ADR-0007: A transação commita antes de a resposta ser enviada

## Status

Aceito.

## Contexto

A Fase 2 fixou três coisas sobre a escrita, e deixou a quarta em aberto de propósito.

**O que estava fixado.** Nenhuma porta tem `commit`, `flush`, nem um `UnitOfWork` ao lado: um caso
de uso capaz de commitar é um caso de uso capaz de commitar metade de um fluxo, e o método não
significaria nada para uma implementação em memória. `ClickRepository.record` emite o `INSERT` na
hora, e não apenas empilha um `session.add`. E uma falha ao gravar o clique **derruba o redirect** —
nada envolve o `record` num `try`, porque um link que silenciosamente para de ser medido é
exatamente o que responder `302` em vez de `301` existe para impedir.

**O que não estava.** Onde o `COMMIT` acontece. A docstring da porta diz que a transação pertence à
borda da requisição, no adaptador — e a borda da requisição tem mais de um lugar.

O formato usual — uma dependência `yield` que commita no código de saída — parece atender e não
atende. No FastAPI, o padrão dessas dependências é encerrar **depois** de a resposta já ter sido
enviada ao cliente. Um `COMMIT` que falha ali não tem mais resposta para mudar: o chamador já
recebeu `201 Created` com um código, ou `302 Found` com um destino, e nenhuma linha foi gravada. A
decisão da Fase 2 viraria falsa na prática sem que uma única linha dela fosse editada.

**Medido, não suposto.** Com o FastAPI 0.141.1 que este projeto trava, uma dependência `yield` cujo
código de saída levanta, sob os três escopos possíveis:

| `scope` | O que o cliente recebe |
|---|---|
| `"function"` | `500 application/problem+json` — o envelope do próprio projeto |
| `"request"` | `200 application/json` — o corpo de sucesso; a falha só existe no log |
| omitido (o default) | idêntico a `"request"` |

O default é o caso errado.

**E um fato que decide o resto:** nenhuma requisição desta API faz mais de um statement de escrita.
`POST /links` é um `SELECT`, um `nextval` e um `INSERT` — mais uma releitura, quando perde a
corrida. `GET /{code}` é um `SELECT` e um `INSERT`. `GET /links/{code}` são dois `SELECT`s. Não
existe atomicidade multi-statement a proteger aqui. A escolha não é sobre consistência: é sobre
**onde a falha aparece**.

## Decisão

**1. Uma `Session` por requisição, aberta por `get_session` em `adapter/config/dependencies.py`,
declarada com `Depends(get_session, scope="function")`.** O escopo é a decisão inteira em uma
palavra: ele faz o código de saída rodar em volta da *função de rota*, e não em volta do *ciclo da
requisição*, portanto antes de a resposta ir para o fio.

**2. A transação é o `begin()` do `sessionmaker`, e não um `commit()` escrito à mão:**

```python
def get_session(request: Request) -> Iterator[Session]:
    with _session_factory(request).begin() as session:
        yield session
```

Saída limpa commita, exceção faz rollback, e as duas coisas estão no gerenciador de contexto do
SQLAlchemy em vez de num `try/except/raise` que alguém precisa reler para conferir.

**3. Os dois repositórios recebem a mesma `Session`.** `get_link_repository` e
`get_click_repository` declaram `SessionDep`, e o cache de sub-dependências do FastAPI entrega uma
instância só por requisição. O `SELECT` do link e o `INSERT` do clique de um redirect são, de fato,
uma transação.

**4. As escritas usam Core — `session.execute(insert(...))` — e nunca `session.add`.** Isso mantém
literalmente verdadeira a promessa de `record`: o `INSERT` sai no momento da chamada, então erro de
constraint, de chave estrangeira ou de conectividade levanta **dentro do caso de uso**, e não no
código de saída. Só a falha do `COMMIT` em si depende do escopo escolhido acima.

**5. `GET /health` fica fora dessa transação.** Ele não depende da `Session`; abre sua própria
conexão curta pela engine. Um `/health` alistado na transação da requisição falharia por
esgotamento de pool — um motivo que nada tem a ver com a saúde que ele relata.

**6. Nenhuma porta ganha `commit`.** A decisão desta ADR é inteiramente do adaptador, e o
`application` não muda uma linha por causa dela.

## Justificativa

**Por que o `scope="function"` e não um middleware.** Os dois commitam antes da resposta. O
middleware custa mais: a sessão passa a ser montada em dois pedaços — um cria e guarda em
`request.state`, o provider lê de volta —, ele roda também para `/docs` e `/openapi.json`, e o
`BaseHTTPMiddleware` traz suas próprias ressalvas de ordenação com respostas em streaming. Máquina a
mais para o mesmo resultado observável.

**Por que não commitar dentro de cada método de escrita do repositório.** Seria robusto e é
defensável — a falha passaria a levantar dentro do caso de uso sem depender de nenhuma sutileza de
framework, e a releitura do passo 4 da deduplicação ganharia uma transação nova, o que fecharia o
ramo `RuntimeError` do `CreateLinkUseCaseImpl` até sob `REPEATABLE READ`. Foi recusada por
contradizer o que a porta já afirma: a transação pertence à borda da requisição. Com o commit no
repositório, a resposta à pergunta "qual é a unidade de trabalho desta API?" passa a ser "não há
nenhuma" — verdadeira hoje, e frágil no dia em que uma rota fizer duas escritas.

**Por que não `AUTOCOMMIT` na engine.** É a menor superfície possível e faz o `INSERT` do clique ser
durável sozinho. Mas fecha a porta para tornar dois statements atômicos sem trocar a engine, lê-se
estranho ao lado de uma `Session`, e rebaixa o argumento de `READ COMMITTED` que já está escrito no
`create_link_use_case.py` — ele fala sobre o que a *transação* enxerga, e sem transação a frase muda
de assunto.

**O que cada rota faz, e o que uma falha em cada ponto produz.**

| Rota | Statements na transação | Falha no commit |
|---|---|---|
| `POST /links` | `SELECT` por hash, `nextval`, `INSERT ... ON CONFLICT` | `500`, e nada fica |
| `GET /{code}` | `SELECT` do link, `INSERT` do clique | `500` — a decisão da Fase 2 |
| `GET /links/{code}` | dois `SELECT`s | um commit sem escrita não falha |

**O `nextval` é a exceção, e é intencional.** Uma sequence não obedece a rollback: o valor lido no
passo 3 é gasto mesmo que a transação inteira volte atrás. O buraco resultante é esperado e
inofensivo — a sequence é um gerador de id, não uma contagem de links — e é a mesma razão pela qual
`validate_target_url` roda **antes** dela.

**Um 404 continua sendo um 404.** Medido: com `scope="function"`, um `LinkNotFoundError` levantado
pelo endpoint é jogado *dentro* do gerador — o `begin()` faz rollback — **e** ainda chega ao handler
que o mapeia para `404 application/problem+json`. As duas coisas ao mesmo tempo. Se não fosse assim,
esta ADR teria trocado toda recusa de negócio por um `500`.

## Alternativas consideradas

- **Dependência `yield` com o escopo default.** Não adotada, e é a armadilha que esta ADR existe
  para registrar: o código idêntico, sem a palavra `scope`, entrega ao cliente o `302` de um
  redirect que não gravou nada. Nenhum teste do projeto reprovaria.
- **Commitar dentro de `save` e de `record`.** Não adotada: contradiz a docstring da porta e apaga a
  noção de unidade de trabalho. Veja a justificativa.
- **`create_engine(..., isolation_level="AUTOCOMMIT")`.** Não adotada: menor superfície, ao custo de
  não poder tornar dois statements atômicos sem trocar a engine.
- **`BaseHTTPMiddleware` ou um `APIRoute` customizado que commita antes de escrever a resposta.**
  Não adotada: independente de versão do FastAPI, e é a alternativa a adotar se o `scope` sumir —
  mas hoje é máquina a mais para o mesmo resultado.
- **`commit()` no fim do corpo do controller.** Não adotada, e desqualificada duas vezes: põe uma
  chamada de persistência num controller que hoje não importa sessão nenhuma, e quebra o critério da
  própria fase, de que o commit da troca não toca em nenhum arquivo de `adapter/web/`.

## Consequências

**Positivas:**

- A decisão da Fase 2 — uma falha ao gravar o clique derruba o redirect — passa a ser verdade
  observável de ponta a ponta, e não só verdade dentro do caso de uso.
- Um erro em qualquer ponto da escrita sai no envelope Problem Details do projeto, porque acontece
  enquanto ainda existe resposta para trocar.
- `application` e `domain` não mudam uma linha. A ADR inteira mora em um arquivo do adaptador.
- O redirect lê o link e grava o clique na mesma transação e no mesmo snapshot, sem que nenhum caso
  de uso precise saber disso.

**Negativas / custos:**

- **A garantia depende de um recurso do FastAPI ≥ 0.121.** Um upgrade que mude o comportamento do
  `scope` reverteria silenciosamente para o caso errado, com a suíte inteira verde. Por isso existe
  um teste que lê o `scope` declarado na rota e afirma `"function"` — ele não prova o comportamento,
  prova que a palavra não foi apagada; o comportamento é o que o experimento acima mediu, e o que um
  teste de integração da Fase 5 pode envenenar de propósito.
- **`dependency_overrides` não consegue simular isso.** O escopo é lido do `Depends` original, então
  um override troca a dependência mas não o momento em que ela encerra. Um teste unitário não
  alcança essa ordenação.
- **Uma transação por requisição significa uma conexão segurada durante a rota inteira**, inclusive
  enquanto o FastAPI serializa a resposta. No tamanho deste projeto é irrelevante; num que faça I/O
  externo no meio do handler, não seria.
- O `/health` precisou ficar de fora, e essa exceção teve que ser escrita em vez de descoberta.
