#!/bin/bash
# Provisiona os recursos que a aplicação espera encontrar no perfil 'local'.
# Executado automaticamente pelo LocalStack quando ele fica pronto.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ENDPOINT="http://localhost:4566"

awslocal() { aws --endpoint-url "$ENDPOINT" --region "$REGION" "$@"; }

echo "==> Criando filas SQS"

# A DLQ precisa existir antes da fila principal: a redrivePolicy referencia o ARN dela.
awslocal sqs create-queue --queue-name pedido_queue_dlq

DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url "$ENDPOINT/000000000000/pedido_queue_dlq" \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

# maxReceiveCount=3: a aplicação NÃO roteia nada para DLQ — ela só deixa de confirmar a mensagem
# em caso de falha, e é esta política que encerra o ciclo. Sem ela, uma mensagem que sempre falha
# é reentregue indefinidamente. Espelha o que o Terraform deve configurar em dev/hom/prod.
awslocal sqs create-queue --queue-name pedido_queue --attributes "$(cat <<JSON
{
  "VisibilityTimeout": "30",
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"${DLQ_ARN}\",\"maxReceiveCount\":\"3\"}"
}
JSON
)"

awslocal sqs create-queue --queue-name publicacao_queue

echo "==> Criando bucket de destino e delivery streams do Firehose"

awslocal s3 mb s3://msdemoworker-firehose

criar_stream() {
  awslocal firehose create-delivery-stream \
    --delivery-stream-name "$1" \
    --delivery-stream-type DirectPut \
    --s3-destination-configuration "RoleARN=arn:aws:iam::000000000000:role/localstack,BucketARN=arn:aws:s3:::msdemoworker-firehose,Prefix=$1/"
}

criar_stream pedido-stream
criar_stream auditoria-stream

echo "==> Criando tabela de idempotencia"

awslocal dynamodb create-table \
  --table-name msdemoworker-idempotencia \
  --attribute-definitions AttributeName=chave,AttributeType=S \
  --key-schema AttributeName=chave,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# TTL: o DynamoDB remove os registros sozinho, sem job de limpeza.
awslocal dynamodb update-time-to-live \
  --table-name msdemoworker-idempotencia \
  --time-to-live-specification "Enabled=true,AttributeName=expiraEm"

echo "==> Recursos prontos:"
awslocal sqs list-queues
awslocal firehose list-delivery-streams
awslocal dynamodb list-tables
