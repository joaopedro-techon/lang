# Instruções para agentes neste repositório

Este é um **template**: ele é replicado por um agente gerador para criar novos projetos worker.
Qualquer defeito introduzido aqui é herdado por todo projeto derivado. Trate mudanças com o rigor
de código compartilhado, não de código de aplicação.

## Regras que não podem ser quebradas

1. **A dependência aponta para dentro.** `domain` não importa `application` nem `infrastructure`;
   `application` não importa `infrastructure`. Precisa de algo de fora? Declare uma porta em
   `application/ports/outbound` e implemente o adaptador em `infrastructure`. Ver ADR-0003.

2. **O listener só confirma a mensagem no caminho de sucesso.** Nenhum caminho de falha pode
   chamar `acknowledge()` — é isso que garante a reentrega e, por consequência, a DLQ.
   Ver ADR-0001.

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

## Antes de adicionar dependência

Este pom já teve `starter-sns`, `starter-dynamodb`, `resilience4j` e `micrometer-registry-prometheus`
removidos por não terem uso algum. Dependência morta num template é copiada para todo projeto
gerado e entra na superfície de CVE de cada um. Adicione quando houver o primeiro uso real, no
mesmo commit.

## Verificando uma mudança

O build padrão exige JDK 25 e acesso ao Artifactory interno.

```bash
cd app && ./mvnw verify        # inclui jacoco:check, enforcer e SBOM
docker compose up -d           # LocalStack, para exercitar o fluxo de ponta a ponta
```

Checagem da regra de dependência (deve não retornar nada):

```bash
grep -rn "import com.itau.sg2.custodiaposvenda.infrastructure" \
  app/src/main/java/com/itau/sg2/custodiaposvenda/{domain,application}
```

8. **Não mexa na ordem das operações de idempotência** sem ler o
   `ProcessarPedidoFacadeTest`. `concluir` vem **depois** do processamento e `liberar` no `catch`.
   Inverter faz a mensagem sumir em silêncio numa falha — sem DLQ, sem log, sem métrica.

## Estado conhecido

- **Cobertura abaixo do gate.** `jacoco:check` está com mínimo `0.00` porque a suíte ainda é
  pequena; o pipeline exige `Sonar-90`. Subir o mínimo conforme escrever testes.
- **Build verde não significa integração testada.** O `PedidoFluxoCompletoIT` é
  `@Testcontainers(disabledWithoutDocker = true)`: sem Docker ele é pulado em silêncio. Se o agente
  de CI não tiver Docker, o único teste que valida wiring de beans nunca roda. Confira os testes
  PULADOS no relatório do failsafe.
- **`jacoco.version` é acoplada a `java.version`.** O JaCoCo recusa class file major version que
  não conhece (Java 25 = major 69). Todo bump de JDK exige bump do JaCoCo; o Boot não gerencia
  essa versão.
- O fluxo ponta a ponta e o caminho de DLQ no `PedidoFluxoCompletoIT` são placeholder.
- `RegraDeDependenciaTest` usa varredura de imports em vez de ArchUnit. Trocar quando houver
  acesso ao Artifactory.
- O histórico completo da revisão que produziu o estado atual, com o raciocínio de cada decisão,
  está em `REVISAO-TEMPLATE.md`.
