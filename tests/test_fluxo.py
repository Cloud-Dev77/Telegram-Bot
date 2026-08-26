"""Testes do fluxo completo, do pedido de entrada até a decisão final.

Cobrem justamente os pontos em que este tipo de bot costuma falhar:
resposta fora de ordem, reinício da hospedagem no meio do cadastro, clique
duplo nos botões administrativos e solicitação que sumiu do Telegram.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from telegram.error import BadRequest

from bot.handlers import admin, onboarding
from bot.models import (
    STATUS_AGUARDANDO,
    STATUS_APROVADO,
    STATUS_EM_ANDAMENTO,
    STATUS_RECUSADO,
)
from bot.store import Store
from tests.fakes import (
    PlanilhaFalsa,
    config_falsa,
    contexto_falso,
    mensagens_para,
    query_falsa,
    texto_falso,
    update_falso,
    usuario_falso,
)

USER_ID = 555


class BaseFluxo(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.planilha = PlanilhaFalsa()
        self.store = Store(self.planilha)
        await self.store.carregar()
        self.config = config_falsa()
        self.context = contexto_falso(self.config, self.store, self.planilha)
        self.usuario = usuario_falso(USER_ID)

    async def criar_solicitacao(self):
        return await self.store.criar_ou_reiniciar(USER_ID, "fulano", "Fulano")

    async def responder(self, texto: str):
        await onboarding.on_resposta(
            texto_falso(texto, self.usuario, USER_ID), self.context
        )

    async def escolher_categoria(self, indice: int = 0):
        query = query_falsa(f"cat:{indice}", chat_id=USER_ID)
        await onboarding.on_categoria(
            update_falso(query, self.usuario, USER_ID), self.context
        )
        return query

    async def preencher_tudo(self):
        await self.criar_solicitacao()
        await self.escolher_categoria(0)
        await self.responder("Maria Aparecida de Souza")
        await self.responder("SP, Campinas")
        await self.responder("Hospital Municipal")
        await self.responder("CRM-SP 123456")


class TestColetaDeDados(BaseFluxo):
    async def test_grava_linha_no_primeiro_contato(self):
        solicitacao = await self.criar_solicitacao()
        self.assertEqual(solicitacao.linha, 2)
        self.assertEqual(self.planilha.celula(2, "B"), str(USER_ID))
        self.assertEqual(self.planilha.celula(2, "K"), STATUS_EM_ANDAMENTO)

    async def test_avanca_uma_pergunta_por_vez(self):
        await self.criar_solicitacao()
        await self.escolher_categoria(0)
        self.assertEqual(self.store.obter(USER_ID).etapa, 1)
        await self.responder("Maria Aparecida de Souza")
        self.assertEqual(self.store.obter(USER_ID).etapa, 2)

    async def test_resposta_invalida_nao_avanca(self):
        await self.criar_solicitacao()
        await self.escolher_categoria(0)
        await self.responder("Maria")  # sem sobrenome
        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.etapa, 1)
        self.assertEqual(solicitacao.nome_completo, "")
        enviadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("⚠️" in m for m in enviadas))

    async def test_grava_cada_resposta_na_planilha_na_hora(self):
        await self.criar_solicitacao()
        await self.escolher_categoria(0)
        self.assertEqual(self.planilha.celula(2, "E"), "Membro Efetivo")
        await self.responder("Maria Aparecida de Souza")
        self.assertEqual(self.planilha.celula(2, "F"), "Maria Aparecida de Souza")
        await self.responder("SP, Campinas")
        self.assertEqual(self.planilha.celula(2, "G"), "SP")
        self.assertEqual(self.planilha.celula(2, "H"), "Campinas")

    async def test_botao_de_categoria_antigo_nao_sobrescreve(self):
        """Clicar de novo no botão da pergunta 1 não pode voltar o fluxo."""
        await self.criar_solicitacao()
        await self.escolher_categoria(0)
        await self.responder("Maria Aparecida de Souza")

        query = await self.escolher_categoria(1)  # clique tardio em outra opção
        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.etapa, 2)
        self.assertEqual(solicitacao.categoria, "Membro Efetivo")
        query.answer.assert_awaited()


class TestReinicioDaHospedagem(BaseFluxo):
    async def test_estado_sobrevive_a_reinicio(self):
        await self.criar_solicitacao()
        await self.escolher_categoria(0)
        await self.responder("Maria Aparecida de Souza")

        # Simula o processo caindo e subindo de novo: planilha igual, cache zerado.
        planilha2 = self.planilha.clonar()
        store2 = Store(planilha2)
        await store2.carregar()

        recuperada = store2.obter(USER_ID)
        self.assertIsNotNone(recuperada)
        self.assertEqual(recuperada.etapa, 2)
        self.assertEqual(recuperada.nome_completo, "Maria Aparecida de Souza")
        self.assertEqual(recuperada.linha, 2)

    async def test_start_retoma_da_etapa_correta(self):
        await self.criar_solicitacao()
        await self.escolher_categoria(0)

        planilha2 = self.planilha.clonar()
        store2 = Store(planilha2)
        await store2.carregar()
        context2 = contexto_falso(self.config, store2, planilha2)

        await onboarding.on_start(
            texto_falso("/start", self.usuario, USER_ID), context2
        )
        enviadas = mensagens_para(context2.bot, USER_ID)
        self.assertTrue(any("Pergunta 2 de 5" in m for m in enviadas))


class TestReinicioDoCadastro(BaseFluxo):
    async def test_refazer_reaproveita_a_mesma_linha(self):
        await self.preencher_tudo()
        linha_antes = self.store.obter(USER_ID).linha

        query = query_falsa("conf:nao", chat_id=USER_ID)
        await onboarding.on_confirmacao(
            update_falso(query, self.usuario, USER_ID), self.context
        )

        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.linha, linha_antes)
        self.assertEqual(solicitacao.etapa, 0)
        self.assertEqual(solicitacao.nome_completo, "")
        self.assertEqual(len(self.planilha.linhas), 2)  # cabeçalho + 1 linha

    async def test_nova_solicitacao_apos_recusa_cria_linha_nova(self):
        await self.preencher_tudo()
        solicitacao = self.store.obter(USER_ID)
        await self.store.marcar_decisao(solicitacao, aprovado=False, decidido_por="Ana")

        nova = await self.criar_solicitacao()
        self.assertEqual(nova.linha, 3)
        self.assertEqual(self.planilha.celula(2, "K"), STATUS_RECUSADO)


class TestCardAdministrativo(BaseFluxo):
    async def test_confirmacao_envia_card_e_marca_aguardando(self):
        await self.preencher_tudo()
        query = query_falsa("conf:sim", chat_id=USER_ID)
        await onboarding.on_confirmacao(
            update_falso(query, self.usuario, USER_ID), self.context
        )

        cards = mensagens_para(self.context.bot, self.config.admin_group_id)
        self.assertEqual(len(cards), 1)
        self.assertIn("Maria Aparecida de Souza", cards[0])
        self.assertIn("CRM-SP 123456", cards[0])
        self.assertIn("Campinas", cards[0])

        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.status, STATUS_AGUARDANDO)
        self.assertEqual(solicitacao.msg_admin_id, 9001)
        self.assertEqual(self.planilha.celula(2, "K"), STATUS_AGUARDANDO)

    async def test_dados_do_usuario_sao_escapados(self):
        """Uma resposta com '<' não pode quebrar o HTML do card."""
        await self.criar_solicitacao()
        await self.escolher_categoria(0)
        await self.responder("Maria Aparecida de Souza")
        await self.responder("SP, Campinas")
        await self.responder("Unidade <b>falsa</b> & cia")
        await self.responder("CRM-SP 123456")

        query = query_falsa("conf:sim", chat_id=USER_ID)
        await onboarding.on_confirmacao(
            update_falso(query, self.usuario, USER_ID), self.context
        )
        card = mensagens_para(self.context.bot, self.config.admin_group_id)[0]
        self.assertIn("&lt;b&gt;falsa&lt;/b&gt; &amp; cia", card)


class TestDecisao(BaseFluxo):
    async def enviar_para_analise(self):
        await self.preencher_tudo()
        await onboarding.on_confirmacao(
            update_falso(query_falsa("conf:sim", chat_id=USER_ID), self.usuario, USER_ID),
            self.context,
        )
        self.context.bot.send_message.reset_mock()

    async def clicar(self, acao: str, chat_id: int | None = None):
        query = query_falsa(
            f"adm:{acao}:{USER_ID}",
            chat_id=chat_id if chat_id is not None else self.config.admin_group_id,
        )
        admin_user = usuario_falso(777, "ana", "Ana")
        await admin.on_decisao(
            update_falso(query, admin_user, self.config.admin_group_id), self.context
        )
        return query

    async def test_aprovar_chama_a_api_e_grava_na_planilha(self):
        await self.enviar_para_analise()
        query = await self.clicar("ap")

        self.context.bot.approve_chat_join_request.assert_awaited_once_with(
            chat_id=self.config.main_group_id, user_id=USER_ID
        )
        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.status, STATUS_APROVADO)
        self.assertEqual(solicitacao.decidido_por, "Ana")
        self.assertEqual(self.planilha.celula(2, "K"), STATUS_APROVADO)
        self.assertTrue(self.planilha.celula(2, "L"))
        self.assertEqual(self.planilha.celula(2, "M"), "Ana")
        query.edit_message_text.assert_awaited()

    async def test_recusar_chama_decline(self):
        await self.enviar_para_analise()
        await self.clicar("rc")
        self.context.bot.decline_chat_join_request.assert_awaited_once_with(
            chat_id=self.config.main_group_id, user_id=USER_ID
        )
        self.assertEqual(self.store.obter(USER_ID).status, STATUS_RECUSADO)

    async def test_clique_duplo_nao_aprova_duas_vezes(self):
        await self.enviar_para_analise()
        await self.clicar("ap")
        segundo = await self.clicar("ap")

        self.assertEqual(
            self.context.bot.approve_chat_join_request.await_count, 1
        )
        alerta = segundo.answer.await_args.args[0]
        self.assertIn("Ana", alerta)

    async def test_recusar_depois_de_aprovar_nao_reverte(self):
        await self.enviar_para_analise()
        await self.clicar("ap")
        await self.clicar("rc")

        self.context.bot.decline_chat_join_request.assert_not_awaited()
        self.assertEqual(self.store.obter(USER_ID).status, STATUS_APROVADO)

    async def test_clique_fora_do_grupo_de_admins_e_recusado(self):
        await self.enviar_para_analise()
        query = await self.clicar("ap", chat_id=-1009999999999)
        self.context.bot.approve_chat_join_request.assert_not_awaited()
        query.answer.assert_awaited()
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))

    async def test_solicitacao_expirada_ainda_grava_na_planilha(self):
        """O pedido sumiu do Telegram, mas a decisão precisa ficar registrada."""
        await self.enviar_para_analise()
        self.context.bot.approve_chat_join_request = AsyncMock(
            side_effect=BadRequest("HIDE_REQUESTER_MISSING")
        )
        await self.clicar("ap")

        self.assertEqual(self.store.obter(USER_ID).status, STATUS_APROVADO)
        self.assertEqual(self.planilha.celula(2, "K"), STATUS_APROVADO)

    async def test_erro_inesperado_mantem_os_botoes(self):
        await self.enviar_para_analise()
        self.context.bot.approve_chat_join_request = AsyncMock(
            side_effect=BadRequest("CHAT_ADMIN_REQUIRED")
        )
        query = await self.clicar("ap")

        self.assertEqual(self.store.obter(USER_ID).status, STATUS_AGUARDANDO)
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))

    async def test_candidato_e_avisado_da_decisao(self):
        await self.enviar_para_analise()
        await self.clicar("ap")
        avisos = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("aprovada" in m.lower() for m in avisos))


class TestRespostasForaDeHora(BaseFluxo):
    async def test_texto_sem_solicitacao_orienta_o_usuario(self):
        await self.responder("oi")
        enviadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("Solicitar entrada" in m for m in enviadas))

    async def test_texto_apos_envio_nao_altera_nada(self):
        await self.preencher_tudo()
        await onboarding.on_confirmacao(
            update_falso(query_falsa("conf:sim", chat_id=USER_ID), self.usuario, USER_ID),
            self.context,
        )
        escritas_antes = self.planilha.escritas
        await self.responder("mudei de ideia, meu nome é outro")

        self.assertEqual(self.planilha.escritas, escritas_antes)
        self.assertEqual(
            self.store.obter(USER_ID).nome_completo, "Maria Aparecida de Souza"
        )

    async def test_texto_apos_aprovacao_informa_o_status(self):
        await self.preencher_tudo()
        solicitacao = self.store.obter(USER_ID)
        await self.store.marcar_decisao(solicitacao, aprovado=True, decidido_por="Ana")
        self.context.bot.send_message.reset_mock()

        await self.responder("oi")
        enviadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("aprovada" in m.lower() for m in enviadas))


if __name__ == "__main__":
    unittest.main()
