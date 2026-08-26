"""Registro de todos os handlers na aplicação.

A ordem importa: o Telegram entrega cada atualização ao primeiro handler que
a aceitar dentro de um mesmo grupo.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from . import admin, errors, onboarding
from .common import CB_CATEGORIA, CB_CONFIRMAR, CB_DECISAO

PRIVADO = filters.ChatType.PRIVATE


def registrar(application: Application) -> None:
    # --- entrada no grupo -------------------------------------------------
    application.add_handler(ChatJoinRequestHandler(onboarding.on_join_request))

    # --- comandos ---------------------------------------------------------
    application.add_handler(CommandHandler("start", onboarding.on_start, filters=PRIVADO))
    application.add_handler(
        CommandHandler("cancelar", onboarding.on_cancelar, filters=PRIVADO)
    )
    application.add_handler(CommandHandler("status", admin.on_status))
    application.add_handler(CommandHandler("link", admin.on_link))
    application.add_handler(CommandHandler("id", admin.on_id))
    application.add_handler(CommandHandler(["ajuda", "help"], admin.on_ajuda))

    # --- botões -----------------------------------------------------------
    application.add_handler(
        CallbackQueryHandler(admin.on_decisao, pattern=rf"^{CB_DECISAO}:")
    )
    application.add_handler(
        CallbackQueryHandler(onboarding.on_categoria, pattern=rf"^{CB_CATEGORIA}:")
    )
    application.add_handler(
        CallbackQueryHandler(onboarding.on_confirmacao, pattern=rf"^{CB_CONFIRMAR}:")
    )

    # --- respostas às perguntas (sempre por último entre as mensagens) ----
    application.add_handler(
        MessageHandler(PRIVADO & filters.TEXT & ~filters.COMMAND, onboarding.on_resposta)
    )
    # Foto, áudio, figurinha... — sem isto o candidato ficaria sem resposta.
    application.add_handler(
        MessageHandler(PRIVADO & ~filters.TEXT & ~filters.COMMAND, onboarding.on_nao_texto)
    )

    # --- o bot foi adicionado a um grupo ----------------------------------
    application.add_handler(
        ChatMemberHandler(admin.on_bot_adicionado, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    # --- rede de segurança ------------------------------------------------
    application.add_error_handler(errors.on_error)


# Tipos de atualização que o bot precisa receber. `chat_join_request` NÃO vem
# na lista padrão do Telegram — sem declará-lo explicitamente, o evento
# principal do bot nunca chegaria.
#
# `edited_message` fica de fora de propósito: editar uma resposta antiga não
# pode reabrir uma pergunta já respondida.
ALLOWED_UPDATES = [
    Update.MESSAGE,
    Update.CALLBACK_QUERY,
    Update.CHAT_JOIN_REQUEST,
    Update.MY_CHAT_MEMBER,
]
