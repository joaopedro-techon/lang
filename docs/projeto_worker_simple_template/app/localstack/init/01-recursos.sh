#!/bin/bash
# Provisiona os recursos que a aplicação espera encontrar no perfil 'local'.
# Executado automaticamente pelo LocalStack quando ele fica pronto.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ENDPOINT="http://localhost:4566"
CONTA="000000000000"

awslocal() { aws --endpoint-url "$ENDPOINT" --region "$REGION" "$@"; }

echo "==> Criando filas SQS"

# A DLQ precisa existir antes da fila principal: a redrivePolicy referencia o ARN dela.
awslocal sqs create-queue --queue-name pedido_queue_dlq

DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url "$ENDPOINT/$CONTA/pedido_queue_dlq" \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

# maxReceiveCount=3: a aplicação NÃO roteia nada para DLQ — ela só deixa de confirmar a mensagem
# em caso de falha, e é esta política que encerra o ciclo. Sem ela, uma mensagem que sempre falha
# é reentregue indefinidamente. Espelha o que o Terraform configura em dev/hom/prod.
awslocal sqs create-queue --queue-name pedido_queue --attributes "$(cat <<JSON
{
  "VisibilityTimeout": "30",
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"${DLQ_ARN}\",\"maxReceiveCount\":\"3\"}"
}
JSON
)"

# Fila de SAÍDA do fluxo PUBLICA_SQS. Precisa ser diferente da de entrada: publicar de volta na
# mesma fila cria um laço em que cada mensagem se reproduz.
awslocal sqs create-queue --queue-name publicacao_queue

echo "==> Criando tópico SNS"

awslocal sns create-topic --name pedido_topic

# Assina uma fila ao tópico para que dê para VER o resultado do fluxo PUBLICA_SNS: sem nenhum
# assinante, a publicação no SNS é aceita e descartada, sem deixar rastro.
SONDA_URL=$(awslocal sqs create-queue --queue-name sns_sonda_queue --query 'QueueUrl' --output text)
SONDA_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url "$SONDA_URL" --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

awslocal sns subscribe \
  --topic-arn "arn:aws:sns:${REGION}:${CONTA}:pedido_topic" \
  --protocol sqs \
  --notification-endpoint "$SONDA_ARN" \
  --attributes RawMessageDelivery=true

echo "==> Criando bucket de destino e delivery stream do Firehose"

awslocal s3 mb s3://msdemoworker-firehose

awslocal firehose create-delivery-stream \
  --delivery-stream-name pedido-stream \
  --delivery-stream-type DirectPut \
  --s3-destination-configuration "RoleARN=arn:aws:iam::${CONTA}:role/localstack,BucketARN=arn:aws:s3:::msdemoworker-firehose,Prefix=pedido-stream/"

echo "==> Recursos prontos:"
awslocal sqs list-queues
awslocal sns list-topics
awslocal firehose list-delivery-streams
