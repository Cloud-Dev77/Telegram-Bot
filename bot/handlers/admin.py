"""Painel administrativo: os botões [Aprovar] / [Recusar] e comandos de apoio.

Cuidados implementados aqui, todos vindos de situações reais de operação:

* Cliques duplos e cliques simultâneos de dois administradores — resolvidos
  com uma trava por usuário e verificação de status dentro dela.
* Cards antigos que voltam à tona quando alguém rola a conversa e clica de
  novo — o botão responde explicando quem já decidiu e quando.
* Solicitações que deixaram de existir no Telegram (a pessoa desistiu, entrou
  por outro caminho ou um administrador resolveu direto pela tela do grupo) —
  a planilha é atualizada mesmo assim, e o card explica o que aconteceu.
* Cliques vindos de fora do grupo de administradores são recusados.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from .. import texts
from ..models import STATUS_APROVADO, STATUS_RECUSADO, Solicitacao
from ..utils import h, nome_exibicao
from .common import (
    enviar_html,
    get_config,
    get_store,
    nome_do_grupo,
    remover_botoes,
)

logger = logging.getLogger(__name__)

# Trechos de erro do Telegram que significam "a solicitação não existe mais".
_SOLICITACAO_SUMIU = (
    "hide_requester_missing",
    "user_already_participant",
    "participant_id_invalid",
    "chat member status can't be changed",
)


def _solicitacao_inexistente(exc: BadRequest) -> bool:
    mensagem = str(exc).lower()
    return any(trecho in mensagem for trecho in _SOLICITACAO_SUMIU)


# ---------------------------------------------------------------------------
# Botões de decisão
# ---------------------------------------------------------------------------


async def on_decisao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    config = get_config(context)
    store = get_store(context)
    admin = update.effective_user

    # Só o grupo de administradores pode decidir. Sem isso, qualquer pessoa
    # que encaminhasse o card para outro chat poderia aprovar membros.
    if query.message is None or query.message.chat_id != config.admin_group_id:
        await query.answer("Ação permitida apenas no grupo de administradores.", show_alert=True)
        return

    try:
        _, acao, bruto = query.data.split(":", 2)
        user_id = int(bruto)
    except ValueError:
        await query.answer("Botão inválido.", show_alert=True)
        return

    aprovar = acao == "ap"
    nome_admin = nome_exibicao(admin)

    async with store.lock(user_id):
        solicitacao = store.obter(user_id)

        if solicitacao is None:
            await query.answer(
                "Solicitação não encontrada na planilha.", show_alert=True
            )
            await remover_botoes(query)
            return

        # Já decidida: informa quem decidiu e encerra, sem tocar no Telegram.
        if solicitacao.decidida:
            await query.answer(
                texts.ALERTA_JA_PROCESSADO.format(
                    status=solicitacao.status.lower(),
                    admin=solicitacao.decidido_por or "outro administrador",
                ),
                show_alert=True,
            )
            await remover_botoes(query)
            return

        # A partir daqui a decisão é desta pessoa. Como a trava só é liberada
        # no fim, um segundo clique cai no ramo `decidida` acima.
        aviso_extra = ""
        try:
            if aprovar:
                await context.bot.approve_chat_join_request(
                    chat_id=config.main_group_id, user_id=user_id
                )
            else:
                await context.bot.decline_chat_join_request(
                    chat_id=config.main_group_id, user_id=user_id
                )
            await query.answer(
                texts.ALERTA_APROVADO_OK if aprovar else texts.ALERTA_RECUSADO_OK
            )
        except BadRequest as exc:
            if not _solicitacao_inexistente(exc):
                logger.exception("Falha ao decidir sobre %s", user_id)
                await query.answer(texts.ALERTA_ERRO, show_alert=True)
                await _anexar_ao_card(
                    query,
                    f"\n\n⚠️ <b>Erro do Telegram:</b> {h(exc)}",
                    manter_botoes=True,
                )
                return
            # A solicitação sumiu, mas a decisão administrativa continua
            # valendo e precisa ficar registrada na planilha.
            logger.info("Solicitação de %s não existe mais no Telegram: %s", user_id, exc)
            aviso_extra = texts.CARD_SOLICITACAO_EXPIRADA.format(
                status=STATUS_APROVADO if aprovar else STATUS_RECUSADO
            )
            await query.answer(
                "A solicitação não existe mais no Telegram. Registrei na planilha.",
                show_alert=True,
            )
        except TelegramError as exc:
            logger.exception("Erro de rede ao decidir sobre %s", user_id)
            await query.answer(texts.ALERTA_ERRO, show_alert=True)
            await _anexar_ao_card(
                query, f"\n\n⚠️ <b>Erro:</b> {h(exc)}", manter_botoes=True
            )
            return

        await store.marcar_decisao(solicitacao, aprovar, nome_admin)

    # Fora da trava: avisos que não afetam a consistência do estado.
    avisado = await _avisar_candidato(context, solicitacao, aprovar)
    if not avisado:
        aviso_extra += texts.AVISO_DM_BLOQUEADA

    modelo = (
        texts.CARD_DECIDIDO_APROVADO if aprovar else texts.CARD_DECIDIDO_RECUSADO
    )
    await _anexar_ao_card(
        query,
        modelo.format(admin=h(nome_admin), data_hora=h(solicitacao.decidido_em))
        + aviso_extra,
    )


async def _avisar_candidato(
    context: ContextTypes.DEFAULT_TYPE, solicitacao: Solicitacao, aprovado: bool
) -> bool:
    from .common import notificar_candidato

    modelo = texts.APROVADO if aprovado else texts.RECUSADO
    return await notificar_candidato(
        context.bot,
        solicitacao.user_id,
        modelo.format(grupo=h(nome_do_grupo(context))),
    )


async def _anexar_ao_card(query, adicional: str, manter_botoes: bool = False) -> None:
    """Reescreve o card mantendo o conteúdo original e removendo os botões."""
    original = query.message.text_html if query.message else ""
    teclado = query.message.reply_markup if manter_botoes else None
    try:
        await query.edit_message_text(
            text=(original or "") + adicional,
            parse_mode=ParseMode.HTML,
            reply_markup=teclado,
            disable_web_page_preview=True,
        )
    except BadRequest as exc:
        # "Message is not modified" e mensagens antigas demais são inofensivos.
        logger.info("Não foi possível atualizar o card: %s", exc)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


async def on_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = get_config(context)
    store = get_store(context)

    if update.effective_chat.id != config.admin_group_id:
        await update.effective_message.reply_text(texts.APENAS_ADMIN)
        return

    contagem = store.estatisticas()
    repo = context.bot_data["repo"]
    await enviar_html(
        context.bot,
        update.effective_chat.id,
        texts.STATUS_BOT.format(
            bot_username=h(context.bot.username),
            main_group=config.main_group_id,
            admin_group=config.admin_group_id,
            planilha_url=repo.url,
            aba=h(repo.aba),
            service_account=h(config.service_account_email),
            em_andamento=contagem.get("Em andamento", 0),
            aguardando=contagem.get("Aguardando aprovação", 0),
            aprovadas=contagem.get("Aprovado", 0),
            recusadas=contagem.get("Recusado", 0),
        ),
    )


async def on_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cria um link de convite já com aprovação obrigatória ativada.

    Configurar isso à mão é o passo que mais dá errado na instalação: um link
    de convite comum deixa a pessoa entrar direto e o bot nunca chega a ser
    acionado. Aqui o próprio bot cria o link certo.
    """
    config = get_config(context)
    if update.effective_chat.id != config.admin_group_id:
        await update.effective_message.reply_text(texts.APENAS_ADMIN)
        return

    try:
        convite = await context.bot.create_chat_invite_link(
            chat_id=config.main_group_id,
            name="Cadastro pelo bot",
            creates_join_request=True,
        )
    except TelegramError as exc:
        logger.error("Falha ao criar link de convite: %s", exc)
        await enviar_html(
            context.bot,
            update.effective_chat.id,
            texts.LINK_ERRO.format(erro=h(exc)),
        )
        return

    logger.info("Link de convite com aprovação criado: %s", convite.invite_link)
    await enviar_html(
        context.bot,
        update.effective_chat.id,
        texts.LINK_GERADO.format(link=h(convite.invite_link)),
    )


