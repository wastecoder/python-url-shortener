# ADR-0004: A fronteira da aplicação não carrega objeto de domínio

## Status

Aceito.

## Contexto

A Fase 2 criou as duas superfícies que o adaptador web vai ler na Fase 3: os *viewmodels*
(`application/viewmodel/`) e as portas de entrada (`application/port/inbound/`). Juntas, elas são
tudo o que um controller enxerga da aplicação.

A regra de que o objeto de domínio **não** atravessa para o adaptador já estava escrita na
docstring do pacote `viewmodel` desde a Fase 0. O problema é que docstring não reprova build. O
contrato `layers` do `.importlinter` permite `adapter -> domain` — e permite corretamente, porque
o mapper da Fase 4 precisa importar `Link` para converter linha em entidade. Consequência: nada
hoje impede um `LinkResult` de ter o campo `code: ShortCode`, nem uma porta de entrada de declarar
`-> Link`. As duas coisas passam no `mypy`, no `ruff` e nos três contratos existentes.

Isso importa porque é o tipo de erro que **não** dói na hora. Um `ShortCode` num viewmodel funciona
perfeitamente na Fase 3; o preço aparece na Fase 4, quando trocar o adaptador de persistência
deixa de produzir diff vazio na camada web — que é a demonstração mais barata que este projeto
tem da arquitetura que ele afirma ter.

## Decisão

Um quarto contrato no `.importlinter`, do tipo `forbidden`, cobrindo as **duas** metades da
fronteira:

```ini
[importlinter:contract:boundary-carries-no-domain-object]
name = The application boundary carries no domain object
type = forbidden
source_modules =
    url_shortener.application.viewmodel
    url_shortener.application.port.inbound
forbidden_modules =
    url_shortener.domain
```

A conversão de entidade para viewmodel fica numa função privada do módulo do caso de uso —
`_as_result(link, *, was_created)` —, e nunca num `LinkResult.from_link`. Um classmethod desses
faria o `viewmodel` importar exatamente aquilo que ele existe para barrar, e quebraria este
contrato na primeira linha.

## Justificativa

**As duas metades, e não só a primeira.** Cobrir apenas `viewmodel` protegeria a metade que
ninguém ia quebrar: o viewmodel é uma dataclass de campos primitivos, e acrescentar um `ShortCode`
ali é uma decisão consciente. A metade perigosa é a porta de entrada, porque ela é a assinatura
que o controller lê — um `-> Link` ali é conveniente, parece inofensivo e vaza o domínio inteiro
para dentro do adaptador de uma vez.

**Não é vacuoso, e foi verificado nos dois sentidos** neste repositório:

- com `from url_shortener.domain.model.short_code import ShortCode` em `link_result.py`, o
  contrato quebra **duas vezes**: pela metade `viewmodel` (import direto) e pela metade
  `port.inbound` (cadeia `create_link_use_case -> link_result -> short_code`);
- com `from url_shortener.domain.model.link import Link` em
  `application/port/inbound/get_link_details_use_case.py`, quebra só pela metade `port.inbound`,
  apontando a linha. **O caminho completo importa aqui:** existe um arquivo de mesmo nome em
  `application/usecase/`, e lá importar `Link` é legítimo e não quebra contrato nenhum — quem
  reproduzir a verificação no arquivo errado vê o contrato verde e conclui que esta seção mente.

O `CLAUDE.md` exige ADR para mexer no `.importlinter`. A exigência foi escrita pensando em
*afrouxar* um contrato, mas o registro de por que um contrato foi *acrescentado* é o artefato que
o revisor quer ler quando o build reprovar por causa dele.

## Alternativas consideradas

- **Deixar a regra só na docstring.** Não adotada: é a situação de antes desta ADR. A regra estava
  escrita, era correta, e não impedia nada.
- **Fazer o contrato `layers` proibir `adapter -> domain`.** Não adotada, e seria errado: o mapper
  da Fase 4 tem que importar `Link` e `Click`. A camada de fora **pode** conhecer o domínio; o que
  não pode é o domínio chegar até ela *através da fronteira da aplicação*.
- **Um contrato por metade, com dois nomes.** Não adotada: são a mesma regra vista de dois lados, e
  dois contratos permitiriam apagar um deles sem que a intenção do outro protestasse.

## Consequências

**Positivas:**

- A regra que dá sentido ao pacote `viewmodel` passa a ser verificada por máquina, no CI, em todo
  pull request.
- O diff vazio na camada web na Fase 4 deixa de depender de disciplina e passa a depender de um
  contrato.

**Negativas / custos:**

- A conversão entidade→viewmodel fica um pouco mais verbosa: uma função privada por caso de uso em
  vez de um construtor no próprio viewmodel.
- Mais um contrato para manter, e uma armadilha operacional junto: o `lint-imports` tem cache em
  `.import_linter_cache/`. Ao verificar que um contrato quebra de propósito, apague o cache antes,
  ou o resultado velho aparece como quebra que não sai mais.
