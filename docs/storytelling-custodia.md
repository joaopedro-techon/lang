# Custod.IA — storytelling da apresentação

> Custódia de Ativos PF · Engenharia
> 12 slides · Python · LangGraph · IaraGenAI

**O arco:** conquista → tensão → as ferramentas → a virada → a decisão → o produto →
os pilares → os cases → o motor e a prática → o RAG → a provocação → o pedido.

Cada slide tem **o que vai na tela** e **o que você fala** (roteiro). O texto do
roteiro é para ser dito, não lido — está em primeira pessoa do plural de propósito.

---

## 1 · Onde chegamos — e a pergunta que sobrou

### Na tela

# Agora temos uma arquitetura de referência.

Padrões de projeto. Camadas e regra de dependência. Princípios de segurança.
Integração entre domínios. E as decisões registradas em **ADR** — com contexto,
alternativa descartada e consequência.

| | |
|---|---|
| **Padrões e camadas** | Como o projeto se organiza, o que cada camada pode enxergar, os contratos entre as peças. |
| **Segurança** | Os princípios que valem para todo projeto novo, não a interpretação de cada um. |
| **Integração entre domínios** | Como a custódia conversa com o resto — contratos, e não combinado de corredor. |
| **ADRs** | A decisão escrita e datada. Quem chega depois lê *por que*, não só *o quê*. |

> **O mapa existe e está acordado.**
> Mas uma pergunta ainda não foi respondida:
> ## Como essa arquitetura de referência vira código nos nossos projetos?

### O que você fala

"Antes de qualquer coisa, vale reconhecer o que já foi feito: a arquitetura de
referência está de pé. Não é rascunho — tem padrão de projeto, tem camada, tem regra
de dependência, tem princípio de segurança, tem o desenho de como os domínios se
integram, e tem as decisões registradas em ADR. Isso é trabalho de meses e é uma
conquista real do time.

Só que, com o mapa pronto, apareceu a pergunta difícil. E é essa pergunta que motiva
essa conversa: **como esse desenho vira código, todo dia, em todo projeto?** Porque o
documento, sozinho, não escreve linha nenhuma."

---

## 2 · A tensão — o desenho não atravessa sozinho

### Na tela

# Evoluímos. E ainda precisamos evoluir.

**Duas squads. A mesma arquitetura de referência. As mesmas páginas.
Dois projetos completamente diferentes.**

- **A distância entre o desenho e o código é humana** — e por isso varia. Depende de
  quem leu, de como interpretou e de quanto tempo teve.
- **A ordem da execução está invertida.** Hoje pedimos ao Devin, ao Claude Code e aos
  demais que programem — e **só no fim** roda uma pipeline para verificar se o projeto
  segue a arquitetura de referência.

```
   HOJE           código  ─────────────────────►  pipeline verifica  ──►  retrabalho
                  (livre)                          (conformidade)          caro, no fim

   O QUE FALTA    arquitetura aplicada  ──►  código  ──►  pipeline confirma
                  (no momento de escrever)                 (e quase não acha nada)
```

> Conformidade virou **auditoria depois**, quando corrigir já é caro — em vez de
> **garantia antes**, quando ainda é barato.
>
> ## Precisamos de estratégia para aplicar a arquitetura no código. Não de mais documentação sobre ela.

### O que você fala

"E aqui é onde eu quero ser honesto sobre onde estamos. Estamos indo bem, evoluímos
muito — e ainda precisamos evoluir.

Dois sintomas concretos.

O primeiro: hoje temos duas squads trabalhando com a mesma arquitetura de referência,
lendo exatamente as mesmas páginas, e entregando códigos e projetos completamente
diferentes. Ninguém errou. Cada um leu, interpretou e aplicou — e interpretação varia.
Documento é passivo por natureza: ele depende de alguém lembrar que existe, abrir,
entender e aplicar. Projeto a projeto, dev a dev, sprint a sprint.

