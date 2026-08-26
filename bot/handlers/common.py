"""Peças compartilhadas pelos handlers: teclados, envio de perguntas e acesso
aos objetos globais guardados em `application.bot_data`.
"""

from __future__ import annotations

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from .. import texts
from ..config import Config
from ..models import Solicitacao
from ..questions import PERGUNTAS, TOTAL_PERGUNTAS
from ..store import Store

logger = logging.getLogger(__name__)

# Prefixos de callback_data. Mantidos curtos: o Telegram limita o campo a 64 bytes.
CB_CATEGORIA = "cat"
CB_CONFIRMAR = "conf"
CB_DECISAO = "adm"


# ---------------------------------------------------------------------------
# Acesso aos objetos globais
# ---------------------------------------------------------------------------


def get_config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.bot_data["config"]


def get_store(context: ContextTypes.DEFAULT_TYPE) -> Store:
    return context.bot_data["store"]


def nome_do_grupo(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.bot_data.get("grupo_nome", "a comunidade")


# ---------------------------------------------------------------------------
# Teclados
# ---------------------------------------------------------------------------


def teclado_opcoes(opcoes: tuple[str, ...]) -> InlineKeyboardMarkup:
    """Um botão por linha — nomes de categoria costumam ser longos."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(opcao, callback_data=f"{CB_CATEGORIA}:{indice}")]
            for indice, opcao in enumerate(opcoes)
        ]
    )


def teclado_confirmacao() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(texts.BOTAO_CONFIRMAR, callback_data=f"{CB_CONFIRMAR}:sim")],
            [InlineKeyboardButton(texts.BOTAO_REFAZER, callback_data=f"{CB_CONFIRMAR}:nao")],
        ]
    )


def teclado_decisao(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    texts.BOTAO_APROVAR, callback_data=f"{CB_DECISAO}:ap:{user_id}"
                ),
                InlineKeyboardButton(
                    texts.BOTAO_RECUSAR, callback_data=f"{CB_DECISAO}:rc:{user_id}"
                ),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Envio de mensagens
# ---------------------------------------------------------------------------


async def enviar_html(bot: Bot, chat_id: int, texto: str, **kwargs):
    """Envio padrão: HTML, sem prévia de link."""
    return await bot.send_message(
        chat_id=chat_id,
        text=texto,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        **kwargs,
    )


async def avancar(bot: Bot, chat_id: int, solicitacao: Solicitacao) -> None:
    """Envia o próximo passo do fluxo: a pergunta atual ou o resumo final."""
    if solicitacao.etapa >= TOTAL_PERGUNTAS:
        await enviar_resumo(bot, chat_id, solicitacao)
        return

    pergunta = PERGUNTAS[solicitacao.etapa]
    teclado = teclado_opcoes(pergunta.opcoes) if pergunta.opcoes else None
    await enviar_html(bot, chat_id, pergunta.pergunta, reply_markup=teclado)


async def enviar_resumo(bot: Bot, chat_id: int, solicitacao: Solicitacao) -> None:
    await enviar_html(
        bot,
        chat_id,
        texts.RESUMO_CONFIRMACAO.format(resumo=solicitacao.resumo_para_candidato()),
        reply_markup=teclado_confirmacao(),
    )


async def notificar_candidato(bot: Bot, user_id: int, texto: str) -> bool:
    """Avisa o candidato no privado. Devolve False se não foi possível.

    Falha é esperada e não é erro: a pessoa pode ter bloqueado o bot ou
    apagado a conversa. O fluxo administrativo segue normalmente.
    """
    try:
        await enviar_html(bot, user_id, texto)
        return True
    except (Forbidden, BadRequest) as exc:
        logger.info("Não foi possível avisar o usuário %s: %s", user_id, exc)
        return False
    except TelegramError as exc:
        logger.warning("Erro ao avisar o usuário %s: %s", user_id, exc)
        return False


async def remover_botoes(query) -> None:
    """Tira os botões de uma mensagem já processada, ignorando falhas."""
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest:
        pass
