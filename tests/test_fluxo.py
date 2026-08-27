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
from bot.questions import OPCOES_TITULAR
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


def query_teclado_texto(bot) -> list[str]:
    """Rótulos dos botões inline da última mensagem enviada."""
    for chamada in reversed(bot.send_message.await_args_list):
        teclado = chamada.kwargs.get("reply_markup")
        if teclado is not None and getattr(teclado, "inline_keyboard", None):
            return [b.text for linha in teclado.inline_keyboard for b in linha]
    return []


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
        """Pergunta 1 é respondida por TEXTO, não por botão inline.

        O teclado de resposta faz o Telegram enviar a palavra escolhida como
        mensagem do usuário — é justamente isso que abre o canal privado e
        destrava o envio da pergunta 2.
        """
        await self.responder(OPCOES_TITULAR[indice])

    async def abrir_menu_correcao(self):
        query = query_falsa("conf:nao", chat_id=USER_ID)
        await onboarding.on_confirmacao(
            update_falso(query, self.usuario, USER_ID), self.context
        )
        return query

    async def escolher_correcao(self, alvo):
        query = query_falsa(f"fix:{alvo}", chat_id=USER_ID)
        await onboarding.on_corrigir(
            update_falso(query, self.usuario, USER_ID), self.context
        )
        return query

    async def preencher_tudo(self):
        await self.criar_solicitacao()
        await self.escolher_categoria(0)
        await self.responder("Maria Aparecida de Souza")
        await self.responder("Campinas/SP")
        await self.responder("1º Cartório de Notas")
        await self.responder("123456-7")


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
        self.assertEqual(self.planilha.celula(2, "E"), "Sim")
        await self.responder("Maria Aparecida de Souza")
        self.assertEqual(self.planilha.celula(2, "F"), "Maria Aparecida de Souza")
        await self.responder("Campinas/SP")
        self.assertEqual(self.planilha.celula(2, "G"), "Campinas")
        self.assertEqual(self.planilha.celula(2, "H"), "SP")

    async def test_botao_inline_antigo_orienta_a_digitar(self):
        """Quem ficou com o botão inline da versão anterior na tela.

        O popup do `answer` funciona mesmo com o canal privado fechado — é o
        único caminho que sobra para orientar essa pessoa.
        """
        await self.criar_solicitacao()
        query = query_falsa("cat:0", chat_id=USER_ID)
        await onboarding.on_categoria(
            update_falso(query, self.usuario, USER_ID), self.context
        )
        query.answer.assert_awaited()
        alerta = query.answer.await_args.args[0]
        self.assertIn("Sim", alerta)
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))
        # Nada foi gravado: a resposta válida vem pelo texto.
        self.assertEqual(self.store.obter(USER_ID).etapa, 0)


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
    async def test_corrigir_nao_apaga_as_outras_respostas(self):
        """O ponto do relato do cliente: errar 1 dado não pode zerar os 5."""
        await self.preencher_tudo()
        linha_antes = self.store.obter(USER_ID).linha

        await self.abrir_menu_correcao()

        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.linha, linha_antes)
        self.assertEqual(solicitacao.nome_completo, "Maria Aparecida de Souza")
        self.assertEqual(solicitacao.cns, "123456-7")
        self.assertEqual(len(self.planilha.linhas), 2)  # cabeçalho + 1 linha

    async def test_nova_solicitacao_apos_recusa_cria_linha_nova(self):
        await self.preencher_tudo()
        solicitacao = self.store.obter(USER_ID)
        await self.store.marcar_decisao(solicitacao, aprovado=False, decidido_por="Ana")

        nova = await self.criar_solicitacao()
        self.assertEqual(nova.linha, 3)
        self.assertEqual(self.planilha.celula(2, "K"), STATUS_RECUSADO)


