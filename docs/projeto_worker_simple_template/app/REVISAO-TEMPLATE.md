# Revisão do worker template — estado do trabalho

Contexto: `msdemoworker` é o projeto-molde que o agente LangGraph vai replicar para gerar novos
projetos. Cada defeito aqui é herdado por todo projeto derivado, o que eleva a severidade de
qualquer achado.

Última sessão: **2026-07-28**. Revisão concluída; blocos 1 a 8 aplicados — **os 54 itens foram
tratados**, 50 fechados por completo e 4 parciais (25, 26, 27, 37).

> **Achados do primeiro `mvn clean install` real (2026-07-28):** dois defeitos que a verificação
> por compilação nunca pegaria — ver "Achados do primeiro build" logo abaixo.
>
> **O que falta antes do commit:** subir a aplicação uma vez. Existe agora um `contextLoads`
> (`PedidoFluxoCompletoIT`), que compila mas **nunca rodou** — o Docker Desktop desta máquina
> travou com `metadata.db: input/output error` e não responde. É o único teste que pega erro de
> wiring de beans, e o refactor do bloco 7 mexeu em praticamente todos.
>
> **Pré-requisito de infra novo:** a task role precisa de `dynamodb:PutItem` e
> `dynamodb:DeleteItem` na tabela de idempotência. Sem isso a aplicação sobe e falha na primeira
> mensagem. As policies ficam nos JSON de `iamsr/policy/`, fora deste repositório.

> **Bloqueio operacional em aberto:** o Docker Desktop desta máquina travou com
> `metadata.db: input/output error` e não responde mais (`docker ps` pendura). Isso impede a
> validação em runtime dos blocos 2 (container não-root) e 6 (LocalStack). Reiniciar o Docker
> Desktop destrava as duas de uma vez.

---

## Achados do primeiro build real (2026-07-28)

O usuário rodou `mvn clean install` num ambiente com Artifactory acessível — o **primeiro build de
verdade** deste template. Apareceram dois defeitos que sete blocos de revisão por compilação não
pegariam. Vale como calibragem do que a verificação estática deixa passar.

### 1. JaCoCo 0.8.12 não suporta Java 25

```
Unsupported class file major version 69
```

Java 25 gera **major 69**; o JaCoCo 0.8.12 (março/2024) para no 22. **Não é regressão da
revisão** — o pino `0.8.12` sob `java.version=25` estava no template desde o início, e todo
projeto gerado quebraria no primeiro `mvn install`. Ficou escondido porque nunca houve um build
funcionando nesta máquina.

Conferido que **o Spring Boot 4.0.5 não gerencia essa versão** (nem em `spring-boot-dependencies`
nem no `starter-parent`), então o pino é obrigatório. Corrigido para `0.8.14` com o acoplamento
`jacoco.version` ↔ `java.version` documentado no `pom.xml`.

### 2. O teste de integração quebrava o build sem Docker

O failsafe rodou o `PedidoFluxoCompletoIT` e ele falhou com
`Could not find a valid Docker environment` — o mesmo Docker Desktop travado.

Corrigido com `@Testcontainers(disabledWithoutDocker = true)`: sem Docker a classe é **pulada**,
não quebrada. Docker fora do ar na máquina de quem desenvolve não pode reprovar o build.

**Contrapeso registrado no CLAUDE.md:** isso significa que um agente de CI sem Docker produz build
verde com cobertura de integração **zero**, em silêncio — e o `PedidoFluxoCompletoIT` é o único
teste que valida wiring de beans. Conferir os testes PULADOS no relatório do failsafe antes de
confiar num build verde.

### O que o build confirmou de bom

Passou por compilação, testes unitários, JaCoCo e chegou ao failsafe — ou seja, **os 30 unitários
passaram também sob Maven**, não só sob o launcher improvisado.

---

## Como validar as mudanças (importante)

O build normal **não funciona nesta máquina**:

- `C:\Program Files\Java\jdk-25.0.3` está **quebrado** — crasha com `EXCEPTION_ACCESS_VIOLATION`
  (`jvm.dll+0xfdc55`) até em `java -version`. Não é problema do Maven.
- O `mvn` do PATH roda sob JDK 11; o `pom.xml` exige Java 25.
- `maven-dependency-plugin` não está no `~/.m2` e o Artifactory interno é inacessível daqui.

Contorno usado: compilar com o `javac` do **JDK 21** montando o classpath a partir do `~/.m2`,
pegando a **maior versão de cada artefato** (assim resolve awspring 4.0.0 e Boot 4.0.5, e não as
versões antigas também presentes no cache).

```
--release 21 --enable-preview -proc:none
```

- `--enable-preview` é necessário por causa do `_` (unnamed variable, Java 22+) em
  `MetricsConfig.java:32` — único recurso acima de 21 no código.
- `-proc:none` evita que um Lombok solto no `~/.m2` seja carregado como annotation processor.

Scripts ficaram no scratchpad da sessão (`build.ps1`, `mkcp.ps1`) — descartáveis, fáceis de
recriar a partir desta descrição.

**Limite da verificação:** só há garantia de *compilação*. Nada foi executado — sem testes, sem
LocalStack, sem subida de contexto Spring. Nenhum comportamento de runtime foi observado.

---

## Bloco 1 — CONCLUÍDO (não commitado)

Alterações aplicadas em `app/src/main/java/...`:

| Arquivo | Mudança |
|---|---|
| `application/facade/ProcessarPedidoFacade.java` | Drena a auditoria na thread produtora antes de submeter ao executor |
| `domain/auditoria/AuditoriaContext.java` | Novo `drenar()` (captura + limpa numa operação) |
| `infrastructure/logging/Logger.java` | Overloads `(String, Throwable)` p/ `error`/`warn`; `LOG` `volatile` com logger padrão |
| `domain/pedido/PedidoEvent.java` | Validação saiu do construtor canônico → `validar()` explícito |
| `domain/pedido/enums/Fluxo.java` | `@JsonCreator` tolerante: valor desconhecido vira `null` |
| `domain/pedido/exception/` *(novo)* | `PedidoNaoProcessavelException`, `PedidoInvalidoException`, `FluxoNaoSuportadoException` |
| `infrastructure/adapters/inbound/PedidoQueueListener.java` | Chama `event.validar()`; confirma só no sucesso, falha propaga sem `ack` |
| `infrastructure/adapters/inbound/PedidoQueueErrorHandler.java` | Classifica permanente x transitória (percorrendo a cadeia de causas) em log e métrica |
| `infrastructure/config/MetricsConfig.java` | `METRIC_PEDIDO_FALHA`, `TAG_TIPO_FALHA`, `TAG_EXCECAO`, `TIPO_FALHA_*` |
| `infrastructure/adapters/outbound/FirehoseBatchClient.java` | Retry só dos registros rejeitados, backoff exponencial, particionamento por bytes, `enviarSincrono()` desembrulhando `CompletionException` |
| `infrastructure/adapters/outbound/FirehoseProperties.java` | `maxTentativas`, `backoffInicialMs` |
| `infrastructure/adapters/outbound/FirehosePublicacaoException.java` | Construtor só-mensagem |
| `infrastructure/adapters/outbound/FirehoseBatchPublicador.java` / `FirehosePublicadorAuditoria.java` | Usam `enviarSincrono()` |
| `application/usecase/ProcessarPedidoUseCasePortImpl.java` | Merge function explícita, `FluxoNaoSuportadoException`, WARN de fluxos sem publicador no startup |
| `infrastructure/config/QueueProperties.java` | `pedidoMaxConcurrent` virou `int` |
| `infrastructure/config/MdcAwareExecutor.java` | `catch` logando falha de tarefa fire-and-forget |
| `resources/application.yml` | `app.firehose.max-tentativas`, `app.firehose.backoff-inicial-ms`; comentário declarando a `redrivePolicy` como pré-requisito |

