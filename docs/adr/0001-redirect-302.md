# ADR-0001: O redirect é 302, não 301

## Status

Aceito.

## Contexto

O `GET /{code}` responde com um redirect para a URL longa. Há duas escolhas defensáveis, `301 Moved
Permanently` e `302 Found`, e a diferença entre elas não é só semântica de HTTP: ela decide se o
serviço continua enxergando o tráfego depois do primeiro acesso.

O `301` é cacheado pelo navegador. Da segunda vez em diante o cliente vai direto ao destino sem
passar por aqui. Este projeto tem uma tabela `click` e uma rota que devolve o total de acessos —
as duas dependem de o acesso passar pelo serviço.

## Decisão

`302 Found`, com o `Location` apontando para a URL longa, em todo redirect.

O default do `RedirectResponse` do Starlette é `307`, então o `status_code=302` é explícito no
código e está coberto por teste.

## Alternativas consideradas

- **`301 Moved Permanently`.** Não adotado. Ele alivia carga — é literalmente para isso que serve —
  mas mata a contagem de acesso e, pior, torna impossível trocar ou desligar o destino para quem já
  acessou uma vez, porque o cache do navegador não tem invalidação. Seria a escolha certa se a
  prioridade fosse carga; a prioridade aqui é medição e controle.
- **`307 Temporary Redirect`.** Não adotado. Preserva o método HTTP, o que não faz sentido para um
  link curto: clicar num link é sempre `GET`. É o default do Starlette e, por isso, o erro mais
  fácil de cometer neste projeto.
- **`308 Permanent Redirect`.** Não adotado: junta a objeção do `301` com a do `307`.

## Consequências

**Positivas:**

- Todo acesso passa pelo serviço, então a medição existe de verdade.
- O destino continua sob controle: trocar, desativar e expirar (V2) só funcionam com `302`.

**Negativas / custos:**

- Cada acesso é uma requisição ao servidor e uma consulta ao banco. Em volume alto, isso é
  exatamente o problema que o cache da Fase 10 do `PROGRESS-V2.md` resolveria — e é por isso que o
  repositório está atrás de uma porta.
