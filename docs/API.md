# API

Quatro rotas e nada além delas. Não há autenticação, não há versionamento de caminho e não há
paginação — a API é pequena o bastante para caber inteira nesta página. **Todo erro sai no mesmo
envelope**, `application/problem+json` (RFC 7807), inclusive os que o roteador produz antes de
qualquer código deste projeto rodar.

Base local: `http://localhost:8000`, que é o que `docker compose up` publica. Os exemplos abaixo
foram **capturados da aplicação rodando**, não escritos à mão.

- [1. Rotas](#1-rotas)
- [2. Erros (RFC 7807)](#2-erros-rfc-7807)
- [3. Walkthrough do fluxo](#3-walkthrough-do-fluxo)
- [4. OpenAPI e a interface deste projeto](#4-openapi-e-a-interface-deste-projeto)
- [5. Referências](#5-referências)

## 1. Rotas

| Método | Rota | Sucesso | O que faz |
|---|---|---|---|
| `POST` | `/links` | `201 Created` ou `200 OK` | Encurta a URL, ou devolve o link que ela já tinha. |
| `GET` | `/{code}` | `302 Found` | Redireciona para o destino e **registra o acesso**. |
| `GET` | `/links/{code}` | `200 OK` | Destino, data de criação e total de acessos. Não registra nada. |
| `GET` | `/health` | `200 OK` ou `503` | Diz se o serviço consegue falar com o banco. |

Nenhuma das quatro é definida com barra no fim, e a aplicação sobe com `redirect_slashes=False`:
`GET /links/` responde **`404` no envelope de erro**, e não o `307` de conveniência do Starlette.
Aquele `307` monta o `Location` a partir do `Host` que o cliente mandou — exatamente o palpite que
`public_url.py` existe para recusar.

### 1.1 `POST /links` — encurtar

Corpo: um único campo `url`, string. **Campo desconhecido é recusado** (`extra="forbid"`), e a URL
é **guardada e redirecionada exatamente como chegou** — sem normalização, então
`https://example.com` e `https://example.com/` são dois links diferentes. O campo é `str` e não um
tipo de URL do Pydantic, de propósito: [ADR-0005](adr/0005-corpo-de-requisicao-sem-httpurl.md).

```bash
curl -i -X POST localhost:8000/links \
     -H 'content-type: application/json' \
     -d '{"url": "https://docs.python.org/3/library/dataclasses.html"}'
```

**`201 Created`** — a URL era nova:

```http
HTTP/1.1 201 Created
content-type: application/json
location: http://localhost:8000/links/0000001
```

```json
{
  "code": "0000001",
  "short_url": "http://localhost:8000/0000001",
  "url": "https://docs.python.org/3/library/dataclasses.html",
  "created_at": "2026-03-14T15:09:26Z"
}
```

**`200 OK`** — a mesma URL de novo. **Corpo idêntico, sem `Location`:**

```http
HTTP/1.1 200 OK
content-type: application/json
```

```json
{
  "code": "0000001",
  "short_url": "http://localhost:8000/0000001",
  "url": "https://docs.python.org/3/library/dataclasses.html",
  "created_at": "2026-03-14T15:09:26Z"
}
```

Três coisas nesse par valem ser lidas devagar:

- **`201` versus `200` é a única diferença entre os dois desfechos.** O corpo é o mesmo modelo nos
  dois casos, e "foi criado agora" **não** é um campo do corpo — seria o mesmo fato em dois lugares,
  livres para discordar. Quem chama distingue pelo status.
- **O `Location` do `201` aponta para `/links/{code}`, não para a URL curta.** Ele nomeia *o recurso
  que foi criado*, e nesta API isso é o membro da coleção `/links`. `GET /{code}` não é uma
  representação do link, é uma ação sobre ele — e a URL curta já está no corpo.
- **Não há `Location` no `200`.** Nada foi criado, então não há para onde apontar.

O `code` tem sempre **sete caracteres** do alfabeto base 62 (`0-9a-zA-Z`), com zeros à esquerda. O
`short_url` é montado a partir do `BASE_URL` configurado — **a API nunca adivinha o próprio host
público**. O `created_at` vem do relógio do domínio, sempre em UTC, serializado em RFC 3339 com `Z`.

Erros desta rota: `400` quando a política de destino recusa a URL, `422` quando o corpo não tem
sequer a forma certa. A diferença está em [§2](#2-erros-rfc-7807).

### 1.2 `GET /{code}` — seguir o código

```bash
curl -i localhost:8000/0000001
```

```http
HTTP/1.1 302 Found
location: https://docs.python.org/3/library/dataclasses.html
cache-control: no-store
```

Sem corpo. O `Location` carrega a URL de destino **byte a byte como foi enviada**.

**É `302`, nunca `301` e nunca `307`.** O `307` é o default do `RedirectResponse` do Starlette e
está errado aqui por preservar o método, que não é o que um link curto significa; o `301` é pior,
porque o navegador o guarda em cache e o segundo clique nunca chega ao servidor — o que mata a
medição e torna o destino impossível de trocar ou desativar depois.
[ADR-0001](adr/0001-redirect-302.md).

O `Cache-Control: no-store` não acrescenta regra nenhuma: um `302` já não é cacheável sem
informação explícita de validade. Ele torna a regra **verificável com um `curl -i`** em vez de com
uma leitura da RFC 9111.

**O acesso é gravado antes de a resposta ser montada, e uma falha ao gravar derruba o redirect.**
Nada captura essa falha, e isso é decisão e não descuido: não há fila nem outbox, então engolir o
erro transformaria uma falha de banco no único caminho de escrita desta rota numa linha de log sem
nenhum alarme atrás. [ADR-0007](adr/0007-fronteira-da-transacao.md).

O que é registrado: o instante, o `User-Agent`, o `Referer` e o endereço IP de quem chamou — os
três primeiros direto dos cabeçalhos, e o endereço a partir do peer da conexão. Cabeçalho ausente
vira `NULL`; um endereço que não parseia vira `NULL` também, e não um erro.

### 1.3 `GET /links/{code}` — ler o link

```bash
curl -sS localhost:8000/links/0000001
```

```json
{
  "code": "0000001",
  "short_url": "http://localhost:8000/0000001",
  "url": "https://docs.python.org/3/library/dataclasses.html",
  "created_at": "2026-03-14T15:09:26Z",
  "total_clicks": 1
}
```

Os quatro campos do `POST` mais o **`total_clicks`**, que é um `COUNT` sobre a tabela `click` no
momento da leitura — **não** uma coluna de contador em `link`. A tabela `click` só recebe `INSERT`;
o total é calculado na leitura, que é o caminho frio. Ver [§Modelo de dados][modelo] em
`ARCHITECTURE.md`.

**Ler não registra nada.** Só `GET /{code}` grava clique.

### 1.4 `GET /health` — reportar saúde

```bash
curl -sS localhost:8000/health
```

```json
{ "status": "ok" }
```

Servido como `application/json` comum — só a resposta de falha usa o envelope de problema.

**Este endpoint checa a dependência dele.** Ele roda um `SELECT 1` no banco e responde `503` quando
o banco não responde; um health check que sempre devolve `200` é uma mentira. E ele faz isso numa
**segunda engine, sem pool**: a sessão da requisição o alistaria na transação sobre a qual ele
reporta, e a engine da requisição o poria na fila de um pool que a carga esgotou — onde um checkout
espera o `pool_timeout` antes de desistir, e o endpoint travaria para depois culpar o PostgreSQL
por este processo estar ocupado. [ADR-0008](adr/0008-health-responde-503-no-mesmo-envelope.md).

`503` é o único status desta API que não fala sobre a requisição, e **`/health` é a única rota que
o produz**: uma queda do banco nas três rotas de negócio continua sendo `500`.

## 2. Erros (RFC 7807)

Toda falha sai como `application/problem+json` com quatro membros obrigatórios e dois de extensão:

| Membro | Tipo | Sempre presente | O que carrega |
|---|---|---|---|
| `type` | string | sim | O slug da taxonomia, **relativo** — `invalid-target-url`, nunca uma URL absoluta nem uma URN |
| `title` | string | sim | Frase curta e estável, a mesma para todo erro daquele tipo |
| `status` | int | sim | O mesmo status da linha de resposta |
| `detail` | string | sim | O que houve **nesta** requisição |
| `instance` | string | não | O caminho em que a falha aconteceu |
| `reason` | string | só no `400` | O motivo exato da recusa do destino |
| `errors` | lista | só no `422` | Um item por campo inválido: `field`, `message`, `type` |

Os membros de extensão são **omitidos** quando não têm o que carregar, e não serializados como
`null` — um `404` não carrega nem `reason` nem `errors`.

O `type` é um slug relativo por decisão: a RFC chama o membro de referência de URI, e uma relativa
é legal. O que se ganha é ele nunca virar link morto prometendo documentação que ninguém escreveu.

### A taxonomia

Seis tipos, e a lista é fechada:

| Situação | Status | `type` |
|---|---|---|
| O destino foi recusado pela política de domínio | `400` | `invalid-target-url` |
| O corpo não tem a forma que o endpoint aceita | `422` | `validation-error` |
| Nenhum link responde por esse código | `404` | `link-not-found` |
| O **roteador** recusou — método errado, caminho sem rota | do próprio erro | `http-error` |
| Uma dependência não está respondendo — só `/health` | `503` | `service-unavailable` |
| Qualquer coisa não tratada | `500` | `internal-error` |

Três distinções sustentam essa tabela:

- **`400` versus `422`** é *o schema está certo e a regra de negócio diz não* contra *o payload nem
  tem a forma certa*. A validação do Pydantic responde `422` antes de qualquer caso de uso rodar; a
  política de destino responde `400` depois.
- **`http-error` não tem status fixo.** Ele é uma família, não uma situação: o roteador recusa um
  método errado com `405` e um caminho sem rota com `404`, antes de qualquer controlador. O status
  viaja na exceção e o `title` é a frase daquele status. Escrever "`http-error` -> `405`" é errado.
  Ele existe para que "todo erro sai no mesmo envelope" seja literalmente verdade — sem ele, um
  `DELETE /links` responderia `{"detail": ...}` em `application/json`.
  [ADR-0006](adr/0006-envelope-de-erro-problem-details.md).
- **`500`, `http-error` e `503` são três coisas diferentes.** `500` é esta API **falhando**,
  `http-error` é esta API **recusando**, e `503` é esta API **incapaz de servir** porque algo de que
  ela depende está fora. Só o primeiro é bug daqui, e só o último vale tirar uma instância da
  rotação de um balanceador. [ADR-0008](adr/0008-health-responde-503-no-mesmo-envelope.md).

### Exemplo — destino recusado (`400`)

```bash
curl -sS -X POST localhost:8000/links \
     -H 'content-type: application/json' -d '{"url": "javascript:alert(1)"}'
```

```json
{
  "type": "invalid-target-url",
  "title": "The target URL was refused",
  "status": 400,
  "detail": "the scheme 'javascript' is not accepted; only http and https are",
  "instance": "/links",
  "reason": "unsupported-scheme"
}
```

O mesmo tipo, com outro `reason`, para um endereço que aponta para dentro da infraestrutura:

```json
{
  "type": "invalid-target-url",
  "title": "The target URL was refused",
  "status": 400,
  "detail": "169.254.169.254 is not a publicly routable address",
  "instance": "/links",
  "reason": "non-public-address"
}
```

**O `reason` não é uma segunda taxonomia de status.** Os nove motivos possíveis —
`url-too-long`, `forbidden-character`, `malformed-url`, `missing-scheme`, `unsupported-scheme`,
`missing-host`, `credentials-in-url`, `non-public-host`, `non-public-address` — mapeiam todos para
o mesmo `400` e o mesmo `type`. O que cada um recusa está em [`SECURITY.md`](SECURITY.md).

### Exemplo — corpo inválido (`422`)

Faltando o campo:

```json
{
  "type": "validation-error",
  "title": "The request body is not valid",
  "status": 422,
  "detail": "The request does not match the schema this endpoint accepts.",
  "instance": "/links",
  "errors": [
    { "field": "body.url", "message": "Field required", "type": "missing" }
  ]
}
```

Com um campo que a API não conhece:

```json
{
  "type": "validation-error",
  "title": "The request body is not valid",
  "status": 422,
  "detail": "The request does not match the schema this endpoint accepts.",
  "instance": "/links",
  "errors": [
    { "field": "body.ttl", "message": "Extra inputs are not permitted", "type": "extra_forbidden" }
  ]
}
```

O `detail` do `422` é fixo e **não reflete o que foi enviado**. O que é descartado é o `input` do
Pydantic: um corpo arbitrário, de tamanho e forma escolhidos por quem chamou.

### Exemplo — código desconhecido (`404`)

```json
{
  "type": "link-not-found",
  "title": "No link answers to that code",
  "status": 404,
  "detail": "no link exists for code 'aaaaaaa'",
  "instance": "/aaaaaaa"
}
```

**`GET /{code}` e `GET /links/{code}` respondem exatamente a mesma coisa**, e um caminho que nem
tem sete caracteres (`/nao-e-codigo`) responde igual. É de propósito: distinguir "não existe" de
"nem é um código" contaria a quem está enumerando quais palpites eram ao menos bem formados.

### Exemplo — método errado (`405`)

```bash
curl -i -X DELETE localhost:8000/links
```

```http
HTTP/1.1 405 Method Not Allowed
content-type: application/problem+json
allow: POST
```

```json
{
  "type": "http-error",
  "title": "Method Not Allowed",
  "status": 405,
  "detail": "Method Not Allowed",
  "instance": "/links"
}
```

O `Allow` do roteador é preservado — é o único caso em que uma resposta de problema carrega
cabeçalho extra.

### Exemplo — dependência fora (`503`)

```json
{
  "type": "service-unavailable",
  "title": "The service cannot serve requests right now",
  "status": 503,
  "detail": "The database this service depends on is not answering.",
  "instance": "/health"
}
```

O corpo diz **o quê**, e não **onde**: nome da dependência e mais nada. Sem mensagem do driver, sem
host, sem DSN.

## 3. Walkthrough do fluxo

Com a stack de pé (`docker compose up -d --wait`), o fluxo inteiro em quatro chamadas:

```bash
# 1) encurta -- 201, com Location para os metadados
curl -sS -X POST localhost:8000/links \
     -H 'content-type: application/json' \
     -d '{"url": "https://docs.python.org/3/library/dataclasses.html"}'

# 2) a mesma URL de novo -- 200, mesmo codigo, e o banco continua com uma linha
curl -sS -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/links \
     -H 'content-type: application/json' \
     -d '{"url": "https://docs.python.org/3/library/dataclasses.html"}'

# 3) segue o codigo -- 302, e o acesso fica registrado
curl -i -o /dev/null -w 'status=%{http_code} destino=%{redirect_url}\n' localhost:8000/0000001

# 4) o que ficou registrado -- total_clicks: 1
curl -sS localhost:8000/links/0000001
```

Para conferir que a deduplicação é do banco e não de uma checagem em Python, o interessante é a
linha, não a resposta:

```bash
docker compose exec postgres \
  psql -U url_shortener -d url_shortener -c 'SELECT count(*) FROM link;'
```

## 4. OpenAPI e a interface deste projeto

| Recurso | URL |
|---|---|
| Swagger UI | <http://localhost:8000/docs> |
| ReDoc | <http://localhost:8000/redoc> |
| Documento OpenAPI | <http://localhost:8000/openapi.json> |

**O `/docs` é a interface deste projeto.** Não há front-end porque não é preciso um.

O documento gerado **não descreve este envelope sozinho**, e `create_app` o corrige uma vez e
guarda o resultado em cache. São duas correções distintas:

1. O FastAPI arquiva todo corpo de problema sob `application/json`, que é o media type errado.
   Declarar `content` à mão em cada rota não resolve — ele mescla a entrada dele ao lado, deixando
   duas, uma delas errada. A correção **renomeia** a chave para `application/problem+json`.
2. O FastAPI injeta um `422` apontando para o `HTTPValidationError` dele em toda operação que tem
   parâmetro — uma resposta que **não pode acontecer** em `GET /links/{code}` nem em `GET /{code}`,
   onde `code` é uma `str` sem validação. A correção **apaga** essa entrada, e depois remove os
   schemas que ficaram sem ninguém apontando para eles.

O resultado é conferido por teste, e os conjuntos documentados são exatamente estes:

| Operação | Respostas documentadas |
|---|---|
| `POST /links` | `200`, `201`, `400`, `422` |
| `GET /links/{code}` | `200`, `404` |
| `GET /{code}` | `302`, `404` |
| `GET /health` | `200`, `503` |

## 5. Referências

- [ARCHITECTURE.md](ARCHITECTURE.md) — as camadas por trás destas rotas, os dois fluxos em diagrama
  de sequência e o modelo de dados.
- [SECURITY.md](SECURITY.md) — o que a política de destino recusa, motivo por motivo, e o que não
  está defendido.
- [TESTS.md](TESTS.md) — os testes que sustentam cada afirmação desta página.
- [DEVELOPMENT.md](DEVELOPMENT.md) — como subir a stack para rodar os exemplos acima.
- ADRs: [0001](adr/0001-redirect-302.md) · [0005](adr/0005-corpo-de-requisicao-sem-httpurl.md) ·
  [0006](adr/0006-envelope-de-erro-problem-details.md) ·
  [0007](adr/0007-fronteira-da-transacao.md) ·
  [0008](adr/0008-health-responde-503-no-mesmo-envelope.md)

[modelo]: ARCHITECTURE.md#7-modelo-de-dados
