# Progresso V2 — url-shortener (o que ficou de fora)

Evolução do projeto **depois** do V1. Mesmo formato do [`PROGRESS-V1.md`](PROGRESS-V1.md): ao
concluir, marque a caixa, risque o texto e acrescente os subitens em negrito descrevendo o que foi
feito, com um subitem `Verificado:`. **Nada aqui é necessário para 01/09.**

Cada item desta lista foi **cortado de propósito**, e é isso que separa "projeto pequeno" de
"escopo decidido": o que ficou de fora rende tanto em entrevista quanto o que ficou dentro. A
resposta pronta para cada corte mora na tabela **"o que ficou de fora"** do `README.md` (Fase 7 do
V1) — **as duas coisas precisam andar juntas**: puxar um item para o código sem tirar a linha
correspondente da tabela deixa o README mentindo.

**Se o projeto continuar, comece pela Fase 8.** A permutação é a melhor resposta técnica que o
projeto ainda não tem, e custa quinze linhas.

**Antes de puxar qualquer item para antes da entrevista:** o risco deste projeto nunca foi o
prazo, foi ele parecer um encurtador de tutorial. Uma fase daqui construída pela metade custa mais
do que ela entrega.

## Fase 8 — Fechar os furos conhecidos

- [ ] **Permutação multiplicativa** sobre o id antes de converter para base 62, matando a enumerabilidade sem perder a garantia de nunca colidir: uma bijeção sobre o espaço inteiro, com `M = 62^7`, um multiplicador `A` coprimo com `M` e o inverso modular `A_INV = pow(A, -1, M)`
- [ ] Duas armadilhas, verificadas por teste, não por confiança: `A` precisa ser **grande**, próximo de `M`, senão os primeiros ids não dão a volta e os códigos saem em ordem — que é justamente o problema que se estava resolvendo; e `A` precisa ser **ímpar e não divisível por 31**, porque `M = 2^7 * 31^7` e sem coprimalidade a função deixa de ser bijetiva e passa a colidir
- [ ] **Rate limit por IP** na criação de links. É o primeiro item da lista de próximos passos do próprio capítulo do Xu, e existe pelo mesmo motivo: sem limite, alguém cria milhões de links de graça
- [ ] **API key e dono do link**: uma tabela, um header e autorização por recurso. Sem dono, qualquer um encurta — num serviço real isso é obrigatório, junto do limite por chave, senão o encurtador vira ferramenta de spam
- **Critério:** os ids 1, 2 e 3 produzem códigos sem relação visível entre si; um teste sobre uma faixa grande de ids não encontra nenhuma colisão e prova o round-trip `codigo_para_id(id_para_codigo(n)) == n`; uma chamada sem chave é recusada e uma chave que estoura o limite recebe `429`.

## Fase 9 — Funcionalidade cortada de propósito

- [ ] **Expiração de link**: coluna `expires_at` e uma checagem no redirect. Um link vencido devolve **`410 Gone`**, não `404` — `404` é "nunca existiu", `410` é "existiu e acabou", e quem consome a API trata os dois diferente
- [ ] **Alias customizado**: campo opcional no `POST /links` e tratamento de `409 Conflict`. A partir daqui a `UNIQUE` em `code` **deixa de ser rede e vira mecanismo de verdade**, porque passa a existir um segundo caminho escrevendo naquela coluna — e a lista de códigos reservados deixa de ser defesa em profundidade e passa a ser a única defesa
- [ ] **Estatísticas**: rota de agregação sobre `click`, por dia, por `referer` e por `user_agent`. A tabela já guarda o dado bruto, então isto é uma consulta e não uma mudança de modelo — foi exatamente por isso que não existe um contador dentro de `link`
- [ ] **Desativar link** (soft delete), respondendo `410` também
- **Critério:** um link vencido devolve `410`, um desativado devolve `410`, e um código que nunca existiu devolve `404`. Um cliente da API consegue distinguir os três casos sem ler o corpo da resposta.

## Fase 10 — Escala: as peças do desenho do Xu que foram tiradas

- [ ] **Cache Redis** na frente da leitura, entrando como uma implementação nova de `LinkRepository` **atrás da porta que já existe** — nenhuma outra camada muda. É a prova prática do argumento que a arquitetura do V1 vinha fazendo de graça
- [ ] **Fila para o clique**: o redirect responde `302` na hora e publica o evento; um worker consome e agrega. O critério que decide é este, e não "é assíncrono, então põe fila": perder um clique é aceitável, atrasar um redirect não
- [ ] **Gerador de id distribuído** (Snowflake ou ULID), só quando houver mais de um nó escrevendo. Com um Postgres só, a `BIGSERIAL` **é** o gerador, é transacional e é de graça
- [ ] **Sharding**, pelo mesmo raciocínio: problema de volume que o projeto não tem
- [ ] Um ADR por peça, dizendo **qual premissa de escala passou a ser verdade** e o número que a sustenta
- **Critério:** cada peça só entra acompanhada da medição que a justifica. Uma peça de escala sem número é exatamente o overengineering que este projeto foi desenhado para não ter.

## Fase 11 — Rigor de engenharia

- [ ] **Mutation testing** com `mutmut` sobre `domain/` — o equivalente do Pitest do lado Java, e o único jeito de saber se a cobertura do domínio é real ou decorativa
- [ ] **Teste de carga** leve (k6 ou Locust) medindo a latência do redirect e a vazão, com o número indo para o README
- [ ] **Observabilidade**: log estruturado em JSON, `/metrics` para Prometheus, tracing com OpenTelemetry
- [ ] **Deploy real** (Fly.io, Railway ou Render), com o `compose.yml` virando serviço de verdade e uma URL pública que o entrevistador consegue abrir
- **Critério:** o mutante que troca `302` por `301` morre. Se ele sobrevive, o teste que sustenta a decisão central do produto não estava testando nada.

## Fase 12 — Operação e moderação

- [ ] **Painel Django admin**: ver os links mais clicados, desativar link abusivo, tratar denúncia. É operação feita por quem não é desenvolvedor, e é a resposta pronta para "onde você usaria Django em vez de FastAPI"
- [ ] **Limpeza agendada** de links órfãos e expirados
- **Critério:** alguém que não é desenvolvedor consegue desativar um link abusivo sem abrir o banco e sem pedir deploy.