### Raciocínio que não é óbvio no diff

- **Por que a validação saiu do construtor de `PedidoEvent`:** lançando no construtor canônico, a
  falha ocorre dentro da desserialização do Jackson, *antes* do listener. Sem `Acknowledgement`, a
  mensagem nunca é confirmada nem roteada — reentrega perpétua. Mesma razão para o `@JsonCreator`
  em `Fluxo`.
- **Por que `drenar()` em vez de só reordenar as linhas:** o contexto vive em `ThreadLocal`;
  a API agora torna a captura na thread errada impossível, em vez de depender de o próximo dev
  lembrar da ordem.
- **`ack` só no caminho de sucesso.** É isso — e só isso — que garante a reentrega. Nenhum caminho
  de falha confirma a mensagem.

### DECISÃO (2026-07-27): a aplicação NÃO roteia para DLQ

Uma primeira versão incluía roteamento app-side (`PedidoDlqPublicador` + classificação no
listener). **Foi removida a pedido do usuário**, que já configura `redrivePolicy` com
`maxReceiveCount` nas filas. Não reintroduzir sem discutir.

Motivos:

- A `redrivePolicy` cobre falhas **anteriores** ao listener (JSON malformado, erro de conversão,
  processo encerrado), onde não existe `catch` possível.
- Preserva a mensagem original byte a byte, com `messageId` e atributos — o roteamento app-side
  republicava o payload **re-serializado**, e como `FAIL_ON_UNKNOWN_PROPERTIES` está desabilitado,
  campos não mapeados pelo record sumiriam da DLQ.
- Não exige permissão IAM de `SendMessage` na DLQ.
- Sem janela de inconsistência entre confirmar a mensagem e gravá-la na DLQ.
- Dois mecanismos criariam divergência silenciosa: `app.queue.max-receive-count` e o
  `maxReceiveCount` da fila diferentes → o menor vence e o outro vira código morto.

Custo aceito: uma mensagem que comprovadamente nunca vai passar consome N ciclos de retry antes
de cair na DLQ, em vez de sair na primeira entrega.

**Consequência a vigiar:** a proteção contra poison pill agora depende **inteiramente** de infra
que não está neste repositório (Terraform em `infra/terraform`, conforme `.iupipes.yml`). Projeto
gerado sem `redrivePolicy` fica **sem nenhuma** proteção. Documentado em `application.yml` e no
javadoc do `PedidoQueueErrorHandler` — vale reforçar no README quando o item 54 for feito.

---

## Bloco 2 — CONCLUÍDO (não commitado) — Dockerfile / deploy / segurança de build

Sessão **2026-07-28**. Cobre os itens 23, 24, 25 (parcial), 26 (parcial), 28, 29, 30, 32, 35, 36.

| Arquivo | Mudança |
|---|---|
| `app/Dockerfile` | Reescrito — ver detalhamento abaixo |
| `.dockerignore` *(novo, raiz do repo)* | Contexto do build é a raiz; exclui `src/`, `target/`, `infra/`, `.git`, IDEs e **`app/settings.xml`** |
| `app/settings.xml` | 9 pares `USER`/`PASS` → `${env.ARTIFACTORY_USER}` / `${env.ARTIFACTORY_TOKEN}`; `activeProfile` `fe6-compopen` (inexistente) removido |
| `.iupipes.yml` | `projectPropertiesPath: 'app/'` → `''` |
| `infra/terraform/locals.tf` | `SERVER_PORT` derivado de `local.default_container_port` |
| `infra/terraform/inventories/{dev,hom,prod}/terraform.tfvars` | `datadog_env` removido (variável não declarada) |

### Dockerfile — o que mudou e por quê

- **JDK duplicado (24).** `RUN apk --update add openjdk25` removido: a base
  `amazoncorretto:25-alpine` já é uma imagem JDK. ~180 MB a menos por imagem.
- **Usuário não-root (24).** `addgroup`/`adduser` + `USER app`, com `COPY --chown`.
  Junto veio uma dependência não óbvia: o `chmod -R 774 /opt/datadog/` **tinha** que virar
  `755`. Com 774, "outros" fica sem bit de execução no diretório, e um processo não-root não
  consegue atravessá-lo para carregar o `-javaagent` — o container subiria como root e quebraria
  ao deixar de ser.
- **RAM percentages (29).** `${INITIAL_RAM_PERCENTAGE:-35}` / `${MAX_RAM_PERCENTAGE:-75}`,
  espelhando os valores que o `locals.tf` injeta. Sem default, `docker run` local não sobe.
- **`ENV DD_ENV=${ENVIRONMENT}` removido (29).** `ENV` é resolvido em *build time* e `ENVIRONMENT`
  só existe em *runtime* → o valor saía vazio. O env do tracer agora vem de
  `-Ddd.env=${ENVIRONMENT:-local}` no `ENTRYPOINT`, onde o shell expande em runtime.
- **`EXPOSE` (28).** Era `2000` fixo; virou `EXPOSE ${SERVER_PORT}` com `ARG SERVER_PORT=8006`.
- **`HEALTHCHECK` + `-XX:+ExitOnOutOfMemoryError` (32)** adicionados. O HEALTHCHECK é redundante
  no ECS (o módulo define o seu), mas é o que torna `docker run` local observável.
- **`apk --no-cache`**, RUNs consolidados, `unzip` (não usado) removido.

### Item 30 — o "conserto" era pior que o defeito

`-Ddd.trace.methods=br.com.itau.SIGLA.*[*]` aponta para um pacote que não existe (o real é
`com.itau.sg2.custodiaposvenda`). **Corrigir o pacote ligaria de fato o tracing método a método
de toda a aplicação** — um span por chamada dentro do loop de consumo da fila. Hoje a flag é
inofensiva justamente porque não casa com nada.

A flag foi **removida**, com comentário explicando o porquê e a sintaxe correta caso alguém
precise instrumentar métodos nominalmente. O agente já instrumenta SQS, HTTP e Feign
automaticamente, que é o que dá o trace de ponta a ponta.

Junto: se a flag voltar, precisa de **aspas simples**. O `ENTRYPOINT` roda sob shell e `*`/`[`/`]`
seriam interpretados como glob — bug latente na versão original.

### Item 31 — FALSO POSITIVO (corrigido)

A revisão original afirmava que `COPY app/*.jar` casava dois arquivos. **Não casa.** O Docker usa
`filepath.Match` do Go: `*.jar` exige que o nome *termine* em `.jar`, e
`msdemoworker-0.0.1-SNAPSHOT.jar.original` termina em `.original`. Confirmado contra o `target/`
real (os dois arquivos existem; só um casa). Nada a fazer.

### O que ficou em aberto nestes itens

- **25 (parcial).** `AWS_CLI_VERSION` virou `ARG` (default `latest`), então fixar a versão é uma
  linha — mas continua `latest` porque não tenho como validar qual tag o Artifactory publica.
  Os ARGs de credencial permanecem: ficam confinados ao estágio `files`, que é descartado, e o
  fix correto (`RUN --mount=type=secret`) depende de como o iupipes passa os segredos.
  O linter do BuildKit sinaliza os três (`SecretsUsedInArgOrEnv`).
