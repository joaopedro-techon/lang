# Tópico de destino do fluxo PUBLICA_SNS.
#
# A aplicação recebe o ARN pronto (SNS_PEDIDO_TOPIC_ARN), não o nome do tópico: com o nome, o
# awspring precisaria resolvê-lo chamando CreateTopic, o que exigiria sns:CreateTopic na task role
# e criaria um tópico novo em silêncio se o nome viesse com um typo.

resource "aws_sns_topic" "pedido" {
  name = "${local.feature_name}-${local.microservice_name}-pedido"

  # Sem isto as mensagens ficam em texto claro no serviço. O alias gerenciado da AWS basta aqui:
  # não há requisito de chave própria, e uma CMK adicionaria rotação e custo para gerenciar.
  kms_master_key_id = "alias/aws/sns"

  tags = merge(local.additional_tags, {
    Name = "${local.feature_name}-${local.microservice_name}-pedido"
  })
}

# ATENÇÃO: a task role precisa de sns:Publish neste tópico — e, com a criptografia acima,
# também de kms:GenerateDataKey e kms:Decrypt na chave. Sem as duas, a publicação falha em runtime
# com AccessDeniedException e a mensagem vai para a DLQ.
output "topico_pedido_arn" {
  description = "ARN do tópico SNS, injetado em SNS_PEDIDO_TOPIC_ARN."
  value       = aws_sns_topic.pedido.arn
}
