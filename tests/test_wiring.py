"""Testes de montagem: garantem que a aplicação sobe com tudo registrado.

Erros de ligação (um handler apontando para uma função que não existe, um
padrão de callback escrito errado) só apareceriam em produção. Este arquivo
os transforma em falha de teste.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from telegram.ext import (
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
)

import inspect

from bot import app as app_mod
from bot.app import build_application, preparar
from bot.handlers import ALLOWED_UPDATES
from bot.handlers import onboarding
from bot.models import STATUS_EM_ANDAMENTO
from bot.store import Store
from tests.fakes import (
    PlanilhaFalsa,
    config_falsa,
    contexto_falso,
    mensagens_para,
    usuario_falso,
)


class TestMontagem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.planilha = PlanilhaFalsa()
        self.store = Store(self.planilha)
        await self.store.carregar()
        self.config = config_falsa()
        self.app = build_application(self.config, self.store, self.planilha)

    def _handlers(self):
        return [h for grupo in self.app.handlers.values() for h in grupo]

    def test_objetos_globais_disponiveis(self):
        self.assertIs(self.app.bot_data["config"], self.config)
        self.assertIs(self.app.bot_data["store"], self.store)
        self.assertIs(self.app.bot_data["repo"], self.planilha)

    def test_registra_todos_os_tipos_de_handler(self):
        tipos = [type(h) for h in self._handlers()]
        for esperado in (
            ChatJoinRequestHandler,
            CommandHandler,
            CallbackQueryHandler,
            MessageHandler,
            ChatMemberHandler,
        ):
            self.assertIn(esperado, tipos, f"{esperado.__name__} não registrado")

    def test_todos_os_comandos_documentados_existem(self):
        comandos = set()
        for handler in self._handlers():
            if isinstance(handler, CommandHandler):
                comandos.update(handler.commands)
        self.assertEqual(
            comandos, {"start", "cancelar", "status", "link", "id", "ajuda", "help"}
        )

    def test_tratador_de_erros_registrado(self):
        self.assertTrue(self.app.error_handlers)

    def test_chat_join_request_esta_nas_atualizacoes_permitidas(self):
        """Sem isto o Telegram nunca entregaria o evento principal do bot."""
        self.assertIn("chat_join_request", ALLOWED_UPDATES)
        self.assertNotIn("edited_message", ALLOWED_UPDATES)

    def test_preparacao_e_chamada_nos_dois_modos(self):
        """O PTB NÃO chama `post_init` a partir de `initialize()`.

        Ele só o dispara dentro dos atalhos `run_polling`/`run_webhook`, que
        não usamos. Se alguém voltar a confiar no `post_init`, as verificações
        de permissão e o nome do grupo somem silenciosamente em produção.
        """
        self.assertIsNone(
            self.app.post_init,
            "post_init não é executado no nosso fluxo — não o registre",
        )
        for funcao in (app_mod.run_polling, app_mod.run_webhook):
            codigo = inspect.getsource(funcao)
            self.assertIn(
                "await preparar(application)",
                codigo,
                f"{funcao.__name__} não chama preparar()",
            )

    def test_processamento_sequencial(self):
        """Ordem das respostas depende de não haver concorrência.

        O PTB expõe isso como o número máximo de atualizações simultâneas:
        1 significa uma de cada vez.
        """
        self.assertEqual(self.app.concurrent_updates, 1)


class TestMensagemNaoTextual(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.planilha = PlanilhaFalsa()
        self.store = Store(self.planilha)
        await self.store.carregar()
        self.config = config_falsa()
        self.context = contexto_falso(self.config, self.store, self.planilha)
        self.usuario = usuario_falso(555)

    async def test_figurinha_nao_avanca_a_etapa(self):
        from types import SimpleNamespace

        await self.store.criar_ou_reiniciar(555, "fulano", "Fulano")
        update = SimpleNamespace(
            callback_query=None,
            effective_user=self.usuario,
            effective_chat=SimpleNamespace(id=555, type="private"),
            message=SimpleNamespace(text=None, reply_text=AsyncMock()),
        )
        await onboarding.on_nao_texto(update, self.context)

        solicitacao = self.store.obter(555)
        self.assertEqual(solicitacao.etapa, 0)
        self.assertEqual(solicitacao.status, STATUS_EM_ANDAMENTO)

        enviadas = mensagens_para(self.context.bot, 555)
        self.assertTrue(any("texto" in m for m in enviadas))
        self.assertTrue(any("Pergunta 1 de 5" in m for m in enviadas))


class TestPreparar(unittest.IsolatedAsyncioTestCase):
    """`preparar()` guarda o nome do grupo e registra os comandos."""

    async def asyncSetUp(self):
        from types import SimpleNamespace

        self.planilha = PlanilhaFalsa()
        self.store = Store(self.planilha)
        await self.store.carregar()
        self.config = config_falsa()

        bot = AsyncMock()
        bot.id = 42
        bot.username = "bot_teste"
        bot.get_me = AsyncMock(return_value=SimpleNamespace(id=42, username="bot_teste"))
        bot.get_chat = AsyncMock(
            return_value=SimpleNamespace(id=self.config.main_group_id, title="Comunidade Real")
        )
        bot.get_chat_member = AsyncMock(
            return_value=SimpleNamespace(status="administrator", can_invite_users=True)
        )
        self.bot = bot
        self.app = SimpleNamespace(
            bot=bot,
            bot_data={"config": self.config, "store": self.store, "repo": self.planilha},
        )

    async def test_guarda_o_nome_do_grupo(self):
        await preparar(self.app)
        self.assertEqual(self.app.bot_data["grupo_nome"], "Comunidade Real")

    async def test_registra_os_comandos_do_chat_privado(self):
        await preparar(self.app)
        self.bot.set_my_commands.assert_awaited_once()
        comandos = self.bot.set_my_commands.await_args.args[0]
        self.assertEqual([c.command for c in comandos], ["start", "cancelar"])


if __name__ == "__main__":
    unittest.main()