- **26 (parcial).** `DD_TRACER_URL` virou `ARG`, com exemplo de URL fixa no Artifactory no
  comentário. Sem checksum — o `dtdg.co` não publica um.
- **27, 33, 34** não foram tocados (SBOM/owasp, deps mortas, plugins de qualidade).

### ACHADOS NOVOS desta sessão

- **`datadog_env` nos três `terraform.tfvars` não é declarado em `variables.tf`** e não é usado
  em lugar nenhum → *"Warning: Value for undeclared variable"* a cada plan/apply. O valor é
  idêntico a `var.environment`, que agora alimenta o `-Ddd.env`. Linha removida dos três.
- **Os `<server><id>` do `settings.xml` não casam com os `<repository><id>`** dos profiles
  (ex.: servidor `es8-compopen` × repositório `itau-comp-open-maven-repo`). O Maven só aplica
  credencial quando os ids são iguais, então boa parte desses blocos nunca autentica nada.
  **Não alterado** — alinhar exige validar contra o Artifactory interno. Documentado em comentário
  no próprio arquivo.
- **Item 28 é menos grave do que a revisão original registrou.** Os `terraform.tfvars` dos três
  ambientes sobrescrevem `containerPort = 8006` (o `2000` é só o default do `variables.tf`), e o
  health check usa `local.default_container_port`. Ou seja, o health check **apontava certo**; o
  errado era só o `EXPOSE 2000`, que no ECS/awsvpc não tem efeito funcional. O risco real era
  a divergência futura entre dois números independentes — resolvido injetando `SERVER_PORT` a
  partir do `containerPort`.

### Verificação feita (e o que falta)

Diferente do bloco 1, aqui houve execução real. O registry interno
(`docker-remotes.artifactory.prod.aws.cloud.ihf`) não é acessível fora da rede do banco, então
montei um contexto de teste no scratchpad trocando **só** o que é inalcançável: a base pelo
`amazoncorretto:25-alpine` do Docker Hub (o interno é mirror dela) e o estágio do `aws s3 cp`
por um stub.

- **`docker build --check`** (linter do BuildKit): 4 avisos, todos conhecidos e explicados acima.
- **`docker build`: PASSOU.** Valida `apk --no-cache add`, a sintaxe do `addgroup`/`adduser`,
  o `COPY --chown=app:app` resolvendo o usuário, o download do agente e o parse de
  `EXPOSE ${SERVER_PORT}` / `HEALTHCHECK`.
- **`docker run`: NÃO EXECUTADO.** O Docker Desktop desta máquina falhou com
  `metadata.db: input/output error` ao criar o container e o daemon travou (`docker ps` deixou de
  responder). Precisa de restart do Docker Desktop.

**Falta verificar em runtime — são justamente as duas mudanças mais arriscadas:**

1. que a base `amazoncorretto:25-alpine` realmente traz o JDK sem o `apk add openjdk25`
   (o build não pega isso: `java` só é invocado no `ENTRYPOINT`);
2. que o usuário não-root carrega o `-javaagent` com o `/opt/datadog` em 755.

Comando para retomar quando o Docker voltar (contexto em
`scratchpad/ctx`): `docker run -d --name wtt -e ENVIRONMENT=local worker-template-test:local`,
depois `docker exec wtt id`, `docker exec wtt java -version` e `docker logs wtt`.

---

## Bloco 3 — CONCLUÍDO (não commitado) — item 22, payload de log

Sessão **2026-07-28**.

| Arquivo | Mudança |
|---|---|
| `infrastructure/logging/PayloadLog.java` *(novo)* | Payload de log montado campo a campo, imutável, `@JsonValue` |
| `infrastructure/logging/Log.java` | `Object payload` → `PayloadLog payload` |
| `infrastructure/logging/Logger.java` | Todas as sobrecargas passam a exigir `PayloadLog` |
| `PedidoQueueListener`, `SqsPublicador`, `ProcessarPedidoUseCasePortImpl`, `ProcessarPedidoFacade`, `PedidoQueueErrorHandler` | Call sites passam campos nomeados |

### O diagnóstico original estava incompleto

`PedidoEvent` e `Pedido` hoje têm **apenas** `idOperacao` (Long) e `fluxo` (enum). Não há PII
circulando no template como ele está. O problema nunca foi o dado de hoje — é que `Log.payload`
sendo `Object` faz de "passar o objeto de domínio inteiro" o caminho mais curto, e **todo campo
novo que um projeto gerado adicionar ao evento passa a ser logado em INFO sem ninguém decidir
isso**. Num molde replicado por um gerador, o default é o produto.

Por isso a correção não foi mascarar valores, e sim **fechar o tipo**: `PayloadLog` obriga a
nomear cada campo, então só vai para o log o que alguém escolheu colocar. Campo que ninguém
nomeou não vaza. Mesma linha do `drenar()` do bloco 1 — tornar o erro impossível em vez de
depender de o próximo dev lembrar.

**Não foi criada classe de máscaras** (`Mascara.cpf()` etc.) de propósito: não há hoje nenhum
campo sensível para mascarar, e a classe entraria como código morto — exatamente o que os itens
33/40/53 já criticam. A regra de mascaramento é política de domínio; ficou documentada no javadoc
do `PayloadLog`.

### O compilador achou dois vazamentos que a revisão original não listou

A revisão apontava `PedidoQueueListener`, `SqsPublicador:46` e `ProcessarPedidoFacade`. Ao trocar
o tipo, o `javac` acusou mais dois — em `PedidoQueueErrorHandler:56` e `:65`, que passavam
**`message.getPayload()`**, o corpo cru da mensagem SQS. Eram os piores da lista: numa falha de
conversão, o evento inteiro sem qualquer filtro, em ERROR/WARN.

Agora esses dois logam só `messageId`, `receiveCount` e a causa raiz. O corpo não precisa estar no
log: a `redrivePolicy` já o preserva byte a byte na DLQ — o mesmo argumento que sustentou a decisão
de não rotear DLQ pela aplicação. O log carrega o que localiza a mensagem lá.

Vale como evidência de que fechar o tipo funciona: um grep por `Logger.info(` não pegou esses dois
(o payload estava em linha de continuação); o compilador pegou.

### Limite que permanece

O tipo protege o campo `Payload`. **Não protege `LogMessage`** — `Logger.info("cpf=" + cpf)`
continua possível e nenhum tipo impede. Só ArchUnit ou revisão pega isso.

### Verificação

- **Compilação: PASSOU** (`javac` do JDK 21, contorno descrito no topo). Só as duas notas de
  deprecação/preview já catalogadas no backlog.
- **Serialização: VERIFICADA em JVM real.** Rodei um probe com o Jackson 2 (o mesmo que o
  logstash-logback-encoder usa) sobre as classes compiladas:

  ```
  PayloadLog isolado : {"idOperacao":123,"fluxo":"PUBLICA_SQS"}
  Log completo       : {...,"Payload":{"idOperacao":123,"fluxo":"PUBLICA_SQS"}}
  Log sem payload    : {"Level":"INFO","LogMessage":"sem payload"}
  ```

  Confirma que `@JsonValue` não introduz nível extra de wrapper e que o `@JsonInclude(NON_EMPTY)`
  segue omitindo o campo quando ausente. **O schema do log não muda** para os parsers a jusante.
