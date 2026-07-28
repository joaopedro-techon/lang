##############################################################################
# Stage 1 — baixa o bundle de certificados corporativos do S3
##############################################################################
# 'latest' e' tag mutavel: o build nao e' reproduzivel e uma mudanca upstream
# quebra o pipeline sem que nada tenha mudado no repositorio. Fixe a versao com
# --build-arg AWS_CLI_VERSION=<tag> assim que houver uma tag suportada.
ARG AWS_CLI_VERSION=latest
FROM amazon/aws-cli:${AWS_CLI_VERSION} AS files

# Credenciais chegam como build-args e ficam apenas neste estagio, que e'
# descartado. NAO mover para o estagio final.
ARG AWS_DEFAULT_REGION
ARG AWS_ACCESS_KEY_ID
ARG AWS_SECRET_ACCESS_KEY
ARG AWS_SESSION_TOKEN

RUN mkdir -p /opt/certificates/ \
    && aws s3 cp s3://cloudsec-ca-certs-bundle-prod-sa-east-1/ca_bundle.crt /opt/certificates/ca_bundle.crt

##############################################################################
# Stage 2 — imagem final
##############################################################################
FROM docker-remotes.artifactory.prod.aws.cloud.ihf/amazoncorretto:25-alpine

# A imagem base JA' contem o JDK 25. Nao instalar openjdk via apk.

# Porta HTTP do actuator. DEVE ser igual a 'task_container_port[0].containerPort'
# nos terraform.tfvars: o health check do ECS e o do Datadog fazem
# curl em localhost:<containerPort>/actuator/health.
ARG SERVER_PORT=8006
ENV SERVER_PORT=${SERVER_PORT}

ENV TZ=America/Sao_Paulo

# Datadog.
# DD_ENV nao e' definido aqui de proposito: ENV e' resolvido em build time e
# 'ENVIRONMENT' so' existe em runtime (injetado pelo ECS), entao o valor sairia
# vazio. O env do tracer vem de -Ddd.env no ENTRYPOINT, resolvido pelo shell.
ENV DD_SERVICE="SIGLA-PRODUTO-APP_NAME" \
    DD_VERSION="1.0" \
    DD_LOGS_INJECTION=true \
    DD_DOGSTATSD_ORIGIN_DETECTION_CLIENT=true \
    DD_DOGSTATSD_NON_LOCAL_TRAFFIC=true

# Labels sao build time. A tag de ambiente efetiva vem de DD_ENV/-Ddd.env em runtime.
LABEL com.datadoghq.tags.service="SIGLA-PRODUTO-APP_NAME"
LABEL com.datadoghq.tags.version="1.0"

## Certificado corporativo e utilitarios (--no-cache evita deixar /var/cache/apk na imagem)
RUN apk --no-cache add ca-certificates curl \
    && apk --no-cache upgrade libcrypto3 libssl3 zlib
COPY --from=files /opt/certificates/ca_bundle.crt /usr/local/share/ca-certificates/ca_bundle.crt
RUN update-ca-certificates

## Agente do DataDog
# 'latest-java-tracer' e' um alias mutavel e sem checksum publicado. Para build
# reproduzivel, aponte DD_TRACER_URL para uma versao fixa no Artifactory, ex.:
#   --build-arg DD_TRACER_URL=https://artifactory.prod.aws.cloud.ihf/artifactory/maven-remote-cache/com/datadoghq/dd-java-agent/<VER>/dd-java-agent-<VER>.jar
ARG DD_TRACER_URL=https://dtdg.co/latest-java-tracer
RUN mkdir -p /opt/datadog/ \
    && wget -O /opt/datadog/dd-java-agent.jar "${DD_TRACER_URL}" \
    && chown -R root:root /opt/datadog/ \
    && chmod -R 755 /opt/datadog/

## Usuario nao-root.
# O modo 755 acima e' obrigatorio: com 774 o "outros" ficava sem bit de execucao
# no diretorio, e um usuario nao-root nao conseguiria atravessa'-lo para carregar
# o -javaagent.
RUN addgroup -S app && adduser -S -G app -h /home/app app

COPY --chown=app:app app/*.jar app/app.jar

USER app

EXPOSE ${SERVER_PORT}

# Redundante no ECS (o modulo Terraform define seu proprio task_health_check),
# mas e' o que torna 'docker run' local observavel. Mesmos tempos do Terraform.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -fsS "http://localhost:${SERVER_PORT}/actuator/health/readiness" || exit 1

# Forma shell + 'exec': o java vira PID 1 e recebe o SIGTERM do ECS, pre-requisito
# do shutdown gracioso. Os ${VAR:-default} sao expandidos pelo shell em runtime.
ENTRYPOINT exec java \
    -javaagent:/opt/datadog/dd-java-agent.jar \
    -Ddd.env=${ENVIRONMENT:-local} \
    -Dio.lettuce.core.jfr=false \
    -XX:InitialRAMPercentage=${INITIAL_RAM_PERCENTAGE:-35} \
    -XX:MaxRAMPercentage=${MAX_RAM_PERCENTAGE:-75} \
    -XX:+UseG1GC \
    -XX:MaxGCPauseMillis=200 \
    -XX:+AlwaysPreTouch \
    -XX:+ExitOnOutOfMemoryError \
    -Dspring.profiles.active=${ENVIRONMENT:-local} \
    -jar app/app.jar

# REMOVIDO: -Ddd.trace.methods=br.com.itau.SIGLA.*[*]
#
# O pacote estava errado (o real e' com.itau.sg2.custodiaposvenda), entao a flag
# nao casava com nada e era inofensiva. Corrigir o pacote LIGARIA de fato o
# tracing metodo a metodo de toda a aplicacao — um span por chamada dentro do
# loop de consumo da fila. O agente ja' instrumenta automaticamente SQS, HTTP e
# Feign, que e' o que da' visibilidade de ponta a ponta.
#
# Se precisar rastrear metodos especificos, liste-os nominalmente, nunca com [*]:
#   '-Ddd.trace.methods=com.itau.sg2.custodiaposvenda.application.usecase.ProcessarPedidoUseCasePortImpl[processar]'
#
# Nota: aspas simples sao obrigatorias — o ENTRYPOINT roda sob shell e os
# caracteres * e [ ] seriam interpretados como glob.
