"""Funções auxiliares pequenas usadas em vários pontos do bot."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .config import TIMEZONE

FORMATO_DATA_HORA = "%d/%m/%Y %H:%M:%S"


def fuso() -> ZoneInfo:
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:  # fuso inválido ou base tzdata ausente
        return ZoneInfo("UTC")


def agora_str() -> str:
    """Data e hora atuais no fuso configurado, prontas para a planilha."""
    return datetime.now(fuso()).strftime(FORMATO_DATA_HORA)


def h(valor: object) -> str:
    """Escapa texto para uso seguro em mensagens com parse_mode=HTML.

    Sem isso, um candidato que respondesse "<b" quebraria a mensagem inteira
    do card administrativo — o Telegram recusa HTML malformado.
    """
    return escape(str(valor if valor is not None else ""), quote=False)


def nome_exibicao(usuario) -> str:
    """Nome legível de um usuário do Telegram (`telegram.User`)."""
    if usuario is None:
        return "usuário"
    partes = [p for p in (usuario.first_name, usuario.last_name) if p]
    return " ".join(partes) or (usuario.username or str(usuario.id))


def encurtar(texto: str, limite: int = 60) -> str:
    texto = str(texto or "")
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"