O segundo sintoma é a ordem da execução, e esse é o mais caro. Hoje a gente pede para
os nossos agentes — Devin, Claude Code — programarem à vontade, e só no final roda
outra pipeline para verificar se aquilo segue a arquitetura de referência. Ou seja:
descobrimos o desvio depois de o código existir. É achar o problema no momento mais
caro possível de consertar.

A conclusão a que chegamos é essa: o que falta não é mais documentação sobre a
arquitetura. É estratégia e técnica para **aplicar** a arquitetura dentro do código, no
momento em que o código está sendo escrito."

---

## 3 · As ferramentas são boas — e continuam

### Na tela

# Devin e Claude Code entregam valor real. Todo dia.

Isso não está em discussão, e elas seguem com a gente.

| | |
|---|---|
| **O que elas fazem muito bem** | Escrever, refatorar, testar, explicar código. Velocidade real, já hoje, já medida no nosso dia a dia. |
| **O que elas não têm** | A nossa arquitetura de referência, as nossas ADRs, o nosso domínio de custódia e as nossas contas AWS. Isso não vem de fábrica em ferramenta nenhuma. |

> A pergunta não é *qual ferramenta usar*.
> ## É como aplicar o nosso padrão **por cima** delas.

- **Contexto** — alguém precisa colocar a nossa arquitetura no caminho do modelo.
- **Fronteira** — o que já foi decidido não pode ser reinterpretado a cada projeto.
- **Repetibilidade** — o que é regra tem que sair igual todas as vezes.
- **Reaproveitamento** — um bom prompt resolve um projeto; um trilho resolve todos.

### O que você fala

"Quero deixar isso muito claro, porque não é uma crítica às ferramentas: Devin e Claude
Code são excelentes e já entregam valor real no nosso dia a dia. Ninguém aqui está
propondo trocá-las ou abandoná-las. Elas continuam.

O ponto é outro. Por melhores que sejam, elas não conhecem a nossa arquitetura de
referência, não conhecem as nossas ADRs, não conhecem o domínio da custódia e não
conhecem as nossas contas AWS. Esse conhecimento é nosso, e alguém precisa colocá-lo no
caminho — de forma consistente, em todo projeto, todas as vezes.

Então a pergunta que a gente passou a fazer deixou de ser 'qual ferramenta usar' e
passou a ser: **como a gente aplica o nosso padrão por cima das ferramentas que já
usamos?**"

---

## 4 · A virada de pensamento

### Na tela

# Nem tudo precisa de IA. E o harness é quem sabe a diferença.

| | **Fluxo determinístico** | **Fluxo com LLM** |
|---|---|---|
| **Quem decide o passo** | O código — arestas explícitas do grafo | O modelo, a partir do contexto |
| **Mesma entrada** | **Sempre a mesma saída** | **Saída não garantida** |
| **Serve para** | Coletar requisito, validar, configurar infra, aplicar a regra que já é decisão | Interpretar texto livre, explicar o domínio, escrever código a partir de uma decisão já fechada |
| **Custo de token** | Zero | Real, e cresce com o uso |
| **Risco** | Nenhum | Alucinação e drift — por isso, sempre com freio |

**A regra que adotamos:**
> Onde já existe decisão, o fluxo é determinístico — é aplicação de regra, não
> julgamento. Onde é preciso julgar, entra o modelo — com fronteira e aprovação.

> ## O harness é a camada que escolhe o trilho certo a cada passo.
> É daí que vem a assertividade — e é isso que nenhuma ferramenta de mercado vai
> decidir por nós, porque a regra é nossa.

### O que você fala

"Aqui está a virada de pensamento, e é o slide mais importante dessa apresentação.

A gente começou perguntando 'como faço a IA acertar mais'. E percebeu que a pergunta
certa é outra: **quando a IA deveria estar envolvida?**

Olha a diferença. Um fluxo determinístico é código: mesma entrada, mesma saída, sempre,
custo de token zero, risco zero. Um fluxo com LLM é julgamento: interpreta, decide,
adapta — e por isso é insubstituível onde há ambiguidade, e é perigoso onde não há.