- `com.fasterxml.jackson.annotation.JsonValue` é comum ao Jackson 2 e ao 3 — esta mudança não
  depende da decisão pendente entre as duas versões.

---

## Bloco 4 — CONCLUÍDO (não commitado) — migração para Jackson 3

Decisão do usuário em **2026-07-28**: migrar tudo para Jackson 3.

### O problema

- `SqsAutoConfiguration$LegacySqsJackson2Configuration` é
  `@ConditionalOnMissingClass("tools.jackson.databind.json.JsonMapper")`.
- Spring Boot 4.0.5 traz Jackson 3 (`tools.jackson.core:jackson-databind:3.1.0`).
- Logo o caminho ativo é `SqsJacksonConfiguration`. Confirmado no bytecode que ele faz
  **`jsonMapperProvider.getIfAvailable(JsonMapper::new)`**: usa um bean `JsonMapper` se existir,
  senão constrói um com defaults.

Como o projeto declarava um `ObjectMapper` do **Jackson 2**, nenhum `JsonMapper` existia no
contexto → a fila usava um mapper de defaults. `FAIL_ON_UNKNOWN_PROPERTIES` e `NON_NULL` valiam só
para Firehose e auditoria.

### A correção

| Arquivo | Mudança |
|---|---|
| `infrastructure/config/JacksonConfig.java` | Bean passa a ser `JsonMapper` (Jackson 3), montado via `builder()` |
| `infrastructure/config/AuditoriaConfig.java` | `tools.jackson.databind.ObjectMapper` |
| `domain/auditoria/AuditoriaContext.java` | idem |
| `infrastructure/adapters/outbound/FirehoseBatchClient.java` | idem; `JsonProcessingException` → `JacksonException` |
| `pom.xml` | `jackson-datatype-jsr310` e `-jdk8` removidos; `jackson-databind` (2.x) mantido e documentado |

O bean é tipado como `JsonMapper` **de propósito** — é o tipo que o awspring procura. Como
`JsonMapper extends ObjectMapper`, quem injeta `ObjectMapper` recebe o mesmo bean, e agora as três
saídas (fila, Firehose, auditoria) compartilham uma configuração só.

### Diferenças de API que a migração encontrou

- Mapper é **imutável**: configuração só via `builder()`.
- `JavaTimeModule` **não existe mais** — suporte a `java.time` é embutido no databind 3
  (`tools/jackson/databind/ext/javatime/`).
- `WRITE_DATES_AS_TIMESTAMPS` e `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` saíram de
  `Serialization/DeserializationFeature` para `tools.jackson.databind.cfg.DateTimeFeature`
  (que implementa `DatatypeFeature`, então entram no `builder().disable(...)`).
- `setSerializationInclusion` → `changeDefaultPropertyInclusion(UnaryOperator<JsonInclude.Value>)`.
  **Isso fecha um dos dois itens de depreciação do backlog.**
- Exceções viraram **unchecked** (`JacksonException extends RuntimeException`). O `catch` no
  `FirehoseBatchClient` deixou de ser obrigatório e ganhou comentário explicando por que fica.

### As duas stacks coexistem — verificado, não presumido

Jackson 2 continua no classpath para o logstash-logback-encoder (que serializa os logs). A dúvida
era o pacote `com.fasterxml.jackson.annotation`, comum às duas versões.

Resolvido: **`jackson-annotations` 2.21 já contém `JsonSerializeAs`**, a anotação que o
jackson-databind 3.1.0 exige. Um único jar de annotations serve às duas stacks — não há conflito
de pacote. Isso também valida a escolha de `Fluxo` e `PayloadLog` usarem esse pacote.

### Verificação em JVM real

Compilação limpa, e dois probes executados com **as duas stacks no mesmo classpath**:

```
e' ObjectMapper?      : true
NON_NULL + datas ISO  : {"presente":"x","data":"2026-07-28T10:30:00","instante":"1970-01-01T00:00:00Z"}
campo desconhecido    : OK -> PedidoEvent[idOperacao=42, fluxo=PUBLICA_SQS]
enum desconhecido     : fluxo=null
validar()             : PedidoInvalidoException
```

- `NON_NULL` aplicado (campo `ausente` omitido) e datas em ISO-8601, **sem** `JavaTimeModule`.
- `FAIL_ON_UNKNOWN_PROPERTIES` desabilitado de fato.
- **A tolerância de enum do bloco 1 sobrevive à migração**: `@JsonCreator` no `Fluxo` continua
  devolvendo `null` para valor desconhecido, e `validar()` lança `PedidoInvalidoException`.
- O `Log`/`PayloadLog` segue serializando igual sob o Jackson 2 do encoder.

### Armadilha do harness de build (custa uma hora se redescoberta)

O script que monta o classpath do `~/.m2` pega "a maior versão de cada artefato" — mas ordenando
**string**, `2.8.9` ganha de `2.21`. Isso trazia `jackson-annotations` 2.8.9 e o Jackson 3
quebrava em runtime com `NoClassDefFoundError: JsonSerializeAs`, o que parece defeito do código e
não é. Ordenar por segmento numérico (cada trecho preenchido com zeros à esquerda).

---

## Bloco 5 — CONCLUÍDO (não commitado) — shutdown gracioso e backpressure (itens 8, 45)

Sessão **2026-07-28**. **O item 43 (idempotência) NÃO foi feito** — ver "decisão pendente" abaixo.

| Arquivo | Mudança |
|---|---|
| `infrastructure/config/MdcAwareExecutor.java` | Semáforo de backpressure; `AutoCloseable` com dreno limitado; `getDelegate()` removido |
| `infrastructure/config/ExecutorProperties.java` *(novo)* | `max-tarefas-em-voo`, `timeout-encerramento-segundos` |
| `infrastructure/config/ExecutorConfig.java` | Bean `ExecutorService` avulso eliminado |
| `resources/application.yml` | `server.shutdown: graceful`, `spring.lifecycle.timeout-per-shutdown-phase`, bloco `app.executor`, item 45 |

### A cadeia de tempos precisa ser crescente

```
executor (20s)  <  timeout-per-shutdown-phase (25s)  <  stopTimeout da task ECS (30s)
```

Se o dreno do executor for maior que a fase de shutdown do Spring, o contexto fecha por cima das
tarefas; se a fase for maior que o `stopTimeout`, o SIGKILL chega antes. Os três valores estão
comentados no `application.yml` justamente porque só fazem sentido juntos.

### Por que o `ExecutorService` deixou de ser bean

Eram dois beans com ciclo de vida sobreposto para um recurso só — o Spring fecharia ambos, em
ordem não garantida. Agora o `MdcAwareExecutor` é dono do executor e o único a drená-lo. Isso
também elimina o `getDelegate()`, que era código morto (parte do item 53).

O `close()` é chamado pelo `destroyMethod` inferido. A ordem funciona porque o container do
listener SQS é um `SmartLifecycle`: ele é parado **antes** da destruição dos beans, então quando o
dreno começa já não entram tarefas novas.

### Backpressure: por que semáforo e não fila limitada

`Executors.newVirtualThreadPerTaskExecutor()` não tem fila para limitar — ele cria uma thread por
tarefa. O teto tem que ficar antes da submissão, e é isso que o semáforo faz: ao atingir o limite,
`execute()` **bloqueia o chamador**, que é a thread do listener. A ingestão desacelera junto com a
publicação, que é o comportamento correto.

