# ADR-0002: Código gerado por base 62 sobre a sequence, não por hash da URL

## Status

Aceito.

## Contexto

O código curto precisa ser único, curto e barato de gerar. O capítulo 8 do *System Design
Interview* do Alex Xu apresenta duas famílias: **hash da URL** com resolução de colisão, e **id
único convertido para base 62**.

Também é preciso decidir o comprimento. Alfabeto de 62 caracteres (`0-9a-zA-Z`): `62^6` é
aproximadamente `5,68e10` e `62^7` é aproximadamente `3,52e12`. Na premissa do livro — 100 milhões
de links por dia durante 10 anos, ou 365 bilhões de registros — 6 não cabe e 7 cabe.

## Decisão

`id = nextval(link_id_seq)`, depois base 62 sobre o alfabeto `0-9a-zA-Z`, com padding à esquerda
até **exatamente 7 caracteres**.

A `BIGSERIAL` do PostgreSQL **é** o gerador de id: é transacional, é de graça e já está no banco. O
id é lido da sequence antes do insert, o que permite calcular o código no domínio puro e inserir a
linha com `code NOT NULL` num único statement.

Como todo código tem exatamente 7 caracteres, nenhuma das palavras reservadas da API (`docs`,
`redoc`, `openapi.json`, `health`, `links`) pode ser gerada — nenhuma delas tem exatamente 7
caracteres: quatro são mais curtas e `openapi.json` tem 12. A lista de códigos reservados continua
existindo como rede de segurança para o alias customizado do V2, não como mecanismo.

## Alternativas consideradas

- **Hash da URL (MD5 ou SHA truncado) com resolução de colisão.** Não adotado: dá comprimento fixo,
  mas exige uma ida ao banco por inserção só para checar colisão — é exatamente por isso que o
  livro traz um bloom filter. Com `ON CONFLICT`, o PostgreSQL faz essa checagem de graça e sem
  falso positivo.
- **Gerador de id distribuído (Snowflake, ULID).** Não adotado: existe no livro porque lá há vários
  nós gerando id ao mesmo tempo. Com um único PostgreSQL, esse problema não existe. Entra quando
  houver mais de um nó escrevendo — Fase 10 do `PROGRESS-V2.md`.
- **Comprimento 6.** Não adotado: não cabe na premissa de volume acima. Dimensionar o espaço de
  chave por conta, em vez de escolher um número redondo, é o ponto do item.

## Consequências

**Positivas:**

- Colisão é impossível **por construção**, não por sorte. É por isso que a `UNIQUE` em `code` é
  rede de segurança e não mecanismo — ela existe para garantir que nenhum caminho futuro quebre a
  invariante.
- Nenhuma consulta extra no caminho de geração.

**Negativas / custos:**

- O código é **enumerável**: de `0000001` chega-se a `0000002`. O próprio Xu lista isso como
  problema de segurança do base 62. É aceito conscientemente no V1 e fechado na Fase 8 do
  `PROGRESS-V2.md`, com uma permutação multiplicativa sobre o id — uma bijeção, que continua sem
  colidir.
- Enquanto a permutação não existe, os primeiros códigos saem com zeros à esquerda. É cosmético.
- Gaps na sequence, causados por transações revertidas, são esperados e inofensivos: a sequence não
  faz rollback.