Perguntar ao dev qual é a fila, validar se a sigla existe, escrever o Terraform do
ambiente, gravar a decisão em arquivo — isso não é julgamento, isso é regra que já foi
decidida. Colocar um modelo aí só adiciona variância e custo em cima de uma coisa que
já tinha resposta certa.

Agora: entender uma pergunta em texto livre sobre o domínio da custódia, explicar por
que a ADR decidiu de tal jeito, escrever o código a partir de uma decisão já fechada —
isso é julgamento, e é exatamente onde a IA agrega.

E a peça que faltava é essa: alguém precisa **decidir, a cada passo, qual dos dois
trilhos usar**. Esse alguém é o harness. Não é um prompt melhor, não é um modelo maior:
é uma camada de orquestração que sabe quando aplicar regra e quando pedir julgamento."

---

## 5 · A decisão

### Na tela

# Construir o nosso harness em casa, sobre o que o banco já tem.

**Motivo 01 · Controle sobre a evolução**
O harness é nosso. **Nós decidimos como e quando ele evolui** — uma necessidade nova da
custódia vira feature na nossa agenda, com o contexto que só nós temos, sem depender do
roadmap de terceiro.

**Motivo 02 · A engine é ativo reaproveitável**
Orquestração, guardrails, ferramentas e integração com a plataforma ficam numa base
que serve a **N cases da custódia** — não só a este. O primeiro case paga a engine; do
segundo em diante, o custo marginal é pequeno.

**Motivo 03 · Assenta sobre o IaraGenAI**
Modelos democratizados, gateway autenticado e Knowledge Base vetorial **já existem na
casa**. Consumimos a plataforma do banco em vez de construir outra.

> Não estamos construindo uma plataforma de IA — essa já existe, é o IaraGenAI.
> Não estamos substituindo ferramenta de codificação — essas já são boas.
> ## Estamos construindo o trilho que aplica a nossa arquitetura.

### O que você fala

"Diante disso, a decisão que tomamos foi construir o nosso próprio harness, dentro de
casa, usando o que o banco já nos proporciona.

Três motivos.

Primeiro, controle sobre a evolução. Quando o harness é nosso, nós decidimos como e
quando ele evolui. Se amanhã a custódia precisa de um comportamento novo, isso entra na
nossa agenda — não na fila de prioridade de um fornecedor que não conhece o nosso
domínio.

Segundo, e talvez o mais importante para essa mesa: a engine é reaproveitável. A
orquestração, os guardrails, a integração com a plataforma — isso tudo fica numa base
que atende N cases da custódia. O primeiro case paga a construção; do segundo em
diante, a gente troca o domínio e a base de conhecimento, e a engine é a mesma.

Terceiro, e aqui está a parte de 'usar o que o banco já tem': nós não estamos
construindo plataforma de IA. Isso já existe e chama IaraGenAI — modelos democratizados,
gateway autenticado, e a solução interna de embedding para construção de Knowledge Base.
Nós consumimos a plataforma. O que a gente constrói é só o trilho que aplica a nossa
arquitetura em cima dela."

---

## 6 · O produto

### Na tela

# Custod.IA não é só um agente. É a proposta de um produto.

**Um único lugar para as soluções de IA da custódia** — com governança, observabilidade
e a nossa arquitetura aplicada.

| | |
|---|---|
| **Dar start em projetos** | Um projeto novo que nasce dentro do padrão, com a infraestrutura configurada — por construção, não por revisão no fim. |
| **Tirar dúvidas de arquitetura** | A arquitetura de referência respondendo no terminal, ancorada no documento oficial — não no palpite do modelo. |
| **Tirar dúvidas funcionais da custódia** | O domínio — regras, fluxos, o que cada coisa significa — no mesmo lugar onde o dev já está. |

**Por que "um lugar só" importa:**
- **Governança** — os limites são código, não recomendação em prompt.
- **Observabilidade** — quem usou, para quê, quanto custou. Uso vira dado, e dado prioriza backlog.
- **Aplicabilidade** — a arquitetura chega ao repositório, que é o único lugar onde ela conta.

