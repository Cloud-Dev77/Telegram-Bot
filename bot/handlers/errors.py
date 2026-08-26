"""Tratamento global de erros.

Objetivo: nenhuma exceção inesperada deixa o candidato sem resposta nem passa
despercebida pelos administradores. O bot continua rodando; o incidente vai
para o log e um resumo curto vai para o grupo administrativo.
"""

from __future__ import annotations

import logging
import traceback

from telegram import Update
from telegram.error import Forbidden, NetworkError, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from .. import texts
from ..utils import h
from .common import enviar_html, get_config

logger = logging.getLogger(__name__)

# Falhas transitórias de rede não merecem alarme — o PTB já refaz a chamada.
_SILENCIOSOS = (NetworkError, TimedOut, RetryAfter)

LIMITE_MENSAGEM_TELEGRAM = 3500


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    erro = context.error

    if isinstance(erro, _SILENCIOSOS):
        logger.warning("Falha temporária de rede: %s", erro)
        return

    logger.error("Exceção ao processar uma atualização", exc_info=erro)

    # 1) Não deixar o candidato no vácuo.
    if isinstance(update, Update) and update.effective_user:
        chat = update.effective_chat
        if chat is not None and chat.type == "private":
            try:
                await enviar_html(context.bot, chat.id, texts.ERRO_GENERICO)
            except Forbidden:
                pass
            except Exception:  # nunca falhar dentro do tratador de erros
                logger.debug("Não foi possível avisar o usuário sobre o erro.")

    # 2) Registrar no grupo administrativo, com o contexto mínimo para
    #    diagnóstico (sem despejar o update inteiro, que traz dados pessoais).
    try:
        config = get_config(context)
    except KeyError:
        return

    origem = "desconhecida"
    if isinstance(update, Update):
        usuario = update.effective_user
        origem = f"{usuario.id} (@{usuario.username})" if usuario else "sem usuário"

    trilha = "".join(
        traceback.format_exception(type(erro), erro, erro.__traceback__)
    )[-1200:]

    texto = (
        "🐞 <b>Erro interno do bot</b>\n\n"
        f"Origem: <code>{h(origem)}</code>\n"
        f"Tipo: <code>{h(type(erro).__name__)}</code>\n"
        f"Mensagem: <code>{h(erro)}</code>\n\n"
        f"<pre>{h(trilha)}</pre>"
    )[:LIMITE_MENSAGEM_TELEGRAM]

    try:
        await enviar_html(context.bot, config.admin_group_id, texto)
    except Exception:
        logger.debug("Não foi possível relatar o erro ao grupo administrativo.")