Detalhe que dá bug silencioso: a vaga é devolvida no `finally` da tarefa **e** no
`catch (RejectedExecutionException)`. Sem o segundo, uma tarefa rejeitada durante o shutdown
vazaria a vaga permanentemente.

### Correção da severidade do item 8

A revisão dizia "executor de virtual threads é ilimitado (sem backpressure)" como se fosse
acúmulo livre. Na prática o `maxConcurrentMessages=10` do listener já limitava as mensagens em
voo. O acúmulo real é mais sutil: a mensagem é confirmada assim que a tarefa de auditoria é
*submetida*, não executada — então com Firehose lento as tarefas se acumulam mesmo com o listener
limitado. O teto continua necessário, mas pela razão certa.

### Verificação

- Compilação limpa.
- `application.yml` parseado com snakeyaml — todas as chaves novas resolvem no caminho esperado,
  e `management.endpoints.web.exposure.include` segue íntegro após a correção do item 45.
- **Não verificado em runtime:** o comportamento do dreno e do semáforo sob carga real. Precisa de
  teste de integração (item 37, adiado) ou de uma subida com LocalStack.

---

## Bloco 6 — CONCLUÍDO (não commitado) — rodar fora da AWS (itens 10, 44)

Sessão **2026-07-28**. Escolhido primeiro **não** por ser o mais grave, mas por destravar todo o
resto: enquanto o projeto não sobe localmente, tudo é verificado só por compilação e probe
isolado — que é a situação desde o bloco 1.

| Arquivo | Mudança |
|---|---|
| `adapters/outbound/FirehoseClientConfig.java` | Credenciais/região dos beans do awspring; `endpointOverride`; `overrideConfiguration` |
| `adapters/outbound/FirehoseProperties.java` | `endpoint`, `apiCallTimeoutSegundos`, `apiCallAttemptTimeoutSegundos`, `maxTentativasSdk` |
| `resources/application-{local,dev,hom,prod}.yml` *(novos)* | Perfis por ambiente |
| `docker-compose.yml` *(novo, raiz)* | LocalStack |
| `localstack/init/01-recursos.sh` *(novo)* | Provisiona filas, DLQ com `redrivePolicy` e delivery streams |
| `.gitattributes` *(novo, raiz)* | `eol=lf` para `.sh`, Dockerfile, yml, tf |
| `.dockerignore` | Exclui `docker-compose.yml` e `localstack/` |

### O que estava errado no cliente Firehose

Não existe starter do Spring Cloud AWS para o Firehose, então o cliente é montado à mão — e ficava
de fora de tudo que o awspring configura. Daí as três correções:

- **Credenciais e região agora vêm dos beans do awspring** (`AwsCredentialsProvider`,
  `AwsRegionProvider`), não de `@Value`. Antes a região saía direto da property e as credenciais
  caíam na cadeia default do SDK — podendo divergir do que o SQS usava na mesma aplicação.
  (Reduz também o item 41.)
- **`endpointOverride`** condicional a `app.firehose.endpoint`.
- **`overrideConfiguration`** com `apiCallTimeout`, `apiCallAttemptTimeout` e teto de tentativas.
  Sem `apiCallTimeout`, o `join()` do publicador podia segurar uma thread do listener
  indefinidamente — o item 9 fica menos grave por consequência, embora o bloqueio em si permaneça.

Vale registrar a distinção, porque são dois retries diferentes e o nome confunde:
`app.firehose.max-tentativas` reenvia os **registros rejeitados dentro de uma resposta 200**;
`max-tentativas-sdk` é o retry de transporte do próprio SDK.

### Por que um `docker-compose.yml` e não só os perfis

Só criar `application-local.yml` deixaria o item 44 nominalmente resolvido e praticamente igual: o
perfil apontaria para um LocalStack que ninguém tem. O compose mais o script de init são o que
tornam `docker compose up -d && ./mvnw spring-boot:run` verdadeiro.

O script provisiona a `pedido_queue` **com `redrivePolicy` e DLQ**, espelhando o pré-requisito que
o bloco 1 declarou. Assim o caminho de poison pill passa a ser exercitável localmente — hoje ele é
a única proteção contra reentrega infinita e nunca foi observado rodando.

### Armadilha de plataforma que teria queimado tempo

`core.autocrlf=true` (default em muita instalação Windows) converte LF em CRLF **no checkout**. O
`01-recursos.sh` iria para o container Linux com CRLF e falharia com `$'\r': command not found` —
erro que não aponta para a causa. Daí o `.gitattributes` na raiz fixando `eol=lf`.

### Verificação

- Compilação limpa.
- **Nomes de propriedade conferidos contra o `spring-configuration-metadata.json` do awspring
  4.0.0**, não contra memória: `spring.cloud.aws.endpoint`,
  `spring.cloud.aws.credentials.access-key` e `.secret-key` existem. Property errada aqui falharia
  em silêncio — o perfil local simplesmente não funcionaria.
- API do SDK conferida no bytecode: `apiCallTimeout`, `apiCallAttemptTimeout` e a sobrecarga
  `retryStrategy(Consumer<RetryStrategy.Builder>)` com `maxAttempts(int)`.
- Os 6 YAML (incluindo o compose) parseiam com snakeyaml.
- `bash -n` no script de init: sintaxe válida.
- **NÃO EXECUTADO.** O Docker Desktop continua travado desde o bloco 2
  (`metadata.db: input/output error`), então o LocalStack não subiu. O fluxo ponta a ponta segue
  sem observação nenhuma.

---

## Bloco 7 — CONCLUÍDO (não commitado) — arquitetura, configuração, pom e documentação

Sessão **2026-07-28**. Fecha 26 itens: 11, 12, 13, 15–21, 27, 33, 34, 38, 40–42, 46–54 e a
depreciação do `FeignConfig`.

### Itens 12 e 13 — a regra de dependência

Era o defeito mais caro da lista: um template cujo propósito é ensinar arquitetura hexagonal
tinha a dependência apontando para fora.

Três portas novas em `application/ports/outbound` — `MetricasPort`, `ExecutorAssincronoPort`,
`AuditoriaPort` — e os adaptadores correspondentes em `infrastructure/adapters/outbound`.

Detalhe que quase passou: `MetricsConfig.getTimer()` devolvia um `io.micrometer...Timer`, então
mesmo "usando uma porta" o Micrometer atravessaria a fronteira. Por isso
`MetricasPort.registrarTempo(nome, acao, tags)` recebe a ação em vez de devolver o cronômetro.

**Pacote `shared` (novo).** Log é preocupação transversal: em `infrastructure` obrigava
`domain`/`application` a importar a camada de fora só para logar. As alternativas eram piores —
porta injetada obrigaria a passar um logger por construtor em toda classe, por um ganho de
testabilidade que ninguém exerce. `shared` é usado por todas as camadas e não depende de nenhuma.

**`AuditoriaContext` saiu de `domain`.** Era singleton estático mutável com `ThreadLocal`, `MDC` e
`ObjectMapper` num pacote que deveria ser puro. Virou `AuditoriaContextAdapter` atrás de
`AuditoriaPort`. E `EventoAuditoria.detalhes` virou `Map<String,Object>` em vez de `String` de JSON
pré-serializado — era a serialização que obrigava o domínio a conhecer um mapper; agora quem
serializa é o publicador, que já tem o mapper e sabe o formato do destino.