> Hoje: `pip install custodia-cli`, distribuído pelo **Artifactory interno**.
> Já é instalável, versionado e tem quem use.

### O que você fala

"É aqui que eu apresento o Custod.IA.

E a primeira coisa que eu preciso dizer é que ele não é só um agente. Um agente resolve
um problema. O que estamos propondo é um produto: um único lugar onde as soluções de IA
da custódia moram, com governança, com observabilidade, e com a nossa arquitetura
efetivamente aplicada.

Na prática, ele faz três coisas. Ajuda a dar start em projetos novos, já dentro do
padrão. Tira dúvidas sobre o contexto da arquitetura. E tira dúvidas funcionais da
própria custódia — o domínio, as regras, os fluxos.

E por que 'um lugar só' importa tanto? Porque é o que permite governança de verdade: os
limites viram código, não recomendação. É o que dá observabilidade: a gente passa a
saber quem usou, para quê e quanto custou — e isso prioriza backlog com dado, não com
achismo. E é o que garante a aplicabilidade: a arquitetura chega ao repositório, que é
o único lugar onde ela realmente conta.

E isso não é slide: hoje já é um `pip install custodia-cli` pelo Artifactory interno.
Tem versão, tem release, tem quem use."

---

## 7 · Os pilares

> *Slide de ponte — este número estava vago no roteiro. Ele conecta "o que é o produto"
> (6) com "onde ele pode chegar" (8). Se o tempo apertar, é o primeiro a cair.*

### Na tela

# Onde a IA entra, ela entra com freio.

Essa é a diferença entre um agente de mercado e um agente da casa:
**os limites são código.**

1. **A decisão vem antes do código.** A spec é fechada de forma determinística e
   versionada no repositório. Depois dela, se o modelo errar, ele erra escrevendo
   código — não errando o que foi decidido.
2. **Human-in-the-loop obrigatório.** Toda escrita em arquivo e todo comando de build
   param e pedem aprovação, com o conteúdo na tela.
3. **Sandbox.** As ferramentas do agente estão presas à pasta do projeto.
4. **Só leitura na nuvem.** O agente consulta a AWS, nunca aplica. Quem aplica é o
   Terraform, pelo pipeline de sempre, com a aprovação de sempre.
5. **Auditável.** A decisão vai para o repositório e é revisada em PR, separada do
   código gerado a partir dela.

> Isso é o que permite dizer "sim" para IA em projeto novo sem abrir mão de controle.

### O que você fala

"Antes de mostrar onde isso pode chegar, um slide sobre o que sustenta a proposta —
porque a primeira pergunta que sempre aparece é 'e o controle?'.

A diferença entre usar um agente de mercado e ter um agente da casa é essa: aqui os
limites são código, não são uma recomendação escrita no prompt torcendo para o modelo
obedecer.

A decisão vem antes do código, de forma determinística, e fica versionada. Toda escrita
em arquivo e todo build param e pedem aprovação com o conteúdo na tela. As ferramentas
estão presas à pasta do projeto. Na nuvem, o agente só lê — quem aplica é o Terraform,
pelo pipeline de sempre. E tudo o que foi decidido é revisado em PR.

É isso que permite dizer 'sim' para IA em projeto novo sem abrir mão de controle."

---

## 8 · Os cases

### Na tela

# O que essa engine pode atender.

**Case 01 · Integração com as APIs da custódia**
O agente consulta as nossas próprias APIs para responder perguntas e tirar dúvidas com
**dado real**, não com descrição de contrato. "Como está esse ativo", "esse fluxo passou
por onde" — respondido no terminal, sem trocar de ferramenta.

**Case 02 · Bases de conhecimento no IaraGenAI, por squad**
Cada squad cria e mantém a **sua** base de conhecimento na plataforma. O Custod.IA
escuta todas elas e responde perguntas de cunho funcional. Quem é dono do conhecimento
continua sendo dono — o agente só passa a ser a porta de entrada.