async def on_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o ID do chat atual — usado na configuração inicial."""
    chat = update.effective_chat
    await enviar_html(
        context.bot,
        chat.id,
        texts.ID_DO_CHAT.format(chat_id=chat.id, tipo=chat.type),
    )


async def on_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await enviar_html(context.bot, update.effective_chat.id, texts.AJUDA_ADMIN)


# ---------------------------------------------------------------------------
# Descoberta de IDs ao adicionar o bot a um grupo
# ---------------------------------------------------------------------------


async def on_bot_adicionado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Anuncia o ID do grupo assim que o bot entra nele.

    Poupa a etapa mais confusa da instalação: descobrir o número do grupo sem
    precisar de ferramentas externas.
    """
    atualizacao = update.my_chat_member
    if atualizacao is None:
        return

    anterior = atualizacao.old_chat_member.status
    novo = atualizacao.new_chat_member.status
    entrou = anterior in (
        ChatMemberStatus.LEFT,
        ChatMemberStatus.BANNED,
    ) and novo in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)

    if not entrou or atualizacao.chat.type == "private":
        return

    logger.info(
        "Bot adicionado ao chat %s (%s).", atualizacao.chat.id, atualizacao.chat.title
    )
    try:
        await enviar_html(
            context.bot,
            atualizacao.chat.id,
            texts.ID_DO_CHAT.format(
                chat_id=atualizacao.chat.id, tipo=atualizacao.chat.type
            ),
        )
    except TelegramError as exc:
        logger.info("Não consegui anunciar o ID no chat: %s", exc)
