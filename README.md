# Custod.IA

Agente de engenharia da **custódia de ativos PF**. O desenvolvedor entra na pasta do
repositório e roda `custodia`: ali ele conversa com o agente sobre o domínio e sobre
o código, pede alterações, e usa comandos determinísticos para configurar projetos
novos.

> Pacote: **`custodia-cli`** · comando: **`custodia`** · import: **`custodia`**
> Distribuído **apenas no Artifactory interno** — não vai para o PyPI público.

Construído com **LangGraph** sobre **Claude** — dois modos no mesmo shell: a conversa
(agente ReAct com ferramentas) e os comandos determinísticos, que não usam LLM.

## Estado atual

| Comando | O que faz | Status |
|---|---|---|
| *(texto solto)* ou `/chat` | Conversa: dúvidas e alterações no código | ✅ disponível |
| `/initialize` | Pergunta o tipo do projeto e grava a spec | ✅ disponível |
| `/infra` | Escreve o Terraform do worker (dev/hom/prod) consultando a AWS | ✅ disponível |
| `/status` | Mostra a spec já salva no projeto | ✅ disponível |
| `/help`, `/exit` | Ajuda e saída | ✅ disponível |
| `/generate` | Gera `pom.xml` e o listener SQS a partir da spec | 🚧 em breve |

Dentro do `/initialize`, hoje só o caminho **Worker + consumo SQS** é suportado.
**App** (API REST com load balancer) e **Schedule** (execução agendada) são
selecionáveis, mas encerram o comando avisando que a feature ainda não existe.

## Instalação

Para quem só quer **usar** o agente:

```powershell
python -m pip install custodia-cli
```