**Case 03 · Discovery entre times**
Num único lugar, as bases de conhecimento de **times diferentes**. Descobrir como outro
time resolveu algo deixa de ser "achar a pessoa certa e marcar uma call" e vira uma
pergunta.

> A engine é a mesma nos três. O que muda é a base de conhecimento e as ferramentas
> plugadas. **É por isso que valeu construir engine, e não script.**

### O que você fala

"Agora, alguns cases que já dá para desenhar em cima dessa engine.

O primeiro é integrar com as APIs da própria custódia. O agente consultando os nossos
sistemas para responder com dado real, no lugar onde o dev já está, sem trocar de
ferramenta e sem abrir cinco telas.

O segundo é o que mais escala: bases de conhecimento no IaraGenAI, uma por squad. Cada
squad cria e mantém a sua — quem é dono do conhecimento continua dono. O Custod.IA
escuta essas bases e responde perguntas de cunho funcional. Isso resolve um problema que
todo mundo aqui conhece: o conhecimento existe, está escrito, e mesmo assim ninguém
acha.

E o terceiro é consequência do segundo: discovery entre times. Se as bases de vários
times estão no mesmo lugar, descobrir como outro time resolveu um problema deixa de
depender de achar a pessoa certa e marcar uma call.

Reparem que nos três cases a engine é exatamente a mesma. O que muda é a base de
conhecimento e as ferramentas plugadas. É por isso que valeu a pena construir uma
engine, e não um script."

---

## 9 · O motor — e o que já roda hoje

### Na tela

# LangGraph: o fluxo do agente vira um diagrama.

Em vez de o comportamento ficar espalhado em código, ele é declarado como um **grafo** —
caixas que fazem uma coisa cada, e setas que dizem para onde ir depois.

| | |
|---|---|
| **Nó** | Um passo isolado: perguntar a fila, consultar a AWS, chamar o modelo, gravar a decisão. Dá para testar e trocar um sem mexer nos outros. |
| **Aresta condicional** | A regra fica visível. "Se não confirmou, encerra sem gravar" é uma seta no diagrama — não um `if` perdido no meio de duzentas linhas. |
| **Pausa e retomada** | O grafo congela, diz o que precisa saber e espera. Hoje quem responde é o terminal; amanhã pode ser uma tela web ou um bot — sem tocar no fluxo. |
| **Um motor só** | Determinístico e com LLM são grafos na mesma biblioteca. Uma forma de orquestrar, e a engine inteira reaproveitável. |

## Na prática, hoje:

```
==============================================================
  Custod.IA — Agente da custódia de ativos PF
==============================================================

> qual é o padrão de retry do listener SQS na nossa arquitetura?

  ● buscar_conhecimento   consulta a KB da arquitetura de referência
  Resposta ancorada no documento oficial, com a fonte citada.

> /initialize    wizard determinístico da spec do projeto  — zero token
> /infra         terraform de dev, hom e prod              — lendo a AWS de verdade
```

- **Conversa iterativa** ✅ — texto solto vira diálogo com o agente, com ferramentas.
- **`/initialize`** ✅ — coleta a spec do projeto e grava a decisão. **Sem LLM.**
- **`/infra`** ✅ — escreve o Terraform dos três ambientes consultando a conta AWS. **Sem LLM.**

> Texto solto → assistido por LLM. Comando com barra → 100% determinístico.
> **A separação do slide 4 não é teoria: ela é visível para quem usa.**

### O que você fala

"Uma palavra sobre o motor, porque isso importa para quem vai manter.

Nós usamos LangGraph para orquestrar o agente. É uma biblioteca de orquestração em que
o fluxo do agente vira, literalmente, um grafo: caixas que fazem uma coisa cada, e setas
que dizem para onde ir depois. A vantagem é que a regra deixa de estar escondida no meio
do código e passa a ser desenho — legível para quem revisa, estável para quem mantém. E
o mesmo motor roda os dois trilhos, o determinístico e o com LLM.

