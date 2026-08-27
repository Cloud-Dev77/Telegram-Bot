"""Fluxo do candidato: da solicitação de entrada até o envio para análise.

Sequência completa:

    ChatJoinRequest -> linha criada na planilha -> mensagem privada
    -> 5 perguntas validadas uma a uma -> resumo -> confirmação
    -> card no grupo de administradores

Ponto delicado do Telegram: ao receber um `ChatJoinRequest`, o bot só pode
INICIAR a conversa privada durante uma janela curta (o campo `user_chat_id`
vale por cerca de 5 minutos). Depois disso, só volta a falar com a pessoa se
ela mesma abrir o bot. Por isso a linha da planilha é criada ANTES da tentativa
de contato: assim, quem chegar depois via /start é reconhecido e retoma o
processo exatamente de onde parou.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from .. import texts
from ..models import (
    STATUS_AGUARDANDO,
    STATUS_APROVADO,
    STATUS_FINAIS,
    STATUS_RECUSADO,
    Solicitacao,
)
from ..questions import OPCOES_TITULAR, PERGUNTAS, TOTAL_PERGUNTAS
from ..utils import h, nome_exibicao
from .common import (
    avancar,
    enviar_html,
    enviar_resumo,
    get_config,
    get_store,
    nome_do_grupo,
    remover_botoes,
    teclado_correcao,
    teclado_decisao,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Solicitação de entrada no grupo
# ---------------------------------------------------------------------------


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pedido = update.chat_join_request
    config = get_config(context)
    store = get_store(context)

    if pedido.chat.id != config.main_group_id:
        logger.info(
            "Solicitação ignorada: veio do chat %s, não do grupo principal.",
            pedido.chat.id,
        )
        return

    usuario = pedido.from_user
    context.bot_data["grupo_nome"] = pedido.chat.title or nome_do_grupo(context)

    async with store.lock(usuario.id):
        solicitacao = await store.criar_ou_reiniciar(
            user_id=usuario.id,
            username=usuario.username or "",
            nome_telegram=nome_exibicao(usuario),
        )

    logger.info(
        "Nova solicitação: %s (%s) -> linha %d",
        usuario.id,
        usuario.username or "sem @",
        solicitacao.linha,
    )

    # `user_chat_id` é o canal autorizado para o primeiro contato.
    chat_privado = getattr(pedido, "user_chat_id", None) or usuario.id

    try:
        await enviar_html(
            context.bot,
            chat_privado,
            texts.BOAS_VINDAS.format(
                nome=h(usuario.first_name or nome_exibicao(usuario)),
                grupo=h(pedido.chat.title or "a comunidade"),
            ),
        )
        await avancar(context.bot, chat_privado, solicitacao)
    except (Forbidden, BadRequest) as exc:
        logger.warning(
            "Não consegui abrir conversa com %s: %s", usuario.id, exc
        )
        async with store.lock(usuario.id):
            await store.marcar_sem_contato(solicitacao)
        await _avisar_admins_sem_contato(context, usuario)


async def _avisar_admins_sem_contato(
    context: ContextTypes.DEFAULT_TYPE, usuario
) -> None:
    """Sem esse aviso, uma solicitação sem contato ficaria invisível."""
    config = get_config(context)
    try:
        await enviar_html(
            context.bot,
            config.admin_group_id,
            texts.ALERTA_SEM_CONTATO.format(
                nome=h(nome_exibicao(usuario)),
                username=h(f"@{usuario.username}" if usuario.username else "sem @usuário"),
                user_id=usuario.id,
                bot_username=h(context.bot.username),
            ),
        )
    except TelegramError as exc:
        logger.error("Falha ao avisar o grupo de administradores: %s", exc)


# ---------------------------------------------------------------------------
# 2. /start — primeiro contato ou retomada
# ---------------------------------------------------------------------------


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    usuario = update.effective_user
    store = get_store(context)
    solicitacao = store.obter(usuario.id)

    if solicitacao is None:
        await enviar_html(context.bot, usuario.id, texts.SEM_SOLICITACAO)
        return

    if solicitacao.status == STATUS_APROVADO:
        await enviar_html(context.bot, usuario.id, texts.JA_APROVADO)
        return
    if solicitacao.status == STATUS_RECUSADO:
        await enviar_html(context.bot, usuario.id, texts.JA_RECUSADO)
        return
    if solicitacao.status == STATUS_AGUARDANDO:
        await enviar_html(context.bot, usuario.id, texts.JA_ENVIADO)
        return

    # Solicitação aberta: retoma exatamente da etapa em que parou. É este
    # caminho que salva quem só abriu o bot depois da janela inicial.
    async with store.lock(usuario.id):
        if usuario.username and usuario.username != solicitacao.username:
            solicitacao.username = usuario.username
        await enviar_html(
            context.bot,
            usuario.id,
            texts.RETOMAR.format(nome=h(usuario.first_name or nome_exibicao(usuario))),
        )
        await avancar(context.bot, usuario.id, solicitacao)


async def on_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    usuario = update.effective_user
    store = get_store(context)
    solicitacao = store.obter(usuario.id)

    if solicitacao is None or solicitacao.status in STATUS_FINAIS:
        await enviar_html(context.bot, usuario.id, texts.SEM_SOLICITACAO)
        return

    async with store.lock(usuario.id):
        await store.criar_ou_reiniciar(
            usuario.id, usuario.username or "", nome_exibicao(usuario)
        )
    await enviar_html(context.bot, usuario.id, texts.CANCELADO)


# ---------------------------------------------------------------------------
# 3. Respostas às perguntas
# ---------------------------------------------------------------------------


async def _solicitacao_ativa(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Solicitacao | None:
    """Devolve a solicitação em aberto ou responde explicando o estado atual."""
    usuario = update.effective_user
    store = get_store(context)
    solicitacao = store.obter(usuario.id)

    if solicitacao is None:
        await enviar_html(context.bot, usuario.id, texts.SEM_SOLICITACAO)
        return None
    if solicitacao.status == STATUS_APROVADO:
        await enviar_html(context.bot, usuario.id, texts.JA_APROVADO)
        return None
    if solicitacao.status == STATUS_RECUSADO:
        await enviar_html(context.bot, usuario.id, texts.JA_RECUSADO)
        return None
    if solicitacao.status == STATUS_AGUARDANDO:
        await enviar_html(context.bot, usuario.id, texts.JA_ENVIADO)
        return None
    return solicitacao


async def on_resposta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Texto livre no privado: trata como resposta da pergunta atual."""
    usuario = update.effective_user
    store = get_store(context)

    async with store.lock(usuario.id):
        solicitacao = await _solicitacao_ativa(update, context)
        if solicitacao is None:
            return

        if solicitacao.etapa >= TOTAL_PERGUNTAS:
            # Já respondeu tudo e só falta confirmar.
            await enviar_resumo(context.bot, usuario.id, solicitacao)
            return

        pergunta = PERGUNTAS[solicitacao.etapa]
        resultado = pergunta.validar(update.message.text or "")

        if not resultado.ok:
            await enviar_html(
                context.bot,
                usuario.id,
                texts.RESPOSTA_INVALIDA.format(motivo=resultado.erro),
            )
            await avancar(context.bot, usuario.id, solicitacao)
            return

        if solicitacao.corrigindo:
            # Veio do resumo para arrumar UM dado: grava e volta ao resumo,
            # sem refazer as perguntas seguintes.
            await store.salvar_resposta(
                solicitacao, resultado.valores, solicitacao.etapa + 1
            )
            await store.encerrar_correcao(solicitacao)
            await enviar_html(context.bot, usuario.id, texts.CORRECAO_OK)
            await enviar_resumo(context.bot, usuario.id, solicitacao)
            return

        await store.salvar_resposta(
            solicitacao, resultado.valores, solicitacao.etapa + 1
        )
        await avancar(context.bot, usuario.id, solicitacao)


