"""Configuração central do bot.

Todos os valores sensíveis (token, IDs de grupo, credenciais do Google) vêm de
variáveis de ambiente. Nenhum segredo é escrito no código-fonte.

Em desenvolvimento local, as variáveis podem ficar em um arquivo `.env`
(veja `.env.example`). Na hospedagem, use o painel de variáveis de ambiente.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Fuso horário usado em todas as datas gravadas na planilha.
# `or` no fim: variável definida em branco também cai no padrão. Sem isso, um
# TIMEZONE vazio derrubaria a data para UTC sem avisar, e toda a coluna de
# data/hora da planilha sairia 3 horas adiantada.
TIMEZONE = os.getenv("TIMEZONE", "").strip() or "America/Sao_Paulo"


class ConfigError(RuntimeError):
    """Configuração ausente ou inválida. A mensagem explica como corrigir."""


def _get(name: str, default: str = "") -> str:
    """Valor da variável, tratando "definida porém vazia" como ausente.

    `os.getenv(nome, padrao)` só devolve o padrão quando a variável não
    existe. Painéis de hospedagem deixam criar variáveis em branco com
    facilidade — e aí o padrão nunca entrava, o que já derrubou um deploy
    com `int('')`. Aqui, vazio equivale a não definida.
    """
    return os.getenv(name, "").strip() or default


def _get_int(name: str, default: int) -> int:
    """Inteiro opcional. Valor inválido vira aviso, não queda do serviço.

    Vale para ajustes acessórios como a porta: derrubar o bot inteiro por
    causa de um número mal digitado seria pior do que seguir com o padrão.
    """
    bruto = _get(name)
    if not bruto:
        return default
    try:
        return int(bruto)
    except ValueError:
        logger.warning(
            "%s=%r não é um número inteiro. Usando o padrão %d.",
            name,
            bruto,
            default,
        )
        return default


def _require(name: str, dica: str = "") -> str:
    valor = _get(name)
    if not valor:
        extra = f" {dica}" if dica else ""
        raise ConfigError(
            f"Variável de ambiente obrigatória ausente: {name}.{extra} "
            "Consulte a seção 'Variáveis de ambiente' do README.md."
        )
    return valor


def _require_int(name: str, dica: str = "") -> int:
    bruto = _require(name, dica)
    try:
        return int(bruto)
    except ValueError as exc:
        raise ConfigError(
            f"{name} deve ser um número inteiro (recebido: {bruto!r}). "
            "IDs de grupo do Telegram são negativos, por exemplo -1001234567890."
        ) from exc


def _extrair_id_planilha(valor: str) -> str:
    """Aceita tanto o ID puro quanto a URL completa do Google Planilhas."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", valor)
    return match.group(1) if match else valor


@dataclass(frozen=True)
class Config:
    """Configuração resolvida e validada da aplicação."""

    # --- Telegram ---
    bot_token: str
    main_group_id: int
    admin_group_id: int

    # --- Google Planilhas ---
    spreadsheet_id: str
    worksheet_name: str
    google_credentials: dict[str, Any]

    # --- Execução / hospedagem ---
    webhook_url: str
    webhook_secret: str
    port: int
    log_level: str

    @property
    def modo_webhook(self) -> bool:
        """True quando há URL pública configurada (hospedagem)."""
        return bool(self.webhook_url)

    @property
    def webhook_path(self) -> str:
        return "/telegram"

    @property
    def service_account_email(self) -> str:
        return self.google_credentials.get("client_email", "(desconhecido)")


def _carregar_credenciais_google() -> dict[str, Any]:
    """Lê as credenciais da Service Account.

    Duas formas são aceitas, nesta ordem de prioridade:

    1. `GOOGLE_CREDENTIALS_JSON` — o conteúdo do JSON colado inteiro na
       variável de ambiente. É a forma usada na hospedagem, onde não é
       possível enviar arquivos.
    2. `GOOGLE_CREDENTIALS_FILE` — caminho para o arquivo .json baixado do
       Google Cloud. Prático para desenvolvimento local.
    """
    bruto = _get("GOOGLE_CREDENTIALS_JSON")
    if bruto:
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                "GOOGLE_CREDENTIALS_JSON não contém um JSON válido. "
                "Cole o conteúdo completo do arquivo da conta de serviço, "
                "das chaves { até } inclusive."
            ) from exc
    else:
        caminho = _get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        arquivo = Path(caminho)
        if not arquivo.is_file():
            raise ConfigError(
                "Credenciais do Google não encontradas. Defina "
                "GOOGLE_CREDENTIALS_JSON (conteúdo do JSON) ou "
                f"GOOGLE_CREDENTIALS_FILE apontando para um arquivo existente "
                f"(procurei em: {arquivo.resolve()})."
            )
        dados = json.loads(arquivo.read_text(encoding="utf-8"))

    faltando = [c for c in ("client_email", "private_key") if c not in dados]
    if faltando:
        raise ConfigError(
            "O JSON da conta de serviço está incompleto — faltam os campos: "
            f"{', '.join(faltando)}. Baixe o arquivo novamente no Google Cloud."
        )
    return dados


def _resolver_webhook_url() -> str:
    """Descobre a URL pública do serviço.

    O Render expõe automaticamente `RENDER_EXTERNAL_URL`. Em outras
    hospedagens, defina `WEBHOOK_URL` manualmente. Sem nenhuma das duas, o bot
    roda em modo polling (ideal para testar na sua máquina).
    """
    url = _get("WEBHOOK_URL") or _get("RENDER_EXTERNAL_URL")
    return url.rstrip("/")


def load_config() -> Config:
    """Monta a configuração, falhando cedo e com mensagem clara."""
    config = Config(
        bot_token=_require(
            "BOT_TOKEN", "É o código que o @BotFather envia ao criar o bot."
        ),
        main_group_id=_require_int(
            "MAIN_GROUP_ID", "ID do grupo principal da comunidade."
        ),
        admin_group_id=_require_int(
            "ADMIN_GROUP_ID", "ID do grupo restrito dos administradores."
        ),
        spreadsheet_id=_extrair_id_planilha(
            _require("SPREADSHEET_ID", "ID ou URL completa da planilha.")
        ),
        worksheet_name=_get("WORKSHEET_NAME", "Solicitações Telegram"),
        google_credentials=_carregar_credenciais_google(),
        webhook_url=_resolver_webhook_url(),
        webhook_secret=_get("WEBHOOK_SECRET"),
        port=_get_int("PORT", 8080),
        log_level=_get("LOG_LEVEL", "INFO").upper(),
    )

    if config.main_group_id == config.admin_group_id:
        raise ConfigError(
            "MAIN_GROUP_ID e ADMIN_GROUP_ID são iguais. O grupo da comunidade e "
            "o grupo dos administradores precisam ser grupos diferentes."
        )
    if config.modo_webhook and not config.webhook_secret:
        logger.warning(
            "WEBHOOK_SECRET não definido. Qualquer pessoa que descubra a URL do "
            "serviço poderá enviar atualizações falsas ao bot. Defina um valor "
            "aleatório nessa variável."
        )
    return config


def configurar_logging(nivel: str = "INFO") -> None:
    """Logging legível, com o ruído das bibliotecas HTTP reduzido."""
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        level=getattr(logging, nivel, logging.INFO),
    )
    for ruidoso in ("httpx", "httpcore", "telegram.ext.ExtBot", "urllib3"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