class TestCorrecaoDeUmCampo(BaseFluxo):
    """Corrigir um dado no resumo, sem refazer o questionário inteiro.

    Relato do cliente: ao apontar que o 3º dado estava errado, o bot mandava
    preencher tudo de novo desde a primeira pergunta.
    """

    async def test_menu_lista_os_cinco_campos_com_os_valores(self):
        await self.preencher_tudo()
        await self.abrir_menu_correcao()
        botoes = query_teclado_texto(self.context.bot)
        self.assertEqual(len(botoes), 6)  # 5 campos + voltar
        self.assertIn("Maria Aparecida", " ".join(botoes))
        self.assertIn("Campinas/SP", " ".join(botoes))

    async def test_corrigir_o_terceiro_campo_volta_direto_ao_resumo(self):
        await self.preencher_tudo()
        await self.abrir_menu_correcao()
        await self.escolher_correcao(2)  # Município/UF

        solicitacao = self.store.obter(USER_ID)
        self.assertTrue(solicitacao.corrigindo)
        self.assertEqual(solicitacao.etapa, 2)

        self.context.bot.send_message.reset_mock()
        await self.responder("Santos/SP")

        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.municipio, "Santos")
        self.assertEqual(solicitacao.uf, "SP")
        self.assertFalse(solicitacao.corrigindo)
        self.assertTrue(solicitacao.concluida)

        enviadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("atualizado" in m for m in enviadas))
        self.assertTrue(any("Confira os dados" in m for m in enviadas))
        # E NÃO pode ter voltado a perguntar a 4
        self.assertFalse(any("Pergunta 4 de 5" in m for m in enviadas))

    async def test_os_outros_campos_ficam_intactos(self):
        await self.preencher_tudo()
        await self.abrir_menu_correcao()
        await self.escolher_correcao(2)
        await self.responder("Santos/SP")

        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.titular, "Sim")
        self.assertEqual(solicitacao.nome_completo, "Maria Aparecida de Souza")
        self.assertEqual(solicitacao.serventia, "1º Cartório de Notas")
        self.assertEqual(solicitacao.cns, "123456-7")
        self.assertEqual(self.planilha.celula(2, "G"), "Santos")

    async def test_resposta_invalida_durante_a_correcao_repete_a_pergunta(self):
        await self.preencher_tudo()
        await self.abrir_menu_correcao()
        await self.escolher_correcao(1)  # nome
        self.context.bot.send_message.reset_mock()

        await self.responder("Ana")  # sem sobrenome

        solicitacao = self.store.obter(USER_ID)
        self.assertTrue(solicitacao.corrigindo)  # continua em modo correção
        self.assertEqual(solicitacao.nome_completo, "Maria Aparecida de Souza")
        enviadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("⚠️" in m for m in enviadas))

    async def test_voltar_sem_corrigir_devolve_o_resumo(self):
        await self.preencher_tudo()
        await self.abrir_menu_correcao()
        self.context.bot.send_message.reset_mock()
        await self.escolher_correcao("volta")

        self.assertFalse(self.store.obter(USER_ID).corrigindo)
        enviadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("Confira os dados" in m for m in enviadas))

    async def test_correcao_sobrevive_a_reinicio_da_hospedagem(self):
        """O estado da correção fica na planilha, não só na memória."""
        await self.preencher_tudo()
        await self.abrir_menu_correcao()
        await self.escolher_correcao(2)

        planilha2 = self.planilha.clonar()
        store2 = Store(planilha2)
        await store2.carregar()

        recuperada = store2.obter(USER_ID)
        self.assertTrue(recuperada.corrigindo)
        self.assertEqual(recuperada.editando, 2)
        self.assertEqual(recuperada.etapa, 2)


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
        self.assertIn("123456-7", cards[0])
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
        await self.responder("Campinas/SP")
        await self.responder("Cartório <b>falso</b> & cia")
        await self.responder("123456-7")

        query = query_falsa("conf:sim", chat_id=USER_ID)
        await onboarding.on_confirmacao(
            update_falso(query, self.usuario, USER_ID), self.context
        )
        card = mensagens_para(self.context.bot, self.config.admin_group_id)[0]
        self.assertIn("&lt;b&gt;falso&lt;/b&gt; &amp; cia", card)


class TestElegibilidade(BaseFluxo):
    """A pergunta 1 é critério de entrada, não classificação.

    Quem responde "Não" declara não ser titular de Serventia Extrajudicial —
    justamente o público do grupo. O cadastro continua (quem decide são os
    administradores), mas o card precisa gritar, para ninguém aprovar no
    automático.
    """

    async def preencher_com(self, indice_opcao):
        await self.criar_solicitacao()
        await self.escolher_categoria(indice_opcao)
        await self.responder("Maria Aparecida de Souza")
        await self.responder("Campinas/SP")
        await self.responder("1º Cartório de Notas")
        await self.responder("123456-7")
        await onboarding.on_confirmacao(
            update_falso(query_falsa("conf:sim", chat_id=USER_ID), self.usuario, USER_ID),
            self.context,
        )
        return mensagens_para(self.context.bot, self.config.admin_group_id)[0]

    async def test_sim_nao_gera_alerta(self):
        card = await self.preencher_com(0)  # Sim
        self.assertIn("Titular de Serventia:</b> Sim", card)
        self.assertNotIn("ATENÇÃO", card)
        self.assertTrue(self.store.obter(USER_ID).elegivel)

    async def test_nao_gera_alerta_destacado_no_card(self):
        card = await self.preencher_com(1)  # Não
        self.assertIn("ATENÇÃO", card)
        self.assertIn("NÃO</b> ser titular", card)
        self.assertFalse(self.store.obter(USER_ID).elegivel)

    async def test_nao_continua_o_cadastro_normalmente(self):
        """Responder 'Não' não interrompe nada — a decisão é dos admins."""
        await self.preencher_com(1)
        solicitacao = self.store.obter(USER_ID)
        self.assertEqual(solicitacao.status, STATUS_AGUARDANDO)
        self.assertEqual(solicitacao.titular, "Não")
        self.assertEqual(solicitacao.cns, "123456-7")

    async def test_planilha_espelha_as_colunas_do_formulario(self):
        await self.preencher_com(0)
        self.assertEqual(self.planilha.celula(2, "E"), "Sim")
        self.assertEqual(self.planilha.celula(2, "F"), "Maria Aparecida de Souza")
        self.assertEqual(self.planilha.celula(2, "G"), "Campinas")
        self.assertEqual(self.planilha.celula(2, "H"), "SP")
        self.assertEqual(self.planilha.celula(2, "I"), "1º Cartório de Notas")
        self.assertEqual(self.planilha.celula(2, "J"), "123456-7")


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