**Verificação (0 violações):**

```
grep -rn "import ...infrastructure" domain/ application/   → vazio
grep -rn "import ...(infrastructure|application)" domain/  → vazio
```

Resta **uma** exceção, consciente e documentada no ADR-0003: `Fluxo` importa `@JsonCreator`. A
tolerância a enum desconhecido precisa estar no próprio enum porque a desserialização acontece
antes do listener (ADR-0001). É anotação, não acoplamento comportamental.

### Itens 15–21 — nomes que mentiam

- **15.** `MetricsConfig` → `MicrometerMetricasAdapter`, em `adapters/outbound`. Não era
  `@Configuration`, não declarava bean e não configurava nada: era um adaptador com estado.
  `LoggerConfig` virou `LoggingProperties` (só dados) + `LoggingConfig` (o efeito colateral).
- **16.** `SqsListenerConfig` e `SqsMdcInterceptor` saíram do pacote `logging`.
- **17.** `PedidoQueueErrorHandler` → `SqsErrorHandler`. Era registrado na factory e valia para
  **qualquer** listener, mas logava "fila pedido" — diagnóstico errado garantido assim que o
  segundo listener existisse.
- **18.** A sobrecarga `publicar(List<Pedido>)` foi removida. O defeito era sutil: a interface
  trazia um `default` que iterava chamando `publicar(Pedido)`, enquanto o `FirehoseBatchPublicador`
  sobrescrevia na **direção oposta**. Qualquer chamada atravessava a outra sobrecarga e nenhuma
  das duas era a implementação de verdade. Nada usava a versão em lote.
- **19.** `Pedido` virou `record`. `marcarComoProcessado()` alterava estado que ninguém lia — a
  instância era descartada em seguida — e `equals`/`hashCode` escritos à mão nunca foram usados.
- **20.** Log duplicado resolvido por atribuição de responsabilidade: o listener registra o
  recebimento, a fachada registra o desfecho, o caso de uso não loga sucesso. Eram 4 logs por
  mensagem, agora são 2.
- **21.** `ProcessarPedidoUseCasePortImpl` → `ProcessarPedidoService`.

### Itens 33, 11, 27, 34 — o pom

Removidos por não terem **nenhum** uso: `starter-sns`, `starter-dynamodb`, `resilience4j-spring-boot3`
(que ainda por cima é o artefato para Boot 3, rodando sob Boot 4), `spring-boot-starter-aspectj`
(existia só para servi-lo), `micrometer-registry-prometheus` (dois registries exportando cada
métrica duas vezes, sem scraper nesta topologia), `spring-boot-starter` (redundante com `-web`),
e as properties `aws-crt.version` e `localstack.version`.

Adicionados: `maven-enforcer` (trava Java 25 e `dependencyConvergence`), `maven-failsafe`,
`jacoco:check` e `cyclonedx` para SBOM.

Duas escolhas que merecem registro:

- **`jacoco:check` com mínimo `0.00`.** Não é desistência: é o goal instalado e funcionando, com
  o valor no único número que não quebra um projeto sem testes. Subir junto com a suíte.
- **CycloneDX sim, owasp-dependency-check não.** O owasp exige download da base NVD, que não
  funciona em rede fechada e tornaria o build dependente de um serviço externo. O CycloneDX lê a
  árvore que o Maven já resolveu, offline. Item 27 fica **parcialmente** aberto: há inventário,
  não há checagem automática de CVE.

### Itens 38, 41, 42, 46 — configuração

- **38/41.** `@Validated` + `@NotBlank`/`@Min` nas properties. `FeignConfig` deixou de usar
  `@Value` em campo (novo `FeignHttpProperties`), e o `AuditoriaContextAdapter` também.
  Armadilha encontrada no caminho: `app.auditoria.ativa` é aninhado no yml e **não** faz binding
  com um campo `auditoriaAtiva` — precisou de classe aninhada em `AppProperties`.
- **42.** Probes de liveness/readiness. E o health check do Terraform e do Dockerfile passaram a
  apontar para `/actuator/health/readiness`: com o `/health` agregado, durante o warm-up a
  resposta é DOWN, o ECS entende container morto e reinicia — em loop, sem a aplicação nunca ter
  subido.
- **46.** `spring.threads.virtual.enabled: true`.

### Itens 47–53 — detalhes

- **47.** `MdcHelper.mdcOrNew` agora **grava** o id novo no MDC. Antes só devolvia um UUID sem
  registrá-lo: a mensagem publicada levava um correlation id que não existia em nenhum log —
  inútil exatamente para o que o id serve.
- **48.** `MdcKeys` centraliza as chaves. E o `Logger` passou a **ler** `SiglaAppOrigem` do MDC,
  caindo na sigla própria só como default; antes usava sempre a própria, o que tornava o campo
  inútil (ele existe para identificar quem chamou).
- **49.** `StackWalker` só em WARN/ERROR. A origem no código serve para localizar falha; num INFO
  por mensagem consumida ela custa sem pagar.
- **50.** `SqsMdcInterceptor` faz **uma** passagem pelos headers em vez de quatro varreduras
  lineares com `equalsIgnoreCase`.
- **51.** `Clock` injetado; `Instant` no lugar de `LocalDateTime`; `DateTime` do log em ISO-8601.
  O formato anterior (`dd-MM-yyyy HH:mm:ss.SSS`) não era ordenável lexicograficamente nem
  carregava fuso.
- **52.** O `MDC.clear()` foi mantido, com o porquê escrito: o delegate não é compartilhado — cada
  tarefa roda numa virtual thread criada por este executor, não há contexto de terceiros a
  preservar.
- **53.** `EVENTO_EM_PROCESSAMENTO` (que ninguém emitia), `getDelegate()` e `HELP.md` removidos.

### Item 54 — a documentação

Para um template que é fonte de verdade de um agente gerador, a documentação **é** o produto.
Criados `README.md`, `CLAUDE.md`, `.editorconfig`, `CODEOWNERS` e quatro ADRs em `docs/adr/`:
DLQ pela redrivePolicy, Jackson 3, regra de dependência, payload de log tipado.

O `CLAUDE.md` lista as sete regras que não podem ser quebradas por quem editar o template — todas
com o link para o ADR que explica o porquê.

### ⚠️ Mudanças visíveis fora da aplicação

Estas alteram contrato observável e merecem conferência antes do merge:

1. **Formato do campo `DateTime` do log** mudou para ISO-8601. Se algum parser no Datadog/Splunk
   assumir `dd-MM-yyyy`, ele quebra.
2. **`EventoAuditoria.detalhes`** deixou de ser string de JSON e virou objeto aninhado no payload
   do Firehose. Consumidor que fazia parse duplo precisa parar de fazer.
3. **Health check do ECS** aponta para `/actuator/health/readiness`, não mais `/actuator/health`.
4. **`micrometer-registry-prometheus` removido:** `/actuator/prometheus` deixa de existir.

### Verificação

- Compilação limpa. A única nota do compilador é o uso de preview feature (o `_`), que é Java 22+
  e só aparece por causa do contorno com JDK 21.
- Regra de dependência: **0 violações** nas duas direções.
- `pom.xml` é XML válido; `application.yml` parseia.
- **A depreciação do `FeignConfig` sumiu** — os dois itens de depreciação do backlog estão fechados.
- **Não executado.** Nada disso subiu: sem Docker, sem contexto Spring, sem teste. O risco
  concentrado está no wiring de beans, que só um `contextLoads` pega.

