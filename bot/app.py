"""Montagem e execução da aplicação.

Dois modos, escolhidos automaticamente:

* **polling** — quando não há URL pública configurada. É o modo de
  desenvolvimento: rode na sua máquina e teste sem expor nada na internet.
* **webhook** — quando `WEBHOOK_URL` (ou `RENDER_EXTERNAL_URL`) está definida.
  É o modo de produção. O Telegram entrega as atualizações via HTTPS, o que
  também faz o serviço "acordar" sozinho em hospedagens gratuitas que
  hibernam por inatividade.
"""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route
from telegram import BotCommand, BotCommandScopeAllPrivateChats, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, ApplicationBuilder, Defaults

from . import handlers
from .config import Config
from .sheets import PlanilhaRepo
from .store import Store

logger = logging.getLogger(__name__)

COMANDOS_PRIVADOS = [
    BotCommand("start", "Iniciar ou retomar o cadastro"),
    BotCommand("cancelar", "Recomeçar o cadastro do zero"),
]


# ---------------------------------------------------------------------------
# Construção
# ---------------------------------------------------------------------------


def build_application(config: Config, store: Store, repo: PlanilhaRepo) -> Application:
    # As atualizações são processadas UMA POR VEZ, de propósito.
    #
    # Com processamento concorrente, duas mensagens enviadas em sequência pela
    # mesma pessoa poderiam ser tratadas fora de ordem — e a resposta da
    # pergunta 3 acabaria gravada como resposta da pergunta 2. Num
    # questionário sequencial isso é inaceitável, e o ganho de velocidade não
    # faz falta no volume de um grupo de comunidade: cada atualização leva
    # poucas centenas de milissegundos.
    #
    # ATENÇÃO: nada de `.post_init(...)` aqui. O PTB só executa esse callback
    # dentro dos atalhos `run_polling`/`run_webhook` dele, que não usamos —
    # `Application.initialize()` sozinho NÃO o chama. Como precisamos controlar
    # o laço de eventos, a preparação é chamada explicitamente em
    # `preparar(...)`, invocada pelos dois modos de execução abaixo.
    builder = (
        ApplicationBuilder()
        .token(config.bot_token)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .concurrent_updates(False)
    )

    # O limitador de taxa evita erro 429 quando várias solicitações chegam
    # juntas (uma divulgação do grupo, por exemplo).
    try:
        from telegram.ext import AIORateLimiter

        builder = builder.rate_limiter(AIORateLimiter())
    except ImportError:  # extra opcional não instalado
        logger.info("AIORateLimiter indisponível — seguindo sem limitador.")

    if config.modo_webhook:
        # Em webhook quem recebe as atualizações é o servidor HTTP; o updater
        # interno do PTB não é usado.
        builder = builder.updater(None)

    application = builder.build()
    application.bot_data["config"] = config
    application.bot_data["store"] = store
    application.bot_data["repo"] = repo
    handlers.registrar(application)
    return application


async def preparar(application: Application) -> None:
    """Roda uma vez, com o bot já conectado: diagnóstico e preparação.

    Equivale ao `post_init` do PTB, mas chamado à mão: como usamos nosso
    próprio laço de eventos em vez de `run_polling`/`run_webhook`, o PTB
    nunca dispararia esse callback sozinho.
    """
    config: Config = application.bot_data["config"]
    bot = application.bot

    eu = await bot.get_me()
    # Guardado aqui para que a rota /health não dependa do bot já inicializado.
    application.bot_data["bot_username"] = eu.username
    logger.info("Conectado como @%s (id %s).", eu.username, eu.id)

    await _verificar_grupo_principal(application, config)
    await _verificar_grupo_admin(application, config)

    try:
        await bot.set_my_commands(
            COMANDOS_PRIVADOS, scope=BotCommandScopeAllPrivateChats()
        )
    except TelegramError as exc:
        logger.warning("Não foi possível registrar os comandos: %s", exc)


