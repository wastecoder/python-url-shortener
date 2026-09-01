# Segurança

Um encurtador de URL é, por definição, um serviço que aceita um endereço de um estranho e faz duas
coisas perigosas com ele: **busca-o** — não neste projeto, mas em qualquer variante que gere
preview — e **manda outra pessoa até lá**, com a reputação do seu domínio na frente. Este documento
diz o que é recusado, o que protege a configuração e a imagem, e — igualmente importante — **o que
não está defendido**.

> Não há autenticação, não há autorização e não há limite de taxa neste projeto, de propósito. O
> corte está registrado na tabela do [`README.md`](../README.md) e o item de roadmap em
> [`PROGRESS-V2.md`](PROGRESS-V2.md). O que este documento cobre é a superfície que **existe**.

Todas as recusas abaixo foram **executadas contra a política real** deste repositório; os motivos e
as mensagens são a saída literal.

- [1. A superfície de ataque](#1-a-superfície-de-ataque)
- [2. O que a política de destino recusa](#2-o-que-a-política-de-destino-recusa)
- [3. O que é aceito](#3-o-que-é-aceito)
- [4. Segredos e configuração](#4-segredos-e-configuração)
- [5. A imagem e o processo](#5-a-imagem-e-o-processo)
- [6. O que as respostas de erro não contam](#6-o-que-as-respostas-de-erro-não-contam)
- [7. O que não está defendido](#7-o-que-não-está-defendido)
- [8. Referências](#8-referências)

## 1. A superfície de ataque

Um encurtador que aceita qualquer coisa vira três ferramentas ao mesmo tempo:

| Ameaça | O que o atacante consegue |
|---|---|
| **Redirect aberto** | Usa o seu domínio como trampolim: a vítima vê um link seu, o navegador termina no site de phishing. A reputação gasta é a sua |
| **XSS por esquema** | `javascript:` num `Location` era XSS refletido em navegadores antigos, e continua sendo um link que executa código quando colado numa barra de endereço |
| **SSRF contra a própria infraestrutura** | Um link para `169.254.169.254` ou `10.0.0.1` transforma qualquer coisa que siga o link — um scanner, um preview, um bot interno — numa sonda dentro da sua rede |

A defesa mora em `domain/service/url_policy.py`, é **função pura** e é chamada como **a primeira
instrução** do caso de uso de criação — antes do hash, antes de a sequence ser tocada. Uma URL
recusada não gasta código, não escreve linha e não deixa rastro.

`validate_target_url` devolve `None` quando aceita e levanta `InvalidTargetUrlError` quando recusa,
com um `RejectionReason` anexado. Do lado HTTP, **todas as recusas viram um único `400` com
`type: invalid-target-url`**, e o motivo viaja como o membro de extensão `reason` — não como uma
segunda taxonomia de status.

## 2. O que a política de destino recusa

Onze pontos de recusa, na ordem em que rodam, e nove motivos (`forbidden-character` cobre três
situações diferentes).

### Antes de parsear, na string crua

| Entrada | `reason` | Mensagem |
|---|---|---|
| URL com 2049 caracteres | `url-too-long` | `the URL is 2049 characters long and the limit is 2048` |
| `https://example.com/a b` | `forbidden-character` | `the URL contains ' ', which has to be percent-encoded` |
| `https://example.com/a\tb` | `forbidden-character` | `the URL contains '\t', which has to be percent-encoded` |
| `https://example.com/a\nb` | `forbidden-character` | `the URL contains '\n', which has to be percent-encoded` |

**Este scan roda na string crua, antes do parser, e a ordem é o ponto.** O parser da biblioteca
padrão **apaga** tabulação, retorno de carro e quebra de linha de qualquer posição da URL, e tira os
controles do começo — então uma URL que carrega esses caracteres **parseia como uma coisa e seria
guardada como outra**. O conjunto proibido é todo controle C0, o espaço e o DEL:
`U+0000`–`U+0020` mais `U+007F`.

O limite de 2048 é de fronteira exata: uma URL com exatamente 2048 caracteres é **aceita**.

### O esquema e as credenciais

| Entrada | `reason` |
|---|---|
| `javascript:alert(1)` | `unsupported-scheme` |
| `file:///etc/passwd` | `unsupported-scheme` |
| `data:text/html,<script>alert(1)</script>` | `unsupported-scheme` |
| `ftp://example.com/x` · `mailto:someone@example.com` | `unsupported-scheme` |
| `example.com/path` · `//example.com/path` | `missing-scheme` |
| `https://user:secret@example.com/` | `credentials-in-url` |
| `https://user@example.com/` | `credentials-in-url` |
| `https://@example.com/` | `credentials-in-url` |
| `http://` · `http:///path` | `missing-host` |
| `http://example.com:99999/` | `malformed-url` (`Port out of range 0-65535`) |
| `http://[::1/` | `malformed-url` (`Invalid IPv6 URL`) |

Só `http` e `https` são aceitos — **allowlist, não denylist**, que é a única forma que não fica
obsoleta quando alguém inventa um esquema novo.

A checagem de credencial testa **ausência, não veracidade**: `parts.username is not None`. É por
isso que `https://@example.com/` — nome de usuário vazio — também é recusado. Testar só o nome basta:
uma senha não parseia sem um, então `:secret@host` chega com nome `""` e não `None`.

`malformed-url` só é alcançável porque a porta é **lida** durante a validação. Deixada sem ler, uma
porta impossível apareceria muito depois como erro não tratado, em vez de como recusa.

### O host, quando é um endereço literal

Todos abaixo recusados com `non-public-address`:

| Faixa | Exemplo medido |
|---|---|
| Loopback | `127.0.0.1` · `::1` |
| Endereço nulo | `0.0.0.0` |
| Privados (RFC 1918) | `10.0.0.1` · `172.16.0.1` · `192.168.1.1` |
| **Metadados de cloud** | `169.254.169.254` (link-local `169.254/16`) |
| Carrier NAT | `100.64.0.1` |
| Broadcast e reservados | `255.255.255.255` |
| Multicast | `224.0.0.1` · `ff02::1` |
| IPv6 únicos locais e link-local | `fc00::1` · `fe80::1` |
| IPv6 site-local depreciado | `fec0::1` |
| **IPv4 embrulhado em IPv6** | `::ffff:127.0.0.1` · `::ffff:10.0.0.1` · `2002:7f00:1::` (6to4) · `64:ff9b::7f00:1` (NAT64) |

A decisão é `address.is_global and not address.is_multicast`, e **`is_global` e não `is_private`**:
perguntar `is_private` deixaria o carrier NAT passar, porque aquela faixa não é nem privada nem
global. O multicast é a única coisa que o `is_global` ainda chama de global, e sai à mão.

As quatro grafias de IPv6 que carregam um IPv4 são desembrulhadas e reperguntadas: só a mapeada
(`::ffff:a.b.c.d`) e a 6to4 já são vistas pelo `is_global`; a compatível (`::/96`) e o prefixo NAT64
(`64:ff9b::/96`) foram acrescentadas à mão.

O ponto final do DNS é removido com `rstrip(".")` **antes** da checagem de endereço, e não com
`removesuffix` — `127.0.0.1..` também existe. Sem isso, `127.0.0.1.` passaria pela checagem de
endereço como se fosse um nome.

### O host, quando é um nome

| Entrada | `reason` | Por quê |
|---|---|---|
| `http://127.0.0.1\` | `forbidden-character` | O parser segue a RFC 3986 e vê o host `127.0.0.1\`; **o navegador segue o WHATWG e vê `127.0.0.1`** com o resto virando caminho |
| `http://%6c%6fcalhost.example.com/` | `forbidden-character` | Host percent-encoded |
| `http://-example.com/` · `http://example-.com/` | `forbidden-character` | Hífen no começo ou no fim de um rótulo |
| `http://a..b.com/` | `forbidden-character` | Rótulo vazio |
| `http://exämple.com/` | `forbidden-character` | Host não-ASCII; mande como punycode |
| `http://localhost/` · `http://LOCALHOST/` | `non-public-host` | Nome local exato |
| `http://something.localhost/` | `non-public-host` | Sufixo `.localhost` |
| `http://printer.local/` | `non-public-host` | Sufixo `.local` |
| `http://db.internal/` | `non-public-host` | Sufixo `.internal` |
| `http://gw.home.arpa/` | `non-public-host` | Sufixo `.home.arpa` |
| `http://intranet/` | `non-public-host` | Rótulo único: sem ponto, só pode nomear algo na rede de quem chamou |
| `http://2130706433/` | `non-public-host` | **`127.0.0.1` em decimal** |
| `http://0x7f000001/` | `non-public-host` | **`127.0.0.1` em hexadecimal** |
| `http://127.1/` | `non-public-host` | **Forma curta de `127.0.0.1`** |
| `http://0177.0.0.1/` | `non-public-host` | **`127.0.0.1` em octal** |

As quatro últimas são as interessantes: **o `ipaddress` não as lê como endereço, mas o navegador
resolve todas para `127.0.0.1`.** Elas são pegas pela última regra do ramo de nomes — o rótulo final
tem que ser inteiramente alfabético ou começar com `xn--`. `2130706433` não é nenhum dos dois.

A checagem de "isto está escrito como um nome de host?" existe por causa de um desacordo real entre
padrões, e não por capricho: o parser usado aqui segue a **RFC 3986**, todo navegador segue o
**WHATWG URL Standard**, e os dois discordam sobre a barra invertida. Sem essa checagem,
`http://127.0.0.1\` navegaria direto.

## 3. O que é aceito

Medido, para a lista de recusas não parecer maior do que é:

```text
https://example.com/a?b=1#c          http://8.8.8.8/
http://example.com                   http://172.32.0.1/      (fora de 172.16/12)
https://example.com:8443/path        https://[2001:4860:4860::8888]/
https://example.com./                https://[::ffff:8.8.8.8]/
https://sub.domain.example.co.uk/x   http://my-site.example.com/
https://xn--e1afmkfd.xn--p1ai/       http://under_score.example.com/
https://localhost.example.com/       http://127.0.0.1.example.com/
```

As duas últimas colunas merecem atenção: **`localhost.example.com` e `127.0.0.1.example.com` são
nomes públicos legítimos** — o que decide é o rótulo final, não o começo da string. Uma checagem por
`"localhost" in host` recusaria os dois e seria pior do que inútil.

O sublinhado é aceito num rótulo de host de propósito, apesar de tecnicamente não ser legal: ao
contrário dos caracteres que essa regra existe para pegar, **nenhum parser de URL discorda sobre o
que ele significa**.

**A URL não é normalizada em lugar nenhum.** Ela é guardada, hasheada e redirecionada exatamente
como chegou. Isso é carregado: normalizar faria a linha deixar de conter o que quem chamou mandou —
e duas grafias do mesmo endereço deixariam de ser dois links. A consequência é que
`https://example.com` e `https://example.com/` são **dois links distintos**.

## 4. Segredos e configuração

- **Nenhum segredo no código, nunca.** Toda configuração vem de variável de ambiente por
  `adapter/config/settings.py`.
- **`.env` está no `.gitignore`; `.env.example` é versionado** e não carrega segredo nenhum — só o
  DSN de desenvolvimento que o `compose.yml` também usa.
- **Nada tem default.** `Settings` não dá default a `DATABASE_URL` nem a `BASE_URL`, e usa
  `extra="forbid"`. Uma configuração faltando **falha alto no startup** em vez de rodar em silêncio
  contra o banco errado.
- **O `compose.yml` não usa `env_file: .env`**, e a ausência é decisão: o `.env` de quem seguiu o
  `.env.example` aponta para `localhost:5432`, que dentro de um container é o próprio container.
- **As credenciais do `compose.yml` são de desenvolvimento** e a porta `5432` é publicada em **todas
  as interfaces da máquina**, não só em loopback. Aceitável para um banco de laptop que não guarda
  nada — e exatamente a razão de um banco publicado ter credencial vinda do ambiente e nunca de um
  arquivo do repositório.

## 5. A imagem e o processo

| Defesa | Como |
|---|---|
| **Processo não-root** | Usuário e grupo de sistema `app`, uid/gid fixos em `10001`, sem diretório home, shell `/usr/sbin/nologin` |
| **Uid fixo, e não alocado** | Permissão em mount é um número e não um nome; um uid que a distribuição escolhe pode se mover entre versões da imagem base e levar a permissão de um volume junto |
| **O processo não pode reescrever o que executa** | `.venv` e `migrations/` são copiados **sem `--chown`**: root é o dono, modo 0755/0644, e o usuário tem exatamente o que usa — ler e executar |
| **Contexto de build como allowlist** | `.dockerignore` começa com `*` e libera seis entradas por nome. Um denylist erra por omissão: o próximo arquivo com credencial criado na raiz entraria sem ninguém decidir |
| **Sem `curl` na imagem** | O `HEALTHCHECK` usa `urllib` da biblioteca padrão. Instalar um pacote para o healthcheck seria pagar superfície de ataque por conveniência |
| **Sem `src/` na imagem final** | A aplicação está instalada como wheel dentro da venv; o estágio final não carrega código-fonte |
| **Sem uv na imagem final** | O uv existe só no estágio de build |

### Uma armadilha operacional que vale saber

O `_client_address` do controlador de redirect **não** lê `X-Forwarded-For` — ele lê só o peer da
conexão. Mas o processo como um todo lê: o **uvicorn** vem com `proxy_headers=True` e
`forwarded_allow_ips` de `127.0.0.1`, então o `ProxyHeadersMiddleware` dele reescreve o peer a partir
daquele cabeçalho para qualquer requisição que chegue por loopback.

**Consequência:** se nada confiável estiver na frente, rode com `--forwarded-allow-ips=""` (ou
`--no-proxy-headers`). Caso contrário, um cliente que fale direto com o processo pela loopback pode
escolher o endereço que fica gravado em `click.ip`.

## 6. O que as respostas de erro não contam

| Resposta | O que ela **não** revela |
|---|---|
| `404` de código desconhecido | Nada. `GET /{code}` e `GET /links/{code}` respondem **idênticos**, e um caminho que nem tem sete caracteres responde igual — distinguir contaria a quem enumera quais palpites eram ao menos bem formados |
| `422` de corpo inválido | O `detail` é fixo e **não ecoa o corpo enviado**. Só o caminho do campo (`body.url`), a mensagem e o tipo do erro saem |
| `500` | `The request could not be handled. The failure was recorded on the server.` — e nada mais. O traceback vai para o log do servidor |
| `503` do `/health` | Diz **o quê**, não **onde**: `The database this service depends on is not answering.` Sem mensagem do driver, sem host, sem DSN |

## 7. O que não está defendido

Esta seção é a que importa numa entrevista, e é a razão de este documento existir em vez de a
validação virar uma linha do README.

**1. Não há resolução de nome, e isso é decisão, não esquecimento.** A política decide **só pela
string**. `evil.com` apontando para `127.0.0.1` **passa**. Resolver seria sair do domínio puro —
resolução é I/O, e um teste unitário que precisa de rede não é teste unitário. E, mais importante:
**resolver não fecharia o buraco**, porque o endereço por trás de um nome pode mudar entre a
checagem e o clique (*DNS rebinding*). Só uma verificação no momento da requisição fecha. O item
está na Fase 8 do [`PROGRESS-V2.md`](PROGRESS-V2.md), com as duas armadilhas anotadas.

**2. Os códigos são enumeráveis.** O código é o id da sequence convertido para base 62, então
`0000001`, `0000002`, `0000003` são links consecutivos, e alguém pode varrer o espaço usado e ler o
destino de todo link criado. É o custo aceito por nunca colidir por construção
([ADR-0002](adr/0002-base62-sobre-a-sequence.md)). A correção custa quinze linhas — uma permutação
multiplicativa sobre o id antes de codificar, com `M = 62^7`, um multiplicador `A` coprimo com `M` e
o inverso modular — e é o **primeiro item** da Fase 8 do `PROGRESS-V2.md`.

**3. Não há autenticação nem dono do link.** Qualquer um encurta. Num serviço real isso é
obrigatório, junto do limite por chave, senão o encurtador vira ferramenta de spam.

**4. Não há limite de taxa.** Sem limite, alguém cria milhões de links de graça. É o primeiro item da
lista de próximos passos do próprio capítulo do Xu.

**5. Não há varredura de reputação do destino.** Um link para um site de phishing conhecido é
aceito. Uma integração com uma lista de bloqueio (Google Safe Browsing e afins) resolveria — ao
preço de uma dependência externa no caminho de escrita.

**6. Não há como desativar um link.** `click` é append-only e `link` não tem *soft delete*: um link
abusivo só sai com `DELETE` à mão no banco. Está na Fase 9 do `PROGRESS-V2.md`, junto com o `410
Gone` que distingue "existiu e acabou" de "nunca existiu".

**7. O SHA-256 aqui não é primitiva de segurança.** Ele é chave de largura fixa para o índice único,
e a URL que ele resume está em claro na coluna ao lado. Nada nele protege coisa alguma.

**8. Não há HTTPS neste projeto.** O `compose.yml` publica HTTP puro na 8000. Terminação TLS é
trabalho de quem fica na frente.

## 8. Referências

- [ARCHITECTURE.md](ARCHITECTURE.md) — onde a política mora nas camadas, e por que ela é função pura.
- [API.md](API.md) — o `400` que toda recusa vira, e o envelope de erro.
- [TESTS.md](TESTS.md) — a suíte que cobre cada ramo da política.
- [PROGRESS-V2.md](PROGRESS-V2.md) — a permutação, a resolução de nome, o limite de taxa e a
  autenticação, com o motivo de cada um ter ficado de fora.
- ADRs: [0002](adr/0002-base62-sobre-a-sequence.md) ·
  [0005](adr/0005-corpo-de-requisicao-sem-httpurl.md) ·
  [0006](adr/0006-envelope-de-erro-problem-details.md) ·
  [0008](adr/0008-health-responde-503-no-mesmo-envelope.md)
