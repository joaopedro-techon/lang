"""Calcula o bloco `autoscaling` do worker a partir da vazao esperada.

Esta e a unica regra de NEGOCIO nova do /infra, entao ela mora sozinha aqui:
da para ler, testar e discutir sem abrir o resto do wizard.

O modelo
--------
Uma task processa `concorrencia` mensagens ao mesmo tempo, cada uma levando
`tempo_ms`. Logo:

    vazao_por_task = concorrencia / tempo_por_mensagem      [msg/s]

Com isso, o numero de tasks necessarias para dar conta do pico e:

    min_capacity = teto(vazao_alvo / vazao_por_task)

O `min_capacity` e o piso: quantas tasks o servico mantem de pe para aguentar
a carga esperada sem depender de escalar. O `max_capacity` da folga para o que
nao foi previsto (rajada, reprocessamento, uma fila represada).

Os thresholds sao de BACKLOG (mensagens visiveis na fila), nao de CPU: e o
sinal certo para worker de fila. `scale_up.threshold` e quanto de backlog
equivale a `JANELA_DE_ATRASO_S` segundos de trabalho para a frota atual --
ou seja, sobe uma task quando a fila acumula mais do que o servico consegue
drenar naquela janela.

Todos os numeros derivam das tres entradas; nada aqui e chutado em runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Folga sobre o piso calculado. 3x cobre rajada e reprocessamento sem deixar
# a conta de FinOps aberta -- e o mesmo fator que o template ja usava em prod
# (min 3 / max 10).
FATOR_DE_PICO = 3

# Quantos segundos de acumulo na fila toleramos antes de subir uma task.
JANELA_DE_ATRASO_S = 60

# O scale down precisa ser bem mais conservador que o scale up: descer cedo
# demais devolve a fila para uma frota que acabou de nao dar conta. 1/8 do
# limiar de subida deixa uma zona morta larga entre os dois.
DIVISOR_DE_DESCIDA = 8

# Ritmo das decisoes (segundos / periodos de avaliacao). Subir e barato e deve
# ser rapido; descer e arriscado e deve ser lento.
COOLDOWN_SUBIDA_S = 60
COOLDOWN_DESCIDA_S = 1200
PERIODOS_SUBIDA = 1
PERIODOS_DESCIDA = 5


@dataclass(frozen=True)
class Dimensionamento:
    """O resultado do calculo, pronto para virar HCL."""

    min_capacity: int
    max_capacity: int
    threshold_subida: int
    threshold_descida: int
    vazao_por_task: float

    def explicar(self) -> str:
        """Como cada numero saiu -- mostrado na revisao, antes de gravar."""
        return (
            f"vazao por task       : {self.vazao_por_task:.1f} msg/s\n"
            f"    min_capacity         : {self.min_capacity} task(s)\n"
            f"    max_capacity         : {self.max_capacity} task(s)  "
            f"({FATOR_DE_PICO}x o minimo)\n"
            f"    scale_up.threshold   : {self.threshold_subida} msgs de backlog  "
            f"({JANELA_DE_ATRASO_S}s de trabalho da frota)\n"
            f"    scale_down.threshold : {self.threshold_descida} msgs de backlog  "
            f"(1/{DIVISOR_DE_DESCIDA} do limiar de subida)"
        )


def calcular(
    mensagens_por_segundo: int, tempo_ms: int, concorrencia_por_task: int
) -> Dimensionamento:
    """Deriva o autoscaling. Mesmas entradas, mesma saida, sempre.

    Levanta ValueError se alguma entrada for <= 0 -- as tres viram divisor ou
    multiplicador, e um zero aqui produziria um plano de infra sem sentido em
    vez de um erro.
    """
    if mensagens_por_segundo <= 0 or tempo_ms <= 0 or concorrencia_por_task <= 0:
        raise ValueError("vazao, tempo de processamento e concorrencia devem ser > 0.")

    vazao_por_task = concorrencia_por_task / (tempo_ms / 1000)

    min_capacity = max(1, math.ceil(mensagens_por_segundo / vazao_por_task))
    max_capacity = min_capacity * FATOR_DE_PICO

    # O backlog e medido para a frota INTEIRA no piso, nao para uma task: e a
    # frota que vai drenar a fila.
    threshold_subida = max(1, round(vazao_por_task * min_capacity * JANELA_DE_ATRASO_S))
    threshold_descida = max(1, threshold_subida // DIVISOR_DE_DESCIDA)

    return Dimensionamento(
        min_capacity=min_capacity,
        max_capacity=max_capacity,
        threshold_subida=threshold_subida,
        threshold_descida=threshold_descida,
        vazao_por_task=vazao_por_task,
    )
