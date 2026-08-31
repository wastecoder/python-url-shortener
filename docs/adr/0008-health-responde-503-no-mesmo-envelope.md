# ADR-0008: O `/health` responde 503 no mesmo envelope, e é o único 503 da API

## Status

Aceito.

## Contexto

O contrato da API já dizia que o `/health` roda `SELECT 1` a partir da Fase 4 e responde `503`
quando o banco não responde. O que ele não dizia é **que forma tem esse 503**, e a ADR-0006 tornou
isso uma pergunta com consequência: ela fixou que *todo* erro desta API sai no mesmo envelope
Problem Details, e enumerou cinco `type`s. Um `503` é um erro. Ou ele entra nessa enumeração, ou a
frase deixa de ser verdadeira no dia em que o endpoint passa a poder falhar.

Antes desta fase não existia `503` em lugar nenhum do código — a string aparecia só em prosa. Com o
banco de fato em uso, uma queda dele cairia no handler genérico e sairia como `500 internal-error`,
o que está errado duas vezes: contradiz o contrato, e confunde duas coisas que precisam ficar
separadas. `500` é **esta API falhando**; `503` é **esta API não conseguindo servir porque algo de
que ela depende está fora**. Só o primeiro é bug desta API, e só o segundo é acionável por um
balanceador sem acordar ninguém.

Há ainda a pergunta de **em que** o endpoint se apoia para responder, e ela tem uma armadilha que
esta ADR errou na primeira versão. O argumento original era: uma dependência do FastAPI cuja
*aquisição* falha levanta antes do corpo do controller, então um `/health` sobre a `Session` da
requisição responderia `500` na única situação que ele existe para relatar. **Isso é falso, e foi
medido:** `sessionmaker.begin()` não conecta, então adquirir uma sessão contra um banco morto não
falha — a falha cairia no `execute`, dentro do controller, onde daria para tratar.

O que continua verdadeiro, e é o motivo real, é outra coisa: uma sessão sai do **pool** das
requisições, e um checkout de pool esgotado não falha rápido — ele *espera*, até `pool_timeout`,
trinta segundos por padrão. Um `/health` assim penduraria por meio minuto e depois chamaria o banco
de indisponível porque este processo estava ocupado: um relato sobre a carga local, publicado como
um relato sobre o PostgreSQL.

## Decisão

**1. Um sexto membro em `ProblemType`: `SERVICE_UNAVAILABLE = "service-unavailable"`**, e um sexto
handler, para uma exceção `ServiceUnavailableError` do adaptador web.

**2. A exceção é do adaptador, e não do domínio.** "A dependência está fora" não é um conceito de
negócio; o domínio não conhece HTTP nem banco, e nenhum módulo dele importa status.

**3. O `/health` depende de um `HealthProbe`, e o `HealthProbe` devolve `bool`.** O `Protocol` fica
ao lado do controller que o consome, em `adapter/web/`; quem o satisfaz é o `DatabaseProbe`, em
`adapter/persistence/database/`. A implementação abre uma conexão, roda `SELECT 1`, e converte
qualquer `SQLAlchemyError` em `False`, registrando a causa no log.

**4. O probe roda sobre uma engine própria, com `NullPool`.** É a segunda engine da aplicação,
construída no mesmo lifespan e descartada com a outra. Sem pool não há fila: cada checagem abre e
fecha sua conexão, e o `connect_timeout` passa a ser o limite real de quanto o endpoint pode
demorar. Compartilhar a engine das requisições faria o `/health` esperar no mesmo `QueuePool`, que é
exatamente o defeito descrito no Contexto — e foi o que a primeira implementação fez, até uma
revisão medi-lo.

**5. Adquirir o probe não pode falhar**: é uma leitura de atributo e um construtor. A decisão
200-ou-503 acontece portanto dentro do corpo do controller, onde ela é alcançável.

**6. É o único `503` da API.** As três rotas de negócio continuam respondendo `500` quando o banco
cai.

**7. O corpo de sucesso não muda.** Um `/health` saudável continua respondendo
`200 {"status": "ok"}` em `application/json`; só o caminho de falha entra no envelope de erro.

## Justificativa

**Por que um `type` novo em vez de reaproveitar `http-error`.** `HTTP_ERROR` tem um significado
preciso, escrito na ADR-0006: é o roteador **recusando** antes de qualquer código deste projeto
rodar — um `405` de método errado, um `404` de caminho não casado. Um `503` do `/health` é o oposto:
é um controller nosso, tendo rodado, relatando o que descobriu. Empilhar os dois no mesmo `type`
apagaria a distinção que fez `http-error` existir.

**Por que não `{"status": "down"}` com status 503.** Seria o corpo mais óbvio e custaria menos
código. Foi recusado porque quebra a afirmação central da ADR-0006 — e não só no papel:
`test_every_documented_error_body_is_a_problem_document` reprova qualquer resposta documentada `>=
400` cujo corpo não seja `application/problem+json`, então adotar essa forma exigiria afrouxar o
teste que trava a decisão. Afrouxar o teste para caber a exceção é como uma afirmação verificada
vira uma afirmação decorativa.

