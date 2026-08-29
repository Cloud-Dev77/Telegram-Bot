"""Testes da repetição de chamadas ao Google Planilhas.

Nasceram de um erro em produção:

    APIError [400]: Unable to parse range:
    'Solicitações Telegram'!'Solicitações Telegram'!G57

O `Worksheet.batch_update` do gspread altera no lugar os dicionários que
recebe, prefixando cada intervalo com o nome da aba. Ao repetir a chamada
após uma falha temporária, a mesma lista — já prefixada — era enviada de
novo, o gspread prefixava outra vez, e o Google recusava com 400.

Como 400 não é erro temporário, a repetição não ajudava: a exceção subia e a
resposta daquele candidato se perdia. O sintoma era intermitente porque só
aparecia quando o Google devolvia 429/5xx e o retry entrava em ação.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock

import gspread
from gspread.utils import absolute_range_name

from bot.sheets import PlanilhaRepo

ABA = "Solicitações Telegram"


def erro_api(codigo: int) -> gspread.exceptions.APIError:
    resposta = Mock()
    resposta.status_code = codigo
    resposta.json.return_value = {"error": {"code": codigo, "message": "simulado"}}
    return gspread.exceptions.APIError(resposta)


class GspreadFalso:
    """Reproduz o gspread de verdade: muta o `data` recebido, no lugar.

    Ver gspread/worksheet.py, em `batch_update`:
        for values in data:
            values["range"] = absolute_range_name(self.title, values["range"])
    """

    def __init__(self, falhas_iniciais: int = 0, codigo: int = 429) -> None:
        self.falhas_iniciais = falhas_iniciais
        self.codigo = codigo
        self.intervalos_recebidos: list[str] = []

    def batch_update(self, data, value_input_option=None):
        for values in data:
            values["range"] = absolute_range_name(ABA, values["range"])
        self.intervalos_recebidos.append(data[0]["range"])

        if len(self.intervalos_recebidos) <= self.falhas_iniciais:
            raise erro_api(self.codigo)
        return {"ok": True}


class TestRepeticaoNaoCorrompeOsArgumentos(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = PlanilhaRepo(
            credenciais={"client_email": "x@y.iam.gserviceaccount.com"},
            spreadsheet_id="planilha",
            worksheet_name=ABA,
        )

    async def test_sem_falha_o_intervalo_sai_correto(self):
        falso = GspreadFalso()
        dados = [{"range": "G57", "values": [["Campinas"]]}]
        await self.repo._com_retry(falso.batch_update, dados, value_input_option="RAW")
        self.assertEqual(falso.intervalos_recebidos, [f"'{ABA}'!G57"])

    async def test_apos_uma_falha_o_intervalo_nao_duplica(self):
        """O caso exato do erro em produção."""
        falso = GspreadFalso(falhas_iniciais=1)
        dados = [{"range": "G57", "values": [["Campinas"]]}]
        await self.repo._com_retry(falso.batch_update, dados, value_input_option="RAW")

        self.assertEqual(len(falso.intervalos_recebidos), 2)
        for intervalo in falso.intervalos_recebidos:
            self.assertEqual(
                intervalo.count(ABA), 1, f"nome da aba repetido em {intervalo!r}"
            )

    async def test_varias_falhas_seguidas_continuam_corretas(self):
        falso = GspreadFalso(falhas_iniciais=3)
        dados = [{"range": "K57", "values": [["Aprovado"]]}]
        await self.repo._com_retry(falso.batch_update, dados, value_input_option="RAW")

        self.assertEqual(len(falso.intervalos_recebidos), 4)
        self.assertTrue(
            all(i == f"'{ABA}'!K57" for i in falso.intervalos_recebidos),
            falso.intervalos_recebidos,
        )

    async def test_a_lista_do_chamador_nao_e_alterada(self):
        """Quem chamou continua dono dos próprios dados."""
        falso = GspreadFalso(falhas_iniciais=1)
        dados = [{"range": "G57", "values": [["Campinas"]]}]
        await self.repo._com_retry(falso.batch_update, dados, value_input_option="RAW")
        self.assertEqual(dados, [{"range": "G57", "values": [["Campinas"]]}])

    async def test_erro_definitivo_nao_e_repetido(self):
        """400 não é temporário: repetir não conserta e só atrasa a resposta."""
        falso = GspreadFalso(falhas_iniciais=99, codigo=400)
        with self.assertRaises(gspread.exceptions.APIError):
            await self.repo._com_retry(
                falso.batch_update, [{"range": "G57", "values": [["x"]]}]
            )
        self.assertEqual(len(falso.intervalos_recebidos), 1)


if __name__ == "__main__":
    unittest.main()
