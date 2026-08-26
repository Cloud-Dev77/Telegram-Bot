"""Testes do servidor HTTP usado em produção.

Esta é a porta de entrada do bot na hospedagem: tudo que o Telegram envia
passa por aqui. Um erro nesta camada não aparece em nenhum outro teste — o
bot simplesmente fica mudo depois do deploy.
"""

from __future__ import annotations

import unittest

from starlette.testclient import TestClient

from bot.app import _montar_servidor, build_application
from bot.store import Store
from tests.fakes import PlanilhaFalsa, config_falsa

SEGREDO = "segredo-de-teste-123"

# Atualização mínima válida: uma mensagem no chat privado.
UPDATE_EXEMPLO = {
    "update_id": 1,
    "message": {
        "message_id": 10,
        "date": 1700000000,
        "chat": {"id": 555, "type": "private"},
        "from": {"id": 555, "is_bot": False, "first_name": "Fulano"},
        "text": "SP, Campinas",
    },
}


class BaseServidor(unittest.IsolatedAsyncioTestCase):
    segredo = SEGREDO

    async def asyncSetUp(self):
        self.planilha = PlanilhaFalsa()
        self.store = Store(self.planilha)
        await self.store.carregar()
        self.config = config_falsa(
            webhook_url="https://exemplo.onrender.com",
            webhook_secret=self.segredo,
        )
        self.app = build_application(self.config, self.store, self.planilha)
        self.servidor = _montar_servidor(self.app, self.config)
        self.client = TestClient(self.servidor)


class TestHealth(BaseServidor):
    def test_responde_200_com_json(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertEqual(corpo["status"], "ok")
        self.assertIn("solicitacoes", corpo)

    def test_raiz_tambem_serve_de_health(self):
        """O monitor externo pode apontar para a raiz do serviço."""
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_nao_quebra_antes_de_preparar(self):
        """Antes de `preparar()`, o bot ainda não tem username.

        Se esta rota levantasse exceção, o Render marcaria o serviço como
        doente e entraria em laço de reinício durante a própria subida.
        """
        self.assertNotIn("bot_username", self.app.bot_data)
        corpo = self.client.get("/health").json()
        self.assertEqual(corpo["bot"], "")
        self.assertFalse(corpo["pronto"])

    def test_reporta_pronto_depois_de_preparar(self):
        self.app.bot_data["bot_username"] = "Validador_Titular_bot"
        corpo = self.client.get("/health").json()
        self.assertEqual(corpo["bot"], "Validador_Titular_bot")
        self.assertTrue(corpo["pronto"])


class TestRotaTelegram(BaseServidor):
    def _post(self, corpo=None, segredo=SEGREDO, cru=None):
        cabecalhos = {}
        if segredo is not None:
            cabecalhos["X-Telegram-Bot-Api-Secret-Token"] = segredo
        if cru is not None:
            return self.client.post("/telegram", content=cru, headers=cabecalhos)
        return self.client.post("/telegram", json=corpo, headers=cabecalhos)

    def test_aceita_atualizacao_valida_e_enfileira(self):
        r = self._post(UPDATE_EXEMPLO)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.app.update_queue.qsize(), 1)

    def test_recusa_segredo_errado(self):
        r = self._post(UPDATE_EXEMPLO, segredo="segredo-errado")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.app.update_queue.qsize(), 0)

    def test_recusa_sem_segredo(self):
        r = self._post(UPDATE_EXEMPLO, segredo=None)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.app.update_queue.qsize(), 0)

    def test_recusa_corpo_invalido(self):
        r = self._post(cru=b"isto nao e json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.app.update_queue.qsize(), 0)

    def test_get_na_rota_do_telegram_nao_e_permitido(self):
        self.assertEqual(self.client.get("/telegram").status_code, 405)

    def test_json_valido_mas_sem_update_nao_enfileira(self):
        """Devolver 5xx aqui faria o Telegram reenviar a mesma carga sem fim."""
        r = self._post({"foo": "bar"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.app.update_queue.qsize(), 0)

    def test_carga_hostil_nao_derruba_a_rota(self):
        """Nenhum corpo estranho pode virar 5xx.

        O que for tecnicamente parseável pode até entrar na fila — nenhum
        handler casa com ele e a atualização morre ali. O que não pode
        acontecer é erro 500, porque o Telegram reenviaria em laço.
        """
        for corpo in ([], "texto", 42, {"update_id": "nao-e-numero"}, {"message": {}}):
            with self.subTest(corpo=corpo):
                r = self._post(corpo)
                self.assertLess(r.status_code, 500, f"5xx para {corpo!r}")


class TestSemSegredoConfigurado(BaseServidor):
    """Sem WEBHOOK_SECRET o bot aceita qualquer origem — comportamento
    documentado, com aviso na subida. Fixado em teste para que ninguém o
    mude sem perceber."""

    segredo = ""

    def test_aceita_sem_cabecalho(self):
        r = self.client.post("/telegram", json=UPDATE_EXEMPLO)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.app.update_queue.qsize(), 1)


if __name__ == "__main__":
    unittest.main()
