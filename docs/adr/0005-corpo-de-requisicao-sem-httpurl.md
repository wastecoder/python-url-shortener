# ADR-0005: O corpo do `POST /links` carrega uma string, e não um `HttpUrl`

## Status

Aceito.

## Contexto

A Fase 3 criou o modelo Pydantic do corpo do `POST /links`. O campo é um só, e o tipo dele é a
decisão da fase inteira:

```python
class CreateLinkRequest(BaseModel):
    url: str
```

O Pydantic v2 oferece `HttpUrl` e `AnyHttpUrl` exatamente para este caso, e usá-los é o que a
documentação da biblioteca sugere. Um revisor que abrir o arquivo vai perguntar por que não foram
usados, e a resposta tem que ser melhor do que "preferência".

Três decisões anteriores dependem do que este campo faz com a string que chega:

- **Regra 5** — a URL é guardada, hasheada e redirecionada **exatamente como chegou**. A
  `domain/service/url_policy.py` não normaliza nada, e a docstring dela diz o porquê: normalizar
  faria a linha do banco deixar de conter o que o chamador mandou.
- **Regras 6 e 7** — a deduplicação é o índice único sobre `sha256(url)`. A chave é o digest da
  string, byte a byte. Duas strings diferentes são dois links, e a `url_hash.py` registra isso como
  regra de negócio e não como detalhe: "duas requisições significam o mesmo link quando as strings
  são idênticas".
- **A tabela de erros** — destino recusado pela política do domínio é `400 invalid-target-url`,
  carregando o `reason`; corpo malformado é `422 validation-error`. A distinção é entre *o schema
  está bom e a regra de negócio diz não* e *o payload nem tem a forma certa*.

## Decisão

O campo é `str`. Sem `HttpUrl`, sem `AnyHttpUrl`, sem `constr`, e **sem `max_length`**.

`model_config = ConfigDict(extra="forbid")`, para um nome de campo digitado errado virar 422 em vez
de silêncio — a mesma escolha que o `Settings` faz sobre variável de ambiente.

Quem decide se uma URL é aceitável continua sendo `domain.service.url_policy.validate_target_url`,
chamada como primeira instrução do caso de uso.

## Justificativa

**O Pydantic normaliza, e a normalização foi medida neste repositório:**

```
'https://example.com'     -> 'https://example.com/'      # barra final acrescentada
'https://Example.com/A'   -> 'https://example.com/A'     # host em minúsculas
```

A primeira linha, sozinha, quebra as regras 5, 6 e 7 de uma vez: a linha gravada deixa de ser o que
o chamador mandou, e duas URLs que o domínio considera distintas passam a colidir no índice único
antes de o domínio ser consultado. Não é um arredondamento inofensivo — é a fronteira HTTP tomando
uma decisão de negócio que mora três camadas abaixo dela.

**Ele decide política, e decide pior.** `javascript:alert(1)` viraria `422 validation-error`, quando
o contrato manda `400 invalid-target-url` com `reason: unsupported-scheme`. E o inverso também é
verdade e é o argumento mais forte: `AnyHttpUrl` **aceita** `http://localhost:8000/admin`,
`http://127.0.0.1/` e `http://169.254.169.254/`. Ou seja, ele não substituiria a política — ele
seria uma segunda política, mais fraca, rodando antes da que tem nove motivos de recusa e 104
testes atrás dela. Dois validadores que discordam sobre o que é uma URL é o bug que só aparece em
produção.

**`max_length` fica de fora pelo mesmo motivo.** O limite de 2048 caracteres é
`MAX_TARGET_URL_LENGTH`, na política. Repetido aqui, seriam dois limites livres para divergir, e o
mesmo excesso responderia 422 num lugar e 400 no outro.

**A prova de não-vacuidade.** Trocando `url: str` por `url: AnyHttpUrl` neste repositório,
**11 testes de `tests/unit/test_create_link_request.py` reprovam** — os quatro de normalização, os
seis de política e o que afirma que o valor que chega é a própria string. A decisão não é uma frase
num comentário: é a coisa que a suíte para de aceitar quando alguém a desfaz.

## Alternativas consideradas

- **`HttpUrl` no DTO e a política do domínio depois dele.** Não adotada: é a pior das duas, porque
  paga a normalização *e* mantém a política. A URL que a política valida deixa de ser a que o
  chamador mandou.
- **`str` no DTO, com `max_length=2048` para cortar payload grande cedo.** Não adotada, e a razão é
  o status: o corte responderia 422 a uma URL que o contrato manda recusar com 400 e um `reason`. O
  limite de tamanho de corpo é assunto de servidor e de proxy, não de schema — está anotado como
  limite conhecido no `PROGRESS-V1.md`.
- **Um validador Pydantic chamando `validate_target_url` dentro do modelo.** Não adotada: faria o
  `adapter` levantar `InvalidTargetUrlError` de dentro da validação do Pydantic, que o FastAPI
  embrulha em `RequestValidationError` — o 400 viraria 422 pelo caminho, e a camada web passaria a
  conhecer uma regra que ela existe para não conhecer.

## Consequências

**Positivas:**

- A URL gravada é, por construção, a que chegou. A regra 5 deixa de depender de disciplina.
- Existe exatamente um lugar que decide o que é um destino aceitável, e ele é testável sem
  framework nenhum de pé.
- `400` e `422` continuam significando coisas diferentes, que é o que faz a tabela de erros valer
  alguma coisa.
- O tipo do campo é o lugar mais barato para explicar a decisão numa entrevista: o revisor pergunta
  por que não é `HttpUrl`, e a resposta é uma linha de medição.

**Negativas / custos:**

- O `/docs` mostra `url` como `string` e não como `uri`, então quem lê a documentação gerada não vê
  o formato esperado. Mitigado com `description` e `examples` no `Field`, que aparecem no schema.
- Um cliente que mande `"banana"` só descobre o erro depois de a requisição chegar ao caso de uso —
  em vez de ser recusado pelo schema. O custo real é zero (a resposta é a mesma requisição), e a
  compensação é que a mensagem vem da política, nomeando o que faltou.
- O corpo não tem limite de tamanho declarado, e a consequência é maior do que "sem `max_length`":
  o FastAPI lê e desserializa o corpo inteiro **antes** de qualquer validador rodar, então o corte
  de 2048 caracteres da política só acontece depois de a string já existir na memória do processo.
  Fica como limite conhecido, para um proxy reverso ou para o limite de corpo do servidor resolver,
  e não para o schema — está registrado nos caveats da Fase 3 no `PROGRESS-V1.md`.
