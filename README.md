# springboot-agent

CLI que inicializa projetos **Spring Boot** da organização. O desenvolvedor entra na
pasta do repositório, roda o agente e responde a um wizard; o agente grava a
configuração decidida numa **spec** que os próximos comandos vão consumir.

Construído com **LangGraph** — o mesmo motor que vai orquestrar, mais à frente, os
comandos que usam **Claude** para gerar código.

## Estado atual

| Comando | O que faz | Status |
|---|---|---|
| `/initialize` | Pergunta o tipo do projeto e grava a spec | ✅ disponível |
| `/status` | Mostra a spec já salva no projeto | ✅ disponível |
| `/help`, `/exit` | Ajuda e saída | ✅ disponível |
| `/generate` | Gera `pom.xml`, listener SQS e Terraform a partir da spec | 🚧 em breve |

Dentro do `/initialize`, hoje só o caminho **Worker + consumo SQS** é suportado.
**App** (API REST com load balancer) e **Schedule** (execução agendada) são
selecionáveis, mas encerram o comando avisando que a feature ainda não existe.

## Instalação (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Isso cria o comando `springboot-agent` no PATH do ambiente virtual.

> **Se o comando não for encontrado**, você instalou fora de um venv e o `pip` avisou
> algo como *"The script springboot-agent.exe is installed in ... which is not on
> PATH"*. Duas saídas: use o venv acima (recomendado), ou simplesmente chame
> `python -m springboot_agent.main`, que funciona igual sem depender do PATH.

> A chave da Anthropic (`.env`) ainda **não é necessária**: o `/initialize` não usa
> LLM. Ela só entra quando o `/generate` existir.

## Uso

```powershell
cd C:\dev\meu-repo
springboot-agent
```

Sem argumento, ele usa a pasta atual. Dá para passar um caminho:
`springboot-agent C:\dev\meu-repo`. Sem instalar, funciona igual com
`python -m springboot_agent.main`.

```
==============================================================
  Spring Boot Agent 0.2.0
  Projeto: C:\dev\meu-repo
==============================================================
Digite /help para ver os comandos, /exit para sair.

> /initialize
```

### O fluxo do `/initialize`

```
1. Tipo do projeto?      Worker  |  App (em breve → encerra)
2. O que dispara?        Consumo SQS  |  Schedule (em breve → encerra)
3. Nome da fila SQS      validado no formato da AWS (até 80 chars, .fifo)
4. Mensagens por segundo inteiro de 1 a 100.000
5. Dependências          DynamoDB, Firehose, SNS, Aurora RDS, Feign (várias ou nenhuma)
6. Revisão               mostra tudo e pede confirmação
7. Grava a spec
```

Na multi-escolha das dependências, responda `1,3` (ou `1 3`), ou deixe em branco
para nenhuma. Em qualquer pergunta, uma resposta inválida é recusada com o motivo e
a pergunta é repetida — o wizard nunca "chuta" e nunca segue com dado inválido.

**Nada é escrito em disco antes da confirmação final.** Cancelar, ou escolher uma
feature indisponível, não deixa rastro no projeto.

### O que sai no final

`<projeto>/.springboot-agent/spec.json`:

```json
{
  "spec_version": 1,
  "generated_at": "2026-07-25T17:30:39+00:00",
  "generated_by": "springboot-agent 0.2.0",
  "project": {
    "type": "worker",
    "trigger": "sqs",
    "sqs": { "queue_name": "minha-fila-dev", "messages_per_second": 50 },
    "dependencies": ["dynamodb", "sns"]
  }
}
```

**Commite esse arquivo.** Ele é a documentação revisável em pull request do que foi
decidido sobre o projeto, separada do código que será gerado a partir dele.

## Por que o wizard não usa IA

O `/initialize` decide infraestrutura de verdade. Se o agente "inventar" que o dev
escolheu Aurora RDS, alguém sobe um banco sem precisar. Por isso o fluxo é **100%
determinístico**: as perguntas são dados, as regras de validação são código, e o
caminho pelo grafo é decidido por arestas condicionais — não por um modelo.

O LLM entra depois, no `/generate`, para escrever Java e Terraform **a partir de uma
spec já fechada e validada**. A spec é a fronteira: se o modelo errar, ele erra
escrevendo código — não errando *o que foi decidido*.

## Estrutura

```
src/springboot_agent/
├── main.py         entrada da CLI
├── cli.py          REPL + registro de slash-commands
├── ui.py           renderização das perguntas no terminal
├── initialize.py   o grafo determinístico do /initialize
├── questions.py    as perguntas como dados + validação (fonte única)
├── spec.py         leitura/escrita do .springboot-agent/spec.json
├── config.py       raiz do projeto + barreira de segurança de caminhos
│
├── graph.py        ┐
├── tools.py        ├─ agente ReAct (Claude + ferramentas). Pronto, porém ainda
└── prompts.py      ┘  não usado por nenhum comando — reservado para o /generate.
```

📖 **[docs/arquitetura.md](docs/arquitetura.md)** explica em detalhe os conceitos do
LangGraph usados (state, nós, arestas condicionais, `interrupt`, checkpointer), a
pegadinha de re-execução do `interrupt` e como adicionar perguntas e comandos.

O projeto de exemplo que a organização entrega como ponto de partida está em
[`docs/projeto_inicial/`](docs/projeto_inicial) — é o molde que o `/generate` vai
transformar.

## Próximos passos

- `/generate` — gerar `pom.xml`, o listener SQS e o Terraform do worker a partir da spec.
- Habilitar **App** e **Schedule** (é virar um flag em `questions.py` + ligar os nós).
- Trocar o checkpointer para `SqliteSaver`, permitindo retomar um `/initialize`
  interrompido.