---

## Bloco 8 — CONCLUÍDO (não commitado) — idempotência e testes (itens 43 e 37)

Sessão **2026-07-28**. Fecha os dois últimos itens estruturais.

### Item 43 — idempotência sobre DynamoDB

Escolhido DynamoDB por três razões concretas: a escrita condicional
(`attribute_not_exists`) é **atômica** e resolve a corrida entre duas tasks recebendo a mesma
duplicata; o TTL nativo remove os registros sem job de limpeza; e não há cluster para operar,
ao contrário de um Redis.

| Arquivo | Papel |
|---|---|
| `application/ports/outbound/IdempotenciaPort` | Protocolo de três passos |
| `adapters/outbound/DynamoDbIdempotenciaAdapter` | `PutItem` condicional + TTL |
| `adapters/outbound/DynamoDbClientConfig` | Cliente síncrono, mesmo padrão do Firehose |
| `config/IdempotenciaProperties` | Tabela, TTLs, endpoint |
| `infra/terraform/dynamodb.tf` *(novo)* | Tabela PAY_PER_REQUEST com TTL |

**Por que três passos e não um "já vi esta chave?".** Marcar antes e não desmarcar em caso de
falha é o modo de falha mais perigoso possível: a reentrega encontraria a chave marcada, seria
descartada como duplicata, e a mensagem **sumiria em silêncio** — sem DLQ, sem log de erro, sem
métrica. Perda de dado disfarçada de idempotência. Daí `tentarIniciar` / `concluir` / `liberar`,
com `concluir` **depois** da publicação e `liberar` no `catch`.

A marca provisória tem TTL curto (300s) como rede de segurança para o processo morrer entre
iniciar e concluir; a definitiva tem TTL longo (72h), cobrindo a janela em que uma duplicata
ainda pode chegar.

**A chave inclui o fluxo** (`pedido#<id>#<fluxo>`): a mesma operação pode legitimamente ser
publicada em fluxos diferentes, e usar só o id descartaria a segunda.

Nota de infraestrutura registrada no `dynamodb.tf`: a task role precisa de `dynamodb:PutItem` e
`dynamodb:DeleteItem`. As policies vivem nos JSON de `iamsr/policy/`, fora do alcance desta
revisão — **sem isso a aplicação sobe e falha na primeira mensagem** com `AccessDeniedException`.

### Item 37 — testes

**30 testes unitários, todos passando.** Executados de verdade, não só compilados.

| Arquivo | Cobre |
|---|---|
| `arquitetura/RegraDeDependenciaTest` | A regra do ADR-0003, nas três direções |
| `domain/pedido/PedidoEventTest` | `validar()`, tolerância de enum, invariantes de `Pedido` |
| `application/ProcessarPedidoServiceTest` | Roteamento, fluxo ausente, chave duplicada, `Clock` |
| `application/ProcessarPedidoFacadeTest` | **Ordem** das operações de idempotência |
| `infrastructure/FirehoseBatchClientTest` | Particionamento (501 registros, >4 MiB), retry parcial |
| `PedidoFluxoCompletoIT` | `contextLoads` + idempotência contra LocalStack |

**A regra de arquitetura foi verificada sem ArchUnit**, com varredura de imports em ~40 linhas.
ArchUnit expressaria mais e é a evolução natural — mas não está disponível nesta máquina, e a
regra mais importante do template não podia depender de uma biblioteca estar presente para ser
verificável. Trocar quando houver acesso ao Artifactory.

**O `ProcessarPedidoFacadeTest` é o que mais paga.** Ele testa a *ordem* — concluir depois de
processar, liberar em caso de falha, reentrega funcionando após falha — que é exatamente o que
separa "não duplica" de "some sem deixar rastro", e o que não dá para ver lendo o código.

`jacoco.cobertura.minima` continua em `0.00`: com 30 testes a cobertura real ainda está longe do
gate `Sonar-90`, e travar o build agora atrapalharia mais do que ajudaria. Subir conforme a suíte
crescer.

### Como os testes foram executados aqui

Sem Maven funcional, escrevi um launcher do JUnit Platform no scratchpad
(`RunTests.java`) e rodei com o JDK 21 sobre o classpath do `~/.m2`. Duas armadilhas:

- o classpath ad-hoc traz JUnit 6.0.3 e o `junit-platform-launcher` disponível é 1.10.5 —
  precisa pôr o conjunto alinhado (5.10.5/1.10.5) **antes** no classpath;
- o engine `junit-vintage` é descoberto automaticamente e falha; filtrar com
  `EngineFilter.includeEngines("junit-jupiter")`.

O `PedidoFluxoCompletoIT` **compila mas não foi executado** — exige Docker.

---

## Backlog — numeração da revisão original

### Testes (adiado a pedido do usuário — retomar por aqui)

- [~] **37.** ~~Zero testes~~ — **30 unitários, todos passando** (bloco 8), cobrindo roteamento,
  fluxo ausente, chave duplicada, invariantes de `Pedido`, `validar()`, particionamento e retry
  parcial do Firehose, e a ordem das operações de idempotência. Regra hexagonal travada por teste
  (sem ArchUnit — ver bloco 8).
  Aberto: o `PedidoFluxoCompletoIT` compila mas não rodou (exige Docker), o fluxo
  fila → Firehose e o caminho DLQ ainda são placeholder, e a cobertura está longe do `Sonar-90`.

### Segurança

- [x] **22.** ~~Payload completo em log INFO, sem masking~~ — feito (bloco 3). O diagnóstico
  original estava incompleto em dois pontos: não há PII no template hoje (o risco é o default
  herdado pelos projetos gerados), e faltavam dois call sites piores, em
  `PedidoQueueErrorHandler`, que logavam o corpo cru da mensagem.
- [x] **23.** ~~`settings.xml` versionado com 9 blocos `<password>`~~ — feito (bloco 2). Os valores
  eram os literais `USER`/`PASS`, não segredos reais; o risco era ensinar o padrão. Continua
  versionado de propósito: o `.iupipes.yml` o referencia em `build.settings-path`.
- [x] **24.** ~~Container roda como root; JDK duplicado~~ — feito (bloco 2), pendente de
  validação em runtime.
- [~] **25.** Credenciais AWS como build ARGs; `FROM amazon/aws-cli:latest` (tag mutável).
  Parcial — virou `ARG AWS_CLI_VERSION`, ainda `latest`. Ver bloco 2.
- [~] **26.** Agente Datadog sem pin nem checksum. Parcial — virou `ARG DD_TRACER_URL`.
- [~] **27.** ~~Sem SBOM~~ — CycloneDX adicionado (bloco 7). O `owasp-dependency-check`
  **não** foi: exige download da base NVD, inviável em rede fechada. Falta checagem de CVE.

### Build & Deploy

- [x] **28.** ~~`EXPOSE 2000` vs `server.port: 8006`~~ — feito (bloco 2). Menos grave do que
  registrado: os `tfvars` sobrescrevem `containerPort = 8006` e o health check apontava certo.
- [x] **29.** ~~RAM percentages sem default; `ENV DD_ENV=${ENVIRONMENT}`~~ — feito (bloco 2).
- [x] **30.** ~~`-Ddd.trace.methods` com pacote errado~~ — feito (bloco 2): flag **removida**,
  não corrigida. Corrigir o pacote ligaria tracing método a método no hot path.