class TestAnuncioNoGrupo(BaseFluxo):
    """Após aprovar: boas-vindas no privado E aviso no grupo principal."""

    async def enviar_e_aprovar(self, **cfg):
        if cfg:
            self.config = config_falsa(**cfg)
            self.context = contexto_falso(self.config, self.store, self.planilha)
        await self.preencher_tudo()
        await onboarding.on_confirmacao(
            update_falso(query_falsa("conf:sim", chat_id=USER_ID), self.usuario, USER_ID),
            self.context,
        )
        self.context.bot.send_message.reset_mock()
        query = query_falsa(f"adm:ap:{USER_ID}", chat_id=self.config.admin_group_id)
        await admin.on_decisao(
            update_falso(query, usuario_falso(777, "ana", "Ana"), self.config.admin_group_id),
            self.context,
        )

    async def test_anuncia_no_grupo_principal(self):
        await self.enviar_e_aprovar()
        avisos = mensagens_para(self.context.bot, self.config.main_group_id)
        self.assertEqual(len(avisos), 1)
        aviso = avisos[0]
        self.assertIn("Maria Aparecida de Souza", aviso)
        self.assertIn("1º Cartório de Notas", aviso)
        self.assertIn("Campinas/SP", aviso)

    async def test_anuncio_nao_expoe_dados_de_verificacao(self):
        """CNS, Telegram ID e @usuário são só do grupo dos administradores."""
        await self.enviar_e_aprovar()
        aviso = mensagens_para(self.context.bot, self.config.main_group_id)[0]
        self.assertNotIn("123456-7", aviso)
        self.assertNotIn("fulano", aviso)
        self.assertNotIn("Titular", aviso)

    async def test_avisa_o_usuario_no_privado(self):
        await self.enviar_e_aprovar()
        privadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("aprovada" in m.lower() for m in privadas))

    async def test_recusa_nao_anuncia(self):
        await self.preencher_tudo()
        await onboarding.on_confirmacao(
            update_falso(query_falsa("conf:sim", chat_id=USER_ID), self.usuario, USER_ID),
            self.context,
        )
        self.context.bot.send_message.reset_mock()
        query = query_falsa(f"adm:rc:{USER_ID}", chat_id=self.config.admin_group_id)
        await admin.on_decisao(
            update_falso(query, usuario_falso(777, "ana", "Ana"), self.config.admin_group_id),
            self.context,
        )
        self.assertEqual(mensagens_para(self.context.bot, self.config.main_group_id), [])

    async def test_pode_ser_desligado(self):
        await self.enviar_e_aprovar(anunciar_entrada=False)
        self.assertEqual(mensagens_para(self.context.bot, self.config.main_group_id), [])
        # O aviso no privado continua valendo.
        privadas = mensagens_para(self.context.bot, USER_ID)
        self.assertTrue(any("aprovada" in m.lower() for m in privadas))

    async def test_solicitacao_expirada_nao_anuncia(self):
        """Se o Telegram recusou a entrada, ninguém entrou — não dar boas-vindas."""
        await self.preencher_tudo()
        await onboarding.on_confirmacao(
            update_falso(query_falsa("conf:sim", chat_id=USER_ID), self.usuario, USER_ID),
            self.context,
        )
        self.context.bot.approve_chat_join_request = AsyncMock(
            side_effect=BadRequest("HIDE_REQUESTER_MISSING")
        )
        self.context.bot.send_message.reset_mock()
        query = query_falsa(f"adm:ap:{USER_ID}", chat_id=self.config.admin_group_id)
        await admin.on_decisao(
            update_falso(query, usuario_falso(777, "ana", "Ana"), self.config.admin_group_id),
            self.context,
        )
        self.assertEqual(mensagens_para(self.context.bot, self.config.main_group_id), [])
        self.assertEqual(self.store.obter(USER_ID).status, STATUS_APROVADO)


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
