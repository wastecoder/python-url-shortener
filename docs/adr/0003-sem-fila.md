# ADR-0003: Sem fila, e o lugar exato onde ela entraria

## Status

Aceito.

## Contexto

O `GET /{code}` faz duas coisas: responde o redirect e registra o acesso. Um encurtador em escala
publica o clique numa fila e responde imediatamente, deixando um worker agregar depois. A pergunta
é se essa peça paga neste projeto.

Vale registrar a pergunta invertida também, porque ela é a metade mais interessante da resposta:
**onde a fila atrapalharia.**

## Decisão

Nenhuma fila no V1. O registro do clique é um `INSERT` síncrono, no caminho do redirect, numa
tabela `click` append-only.

## Justificativa

Um `INSERT` numa tabela append-only custa fração de milissegundo e **não disputa lock com
ninguém** — é justamente por isso que `click` é uma tabela separada e não um contador dentro de
`link`. Um contador seria uma escrita no caminho de leitura, na mesma linha, e dois acessos
simultâneos ao mesmo link disputariam aquele lock.

Fila sem justificativa é o erro mais comum de projeto de portfólio. O critério que decide não é "é
assíncrono, então põe fila".

**Onde ela entraria, se entrasse:** o clique, e só o clique. Na premissa do livro são 11.600
leituras por segundo; nessa escala o redirect responde `302` na hora e publica o evento, e um
worker consome e agrega. O critério é este: **perder um clique é aceitável, atrasar um redirect
não.**

**Onde ela não entra:** a criação do link é síncrona de propósito. Quem chamou precisa do código de
volta na mesma requisição — não dá para responder `202 Accepted` a alguém que está esperando uma
URL para colar em algum lugar agora.

## Alternativas consideradas

- **Fila para o clique já no V1.** Não adotada: acrescentaria broker, worker, entrega
  at-least-once e consumidor idempotente para resolver um problema de volume que este projeto não
  tem. Registrada na Fase 10 do `PROGRESS-V2.md`.
- **Contador dentro de `link`, sem tabela de cliques.** Não adotada, e pelo motivo oposto ao que
  parece: seria *mais* simples de escrever e *pior* de operar, por causa da contenção de linha
  descrita acima. Trocar contenção na rota quente por um `COUNT` na rota fria é a decisão certa.

## Consequências

**Positivas:**

- Nada de broker, nada de worker, nada de idempotência de consumidor para manter. O
  `compose.yml` tem dois serviços.
- O caminho do redirect é uma consulta e uma inserção, e nada mais.

**Negativas / custos:**

- Sob carga alta, o `INSERT` do clique está no caminho quente, e uma falha de escrita derruba o
  redirect junto — que é exatamente a razão pela qual a fila entraria. O gatilho para reabrir esta
  decisão é medição, não intuição.
