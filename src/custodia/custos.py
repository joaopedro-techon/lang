"""Quanto a conta AWS esta custando -- pelo Cost Explorer, via CLI.

O `aws.py` responde "o que existe na conta"; este arquivo responde "quanto isso
esta custando". Sao perguntas diferentes, com uma API diferente (`ce`), mas a
mecanica de falar com a AWS e a mesma -- por isso tudo aqui passa pelo
`aws.chamar`: perfil do ~/.aws, fallback de TLS e diagnostico de erro vem
prontos de la.

Tambem so LE. `ce get-cost-and-usage` e uma consulta; nada aqui muda nada na
conta.

Duas decisoes que valem explicacao, porque um numero de custo errado passa
despercebido bem mais facil que uma lista vazia:

- a janela termina ONTEM. O dia corrente ainda esta sendo fechado pela AWS, e
  incluir ele faria "os ultimos 7 dias" parecerem mais baratos que os 7
  anteriores so porque o ultimo dia esta pela metade;
- a metrica e a `UnblendedCost`, que e o que a AWS efetivamente cobrou no dia,
  ja liquido de credito e reembolso. E o numero que bate com a fatura.

As funcoes devolvem estruturas simples (`Gasto`, `Variacao`) e nao texto: quem
formata para o modelo e o `tools.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .aws import AwsIndisponivel, chamar

# O Cost Explorer nao e regional: a particao inteira atende num endpoint so, em
# us-east-1. Chamar com a regiao do perfil (sa-east-1) resolveria um host que
# nao existe -- e o erro sairia como "could not connect", que nao ajuda ninguem.
REGIAO = "us-east-1"

# O que a AWS cobrou de fato, dia a dia, na conta que consumiu. As alternativas
# respondem outra pergunta: `AmortizedCost` espalha o custo de reserva/Savings
# Plan pelo periodo, e `BlendedCost` so faz sentido em organizacao com varias
# contas rateando. Para "quanto gastei" a resposta e esta.
METRICA = "UnblendedCost"

# O Cost Explorer guarda por volta de 14 meses. Um `dias` maior que isso nao da
# erro util: volta menos dado do que o pedido, sem dizer que truncou.
MAX_DIAS = 366

# Por quais dimensoes da para quebrar o gasto, e o que cada uma responde. O
# dicionario existe para (1) recusar dimensao invalida com uma lista do que
# vale, em vez de deixar a CLI responder um erro cru, e (2) alimentar a
# docstring da ferramenta -- e ela que ensina o modelo a escolher.
DIMENSOES = {
    "SERVICE": "por servico da AWS (RDS, ECS, SQS...)",
    "USAGE_TYPE": "por tipo de uso dentro do servico (a quebra mais fina)",
    "OPERATION": "por operacao da API cobrada",
    "REGION": "por regiao",
    "INSTANCE_TYPE": "por tipo de instancia",
    "RECORD_TYPE": "separa uso, credito, imposto e reembolso",
    "LINKED_ACCOUNT": "por conta, quando o perfil e da conta pagadora",
}

# Teto de paginas do `NextPageToken`. Quebrado por SERVICE cabe em uma; por
# USAGE_TYPE numa conta grande, nao. O limite e para uma resposta paginada sem
# fim nao prender a conversa.
MAX_PAGINAS = 20


@dataclass(frozen=True)
class Periodo:
    """Uma janela de dias. `fim` e EXCLUSIVO, como na API do Cost Explorer."""

    inicio: date
    fim: date

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days

    @property
    def ultimo_dia(self) -> date:
        """O ultimo dia INCLUIDO -- o que se mostra para gente."""
        return self.fim - timedelta(days=1)

    def __str__(self) -> str:
        return f"{self.inicio} a {self.ultimo_dia}"

    def argumento(self) -> str:
        """No formato que a CLI espera em `--time-period`."""
        return f"Start={self.inicio},End={self.fim}"


@dataclass(frozen=True)
class Gasto:
    """Quanto UM grupo (servico, regiao...) custou no periodo."""

    grupo: str
    valor: float


@dataclass(frozen=True)
class Variacao:
    """O mesmo grupo em dois periodos: quanto era, quanto e."""

    grupo: str
    antes: float
    agora: float

    @property
    def delta(self) -> float:
        return self.agora - self.antes

    @property
    def percentual(self) -> float | None:
        """None quando nao havia base de comparacao (o grupo e novo).

        Devolver None em vez de 0 ou infinito e proposital: "subiu 100%" e
        "apareceu agora" sao coisas diferentes, e quem le tem que ver a
        diferenca.
        """
        if self.antes == 0:
            return None
        return (self.delta / self.antes) * 100


def ultimos_dias(dias: int, hoje: date | None = None) -> Periodo:
    """A janela de `dias` completos que termina ONTEM.

    `hoje` e injetavel so para teste; em uso normal e a data da maquina.
    """
    referencia = hoje or date.today()
    dias = max(1, min(int(dias), MAX_DIAS))
    return Periodo(inicio=referencia - timedelta(days=dias), fim=referencia)


def periodo_anterior(periodo: Periodo) -> Periodo:
    """A janela de mesmo tamanho imediatamente antes -- a base da comparacao."""
    return Periodo(inicio=periodo.inicio - timedelta(days=periodo.dias), fim=periodo.inicio)


def por_grupo(
    perfil: str, periodo: Periodo, dimensao: str = "SERVICE"
) -> tuple[list[Gasto], str]:
    """Gasto do periodo somado por dimensao, do mais caro para o mais barato.

    Devolve tambem a moeda que a AWS reportou -- ela vem por linha na resposta,
    e sem carregar junto o numero fica sem unidade.
    """
    if dimensao not in DIMENSOES:
        raise AwsIndisponivel(
            f"dimensao desconhecida: {dimensao}. "
            f"Use uma destas: {', '.join(sorted(DIMENSOES))}."
        )

    totais: dict[str, float] = {}
    moeda = ""
    token = ""

    for _ in range(MAX_PAGINAS):
        argumentos = [
            "ce", "get-cost-and-usage",
            "--time-period", periodo.argumento(),
            # MONTHLY, e nao DAILY: o total do periodo e a soma dos blocos de
            # qualquer jeito, e DAILY multiplicaria a resposta pelo numero de
            # dias sem acrescentar nada a pergunta "quanto custou no total".
            "--granularity", "MONTHLY",
            "--metrics", METRICA,
            "--group-by", f"Type=DIMENSION,Key={dimensao}",
        ]
        if token:
            argumentos += ["--next-page-token", token]

        dados = _consultar(perfil, *argumentos)

        # Um bloco por mes tocado pela janela: quem pediu 60 dias recebe dois, e
        # os dois somam no mesmo grupo.
        for bloco in dados.get("ResultsByTime", []) or []:
            for grupo in bloco.get("Groups", []) or []:
                chave = (grupo.get("Keys") or ["(sem nome)"])[0]
                metrica = (grupo.get("Metrics") or {}).get(METRICA) or {}
                totais[chave] = totais.get(chave, 0.0) + _numero(metrica.get("Amount"))
                moeda = moeda or str(metrica.get("Unit") or "")

        token = str(dados.get("NextPageToken") or "")
        if not token:
            break

    gastos = [Gasto(grupo=g, valor=v) for g, v in totais.items()]
    gastos.sort(key=lambda g: g.valor, reverse=True)
    return gastos, (moeda or "USD")


def comparar(
    perfil: str, atual: Periodo, dimensao: str = "SERVICE"
) -> tuple[list[Variacao], Periodo, str]:
    """O mesmo periodo contra os `dias` anteriores, grupo a grupo.

    Ordena pela variacao ABSOLUTA (do que mais caiu para o que mais subiu), que
    e a ordem util para as duas perguntas que aparecem: "o que caiu" se le no
    inicio da lista, "o que subiu" no fim.

    Grupo que existe so em um dos periodos entra com 0 no outro -- e assim que
    servico desligado (ou recem-criado) aparece, em vez de sumir da conta.
    """
    anterior = periodo_anterior(atual)
    agora, moeda = por_grupo(perfil, atual, dimensao)
    antes, moeda_antes = por_grupo(perfil, anterior, dimensao)

    de_antes = {g.grupo: g.valor for g in antes}
    de_agora = {g.grupo: g.valor for g in agora}

    variacoes = [
        Variacao(grupo=chave, antes=de_antes.get(chave, 0.0), agora=de_agora.get(chave, 0.0))
        for chave in set(de_antes) | set(de_agora)
    ]
    variacoes.sort(key=lambda v: v.delta)
    return variacoes, anterior, (moeda or moeda_antes or "USD")


def total(gastos: list[Gasto]) -> float:
    return sum(g.valor for g in gastos)


def _consultar(perfil: str, *argumentos: str):
    """Chama a CLI na regiao do Cost Explorer, enriquecendo o erro."""
    try:
        return chamar(perfil, *argumentos, regiao=REGIAO)
    except AwsIndisponivel as exc:
        raise AwsIndisponivel(_explicar(str(exc))) from exc


def _explicar(mensagem: str) -> str:
    """Acrescenta ao erro o que e especifico do Cost Explorer.

    O `aws.py` ja traduz o que e generico (sessao expirada, perfil inexistente).
    O que ele nao tem como saber e que "AccessDenied" aqui costuma nao ser
    permissao faltando no usuario, e sim a conta errada: numa conta membro da
    organizacao o Cost Explorer simplesmente nao responde. Sem essa frase, o dev
    passa a tarde revisando politica de IAM.
    """
    minusculo = mensagem.lower()

    if "ce:getcostandusage" in minusculo or "accessdenied" in minusculo or "not authorized" in minusculo:
        return (
            f"{mensagem}\n\n"
            "Consultar custo exige a permissao 'ce:GetCostAndUsage'. Se ela ja "
            "existe, o problema costuma ser a conta: o Cost Explorer responde na "
            "conta pagadora (management account) da organizacao -- numa conta "
            "membro a consulta e negada de qualquer jeito."
        )
    if "datavailable" in minusculo or "data is not available" in minusculo or "not enabled" in minusculo:
        return (
            f"{mensagem}\n\n"
            "O Cost Explorer parece nao estar habilitado nesta conta. Ele se "
            "habilita uma unica vez no console de Billing, e os dados levam ate "
            "24h para aparecer depois disso."
        )
    return mensagem


def _numero(bruto) -> float:
    """O Amount vem como string ('123.45'). Valor ilegivel vira 0, nao excecao.

    Uma linha estranha na resposta nao deveria derrubar o relatorio inteiro --
    ela some do total, e o total sem ela ainda responde a pergunta.
    """
    try:
        return float(bruto)
    except (TypeError, ValueError):
        return 0.0