Isso só funciona com o índice interno configurado — veja
[Configurar o índice interno](#configurar-o-índice-interno) logo abaixo. Sem isso o
`pip` procura no PyPI público, onde o pacote **não existe**.

Para **desenvolver** o agente (instalação editável a partir deste repositório):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Qualquer uma das duas cria o comando `custodia` no PATH do ambiente.

> **Depois de um `git pull` que mexa nas dependências, rode `pip install -e .` de novo.**
> Um install editável já existente aponta para o código novo, mas **não** instala
> dependências novas sozinho — o sintoma é um `ModuleNotFoundError` num pacote que
> você nunca viu.

### Configurar o índice interno

O Artifactory da organização expõe o repositório PyPI em
`https://artifactory.prod.aws.cloud.ihf/artifactory/api/pypi/<repo-pypi>/simple`.
Configure uma vez, e o `pip install custodia-cli` passa a funcionar liso:

```powershell
pip config set global.index-url https://artifactory.prod.aws.cloud.ihf/artifactory/api/pypi/<repo-pypi>/simple
```

Ou por execução, sem gravar config:

```powershell
pip install custodia-cli --index-url https://artifactory.prod.aws.cloud.ihf/artifactory/api/pypi/<repo-pypi>/simple
```

> Troque `<repo-pypi>` pelo nome do repositório PyPI da sua squad no Artifactory —
> o análogo do `itau-sg2-maven-release` que aparece no `settings.xml` dos projetos Java.

> **Se o comando não for encontrado**, você instalou fora de um venv e o `pip` avisou
> algo como *"The script custodia.exe is installed in ... which is not on PATH"*.
> Duas saídas: use um venv (recomendado), ou chame `python -m custodia`, que
> funciona igual sem depender do PATH.

### Chave da Anthropic

A **conversa** usa Claude, então precisa de chave. Copie `.env.example` para `.env`
na pasta do seu repositório e preencha:

```
ANTHROPIC_API_KEY=sk-ant-...
AGENT_MODEL=claude-opus-5   # opcional
```

Os comandos determinísticos (`/initialize`, `/status`) **não** usam LLM e continuam
funcionando sem chave nenhuma — o agente só é ligado no primeiro turno de conversa.

## Uso

```powershell
cd C:\dev\meu-repo
custodia
```

Sem argumento, ele usa a pasta atual. Dá para passar um caminho:
`custodia C:\dev\meu-repo`. Sem depender do PATH, funciona igual com
`python -m custodia`.

```
==============================================================
  Custod.IA 0.2.0
  Agente da custódia de ativos PF
  Projeto: C:\dev\meu-repo
==============================================================
Pergunte qualquer coisa, ou digite /help para ver os comandos.

> como funciona o retry do listener SQS aqui?
```

### Conversar com o agente

**Qualquer texto sem barra é conversa** — como no Claude Code. As barras ficam
reservadas para os comandos determinísticos.

```
> o que tem neste projeto?

Custod.IA
  Vou dar uma olhada na estrutura do projeto.
  ● list_directory  path=.
    └ .custodia/
  ● read_file  path=.custodia/spec.json
    └ { (+16 linhas)

Custod.IA
  É um worker que consome SQS (fila minha-fila-dev, ~50 msg/s), com
  dependências de DynamoDB e SNS.
```

A resposta é renderizada como **Markdown** (negrito, listas, blocos de código com
syntax highlighting), um spinner mostra quando o modelo está pensando, e cada chamada
de ferramenta aparece na hora em que acontece.

O agente lê o projeto antes de responder, e **também aplica alterações** quando você
pede. Cada escrita em arquivo e cada `mvn` param para pedir sua aprovação, num painel
com o conteúdo colorizado:

```
┌─ aprovacao necessaria  escrever em pom.xml ──────────────────┐
│                                                              │
│  CRIAR  arquivo novo  ->  614 caracteres                     │
│                                                              │
│     1 <?xml version="1.0" encoding="UTF-8"?>                 │
│     2 <project xmlns="http://maven.apache.org/POM/4.0.0">    │
│    ...                                                       │
└──────────────────────────────────────────────────────────────┘
Aprovar? [s/N]
```

Nada é alterado à sua revelia. As ferramentas também são sandboxed na pasta do
projeto: o agente não escapa dela.

`/chat` abre o mesmo agente num sub-prompt dedicado (`voce>`), com `/limpar` para
esquecer o histórico e `/sair` para voltar. Os dois caminhos **compartilham a mesma
conversa** — o histórico continua o mesmo quando você alterna entre eles.

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

Num terminal de verdade, as perguntas de escolha são **navegáveis**: setas para mover,
enter para confirmar, e **espaço para marcar** nas de múltipla escolha.

```
? Quais dependencias o projeto precisa? (setas movem, espaco marca, enter confirma)
 » ● DynamoDB
   ○ Firehose
   ● SNS
   ○ Aurora RDS
   ○ Feign
```

Fora de um terminal interativo — pipe, CI, ou um terminal Windows não-nativo tipo Git
Bash — o wizard **cai automaticamente no modo digitado** (`1,3`), que continua
funcionando exatamente como antes. Em qualquer um dos dois, uma resposta inválida é
recusada com o motivo e a pergunta é repetida: o wizard nunca "chuta" e nunca segue
com dado inválido.

**Nada é escrito em disco antes da confirmação final.** Cancelar, ou escolher uma
feature indisponível, não deixa rastro no projeto.

## O `/infra`

Escreve o Terraform do worker no `infra/terraform/` do seu projeto, um ambiente por
vez, oferecendo **opções reais da sua conta AWS** em vez de pedir você digitar IDs.

**Pré-requisito:** três profiles no `~/.aws` (em `config` ou `credentials`), um por
ambiente — `CUSTODIA-AI-DEV`, `CUSTODIA-AI-HOM`, `CUSTODIA-AI-PROD`. O agente usa a
AWS CLI, que já resolve SSO, MFA e `role_arn` sozinha; não há credencial a configurar
de novo. Só faz chamadas de leitura (`list`/`describe`) — quem aplica é o Terraform.

**Região.** Toda consulta passa `--region` explicitamente, então um profile sem
`region` configurada funciona. A precedência é: `AWS_REGION` → `AWS_DEFAULT_REGION` →
a `region` do profile → `sa-east-1`. A região usada aparece na primeira pergunta de
cada ambiente, junto com o profile e o número da conta:

```
Perfil CUSTODIA-AI-DEV · conta 028302650210 · regiao sa-east-1
```

Isso não é decoração: **região errada não dá erro, devolve lista vazia**. Ver a região
na tela é o que separa "esta conta não tem cluster nenhum" de "estou olhando para a
região errada".

```
/infra
 ├─ app ou worker?                 app encerra: ainda não disponível
 ├─ quais ambientes?               dev, hom, prod (uma ou várias)
 ├─ confere TODOS os perfis        antes de qualquer outra pergunta
 ├─ confirma as contas             mostra em que conta cada ambiente caiu
 ├─ identidade da aplicação        sigla, produto, squad, e-mails, tags de FinOps…
 └─ por ambiente:                  cluster ECS, VPC, subnets, CIDRs, filas SQS,
                                   vazão, URLs do STS
```

### A conferência dos perfis

Acontece logo depois de você escolher os ambientes, e confere **todos** de uma vez —
não só o primeiro. Um perfil de prod quebrado não pode aparecer depois de 17 perguntas
e da rodada inteira de dev.

São duas checagens, porque falham por motivos diferentes: o perfil pode **não existir**
(erro de configuração) ou existir e **não autenticar** (sessão expirada). A lista de
perfis vem de `aws configure list-profiles`, que junta o `config` e o `credentials` —
ler só o `config` não enxerga perfis declarados apenas no `credentials`.

Se algo falha, você recebe o quadro inteiro para consertar de uma vez:

```
Nem todos os perfis estao prontos:

  dev   CUSTODIA-AI-DEV    OK      conta 028302650210  regiao sa-east-1
  hom   CUSTODIA-AI-HOM    FALHOU  nao existe no ~/.aws (nem em config, nem em credentials).
  prod  CUSTODIA-AI-PROD   FALHOU  a sessao do perfil expirou.
```

Se tudo passa, você confirma antes de seguir — e é aqui que dá para pegar um perfil
copiado e não editado:

```
  dev   CUSTODIA-AI-DEV    OK      conta 999988887777  regiao sa-east-1
  prod  CUSTODIA-AI-PROD   OK      conta 999988887777  regiao sa-east-1

  ATENCAO: dev e prod apontam para a MESMA conta (999988887777).
```

As listas vêm da AWS: clusters ECS, VPCs, subnets (com AZ e CIDR), filas SQS e
secrets. Os CIDRs são derivados das subnets que você escolheu, sem consulta extra. Se
alguma listagem vier vazia — conta nova, ou perfil sem permissão — a pergunta vira
campo de texto em vez de travar o wizard.

### Como o autoscaling é calculado

O `autoscaling` não é copiado do template: sai de uma fórmula em
[`dimensionamento.py`](src/custodia/dimensionamento.py), a partir de três números que
o wizard pergunta.

```
vazão por task = concorrência / tempo por mensagem
min_capacity   = teto(vazão do ambiente / vazão por task)
max_capacity   = min_capacity × 3
scale_up.threshold   = backlog de 60s de trabalho da frota
scale_down.threshold = 1/8 do limiar de subida
```

Tempo de processamento e concorrência são propriedades do **código** e por isso são
perguntados uma vez só; a **vazão** é perguntada por ambiente, porque dev e produção
não recebem a mesma carga. A revisão final mostra a conta inteira antes de gravar.

### O que ele escreve

Tudo dentro de `infra/terraform/` — e só ali; há uma barreira em código que bloqueia
qualquer escrita fora dessa pasta. Os `.tf` vêm do template do worker que viaja dentro
do pacote, com `data.tf` e `locals.tf` preenchidos, e um `terraform.tfvars` por
ambiente escolhido. **Ambiente que você não escolheu não é tocado.**

### O que sai no final

`<projeto>/.custodia/spec.json`:

```json
{
  "spec_version": 1,
  "generated_at": "2026-07-25T17:30:39+00:00",
  "generated_by": "Custod.IA 0.2.0",
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

## Por que o wizard não usa IA (e a conversa usa)

O `/initialize` decide infraestrutura de verdade. Se o agente "inventar" que o dev
escolheu Aurora RDS, alguém sobe um banco sem precisar. Por isso o fluxo é **100%
determinístico**: as perguntas são dados, as regras de validação são código, e o
caminho pelo grafo é decidido por arestas condicionais — não por um modelo.

A **conversa** é o oposto e por isso é separada: ali o problema é aberto, o dev está
no comando e revisa cada escrita antes que ela aconteça. Errar uma resposta custa uma
correção; errar *o que foi decidido* sobre a infra custa um banco no ar sem precisar.

O LLM entra também no `/generate`, para escrever Java e Terraform **a partir de uma
spec já fechada e validada**. A spec é a fronteira: se o modelo errar, ele erra
escrevendo código — não errando *o que foi decidido*.

## Estrutura

```
src/custodia/
├── main.py         entrada da CLI
├── __main__.py     habilita `python -m custodia`
├── cli.py          REPL + registro de slash-commands + roteamento do texto solto
├── ui.py           o console (rich) compartilhado + as perguntas do wizard
├── initialize.py   o grafo determinístico do /initialize
├── questions.py    as perguntas como dados + validação (fonte única)
├── spec.py         leitura/escrita do .custodia/spec.json
├── config.py       raiz do projeto + barreira de segurança de caminhos
│
├── infra.py        ┐  o /infra: grafo determinístico, AWS e escrita do
├── aws.py          ├─ terraform. `templates/worker/` guarda os .tf que
├── terraform.py    │  viajam dentro da wheel.
├── dimensionamento.py ┘  a fórmula do autoscaling, isolada e testável
│
├── chat.py         ┐  a conversa: histórico + streaming das chamadas de
├── graph.py        ├─ ferramenta na tela, sobre o agente ReAct
├── tools.py        │  (Claude + ferramentas, com aprovação s/N na escrita)
└── prompts.py      ┘
```

📖 **[docs/arquitetura.md](docs/arquitetura.md)** explica em detalhe os conceitos do
LangGraph usados (state, nós, arestas condicionais, `interrupt`, checkpointer), a
pegadinha de re-execução do `interrupt` e como adicionar perguntas e comandos.

O projeto de exemplo que a organização entrega como ponto de partida está em
[`docs/projeto_inicial/`](docs/projeto_inicial) — é o molde que o `/generate` vai
transformar.

## Publicar uma nova versão

1. **Suba a versão** em `src/custodia/__init__.py` (`__version__`). É a fonte única:
   o `pyproject.toml` lê esse atributo, e o banner e o campo `generated_by` da spec
   saem daí. Nenhum outro arquivo precisa mudar.

2. **Construa** os artefatos (`sdist` + `wheel`) num `dist/` limpo:

   ```powershell
   pip install -e ".[dev]"
   Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
   python -m build
   ```

3. **Publique** no Artifactory interno:

   ```powershell
   python -m twine upload `
     --repository-url https://artifactory.prod.aws.cloud.ihf/artifactory/api/pypi/<repo-pypi>/ `
     dist/*
   ```

   Credenciais via `TWINE_USERNAME` / `TWINE_PASSWORD` (use um *token* do Artifactory,
   não a senha de rede) ou num `~/.pypirc`.

> **Por que o `--repository-url` é obrigatório:** um `twine upload` sem ele iria para o
> PyPI *público*. O `pyproject.toml` declara o classifier `Private :: Do Not Upload`
> justamente para isso — o PyPI público rejeita o envio, então o engano falha alto em
> vez de vazar o pacote da organização.

## Próximos passos

- `/generate` — gerar `pom.xml`, o listener SQS e o Terraform do worker a partir da spec.
- Habilitar **App** e **Schedule** (é virar um flag em `questions.py` + ligar os nós).
- Trocar o checkpointer para `SqliteSaver`, permitindo retomar um `/initialize`
  interrompido.