async def _verificar_grupo_principal(application: Application, config: Config) -> None:
    """Confere se o bot consegue mesmo aprovar entradas no grupo principal."""
    bot = application.bot
    try:
        chat = await bot.get_chat(config.main_group_id)
    except TelegramError as exc:
        logger.error(
            "Não consegui acessar o grupo principal (%s): %s. "
            "Confirme o MAIN_GROUP_ID e se o bot foi adicionado ao grupo.",
            config.main_group_id,
            exc,
        )
        return

    application.bot_data["grupo_nome"] = chat.title or "a comunidade"
    logger.info("Grupo principal: %r (%s).", chat.title, chat.id)

    try:
        membro = await bot.get_chat_member(config.main_group_id, bot.id)
    except TelegramError as exc:
        logger.warning("Não consegui verificar as permissões do bot: %s", exc)
        return

    if membro.status != ChatMemberStatus.ADMINISTRATOR:
        logger.error(
            "O bot NÃO é administrador do grupo principal. Sem isso ele não "
            "consegue aprovar nem recusar solicitações."
        )
        return
    if not getattr(membro, "can_invite_users", False):
        logger.error(
            "O bot é administrador, mas está sem a permissão 'Adicionar "
            "membros'. É justamente ela que autoriza aprovar solicitações."
        )
        return
    logger.info("Permissões no grupo principal: OK.")


async def _verificar_grupo_admin(application: Application, config: Config) -> None:
    try:
        chat = await application.bot.get_chat(config.admin_group_id)
        logger.info("Grupo de administradores: %r (%s).", chat.title, chat.id)
    except TelegramError as exc:
        logger.error(
            "Não consegui acessar o grupo de administradores (%s): %s. "
            "Confirme o ADMIN_GROUP_ID e se o bot está nesse grupo.",
            config.admin_group_id,
            exc,
        )


# ---------------------------------------------------------------------------
# Execução: polling (desenvolvimento)
# ---------------------------------------------------------------------------


class ProducaoNoAr(RuntimeError):
    """Há um webhook ativo — rodar em polling derrubaria o bot de produção."""


async def _recusar_se_houver_producao_no_ar(application: Application) -> None:
    """Impede que rodar na sua máquina desligue o bot que está no ar.

    Um bot do Telegram só pode estar em UM modo por vez. Ao iniciar o
    polling, o `python-telegram-bot` chama `deleteWebhook` — então rodar
    `python main.py` na máquina de quem desenvolve derrubaria calado o bot
    hospedado, e ninguém perceberia até alguém pedir entrada e nada
    acontecer.

    Por isso a recusa é o padrão. Para rodar mesmo assim (com o serviço da
    hospedagem desligado, por exemplo), defina `PERMITIR_POLLING=1`.
    """
    if os.getenv("PERMITIR_POLLING", "").strip() == "1":
        logger.warning(
            "PERMITIR_POLLING=1: seguindo em polling mesmo com webhook ativo."
        )
        return

    try:
        info = await application.bot.get_webhook_info()
    except TelegramError as exc:  # sem rede, sem informação — não bloqueia
        logger.warning("Não consegui verificar o webhook: %s", exc)
        return

    if not info.url:
        return

    raise ProducaoNoAr(
        "Existe um webhook ativo para este bot:\n\n"
        f"    {info.url}\n\n"
        "Ou seja, ele já está rodando em produção. Iniciar o modo polling "
        "aqui apagaria esse webhook e o bot hospedado pararia de atender "
        "sem dar nenhum sinal.\n\n"
        "O que fazer:\n"
        "  • Só diagnosticar? Use `python tools/diagnostico.py`, que não "
        "mexe no webhook.\n"
        "  • Testar com um bot separado? Crie outro bot no @BotFather e "
        "troque o BOT_TOKEN do seu .env.\n"
        "  • Produção parada de propósito e você quer mesmo assumir o "
        "controle? Rode com PERMITIR_POLLING=1."
    )