**Por que o probe devolve `bool` em vez de levantar.** Porque é o que mantém `adapter/web/` sem
nenhum import de SQLAlchemy. Se o controller precisasse capturar `SQLAlchemyError`, a camada web
passaria a conhecer o driver — e o `Protocol` existe justamente para que ela conheça apenas a
pergunta que faz. O motivo da falha não se perde: ele vai para o log, do lado que sabe o que
`OperationalError` significa.

**Por que o `Protocol` fica no adaptador e não em `application.port.outbound`.** Porque `/health`
não é caso de uso. Não existe porta de entrada para ele, nenhum caso de uso o executa, e a camada de
aplicação não tem por que saber que esse endpoint existe. Criar uma porta ali faria a `application`
crescer para servir um detalhe de operação — exatamente a direção que a arquitetura deste projeto
existe para impedir. O `Protocol` mora onde mora seu consumidor, que é a regra que as portas de
saída já seguem, uma camada acima.

**Por que só o `/health`.** Classificar `OperationalError` como `503` nas rotas de negócio é
defensável e foi considerado. Custa mais do que entrega: ou o adaptador web passa a conhecer as
exceções do driver, ou o repositório traduz erro de infraestrutura em erro de aplicação e a porta
ganha um vocabulário que ela hoje não tem. E o ganho para o cliente é pequeno — quem recebe `500`
num `POST /links` vai tentar de novo do mesmo jeito. Fica registrado como o lugar exato onde essa
mudança entraria, se um dia valer.

## Alternativas consideradas

- **`/health` dependendo da mesma `SessionDep` das outras rotas.** Não adotada, por dois motivos —
  e nenhum deles é o que esta ADR alegava a princípio. Alistaria o `/health` na transação da
  requisição, sobre a qual ele não deveria reportar; e o tiraria do pool das requisições, onde um
  checkout espera `pool_timeout` antes de desistir. O motivo que **não** vale é o que estava escrito
  aqui: a aquisição não falha, porque `sessionmaker.begin()` não conecta.
- **Injetar a `Engine` direto no controller.** Não adotada, e é a alternativa mais próxima: está
  correta e é menor. Perde na testabilidade — para exercitar o ramo `200` sem Docker a suíte teria
  de forjar um objeto `Engine`, que é desajeitado de construir, e na prática um dos dois ramos
  ficaria sem teste. Com o `Protocol`, os dois são duas linhas de fake.
- **Manter `HealthResponse` com `status: "down"` e responder `503` em `application/json`.** Não
  adotada: veja a justificativa.
- **`about:blank`, como a RFC prescreve para problemas sem nome próprio.** Não adotada, pelo mesmo
  motivo que a ADR-0006 já registrou: a taxonomia deste projeto é lida por um humano antes de ser
  lida por um cliente.
- **Responder `503` também nas três rotas de negócio quando o driver falha.** Não adotada: veja a
  justificativa.

## Consequências

**Positivas:**

- "Todo erro desta API sai no mesmo envelope" continua literalmente verdadeiro, agora com seis
  `type`s, e continua verificado pelo mesmo teste em vez de por uma exceção escrita nele.
- O `/health` vira acionável: um balanceador tira a instância do rodízio no `503` e não confunde
  isso com um bug da aplicação.
- Nenhum arquivo de `adapter/web/` importa SQLAlchemy, apesar de o `/health` consultar o banco.
- Os dois ramos do endpoint são testáveis sem Docker, então o `503` não é um caminho que só existe
  em produção.

**Negativas / custos:**

- A taxonomia cresceu, e com ela a tabela de erros do `CLAUDE.md` e o documento OpenAPI: o `/health`
  passa a declarar `["200", "503"]`, e o teste que fixava `["200"]` muda junto.
- **Um `Protocol` dentro do adaptador é incomum**, e convida à pergunta "por que isso não é uma
  porta?". A resposta está na justificativa, e precisa estar pronta.
- Cada chamada ao `/health` abre e fecha uma conexão, porque a engine do probe usa `NullPool`. Num
  health check batido de segundo em segundo isso é uma conexão por segundo — irrelevante nesta
  escala, e é o preço de o endpoint não ficar na fila do pool sobre o qual ele reporta.
- **Duas engines por processo**, e portanto duas coisas para o lifespan descartar. Um teste afirma
  que as duas são descartadas no shutdown, porque esquecer a segunda seria um vazamento que só
  aparece depois de muitos reinícios.
- Um sexto handler registrado à mão, com o mesmo `type: ignore[arg-type]` que quatro dos cinco
  atuais carregam, pela contravariância da assinatura que o Starlette declara.