async def on_nao_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foto, áudio, figurinha, contato... Explica e repete a pergunta."""
    usuario = update.effective_user
    store = get_store(context)

    async with store.lock(usuario.id):
        solicitacao = await _solicitacao_ativa(update, context)
        if solicitacao is None:
            return
        await enviar_html(context.bot, usuario.id, texts.APENAS_TEXTO)
        await avancar(context.bot, usuario.id, solicitacao)


async def on_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Compatibilidade: botão inline antigo da pergunta 1.

    A pergunta 1 passou a usar teclado de resposta, porque tocar num botão
    inline não abre o canal privado e a pergunta seguinte nunca era enviada.
    Este handler existe só para quem ficou com o botão antigo na tela: o
    popup do `answer` sempre funciona, mesmo com o canal fechado, e orienta
    a pessoa a digitar a resposta — o que abre o canal e destrava o fluxo.
    """
    query = update.callback_query
    opcoes = " ou ".join(OPCOES_TITULAR)
    await query.answer(
        f"Este botão é de uma versão anterior. Digite {opcoes} na conversa "
        "para continuar.",
        show_alert=True,
    )
    await remover_botoes(query)


# ---------------------------------------------------------------------------
# 4. Confirmação final e envio ao grupo de administradores
# ---------------------------------------------------------------------------