E o Custod.IA já roda hoje. Três coisas funcionando em máquina de desenvolvedor:

A conversa iterativa com o agente — o dev entra na pasta do repositório, digita
`custodia`, e conversa sobre o domínio e sobre o código.

O `/initialize`, que é um slash command para dar start em projeto: ele coleta a spec do
projeto e grava a decisão. Zero token de LLM — é aplicação de regra.

E o `/infra`, que escreve o Terraform de dev, homologação e produção consultando a conta
AWS de verdade. Também sem LLM.

Repara que aquela separação do slide 4 não ficou na teoria: texto solto vai para o
trilho da IA, comando com barra vai para o trilho determinístico. E isso é visível para
quem usa."

---

## 10 · O RAG

### Na tela

# A arquitetura de referência, respondendo.

Cadastramos bases de conhecimento na plataforma do **IaraGenAI** e usamos a **SDK** dela
para fazer o *retrieval* — o retorno é injetado no contexto da IA antes de ela responder.

```
pergunta do dev
      │
      ▼
 o agente julga: isso é sobre o NOSSO padrão?  ──── não ──►  responde direto
      │ sim
      ▼
 retrieval via SDK do IaraGenAI  ──►  trechos da KB injetados no contexto
      │
      ▼
 resposta ancorada no documento oficial, com a fonte
```

- **A base é a do banco.** A indexação vem da solução interna de embedding do
  IaraGenAI. Não mantemos índice paralelo, não duplicamos conteúdo.
- **A decisão de buscar é do agente.** Ele não busca sempre — buscar sempre custa token
  e traz ruído. Julgar se a pergunta é sobre o nosso padrão ou sobre Java genérico é
  exatamente onde a IA agrega.
- **A resposta vem do nosso documento**, não do treinamento do modelo. É a diferença
  entre consultar a arquitetura e ouvir um palpite plausível.

> **O efeito prático:** a arquitetura de referência deixa de ser um documento que
> ninguém abre e passa a responder no lugar onde o dev já está — o terminal.

### O que você fala

"E aqui está a peça que fecha o ciclo com o slide 1.

Nós conseguimos usar estratégias de RAG dentro do agente. Na prática: cadastramos as
bases de conhecimento na plataforma do IaraGenAI, e usamos a SDK dela para fazer o
retrieval. O que volta é injetado no contexto da IA antes de ela formular a resposta.

Duas coisas que eu quero destacar.

A primeira: a base é a do banco. A indexação vem da solução interna de embedding do
IaraGenAI. A gente não mantém índice paralelo nem duplica conteúdo — quando o documento
oficial muda, é aquele que o agente lê.

A segunda: a decisão de buscar é do agente. Ele não busca sempre, porque buscar sempre
custa token e traz ruído. Julgar se a pergunta é sobre o nosso padrão ou sobre Java
genérico — isso é julgamento, e é exatamente onde a IA agrega valor.

O resultado é que a resposta vem ancorada no nosso documento, com a fonte, e não no que
o modelo aprendeu na internet. Na prática, a arquitetura de referência deixa de ser um
documento que ninguém abre e passa a responder no terminal, que é onde o dev está."

---

## 11 · O fechamento

### Na tela

# Custod.IA é uma provocação à forma como trabalhamos hoje.

| **Hoje** | **Com o Custod.IA** |
|---|---|
| A arquitetura é um documento que alguém precisa lembrar de abrir | A arquitetura responde onde o dev está |
| Cada squad interpreta e entrega diferente | O que é regra sai igual, todas as vezes |
| A conformidade é auditada **no fim**, quando corrigir é caro | O projeto nasce aderente — a pipeline confirma, não descobre |
| Cada case de IA nasce do zero | Uma engine, N cases da custódia |
| A IA opina em tudo | A IA entra onde há julgamento — e com freio |

> **A vantagem não é velocidade. É previsibilidade** — velocidade é consequência.
>
> ## A arquitetura de referência já existe. A pergunta do primeiro slide era como ela chega ao código. O Custod.IA é a nossa resposta.

