"""Testes da leitura de configuração.

Nasceram de uma queda real em produção: o Render subiu com `PORT` definida
porém em branco, `os.getenv("PORT", "8080")` devolveu a string vazia em vez do
padrão, e `int("")` derrubou o serviço antes de o bot chegar a existir.

A regra fixada aqui é simples: **variável em branco vale como não definida**.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from bot import config as cfg

CREDENCIAIS = {
    "type": "service_account",
    "client_email": "teste@exemplo.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfalso\n-----END PRIVATE KEY-----\n",
}

AMBIENTE_MINIMO = {
    "BOT_TOKEN": "123:ABC",
    "MAIN_GROUP_ID": "-1001111111111",
    "ADMIN_GROUP_ID": "-1002222222222",
    "SPREADSHEET_ID": "planilha-x",
    "GOOGLE_CREDENTIALS_JSON": json.dumps(CREDENCIAIS),
}


def ambiente(**extra):
    """Ambiente isolado: só o que o teste declarar existe."""
    valores = dict(AMBIENTE_MINIMO)
    valores.update(extra)
    return patch.dict("os.environ", valores, clear=True)


class TestVariavelEmBranco(unittest.TestCase):
    def test_port_em_branco_usa_o_padrao(self):
        """Foi exatamente isto que derrubou o primeiro deploy."""
        with ambiente(PORT=""):
            self.assertEqual(cfg.load_config().port, 8080)

    def test_port_ausente_usa_o_padrao(self):
        with ambiente():
            self.assertEqual(cfg.load_config().port, 8080)

    def test_port_valida_e_respeitada(self):
        with ambiente(PORT="10000"):
            self.assertEqual(cfg.load_config().port, 10000)

    def test_port_invalida_nao_derruba_o_servico(self):
        with ambiente(PORT="abc"):
            self.assertEqual(cfg.load_config().port, 8080)

    def test_worksheet_em_branco_usa_o_padrao(self):
        with ambiente(WORKSHEET_NAME=""):
            self.assertEqual(
                cfg.load_config().worksheet_name, "Solicitações Telegram"
            )

    def test_log_level_em_branco_usa_o_padrao(self):
        with ambiente(LOG_LEVEL=""):
            self.assertEqual(cfg.load_config().log_level, "INFO")

    def test_espacos_equivalem_a_em_branco(self):
        with ambiente(PORT="   ", WORKSHEET_NAME="  "):
            config = cfg.load_config()
            self.assertEqual(config.port, 8080)
            self.assertEqual(config.worksheet_name, "Solicitações Telegram")


class TestAutoPing(unittest.TestCase):
    def test_padrao_e_10_minutos(self):
        with ambiente():
            self.assertEqual(cfg.load_config().keepalive_minutos, 10)

    def test_zero_desliga(self):
        with ambiente(KEEPALIVE_MINUTES="0"):
            self.assertEqual(cfg.load_config().keepalive_minutos, 0)

    def test_valor_personalizado(self):
        with ambiente(KEEPALIVE_MINUTES="5"):
            self.assertEqual(cfg.load_config().keepalive_minutos, 5)

    def test_em_branco_usa_o_padrao(self):
        with ambiente(KEEPALIVE_MINUTES=""):
            self.assertEqual(cfg.load_config().keepalive_minutos, 10)


class TestModoDeExecucao(unittest.TestCase):
    def test_sem_url_publica_fica_em_polling(self):
        with ambiente():
            self.assertFalse(cfg.load_config().modo_webhook)

    def test_webhook_url_em_branco_cai_para_a_url_do_render(self):
        """No Render a variável nasce vazia; quem vale é RENDER_EXTERNAL_URL."""
        with ambiente(WEBHOOK_URL="", RENDER_EXTERNAL_URL="https://x.onrender.com"):
            config = cfg.load_config()
            self.assertTrue(config.modo_webhook)
            self.assertEqual(config.webhook_url, "https://x.onrender.com")

    def test_barra_final_e_removida(self):
        with ambiente(WEBHOOK_URL="https://x.onrender.com/"):
            self.assertEqual(cfg.load_config().webhook_url, "https://x.onrender.com")

    def test_webhook_url_tem_prioridade_sobre_a_do_render(self):
        with ambiente(
            WEBHOOK_URL="https://meu.dominio", RENDER_EXTERNAL_URL="https://x.onrender.com"
        ):
            self.assertEqual(cfg.load_config().webhook_url, "https://meu.dominio")


class TestObrigatorias(unittest.TestCase):
    def test_token_em_branco_e_tratado_como_ausente(self):
        with ambiente(BOT_TOKEN=""):
            with self.assertRaises(cfg.ConfigError) as ctx:
                cfg.load_config()
            self.assertIn("BOT_TOKEN", str(ctx.exception))

    def test_id_de_grupo_nao_numerico_explica_o_formato(self):
        with ambiente(MAIN_GROUP_ID="abc"):
            with self.assertRaises(cfg.ConfigError) as ctx:
                cfg.load_config()
            self.assertIn("número inteiro", str(ctx.exception))

    def test_grupos_iguais_sao_recusados(self):
        with ambiente(ADMIN_GROUP_ID="-1001111111111"):
            with self.assertRaises(cfg.ConfigError):
                cfg.load_config()

    def test_json_do_google_invalido_da_mensagem_util(self):
        with ambiente(GOOGLE_CREDENTIALS_JSON="{isto nao e json"):
            with self.assertRaises(cfg.ConfigError) as ctx:
                cfg.load_config()
            self.assertIn("GOOGLE_CREDENTIALS_JSON", str(ctx.exception))

    def test_json_do_google_incompleto_aponta_o_campo(self):
        with ambiente(GOOGLE_CREDENTIALS_JSON=json.dumps({"type": "service_account"})):
            with self.assertRaises(cfg.ConfigError) as ctx:
                cfg.load_config()
            self.assertIn("private_key", str(ctx.exception))


class TestPlanilha(unittest.TestCase):
    def test_aceita_url_completa(self):
        url = "https://docs.google.com/spreadsheets/d/ABC123xyz_-/edit?gid=1#gid=1"
        with ambiente(SPREADSHEET_ID=url):
            self.assertEqual(cfg.load_config().spreadsheet_id, "ABC123xyz_-")

    def test_aceita_id_puro(self):
        with ambiente(SPREADSHEET_ID="ABC123xyz_-"):
            self.assertEqual(cfg.load_config().spreadsheet_id, "ABC123xyz_-")


if __name__ == "__main__":
    unittest.main()
