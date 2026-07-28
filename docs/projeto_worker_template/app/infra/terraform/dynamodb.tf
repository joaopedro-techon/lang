# Tabela de idempotência do worker.
#
# O SQS entrega ao menos uma vez; esta tabela é o que impede que uma reentrega vire publicação
# duplicada no destino. A chave é gravada com PutItem condicional (attribute_not_exists), que é
# atômico — é ele que serializa duas tasks recebendo a mesma duplicata ao mesmo tempo.

resource "aws_dynamodb_table" "idempotencia" {
  name = "${local.feature_name}-${local.microservice_name}-idempotencia"

  # Sob demanda: a carga acompanha a profundidade da fila, que é justamente o que o autoscaling
  # do serviço faz variar. Capacidade provisionada exigiria dimensionar para o pico.
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "chave"

  attribute {
    name = "chave"
    type = "S"
  }

  # Expiração pelo próprio DynamoDB, sem job de limpeza. O atributo guarda epoch em SEGUNDOS.
  ttl {
    attribute_name = "expiraEm"
    enabled        = true
  }

  point_in_time_recovery {
    # Desligado de propósito: o conteúdo é efêmero por construção (TTL de 72h) e reconstruível —
    # perder a tabela causa reprocessamento, não perda de dado. PITR aqui seria custo sem retorno.
    enabled = false
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.additional_tags, {
    Name = "${local.feature_name}-${local.microservice_name}-idempotencia"
  })
}

# ATENÇÃO: a task role precisa de dynamodb:PutItem e dynamodb:DeleteItem nesta tabela.
# As policies são gerenciadas pelo módulo iamsr, a partir dos JSON em iamsr/policy/ — adicionar
# lá, senão a aplicação sobe e falha na primeira mensagem com AccessDeniedException.
output "tabela_idempotencia" {
  description = "Nome da tabela de idempotência, para injetar em IDEMPOTENCIA_TABELA."
  value       = aws_dynamodb_table.idempotencia.name
}