**E é uma provocação:** ele não pede para mudarmos de ferramenta. Pede para mudarmos a
ordem — arquitetura **antes** do código, e não verificação depois.

### O que você fala

"Fechando.

A vantagem do Custod.IA não é velocidade. Velocidade é consequência. A vantagem é
previsibilidade: o que é regra sai igual todas as vezes, a conformidade deixa de ser
descoberta no fim, e a arquitetura passa a existir no lugar onde o código é escrito.

E eu quero terminar sendo direto sobre o que isso é: o Custod.IA é uma provocação à
forma como a gente trabalha hoje. Ele não está pedindo para trocarmos de ferramenta —
as ferramentas são boas e continuam. Ele está pedindo para invertermos a ordem: a
arquitetura aplicada antes do código, e não verificada depois dele.

A arquitetura de referência já existe. A pergunta do primeiro slide era como ela chega
ao código. Isso aqui é a nossa resposta."

---

## 12 · O que ainda precisa ser decidido

### Na tela

# O caminho está desenhado. A capacidade, ainda não.

```
──●─────────────●─────────────●- - - - - - -○- - - - - - -○
 Fundação      RAG da       Starter e      Geração      Piloto e
               arquitetura  infraestrutura do código    expansão
                            ▲
                        ESTAMOS AQUI
   ├────────── entregue ──────────┤├──── previsto, sem data ────┤
```

| Estação | Situação | O que é |
|---|---|---|
| **Fundação** | Entregue | CLI instalável pelo Artifactory, conversa iterativa, guardrails de aprovação e sandbox. |
| **RAG da arquitetura** | Entregue | O agente decide quando consultar a KB da arquitetura no IaraGenAI. |
| **Starter e infraestrutura** | Entregue — **estamos aqui** | `/initialize` e `/infra`: spec determinística e Terraform de dev, hom e prod com dados reais da conta. |
| **Geração do código** | Previsto | Código escrito a partir da spec fechada; ampliar além do worker. |
| **Piloto e expansão** | Previsto | Squads-piloto, métricas de uso, e os cases do slide 8. |

## O que precisamos decidir juntos

- **Como esse produto evolui** — quem é o dono, e com que capacidade acordada.
- **Como fica o backlog** — quem prioriza, e com que critério. A proposta é priorizar
  com **dado de uso**, não com achismo — e a observabilidade existe justamente para isso.
- **Quais squads pilotam** — e quais métricas acompanhamos: tempo até o primeiro deploy
  de um projeto novo, desvios de arquitetura encontrados em revisão, e custo por projeto
  configurado.

> Linha cheia é o que já roda em máquina de desenvolvedor. Linha tracejada é escopo
> previsto e priorizado, **ainda sem data comprometida** — assumir prazo antes de
> acordar capacidade é como iniciativa vira dívida.

### O que você fala

"E eu não quero terminar com uma foto bonita, quero terminar com o que ainda está em
aberto — porque é isso que eu preciso dessa mesa.

Na linha do tempo: fundação, RAG da arquitetura e o starter com infraestrutura estão
entregues e rodando em máquina de desenvolvedor. Estamos aqui. À frente, a geração do
código a partir da spec e o piloto com expansão — escopo previsto e priorizado, mas sem
data comprometida, porque assumir prazo antes de acordar capacidade é exatamente como
uma iniciativa dessas vira dívida.

Então o que precisa ser discutido é isso: como esse produto vai ser evoluído, quem é o
dono, com que capacidade, e como fica o backlog. A minha proposta é que o backlog seja
priorizado com dado de uso — e a observabilidade que mencionei no slide 6 existe
exatamente para isso.

E, na prática, o próximo passo concreto que eu peço é escolher as squads-piloto para os
próximos projetos novos da custódia, com as métricas acordadas: tempo até o primeiro
deploy, desvios de arquitetura encontrados em revisão, e custo por projeto configurado."
