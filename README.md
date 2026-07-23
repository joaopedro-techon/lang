# springboot-agent

Um agente de IA de verdade — **LangGraph + Claude (Anthropic)** — especialista em
configurar projetos **Spring Boot**. Ele pega um projeto novo, analisa a estrutura,
ajusta o `pom.xml` com as dependências corretas, organiza os pacotes por camada e
valida com Maven.

## Como funciona (a orquestração)

O agente é um **grafo do LangGraph** com um loop ReAct explícito:

```
START -> assistant -> (pediu ferramenta?) --sim--> tools -> assistant
                            |
                           não
                            v
                           END
```

- **assistant** (`graph.py`): chama o Claude (`claude-opus-4-8`) com as ferramentas.
- **tools** (`tools.py`): executa o que o Claude pediu (ler/escrever arquivo, Maven).
- A **aresta condicional** decide continuar usando ferramentas ou terminar.

O "cérebro" de Spring Boot está no **system prompt** (`prompts.py`), que define o
método: **analisar → planejar → agir → verificar**.

## Estrutura

```
src/springboot_agent/
├── config.py     # raiz do projeto + barreira de segurança de caminhos
├── tools.py      # ferramentas: list/read/write/create_directory/run_maven
├── prompts.py    # system prompt (a persona especialista)
├── graph.py      # o orquestrador LangGraph
└── main.py       # CLI
```

## Instalação (Windows / PowerShell)

```powershell
# 1. Ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar o pacote e dependências
pip install -e .

# 3. Configurar a chave da Anthropic
Copy-Item .env.example .env
# edite .env e coloque sua ANTHROPIC_API_KEY
```

Pegue a chave em: https://console.anthropic.com/settings/keys

## Uso

```powershell
python -m springboot_agent.main [--yes] <caminho-do-projeto> "<instrução opcional>"
```

Exemplo:

```powershell
python -m springboot_agent.main C:\dev\meu-projeto `
    "Configure para uma API REST com JPA e PostgreSQL"
```

Sem instrução, ele usa um padrão (configurar boas práticas gerais).

### Confirmação antes de editar (human-in-the-loop)

Por padrão, **o agente pede sua aprovação (`s/N`) antes de qualquer ação que
mexe no disco/sistema**:

- **sobrescrever ou criar arquivo** (`write_file`) — mostra o caminho, se o
  arquivo já existe (e o tamanho atual), e uma prévia do novo conteúdo;
- **rodar Maven** (`run_maven`) — mostra o comando.

Ações seguras (ler, listar, criar pasta) rodam sem perguntar. Se você negar,
a ferramenta devolve `CANCELADO` e o agente segue sem editar.

Para automação (pular todas as confirmações), use `--yes` / `-y`:

```powershell
python -m springboot_agent.main --yes C:\dev\meu-projeto "configure boas práticas"
```

> Sem terminal interativo (ex.: rodando via pipe/CI sem `--yes`), as ações
> destrutivas são **negadas por segurança** em vez de travar.

## Segurança

- As ferramentas só leem/escrevem **dentro** da pasta do projeto alvo
  (`resolve_inside_project` em `config.py` bloqueia `..`, symlinks e caminhos
  externos).
- **Confirmação humana** antes de escrever arquivos ou rodar Maven (acima).
- `recursion_limit` em `main.py` evita loops infinitos.

## Próximos passos (ideias de evolução)

- **Backup automático** (ex.: `pom.xml.bak`) antes de sobrescrever.
- **Human-in-the-loop avançado** via LangGraph `interrupt` + checkpointer
  (mais idiomático que o gate dentro das ferramentas, porém mais complexo).
- **Nós explícitos** analisar/planejar/verificar como estados separados do grafo.
- Suporte a **Gradle** além de Maven.
- Persistência do histórico com um checkpointer (SQLite).
