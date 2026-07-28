FROM amazon/aws-cli:latest as files
ARG AWS_DEFAULT_REGION
ARG AWS_ACCESS_KEY_ID
ARG AWS_SECRET_ACCESS_KEY
ARG AWS_SESSION_TOKEN

RUN mkdir -p /opt/certificates/
RUN aws s3 cp s3://cloudsec-ca-certs-bundle-prod-sa-east-1/ca_bundle.crt /opt/certificates/ca_bundle.crt

FROM docker-remotes.artifactory.prod.aws.cloud.ihf/amazoncorretto:25-alpine

RUN apk --update add openjdk25

ENV TZ=America/Sao_Paulo

# Define variáveis de ambiente para o Datadog
ENV DD_ENV=${ENVIRONMENT}
ENV DD_SERVICE="SIGLA-PRODUTO-APP_NAME"
ENV DD_VERSION="1.0"
ENV DD_LOGS_INJECTION=true
ENV DD_DOGSTATSD_ORIGIN_DETECTION_CLIENT=true
ENV DD_DOGSTATSD_NON_LOCAL_TRAFFIC=true

# Adiciona labels para o Datadog
LABEL com.datadoghq.tags.service="SIGLA-PRODUTO-APP_NAME"
LABEL com.datadoghq.tags.env="dev"
LABEL com.datadoghq.tags.version="1.0"

## Instalacao de agente do DataDog
RUN mkdir -p /opt/datadog/ && \
    wget -O /opt/datadog/dd-java-agent.jar 'https://dtdg.co/latest-java-tracer' && \
    chown -R root:root /opt/datadog/ && \
    chmod -R 774 /opt/datadog/

## Instalacao de certificado no container
RUN apk --update add ca-certificates unzip && apk upgrade --no-cache libcrypto3 libssl3 && apk add --upgrade zlib
COPY --from=files /opt/certificates/ca_bundle.crt /usr/local/share/ca-certificates/ca_bundle.crt
RUN update-ca-certificates

RUN apk add curl

COPY app/*.jar app/app.jar

EXPOSE 2000

ENTRYPOINT exec java \
    -javaagent:/opt/datadog/dd-java-agent.jar \
    -Dio.lettuce.core.jfr=false \
    -XX:InitialRAMPercentage=${INITIAL_RAM_PERCENTAGE} \
    -XX:MaxRAMPercentage=${MAX_RAM_PERCENTAGE} \
    -XX:+UseG1GC \
    -XX:MaxGCPauseMillis=200 \
    -XX:+AlwaysPreTouch \
    -Dspring.profiles.active=${ENVIRONMENT} \
    -Ddd.trace.methods=br.com.itau.SIGLA.*[*] \
    -jar app/app.jar
