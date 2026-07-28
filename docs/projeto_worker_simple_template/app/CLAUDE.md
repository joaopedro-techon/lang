# Instruções para agentes neste repositório

Este é um **template**: ele é replicado por um agente gerador para criar novos projetos worker.
Qualquer defeito introduzido aqui é herdado por todo projeto derivado. Trate mudanças com o rigor
de código compartilhado, não de código de aplicação.

O objetivo do projeto é ser um **exemplo legível de arquitetura hexagonal**, com um fluxo curto:

```
SQS → loga a entrada → valida → publica no destino do fluxo → ack
```

Resista a aumentar o escopo. Cada mecanismo novo (banco, cache, retry próprio, batching,
idempotência) precisa se justificar contra o custo de ser copiado para todo projeto derivado.

## Regras que não podem ser quebradas

1. **A dependência aponta para dentro.** `domain` não importa `application` nem `infrastructure`;
   `application` não importa `infrastructure`. Precisa de algo de fora? Declare uma porta em
   `application/ports/outbound` e implemente o adaptador em `infrastructure`. Ver ADR-0003.

2. **O listener só confirma a mensagem no caminho de sucesso.** Nenhum caminho de falha pode
   chamar `acknowledge()` — é isso que garante a reentrega e, por consequência, a DLQ.
   Ver ADR-0001. Pelo mesmo motivo, a fachada **relança** a exceção depois de contá-la.

3. **Não reintroduza roteamento app-side para DLQ.** Foi removido por decisão explícita.
   Ver ADR-0001.

4. **Não passe objeto de domínio para o log.** `Logger` só aceita `PayloadLog`, montado campo a
   campo. Ver ADR-0004.

5. **Não valide no construtor canônico de um record que vem da fila.** A exceção ocorreria dentro
   da desserialização do Jackson, antes do listener, sem acesso ao `Acknowledgement`. Use um
   `validar()` explícito.

6. **`Fluxo` e os nomes de suas constantes são contrato de mensagem.** Renomear quebra produtores
   já publicando.

7. **Timestamps vêm do `Clock` injetado**, não de `Instant.now()`/`LocalDateTime.now()` no
   domínio. Sem isso não há teste determinístico sobre o payload publicado.

8. **`PedidoEvent` (entrada) e `Pedido` (saída) permanecem tipos distintos**, mesmo com campos
   quase iguais. Publicar o próprio evento recebido amarra os dois contratos: o dia em que a
   mensagem de entrada ganhar um campo interno, ele vaza para todos os consumidores.

9. **Um destino novo é uma classe nova.** Implemente `PublicadorPedidoPort`, declare o `Fluxo` e
   pronto — não edite o caso de uso, não crie `switch`, não crie fábrica. Ver ADR-0005.

## Antes de adicionar dependência

Este pom já teve `dynamodb`, `starter-dynamodb`, `resilience4j`, `micrometer-registry-prometheus` e
`aws-crt-client` removidos por não terem uso algum. Dependência morta num template é copiada para
todo projeto gerado e entra na superfície de CVE de cada um. Adicione quando houver o primeiro uso
real, no mesmo commit — foi assim que o `starter-sns` voltou, junto com o `SnsPublicador`.

## Verificando uma mudança

O build padrão exige JDK 25 e acesso ao Artifactory interno.

```bash
cd app && ./mvnw verify        # inclui jacoco:check, enforcer, SBOM e o IT com Testcontainers
docker compose up -d           # LocalStack, para exercitar o fluxo de ponta a ponta
```

Checagem da regra de dependência (deve não retornar nada — o `RegraDeDependenciaTest` faz o mesmo
no build):

```bash
grep -rn "import com.itau.sg2.custodiaposvenda.infrastructure" \
  app/src/main/java/com/itau/sg2/custodiaposvenda/{domain,application}
```

## Estado conhecido

- **Não há testes unitários, por decisão do dono do template.** A validação funcional é o
  `PedidoFluxoCompletoIT`; o `RegraDeDependenciaTest` existe como guarda de arquitetura, não como
  teste de comportamento. Não crie testes unitários sem pedir.
- **Build verde não significa integração testada.** O `PedidoFluxoCompletoIT` é
  `@Testcontainers(disabledWithoutDocker = true)`: sem Docker ele é pulado em silêncio. Se o agente
  de CI não tiver Docker, o único teste que valida wiring de beans nunca roda. Confira os testes
  PULADOS no relatório do failsafe.
- **Cobertura abaixo do gate.** `jacoco:check` está com mínimo `0.00`; o pipeline exige `Sonar-90`.
- **Sem idempotência e sem persistência**, por escopo. SQS é at-least-once: uma reentrega
  republica. É inofensivo neste fluxo e deixa de ser assim que o processamento tiver efeito
  acumulativo.
- **`jacoco.version` é acoplada a `java.version`.** O JaCoCo recusa class file major version que
  não conhece (Java 25 = major 69). Todo bump de JDK exige bump do JaCoCo; o Boot não gerencia
  essa versão.
- `RegraDeDependenciaTest` usa varredura de imports em vez de ArchUnit. Trocar quando houver
  acesso ao Artifactory.
- As policies IAM usam `Resource: "*"`. Restringir aos ARNs reais por ambiente.
- `REVISAO-TEMPLATE.md` é o histórico da revisão que produziu o estado **anterior** ao re-escopo
  (quando havia auditoria, idempotência, executor assíncrono e persistência). Vale como registro de
  raciocínio; não vale como descrição do código de hoje.
