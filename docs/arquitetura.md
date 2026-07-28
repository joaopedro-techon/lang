# Arquitetura — como este agente funciona

Documento de aprendizado. Explica **o que** cada peça faz, **por que** ela existe
e **onde mexer** quando for evoluir o agente.

---

## 1. O problema: um wizard não pode alucinar

O `/initialize` faz perguntas cujo resultado vira configuração de infraestrutura
real. Se ele "inventar" que o dev escolheu Aurora RDS, alguém vai subir um banco
sem precisar. Então a primeira decisão de arquitetura foi:

> **O `/initialize` não usa LLM. Nenhum.**

Isso não é preguiça — é o desenho correto. Vale a pena entender a diferença entre
os dois modos, porque o agente vai usar **os dois**:

| | Fluxo determinístico | Fluxo com LLM |
|---|---|---|
| Quem decide o próximo passo | o código (arestas do grafo) | o modelo |
| Mesma entrada → mesma saída | sempre | não garantido |
| Bom para | coletar requisitos, validar, gravar | escrever código Java, interpretar texto livre |
| Risco | nenhum | alucinação, drift |

O `/initialize` é **coleta de requisitos** → determinístico. Os comandos futuros
(`/generate`) escrevem código Java/Terraform → aí sim faz sentido usar o Claude,
mas **partindo de uma spec que já está fechada e validada**.

Essa é a ideia central: **a spec é a fronteira**. Antes dela, tudo é determinístico.
Depois dela, se o LLM errar, ele erra escrevendo código — não errar *o que foi decidido*.

---

## 2. Por que LangGraph, se não tem IA no wizard?

Pergunta justa: dava para fazer com uma sequência de `input()`.

O que ganhamos usando o grafo:

1. **O fluxo vira um diagrama explícito.** As regras de negócio ("App encerra com
   aviso", "Schedule encerra com aviso") são *arestas condicionais* que dá para ler
   e auditar, não `if`s escondidos no meio de 200 linhas.

2. **`interrupt()` separa "a pergunta" de "quem pergunta".** O grafo emite um JSON
   descrevendo a pergunta e congela. Hoje quem responde é o terminal; amanhã pode
   ser uma UI web ou um bot no Slack — **sem tocar no grafo**.

3. **Um motor só.** Os comandos determinísticos e os comandos com LLM rodam no mesmo
   LangGraph. Você aprende uma orquestração, não duas.

### Conceitos do LangGraph usados aqui

- **State** — um dicionário que atravessa o grafo. Cada nó devolve um dict *parcial*
  e o LangGraph faz o merge. Aqui é o `InitializeState`.
- **Node (nó)** — uma função `state -> dict`. Um passo do fluxo.
- **Edge (aresta)** — "depois do nó A vai para o nó B".
- **Conditional edge** — uma função olha o state e devolve para onde ir. É assim que
  "App" desvia para o `END`.
- **Checkpointer** — guarda o state entre execuções. **Obrigatório** para usar
  `interrupt()`, porque é ele que segura o estado enquanto o grafo está pausado.
- **`thread_id`** — identifica a conversa. É por ele que o checkpointer sabe qual
  estado restaurar ao retomar.

---

## 3. O fluxo do `/initialize`

```
START
  │
  ▼
tipo do projeto? ───── "App" ─────────────► END   (feature indisponível)
  │ "Worker"
  ▼
gatilho? ───────────── "Schedule" ────────► END   (feature indisponível)
  │ "SQS"
  ▼
nome da fila SQS
  │
  ▼
mensagens por segundo
  │
  ▼
dependências (multi-escolha)
  │
  ▼
revisar / confirmar ── "não" ─────────────► END   (cancelado)
  │ "sim"
  ▼
grava .springboot-agent/spec.json ────────► END
```

Repare que **nenhuma escrita em disco acontece antes da confirmação**. Os caminhos
que terminam em "feature indisponível" ou "cancelado" não deixam rastro.

---

## 4. As camadas

```
cli.py          REPL: lê /comandos e DIRIGE o grafo (invoke → interrupt → resume)
   │
   ├── ui.py            desenha a pergunta no terminal e insiste até ser válida
   │
   └── initialize.py    o grafo: nós, arestas e as regras de desvio
          │
          ├── questions.py   as perguntas como DADOS + a validação (fonte única)
          └── spec.py        o artefato final: .springboot-agent/spec.json
```

A regra que amarra tudo: **`questions.validate()` é a única fonte da verdade sobre
o que é uma resposta válida.**

- O `ui.py` chama `validate()` para reperguntar na hora, com mensagem amigável.
- O `initialize.py` chama `validate()` de novo, como rede de segurança.

O `ui.py` cuida só de **parsing** (entender `1,3` como duas opções, `s` como sim) —
isso é específico de terminal e pode mudar por frontend. A **regra** é compartilhada.

---

## 5. O padrão human-in-the-loop (a parte mais importante)

É assim que o `cli.py` conversa com o grafo:

```python
estado = grafo.invoke(entrada, config)      # roda até pausar
while estado.get("__interrupt__"):          # pausou pedindo resposta
    pergunta = estado["__interrupt__"][0].value   # o JSON da pergunta
    resposta = perguntar_no_terminal(pergunta)    # o frontend responde
    estado = grafo.invoke(Command(resume=resposta), config)   # retoma
```

Do lado do nó, é só isto:

```python
def no_fila(state):
    return {"queue_name": _perguntar(Q_FILA_SQS)}
```

### ⚠ A pegadinha clássica

Quando o grafo é retomado, **o nó que pausou roda de novo desde a primeira linha**.
`interrupt()` *não* retoma no meio da função — ele re-executa o nó e, dessa vez,
a chamada `interrupt()` devolve o valor que você mandou.

Consequência prática, e por isso os nós deste projeto são tão curtos:

- **um único `interrupt()` por nó**;
- **nenhum efeito colateral antes do `interrupt()`** (nada de escrever arquivo,
  mandar e-mail, chamar API).

Repare que o único nó que escreve em disco — `no_salvar` — não tem `interrupt()`
nenhum. Não é coincidência.

---

## 6. Como evoluir

### Habilitar "App" ou "Schedule" quando a feature existir

A regra mora no catálogo, não no grafo. Em `questions.py`, troque o flag:

```python
Option(value="app", label="App", ..., available=False, note="...")
#                                    ^^^^^^^^^^^^^^^^ vire True
```

Aí é só ligar a aresta correspondente em `initialize.py` para os nós novos, em vez
de `END`.

### Adicionar uma pergunta

1. Declare a `Question` em `questions.py` (com as regras de validação).
2. Crie o nó em `initialize.py` (`return {"campo": _perguntar(Q_NOVA)}`).
3. Ligue no grafo com `add_edge`.
4. Acrescente o campo no `InitializeState` e no `ProjectSpec` (`spec.py`).

O `ui.py` **não muda** — ele já sabe desenhar qualquer pergunta dos tipos
`choice`, `multi_choice`, `text`, `integer` e `confirm`.

### Adicionar um slash-command

Uma entrada nova em `_COMANDOS_UNICOS`, em `cli.py`. O loop do REPL não muda.

### Quando entrar o LLM

Os arquivos `graph.py`, `tools.py` e `prompts.py` são o agente ReAct (Claude +
ferramentas de ler/escrever arquivo e rodar Maven). Hoje eles **não são chamados por
nenhum comando** — ficaram prontos para o `/generate`, que vai:

1. ler a spec com `load_spec()`;
2. montar um prompt com o que foi decidido (fila, throughput, dependências);
3. deixar o Claude gerar o `pom.xml`, o listener SQS e o Terraform do worker;
4. validar com `mvn validate` / `terraform validate`.

### Trocar o checkpointer

Hoje é `MemorySaver` (memória, some ao fechar). Trocar por `SqliteSaver` faria o dev
conseguir **retomar um `/initialize` no dia seguinte** de onde parou. Uma linha em
`build_initialize_graph()`.

---

## 7. Formato da spec

`<projeto>/.springboot-agent/spec.json`:

```json
{
  "spec_version": 1,
  "generated_at": "2026-07-25T17:30:39+00:00",
  "generated_by": "springboot-agent 0.2.0",
  "project": {
    "type": "worker",
    "trigger": "sqs",
    "sqs": {
      "queue_name": "minha-fila-dev",
      "messages_per_second": 50
    },
    "dependencies": ["dynamodb", "sns"]
  }
}
```

Detalhes de propósito:

- **`spec_version`** é a versão do *formato*, não do agente. Quando o formato mudar,
  os comandos detectam uma spec antiga e avisam, em vez de interpretar errado.
- **A lista `dependencies` é ordenada pela ordem do catálogo**, não pela ordem em que
  o dev digitou. Assim escolher `5,3,1` ou `1,3,5` gera **exatamente o mesmo JSON** —
  o diff no git só muda quando a decisão muda.
- **Commite este arquivo.** Ele é a documentação revisável, em pull request, do que
  foi decidido sobre o projeto — separada do código gerado a partir dele.