- [x] **31.** ~~`COPY app/*.jar` casa dois arquivos~~ — **FALSO POSITIVO**, ver bloco 2.
- [x] **32.** ~~Faltam `HEALTHCHECK`, `-XX:+ExitOnOutOfMemoryError`, `.dockerignore`~~ — feito.
- [x] **33.** ~~Deps mortas/redundantes~~ — feito (bloco 7).
- [~] **34.** ~~Sem `enforcer`, `failsafe`; JaCoCo sem `check`~~ — feito (bloco 7).
  `spotless`/`checkstyle` **não** foram adicionados: reformatariam a base inteira num commit,
  enterrando o diff da revisão. Fazer isolado, depois do merge.
- [x] **35.** ~~`projectPropertiesPath: 'app/'` sem `sonar-project.properties`~~ — feito (bloco 2).
  Resolvido zerando o path, não criando o arquivo: em `java-maven` a config do Sonar vem do
  `pom.xml`, e duas fontes divergiriam em silêncio.
- [x] **36.** ~~`settings.xml` ativa `fe6-compopen`, profile inexistente~~ — feito (bloco 2).

### Arquitetura

Todos fechados no bloco 7 — ver detalhamento acima.

- [x] **12.** ~~`application` importa `infrastructure`~~ — 0 violações, verificado.
- [x] **13.** ~~`AuditoriaContext` em `domain` com `ObjectMapper`/`MDC`, singleton estático~~
- [x] **15.** ~~`MetricsConfig`/`LoggerConfig` com nome e responsabilidade enganosos~~
- [x] **16.** ~~`SqsListenerConfig` no pacote `logging`~~
- [x] **17.** ~~Error handler global logando "fila pedido"~~
- [x] **18.** ~~Sobrecarga com delegação em direções opostas~~
- [x] **19.** ~~`Pedido` decorativo~~ — virou `record`
- [x] **20.** ~~Log duplicado entre facade e use case~~ — de 4 logs por mensagem para 2
- [x] **21.** ~~Sufixo `...PortImpl`~~ — `ProcessarPedidoService`

### Resiliência (restante)

- [x] **8.** ~~Shutdown não-gracioso e executor sem backpressure~~ — feito (bloco 5).
- [x] **9.** ~~`.join()` bloqueia thread de plataforma do listener~~ — resolvido em três frentes:
  `spring.threads.virtual.enabled: true` (bloco 7), `apiCallTimeout` no cliente Firehose para o
  bloqueio ser limitado (bloco 6) e o desembrulho da causa (bloco 1).
- [x] **10.** ~~Cliente Firehose sem `overrideConfiguration`, credentials provider nem endpoint
  override~~ — feito (bloco 6), pendente de execução com LocalStack.
- [x] **11.** ~~Resilience4j é dependência morta~~ — removido (bloco 7), junto com o
  `starter-aspectj` que existia só para servi-lo.

### Configuração

- [x] **38.** ~~`@ConfigurationProperties` sem `@Validated`/`@NotBlank`~~ — feito (bloco 7).
- [x] **40.** ~~`RedisProperties` órfã~~ — removida (bloco 7). A idempotência (43) segue aberta e
  independe dela.
- [x] **41.** ~~Mistura de `@Value` e `@ConfigurationProperties`~~ — feito (bloco 7).
- [x] **42.** ~~Sem probes de liveness/readiness~~ — feito (bloco 7); health check do ECS e do
  Dockerfile repontados para `/actuator/health/readiness`.
- [x] **43.** ~~Sem idempotência~~ — feito (bloco 8), sobre DynamoDB com escrita condicional.
- [x] **44.** ~~Sem perfis por ambiente e sem endpoint override~~ — feito (bloco 6), com
  `docker-compose.yml` + LocalStack para o item ser verdadeiro na prática e não só no papel.
- [x] **45.** ~~`application.yml`: `web:` seguido de linha com espaços soltos~~ — feito (bloco 5).
- [x] **46.** ~~`spring.threads.virtual.enabled` desativado~~ — feito (bloco 7).

### Detalhes de implementação

Todos fechados no bloco 7 — ver detalhamento acima.

- [x] **47.** ~~Correlation id descartado~~ — `mdcOrNew` agora grava o id novo no MDC.
- [x] **48.** ~~Chaves de MDC como strings mágicas~~ — `MdcKeys`; e o `Logger` passou a ler
  `SiglaAppOrigem` do MDC em vez de usar sempre a própria sigla.
- [x] **49.** ~~`StackWalker` em todo log~~ — só WARN/ERROR.
- [x] **50.** ~~4 varreduras lineares por mensagem~~ — uma passagem só.
- [x] **51.** ~~Timestamps inconsistentes, sem `Clock`~~ — `Clock` injetado, `Instant`, ISO-8601.
- [x] **52.** ~~`MDC.clear()` frágil~~ — mantido, com a premissa (delegate não compartilhado) escrita.
- [x] **53.** ~~Código morto~~ — os três removidos.
- [x] **54.** ~~Sem documentação~~ — `README.md`, `CLAUDE.md`, `.editorconfig`, `CODEOWNERS` e 4 ADRs.

### Depreciações sob Boot 4 (descobertas na compilação)

- [x] ~~`PoolingHttpClientConnectionManagerBuilder.setConnectionTimeToLive` — `FeignConfig.java:34`~~
  — resolvida no bloco 7: o TTL migrou para `ConnectionConfig` no HttpClient 5.4.
- [x] ~~`ObjectMapper.setSerializationInclusion` — `JacksonConfig.java:28`~~ — resolvida pela
  migração para Jackson 3 (bloco 4)

---

## Ordem sugerida para retomar

0. **Validar o bloco 2 em runtime** (`docker run`) assim que o Docker Desktop voltar — ver
   "Verificação feita" acima. Bloqueia o commit do bloco 2.
1. ~~Dockerfile/deploy (28–32)~~ — feito no bloco 2
2. ~~Segurança (22–26)~~ — feita; 25 e 26 parciais, 27 (SBOM/owasp) em aberto
3. ~~Decisão Jackson 2 x 3~~ — decidida e aplicada (bloco 4)
4. Shutdown gracioso (8) feito no bloco 5; **falta a idempotência (43)** — precisa da decisão
   sobre onde guardar a chave
5. ~~Rodar fora da AWS (10, 44)~~ — feito no bloco 6
6. ~~Arquitetura, configuração, pom e documentação~~ — feito no bloco 7

7. ~~Idempotência (43) e testes (37)~~ — feito no bloco 8

**O que resta, em ordem:**

1. **Rodar `PedidoFluxoCompletoIT`.** Depende do Docker Desktop voltar. É o `contextLoads` — o
   único teste que pega erro de wiring, e o refactor do bloco 7 mexeu em quase todos os beans.
   **Bloqueia o commit.**
2. **Adicionar `dynamodb:PutItem` e `dynamodb:DeleteItem`** às policies em `iamsr/policy/`.
3. **Completar o IT:** fluxo fila → Firehose e caminho DLQ estão como placeholder.
4. Subir `jacoco.cobertura.minima` conforme a suíte crescer, mirando o gate `Sonar-90`.
5. Trocar o `RegraDeDependenciaTest` por ArchUnit quando houver Artifactory.
6. Residuais: **25**/**26** (pins que dependem do que o Artifactory publica), **27** (checagem de
   CVE; o SBOM já existe), `spotless`/`checkstyle` isolados após o merge.