async def on_confirmacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    usuario = update.effective_user
    store = get_store(context)
    escolha = query.data.split(":", 1)[1]

    async with store.lock(usuario.id):
        solicitacao = await _solicitacao_ativa(update, context)
        if solicitacao is None:
            await query.answer()
            await remover_botoes(query)
            return

        if not solicitacao.concluida:
            await query.answer("Ainda faltam perguntas.")
            await remover_botoes(query)
            await avancar(context.bot, usuario.id, solicitacao)
            return

        await query.answer()
        await remover_botoes(query)

        if escolha == "nao":
            await enviar_html(
                context.bot,
                usuario.id,
                texts.ESCOLHER_CORRECAO,
                reply_markup=teclado_correcao(solicitacao),
            )
            return

        await _publicar_card(context, solicitacao)
        await enviar_html(context.bot, usuario.id, texts.ENVIADO_PARA_ANALISE)


async def on_corrigir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Escolha de qual dado corrigir, a partir do resumo."""
    query = update.callback_query
    usuario = update.effective_user
    store = get_store(context)
    escolha = query.data.split(":", 1)[1]

    async with store.lock(usuario.id):
        solicitacao = await _solicitacao_ativa(update, context)
        if solicitacao is None:
            await query.answer()
            await remover_botoes(query)
            return

        await query.answer()
        await remover_botoes(query)

        if escolha == "volta":
            await enviar_resumo(context.bot, usuario.id, solicitacao)
            return

        try:
            indice = int(escolha)
            pergunta = PERGUNTAS[indice]
        except (ValueError, IndexError):
            await enviar_resumo(context.bot, usuario.id, solicitacao)
            return

        _, atual = solicitacao.campos_resumidos()[indice]
        await store.iniciar_correcao(solicitacao, indice)
        await enviar_html(
            context.bot,
            usuario.id,
            texts.CORRIGIR_PERGUNTA.format(atual=h(atual) or "(vazio)"),
        )
        await avancar(context.bot, usuario.id, solicitacao)
        logger.info(
            "Usuário %s corrigindo o campo %d (%s).", usuario.id, indice, pergunta.chave
        )


async def _publicar_card(
    context: ContextTypes.DEFAULT_TYPE, solicitacao: Solicitacao
) -> None:
    """Envia o card de verificação ao grupo restrito de administradores."""
    config = get_config(context)
    store = get_store(context)

    texto = texts.CARD_ADMIN.format(
        alerta="" if solicitacao.elegivel else texts.ALERTA_NAO_ELEGIVEL,
        titular=h(solicitacao.titular),
        nome_completo=h(solicitacao.nome_completo),
        municipio=h(solicitacao.municipio),
        uf=h(solicitacao.uf),
        serventia=h(solicitacao.serventia),
        cns=h(solicitacao.cns),
        user_id=solicitacao.user_id,
        username=h(solicitacao.username_exibicao),
        nome_telegram=h(solicitacao.nome_telegram),
        data_hora=h(solicitacao.data_hora),
        linha=solicitacao.linha,
    )

    mensagem = await enviar_html(
        context.bot,
        config.admin_group_id,
        texto,
        reply_markup=teclado_decisao(solicitacao.user_id),
    )
    await store.marcar_aguardando(solicitacao, mensagem.message_id)
    logger.info(
        "Card enviado aos administradores para %s (msg %d).",
        solicitacao.user_id,
        mensagem.message_id,
    )
