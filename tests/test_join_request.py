"""Testes do evento que inicia tudo: `ChatJoinRequest`.

O caso mais delicado está em `test_dm_bloqueada_*`: o Telegram só deixa o bot
abrir a conversa privada durante uma janela curta após a solicitação. Quando
esse contato falha, a linha na planilha já existe — então a pessoa consegue
retomar depois com /start, e os administradores são avisados na hora.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from telegram.error import Forbidden

from bot.handlers import onboarding
from bot.models import STATUS_EM_ANDAMENTO, STATUS_SEM_CONTATO
from bot.store import Store
from tests.fakes import (
    PlanilhaFalsa,
    config_falsa,
    contexto_falso,
    join_request_falso,
    mensagens_para,
    texto_falso,
    usuario_falso,
)

USER_ID = 555


class TestJoinRequest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.planilha = PlanilhaFalsa()
        self.store = Store(self.planilha)
        await self.store.carregar()
        self.config = config_falsa()
        self.context = contexto_falso(self.config, self.store, self.planilha)
        self.usuario = usuario_falso(USER_ID)

    async def solicitar(self, chat_id: int | None = None):
        update = join_request_falso(
            self.usuario,
            chat_id if chat_id is not None else self.config.main_group_id,
        )
        await onboarding.on_join_request(update, self.context)

    async def test_cria_linha_e_faz_a_primeira_pergunta(self):
        await self.solicitar()

        solicitacao = self.store.obter(USER_ID)
        self.assertIsNotNone(solicitacao)
        self.assertEqual(solicitacao.linha, 2)
        self.assertEqual(solicitacao.status, STATUS_EM_ANDAMENTO)
        self.assertEqual(self.planilha.celula(2, "C"), "fulano")
        self.assertTrue(self.planilha.celula(2, "A"))  # data/hora registrada

        enviadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("solicitação" in m.lower() for m in enviadas))
        self.assertTrue(any("Pergunta 1 de 5" in m for m in enviadas))

    async def test_ignora_solicitacao_de_outro_grupo(self):
        await self.solicitar(chat_id=-1009999999999)
        self.assertIsNone(self.store.obter(USER_ID))
        self.context.bot.send_message.assert_not_awaited()

    async def test_dm_bloqueada_marca_sem_contato(self):
        self.context.bot.send_message = AsyncMock(
            side_effect=Forbidden("bot was blocked by the user")
        )
        await self.solicitar()

        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.status, STATUS_SEM_CONTATO)
        self.assertEqual(self.planilha.celula(2, "K"), STATUS_SEM_CONTATO)

    async def test_dm_bloqueada_avisa_os_administradores(self):
        # Falha só na conversa privada; a mensagem ao grupo de admins passa.
        async def send(chat_id, **kwargs):
            if chat_id == USER_ID:
                raise Forbidden("bot was blocked by the user")
            return AsyncMock(message_id=1)

        self.context.bot.send_message = AsyncMock(side_effect=send)
        await self.solicitar()

        avisos = [
            c.kwargs.get("text", "")
            for c in self.context.bot.send_message.await_args_list
            if c.kwargs.get("chat_id") == self.config.admin_group_id
        ]
        self.assertEqual(len(avisos), 1)
        self.assertIn(str(USER_ID), avisos[0])

    async def test_retoma_com_start_apos_janela_expirada(self):
        """Cenário real: a pessoa só abre o bot horas depois."""
        self.context.bot.send_message = AsyncMock(
            side_effect=Forbidden("bot can't initiate conversation with a user")
        )
        await self.solicitar()
        self.assertEqual(self.store.obter(USER_ID).status, STATUS_SEM_CONTATO)

        # Ela toca em INICIAR: a partir daí o bot pode falar normalmente.
        self.context.bot.send_message = AsyncMock(return_value=AsyncMock(message_id=1))
        await onboarding.on_start(
            texto_falso("/start", self.usuario, USER_ID), self.context
        )

        enviadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("Pergunta 1 de 5" in m for m in enviadas))

    async def test_solicitar_de_novo_reaproveita_a_linha(self):
        await self.solicitar()
        await self.solicitar()
        self.assertEqual(len(self.planilha.linhas), 2)  # cabeçalho + 1 linha
        self.assertEqual(self.store.obter(USER_ID).linha, 2)


if __name__ == "__main__":
    unittest.main()
