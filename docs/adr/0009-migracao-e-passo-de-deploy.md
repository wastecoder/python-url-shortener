# ADR-0009: A migração é um passo do deploy, e não do startup da aplicação

## Status

Aceito.

## Contexto

A Fase 6 empacota o projeto, e o critério dela é uma frase curta com consequência grande: num clone
limpo, `docker compose up` sobe tudo e o fluxo funciona **sem nenhum passo manual**. Como o schema
só existe através de migration — `Base.metadata.create_all()` é proibido neste projeto, inclusive
nos testes —, isso obriga a responder uma pergunta que até aqui nunca precisou de resposta: **quem
roda `alembic upgrade head`, e quando.**

Até a Fase 5 a resposta era "você, na mão, antes de rodar a aplicação" no desenvolvimento, e a
fixture do Testcontainers dentro da sessão de teste. Nenhuma das duas serve para um `up`.

A pergunta parece de arrumação e não é. Ela decide o que a imagem faz quando alguém a executa, e
decide o que acontece quando a migration falha.

## Decisão

Um serviço próprio no `compose.yml`, `migrate`, **usando a mesma imagem da `api`**, com
`command: ["alembic", "upgrade", "head"]`. Ele espera o `postgres` ficar saudável, roda e sai. A
`api` só é iniciada depois:

```yaml
api:
  depends_on:
    postgres:
      condition: service_healthy
    migrate:
      condition: service_completed_successfully
```

A imagem carrega `alembic.ini` e `migrations/` justamente para que esse serviço exista sem uma
segunda imagem. O processo da aplicação continua sendo só um servidor: nada no `lifespan` toca no
schema.

## Justificativa

**Uma migration acontece uma vez por deploy, não uma vez por processo.** É a frase inteira. Um
serviço web escala por réplica; se migrar for parte de subir, então subir três réplicas é executar
a mesma migration três vezes ao mesmo tempo, e o que acontece aí depende de sorte e do conteúdo da
migration. Com um serviço separado a contagem de réplicas deixa de ter qualquer relação com a
contagem de migrações.

**Uma migration que falha tem que parar o deploy, não produzir uma API servindo.** É a diferença
observável entre as duas opções, e foi medida com a DSN do `migrate` apontada para um banco
inexistente:

```
migrate    Exited (1)
api        Created            <- nunca iniciou
$ curl localhost:8000/health
curl: (7) Failed to connect to localhost port 8000
```

O `docker compose up --wait` sai com código 1 nesse caso, que é o que faz o job do CI reprovar. Com
a migration no startup da API, o mesmo erro daria um container reiniciando em laço e respondendo,
nas janelas em que estivesse de pé, `500` em cima de um schema que não existe.

**A ordem é declarada, não cronometrada.** `service_completed_successfully` é uma condição sobre o
código de saída de outro container. Nenhum `sleep 5`, nenhum retry loop escrito à mão, e nada que
funcione na máquina rápida e falhe na lenta.

**E o processo da aplicação continua sendo uma coisa só.** O `lifespan` de `main.py` lê as
configurações, constrói duas engines e as descarta; ele é executado também pela suíte de testes, que
constrói a aplicação de verdade. Enfiar DDL ali significaria ou migrar dentro de todo teste, ou uma
condicional dizendo quando não migrar — e uma condicional que decide se o banco vai ser alterado é
exatamente o tipo de coisa que ninguém quer descobrir estando errada.

## Alternativas consideradas

- **Entrypoint na própria imagem: `alembic upgrade head && exec uvicorn ...`.** Não adotada. Toda
  réplica migra, que é o problema acima; e, pior, a imagem passa a **alterar o banco como condição
  para iniciar**. Um `docker run` para inspecionar alguma coisa vira uma escrita no schema, o que é
  um efeito colateral que ninguém espera de "subir o servidor".

- **`command: sh -c "alembic upgrade head && uvicorn ..."` no serviço `api`.** Não adotada, e é a
  mais tentadora porque é uma linha. Três custos: a correção da imagem passa a morar no
  `compose.yml`, então `docker run url-shortener:0.1.0` pula a migração em silêncio; a réplica
  continua migrando; e o `sh` vira o pid 1. Um pid 1 sem handler registrado **não recebe**
  `SIGTERM` — o kernel só entrega a ele os sinais que ele trata —, então o shell não sai, o uvicorn
  nunca é avisado, e o Docker espera o `stop_grace_period` inteiro antes de matar com `SIGKILL`.
  **Medido:** um container `sh -c "sleep 300 && echo never"` leva **10,65 s** para parar e sai com
  **137** (128 + 9); a imagem desta fase para em **1,44 s**.

- **Migrar dentro do `lifespan` da aplicação.** Não adotada, pelo motivo do último parágrafo da
  justificativa. É a versão da anterior que também contamina a suíte de testes.

- **`alembic upgrade head` na mão antes do `up`.** Não adotada: é literalmente o passo manual que o
  critério da fase proíbe.

## Consequências

**Positivas:**

- A migração é executável por qualquer orquestrador como *job*, sem shell e sem script: é a mesma
  imagem com outro `command`. `kubectl create job --image=...` e um task do ECS aceitam a mesma
  forma que o compose aceita.
- Uma migração que falha reprova o deploy inteiro, e o CI vê isso pelo código de saída.
- O `docker compose up` de um clone limpo tem, de fato, zero passo manual.

**Negativas / custos:**

- A imagem carrega `alembic.ini` e `migrations/`, e o `alembic` continua sendo dependência de
  runtime e não de desenvolvimento. São alguns kilobytes e um pacote; o preço é aceitável e a
  alternativa seria uma segunda imagem para manter em dia com a primeira.
- **`docker run url-shortener:0.1.0` sozinho não migra nada.** A imagem depende de alguém orquestrar
  os dois passos — o compose aqui, o pipeline de deploy em produção. Isso é acoplamento real, e é
  deliberado: o alternativo é a imagem decidir sozinha alterar um banco.
- O serviço `migrate` precisa de `BASE_URL` no ambiente, que ele nunca usa, porque `migrations/env.py`
  lê o mesmo objeto `Settings` da aplicação e `Settings` proíbe chave extra e não tem default. Fica
  registrado como o que é: um efeito de a configuração ser única, e não uma variável esquecida.
- Não existe serviço de `downgrade`. Reverter uma migration continua sendo um comando na mão, o que
  é adequado enquanto há uma revisão só e vira dívida no dia em que houver dez.