async def run_polling(application: Application) -> None:
    """Consulta o Telegram periodicamente. Não precisa de URL pública.

    É `async` (em vez do atalho `run_polling` do PTB) para que os dois modos
    compartilhem o mesmo laço de eventos da preparação da planilha — objetos
    como `asyncio.Lock` não podem migrar entre laços diferentes.
    """
    logger.info("Iniciando em modo POLLING (desenvolvimento).")
    async with application:
        await _recusar_se_houver_producao_no_ar(application)
        await preparar(application)
        await application.start()
        await application.updater.start_polling(
            allowed_updates=handlers.ALLOWED_UPDATES,
            drop_pending_updates=False,
        )
        logger.info("Bot no ar. Pressione Ctrl+C para encerrar.")
        try:
            await asyncio.Event().wait()  # roda até ser interrompido
        finally:
            await application.updater.stop()
            await application.stop()
            logger.info("Bot encerrado.")


# ---------------------------------------------------------------------------
# Execução: webhook (hospedagem)
# ---------------------------------------------------------------------------


def _montar_servidor(application: Application, config: Config) -> Starlette:
    async def telegram(request: Request) -> Response:
        # O cabeçalho secreto garante que a atualização veio mesmo do Telegram.
        if config.webhook_secret:
            enviado = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if enviado != config.webhook_secret:
                logger.warning("Requisição rejeitada: segredo do webhook inválido.")
                return PlainTextResponse("forbidden", status_code=403)
        try:
            dados = await request.json()
        except Exception:
            return PlainTextResponse("bad request", status_code=400)

        # Um corpo que não vira `Update` é descartado com 200 de propósito.
        # Devolver 5xx faria o Telegram reenviar a mesma carga sem parar — e
        # nenhuma repetição consertaria um payload que não sabemos ler.
        try:
            atualizacao = Update.de_json(data=dados, bot=application.bot)
        except Exception:
            logger.warning("Corpo recebido não é uma atualização válida; descartado.")
            return PlainTextResponse("ignored")

        if atualizacao is not None:
            await application.update_queue.put(atualizacao)
        # Responder 200 rápido; o processamento acontece na fila.
        return PlainTextResponse("ok")

    async def health(request: Request) -> Response:
        """Usado pelo monitor externo que mantém o serviço acordado.

        Nunca levanta exceção de propósito. O Render trata um health check com
        erro como serviço doente e reinicia o processo — o que viraria um laço
        de reinícios só porque a rota foi consultada durante a subida, antes de
        `preparar()` terminar.
        """
        store: Store | None = application.bot_data.get("store")
        return JSONResponse(
            {
                "status": "ok",
                "bot": application.bot_data.get("bot_username", ""),
                "pronto": bool(application.bot_data.get("bot_username")),
                "solicitacoes": store.estatisticas() if store else {},
            }
        )

    return Starlette(
        routes=[
            Route(config.webhook_path, telegram, methods=["POST"]),
            Route("/", health, methods=["GET", "HEAD"]),
            Route("/health", health, methods=["GET", "HEAD"]),
        ]
    )


async def run_webhook(application: Application, config: Config) -> None:
    url = f"{config.webhook_url}{config.webhook_path}"
    logger.info("Iniciando em modo WEBHOOK: %s (porta %d).", url, config.port)

    servidor = uvicorn.Server(
        uvicorn.Config(
            app=_montar_servidor(application, config),
            host="0.0.0.0",
            port=config.port,
            log_level="warning",
            access_log=False,
        )
    )

    async with application:
        await preparar(application)
        await application.bot.set_webhook(
            url=url,
            secret_token=config.webhook_secret or None,
            allowed_updates=handlers.ALLOWED_UPDATES,
            drop_pending_updates=False,
            max_connections=40,
        )
        await application.start()
        try:
            await servidor.serve()
        finally:
            await application.stop()
            logger.info("Bot encerrado.")
