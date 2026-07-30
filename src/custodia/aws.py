"""Consulta a AWS pela CLI oficial, para o /infra oferecer opcoes reais.

Por que a CLI e nao o boto3
---------------------------
A CLI ja resolve, sozinha, tudo o que seria trabalhoso replicar: perfis do
`~/.aws/config`, SSO, MFA, `credential_process`, `role_arn` com `source_profile`
e a renovacao de token. O desenvolvedor da area ja tem essa configuracao
funcionando; pedir a ele para configurar credencial de novo (agora para o
boto3) seria pedir para manter duas verdades.

Nada aqui ESCREVE na AWS. Sao todas chamadas de leitura (`list`/`describe`),
usadas so para montar as listas que o wizard mostra. O terraform e que aplica.

Cada funcao devolve estrutura simples (dict/list de str), nunca o JSON cru da
AWS -- assim o wizard nao fica acoplado ao formato de resposta da CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from .ui import console

# Os perfis que a area padronizou, um por ambiente.
PERFIS = {
    "dev": "CUSTODIA-AI-DEV",
    "hom": "CUSTODIA-AI-HOM",
    "prod": "CUSTODIA-AI-PROD",
}

# Regiao usada quando nem o ambiente nem o perfil dizem qual e. E a regiao que
# o proprio template do worker referencia (ECR e Secrets Manager em sa-east-1).
REGIAO_PADRAO = "sa-east-1"

# Consulta na AWS raramente passa disso; o limite existe para o wizard nao
# ficar pendurado num terminal esperando resposta que nao vem.
TIMEOUT = 60

# Trechos que aparecem na saida da CLI quando o handshake TLS falhou na
# VALIDACAO do certificado -- e nao por rede fora do ar ou host errado. So
# esses valem a segunda tentativa: a lista e restrita de proposito, para um
# "connection refused" nunca acabar desligando a verificacao.
_SINAIS_DE_SSL = (
    "certificate_verify_failed",
    "certificate verify failed",
    "sslcertverificationerror",
    "ssl validation failed",
    "unable to get local issuer certificate",
    "self signed certificate",
    "self-signed certificate",
)

# Vira True na primeira falha de TLS. Um proxy que intercepta uma chamada
# intercepta as seguintes -- sem isto o wizard pagaria o erro, o aviso e a
# repeticao a cada consulta. Mesma ideia do `_navegacao_quebrada` no ui.py.
_sem_verificacao_ssl = False


class AwsIndisponivel(RuntimeError):
    """Nao foi possivel consultar a AWS (CLI ausente, perfil errado, sessao expirada)."""


def perfil_do_ambiente(ambiente: str) -> str:
    """Traduz 'dev' no nome do perfil que o dev configurou no ~/.aws."""
    try:
        return PERFIS[ambiente]
    except KeyError:
        raise AwsIndisponivel(f"ambiente desconhecido: {ambiente}") from None


def cli_instalada() -> bool:
    return shutil.which("aws") is not None


def regiao_do_perfil(perfil: str) -> str:
    """Descobre em qual regiao consultar, nesta ordem de precedencia.

    1. `AWS_REGION` / `AWS_DEFAULT_REGION` no ambiente -- se o dev exportou,
       ele quis dizer alguma coisa;
    2. a `region` do proprio perfil no ~/.aws/config;
    3. `REGIAO_PADRAO`.

    Passar `--region` explicitamente em toda chamada resolve o `NoRegion` de
    perfis que nao declaram regiao, e -- mais importante -- torna a regiao
    VISIVEL. Uma regiao errada nao da erro: ela devolve listas vazias, e o
    wizard cairia no modo "digite voce mesmo" sem ninguem entender por que.
    """
    for variavel in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        if os.getenv(variavel):
            return os.environ[variavel]

    try:
        resultado = subprocess.run(
            ["aws", "configure", "get", "region", "--profile", perfil],
            capture_output=True,
            text=True,
            timeout=15,
        )
        configurada = (resultado.stdout or "").strip()
        if resultado.returncode == 0 and configurada:
            return configurada
    except (subprocess.TimeoutExpired, OSError):
        pass  # sem regiao no perfil: cai para o padrao

    return REGIAO_PADRAO


def _chamar(perfil: str, *args: str) -> Any:
    """Roda `aws ... --profile <perfil> --region <regiao> --output json`.

    Se a chamada falhar na validacao do certificado, repete UMA vez com
    `--no-verify-ssl` -- ver `_e_erro_de_ssl`.
    """
    global _sem_verificacao_ssl

    if not cli_instalada():
        raise AwsIndisponivel(
            "a AWS CLI nao esta no PATH. Instale a v2 e configure os perfis "
            f"({', '.join(PERFIS.values())})."
        )

    comando = [
        "aws", *args,
        "--profile", perfil,
        "--region", regiao_do_perfil(perfil),
        "--output", "json",
    ]
    resultado = _rodar(comando, sem_verificar=_sem_verificacao_ssl)

    if (
        resultado.returncode != 0
        and not _sem_verificacao_ssl
        and _e_erro_de_ssl(resultado.stderr or resultado.stdout)
    ):
        _avisar_ssl()
        _sem_verificacao_ssl = True
        resultado = _rodar(comando, sem_verificar=True)

    if resultado.returncode != 0:
        raise AwsIndisponivel(_diagnosticar(perfil, resultado.stderr or resultado.stdout))

    try:
        return json.loads(resultado.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AwsIndisponivel(f"resposta da AWS nao e JSON valido: {exc}") from exc


def _rodar(comando: list[str], sem_verificar: bool = False) -> subprocess.CompletedProcess:
    """Executa a CLI. `sem_verificar` acrescenta o `--no-verify-ssl`."""
    if sem_verificar:
        comando = [*comando, "--no-verify-ssl"]
    try:
        return subprocess.run(
            comando, capture_output=True, text=True, timeout=TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise AwsIndisponivel(f"a AWS demorou mais de {TIMEOUT}s para responder.") from None


def _e_erro_de_ssl(saida: str) -> bool:
    """A chamada morreu validando o certificado do endpoint?

    O caso real e proxy corporativo que reassina o TLS com uma CA propria: o
    certificado que chega e valido, so nao esta no bundle que a CLI carrega.
    Repetir sem verificacao faz a consulta passar, mas desliga a checagem de
    quem esta do outro lado -- por isso e fallback, nunca o padrao, e por isso
    ele avisa em voz alta quando acontece.
    """
    minusculo = (saida or "").lower()
    return any(sinal in minusculo for sinal in _SINAIS_DE_SSL)


def _avisar_ssl() -> None:
    """Diz que a verificacao caiu, e como parar de precisar disso.

    Nada de silencioso aqui: uma consulta sem validar certificado e uma
    consulta em que nao da para provar com quem se falou.
    """
    console.print(
        "\n[yellow]Certificado TLS recusado ao falar com a AWS.[/yellow] "
        "Repetindo com [bold]--no-verify-ssl[/bold] -- vale para as proximas "
        "consultas desta sessao.\n"
        "[dim]Isto desliga a validacao do certificado. Costuma ser proxy da "
        "empresa reassinando o TLS; a correcao definitiva e apontar o CA dele "
        "em AWS_CA_BUNDLE (ou REQUESTS_CA_BUNDLE).[/dim]\n"
    )


def _diagnosticar(perfil: str, saida: str) -> str:
    """Traduz o erro da CLI em algo acionavel.

    A mensagem crua da AWS costuma dizer o que falhou, mas nao o que fazer --
    e aqui a acao quase sempre e a mesma: renovar a sessao daquele perfil.
    """
    texto = (saida or "").strip()
    minusculo = texto.lower()

    if "could not be found" in minusculo and "profile" in minusculo:
        return (
            f"o perfil '{perfil}' nao existe no seu ~/.aws/config. "
            "Configure-o antes de rodar o /infra."
        )
    if "expired" in minusculo or "invalidclienttokenid" in minusculo:
        return f"a sessao do perfil '{perfil}' expirou. Rode 'aws sso login --profile {perfil}'."
    if "noregion" in minusculo or "must specify a region" in minusculo:
        return (
            f"o perfil '{perfil}' nao tem regiao e nao consegui deduzir uma.\n"
            f"Adicione 'region = {REGIAO_PADRAO}' ao perfil no ~/.aws/config, "
            "ou exporte AWS_REGION antes de rodar."
        )
    if "accessdenied" in minusculo or "unauthorized" in minusculo:
        return f"o perfil '{perfil}' nao tem permissao para esta consulta.\n{texto}"
    if "ssl" in minusculo or "certificate" in minusculo:
        # Chegar aqui significa que nem o --no-verify-ssl resolveu, ou que o
        # erro de TLS veio com um texto que o `_e_erro_de_ssl` nao reconhece.
        # Nos dois casos a pista util e a mesma.
        return (
            f"falha de TLS ao falar com a AWS pelo perfil '{perfil}'.\n"
            "Se a sua rede usa proxy com certificado proprio, aponte o CA dele "
            "em AWS_CA_BUNDLE.\n"
            f"{texto}"
        )
    return f"falha ao consultar a AWS com o perfil '{perfil}':\n{texto}"


# ---------------------------------------------------------------------------
# Conferencia dos perfis (roda antes de tudo)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Conferencia:
    """O resultado de checar UM ambiente."""

    ambiente: str
    perfil: str
    ok: bool
    conta: str = ""
    regiao: str = ""
    erro: str = ""

    def linha(self) -> str:
        if self.ok:
            return (
                f"  {self.ambiente:<5} {self.perfil:<18} OK      "
                f"conta {self.conta}  regiao {self.regiao}"
            )
        return f"  {self.ambiente:<5} {self.perfil:<18} FALHOU  {self.erro}"


def perfis_configurados() -> set[str]:
    """Perfis que a CLI enxerga, do `config` E do `credentials`.

    Ler so o ~/.aws/config engana: um perfil declarado apenas no
    ~/.aws/credentials existe e funciona, mas nao aparece la. `aws configure
    list-profiles` junta os dois, que e a unica resposta confiavel.
    """
    if not cli_instalada():
        return set()
    try:
        resultado = subprocess.run(
            ["aws", "configure", "list-profiles"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return set()
    if resultado.returncode != 0:
        return set()
    return {linha.strip() for linha in resultado.stdout.splitlines() if linha.strip()}


def conferir_perfis(ambientes: list[str]) -> list[Conferencia]:
    """Confere TODOS os ambientes escolhidos antes de o wizard perguntar algo.

    Confere ate o fim mesmo depois de uma falha: quem esqueceu de configurar
    um perfil provavelmente esqueceu dois, e e melhor entregar a lista inteira
    de uma vez do que um erro por vez.

    A checagem tem duas partes porque elas falham por motivos diferentes: o
    perfil pode nao existir (erro de configuracao) ou existir e nao autenticar
    (sessao expirada, chave revogada).
    """
    if not cli_instalada():
        return [
            Conferencia(
                ambiente=a,
                perfil=PERFIS.get(a, "?"),
                ok=False,
                erro="a AWS CLI nao esta no PATH.",
            )
            for a in ambientes
        ]

    existentes = perfis_configurados()
    resultados: list[Conferencia] = []

    for ambiente in ambientes:
        perfil = perfil_do_ambiente(ambiente)
        if perfil not in existentes:
            resultados.append(
                Conferencia(
                    ambiente=ambiente,
                    perfil=perfil,
                    ok=False,
                    erro="nao existe no ~/.aws (nem em config, nem em credentials).",
                )
            )
            continue
        try:
            quem = identidade(perfil)
        except AwsIndisponivel as exc:
            resultados.append(
                Conferencia(ambiente=ambiente, perfil=perfil, ok=False, erro=str(exc))
            )
            continue
        resultados.append(
            Conferencia(
                ambiente=ambiente,
                perfil=perfil,
                ok=True,
                conta=quem["account"],
                regiao=quem["regiao"],
            )
        )
    return resultados


def contas_repetidas(resultados: list[Conferencia]) -> dict[str, list[str]]:
    """Ambientes diferentes que caem na MESMA conta.

    Nao e erro -- ha times que usam uma conta so -- mas dev e prod apontando
    para o mesmo lugar costuma ser perfil copiado e nao editado, e o estrago
    disso e escrever infra de producao achando que era dev.
    """
    por_conta: dict[str, list[str]] = {}
    for r in resultados:
        if r.ok:
            por_conta.setdefault(r.conta, []).append(r.ambiente)
    return {conta: ambs for conta, ambs in por_conta.items() if len(ambs) > 1}


# ---------------------------------------------------------------------------
# Consultas usadas pelo wizard
# ---------------------------------------------------------------------------

def identidade(perfil: str) -> dict[str, str]:
    """Confirma que o perfil autentica e diz em qual conta ele caiu.

    E a primeira chamada do fluxo de cada ambiente, de proposito: melhor
    descobrir que a sessao expirou agora do que depois de oito perguntas. E
    mostrar o numero da conta e a unica forma de o dev perceber que o perfil
    de dev aponta para a conta de producao.
    """
    dados = _chamar(perfil, "sts", "get-caller-identity")
    return {
        "account": str(dados.get("Account", "?")),
        "arn": str(dados.get("Arn", "?")),
        "regiao": regiao_do_perfil(perfil),
    }


def listar_clusters_ecs(perfil: str) -> list[str]:
    """Nomes (nao ARNs) dos clusters ECS da conta."""
    dados = _chamar(perfil, "ecs", "list-clusters")
    return sorted(arn.rsplit("/", 1)[-1] for arn in dados.get("clusterArns", []))


def listar_vpcs(perfil: str) -> list[dict[str, str]]:
    """VPCs da conta, com o Name (se houver tag) e o CIDR principal."""
    dados = _chamar(perfil, "ec2", "describe-vpcs")
    vpcs = []
    for vpc in dados.get("Vpcs", []):
        vpcs.append(
            {
                "id": vpc.get("VpcId", ""),
                "nome": _tag_name(vpc) or "(sem tag Name)",
                "cidr": vpc.get("CidrBlock", ""),
            }
        )
    return sorted(vpcs, key=lambda v: v["nome"])


def listar_subnets(perfil: str, vpc_id: str) -> list[dict[str, str]]:
    """Subnets de uma VPC, com AZ e CIDR.

    O CIDR vem junto porque o wizard usa essa mesma lista para montar o
    `service_cidr_blocks` -- sem uma segunda consulta.
    """
    dados = _chamar(
        perfil, "ec2", "describe-subnets", "--filters", f"Name=vpc-id,Values={vpc_id}"
    )
    subnets = []
    for subnet in dados.get("Subnets", []):
        subnets.append(
            {
                "id": subnet.get("SubnetId", ""),
                "nome": _tag_name(subnet) or "(sem tag Name)",
                "az": subnet.get("AvailabilityZone", ""),
                "cidr": subnet.get("CidrBlock", ""),
            }
        )
    return sorted(subnets, key=lambda s: (s["az"], s["id"]))


def listar_filas_sqs(perfil: str) -> list[str]:
    """Nomes das filas SQS da conta (a CLI devolve URLs; ficamos com o nome)."""
    dados = _chamar(perfil, "sqs", "list-queues")
    return sorted(url.rsplit("/", 1)[-1] for url in dados.get("QueueUrls", []))


def listar_secrets(perfil: str) -> list[str]:
    """Nomes dos secrets do Secrets Manager."""
    dados = _chamar(perfil, "secretsmanager", "list-secrets")
    return sorted(s.get("Name", "") for s in dados.get("SecretList", []) if s.get("Name"))


def _tag_name(recurso: dict[str, Any]) -> str:
    for tag in recurso.get("Tags", []) or []:
        if tag.get("Key") == "Name":
            return str(tag.get("Value", ""))
    return ""
