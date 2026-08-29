"""Camada de acesso ao Google Planilhas via Service Account.

A biblioteca `gspread` é síncrona. Como o bot é assíncrono, toda chamada de
rede é executada em uma thread separada (`asyncio.to_thread`) para não
bloquear o laço de eventos — caso contrário, uma escrita lenta na planilha
travaria o bot inteiro.

Todas as escritas usam `value_input_option="RAW"`, de modo que uma resposta
começando com "=" seja gravada como texto e nunca interpretada como fórmula.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from .models import CABECALHO, NUM_COLUNAS, ULTIMA_COLUNA, Solicitacao

logger = logging.getLogger(__name__)

ESCOPOS = ["https://www.googleapis.com/auth/spreadsheets"]

# Tentativas em caso de erro temporário do Google (cota, indisponibilidade).
MAX_TENTATIVAS = 4
ESPERA_BASE_S = 1.5
CODIGOS_TEMPORARIOS = {429, 500, 502, 503, 504}


class SheetsError(RuntimeError):
    """Falha ao falar com o Google Planilhas."""


class PlanilhaRepo:
    """Leitura e escrita da aba de solicitações."""

    def __init__(
        self,
        credenciais: dict[str, Any],
        spreadsheet_id: str,
        worksheet_name: str,
    ) -> None:
        self._credenciais = credenciais
        self._spreadsheet_id = spreadsheet_id
        self._worksheet_name = worksheet_name
        self._ws: gspread.Worksheet | None = None
        self._url = ""
        self._abas_existentes: list[str] = []
        # Serializa as escritas: o Google aplica cota por minuto e a ordem das
        # atualizações de uma mesma linha precisa ser preservada.
        self._lock = asyncio.Lock()

    # -- propriedades ---------------------------------------------------------

    @property
    def url(self) -> str:
        return self._url or f"https://docs.google.com/spreadsheets/d/{self._spreadsheet_id}"

    @property
    def aba(self) -> str:
        return self._worksheet_name

    @property
    def abas_existentes(self) -> list[str]:
        """Todas as abas da planilha, preenchido em `conectar()`."""
        return list(self._abas_existentes)

    # -- conexão --------------------------------------------------------------

    async def conectar(self) -> None:
        """Abre a planilha, cria a aba se necessário e garante o cabeçalho."""
        await asyncio.to_thread(self._conectar_sync)
        logger.info(
            "Planilha conectada: aba %r (%s)", self._worksheet_name, self.url
        )

    def _conectar_sync(self) -> None:
        creds = Credentials.from_service_account_info(
            self._credenciais, scopes=ESCOPOS
        )
        cliente = gspread.authorize(creds)

        try:
            planilha = cliente.open_by_key(self._spreadsheet_id)
        except gspread.SpreadsheetNotFound as exc:
            raise SheetsError(
                "Planilha não encontrada. Confira o SPREADSHEET_ID e, "
                "principalmente, compartilhe a planilha (como Editor) com o "
                f"e-mail da conta de serviço: {self._credenciais.get('client_email')}"
            ) from exc
        except gspread.exceptions.APIError as exc:
            if getattr(exc.response, "status_code", None) == 403:
                raise SheetsError(
                    "Acesso negado à planilha. Compartilhe-a como Editor com o "
                    f"e-mail {self._credenciais.get('client_email')} e confirme "
                    "que a Google Sheets API está ativada no projeto do Google Cloud."
                ) from exc
            raise

        self._url = planilha.url

        # Registrar as abas existentes ajuda no diagnóstico e deixa explícito
        # que o bot mexe em uma aba só — importante quando a planilha também
        # recebe respostas de um Formulário Google, cuja aba é reorganizada
        # pelo próprio Google e não pode ser usada como banco de dados.
        self._abas_existentes = [aba.title for aba in planilha.worksheets()]
        logger.info(
            "Abas na planilha: %s", ", ".join(repr(a) for a in self._abas_existentes)
        )

        try:
            ws = planilha.worksheet(self._worksheet_name)
        except gspread.WorksheetNotFound:
            logger.info("Aba %r não existe — criando.", self._worksheet_name)
            ws = planilha.add_worksheet(
                title=self._worksheet_name, rows=2000, cols=NUM_COLUNAS
            )

        self._ws = ws
        self._garantir_cabecalho()

    def _garantir_cabecalho(self) -> None:
        """Escreve a primeira linha se ela estiver vazia ou desatualizada."""
        assert self._ws is not None
        atual = self._ws.row_values(1)
        if [c.strip() for c in atual[:NUM_COLUNAS]] == list(CABECALHO):
            return
        logger.info("Gravando cabeçalho na aba %r.", self._worksheet_name)
        self._ws.update(
            range_name=f"A1:{ULTIMA_COLUNA}1",
            values=[list(CABECALHO)],
            value_input_option="RAW",
        )
        self._ws.freeze(rows=1)
        self._ws.format(
            f"A1:{ULTIMA_COLUNA}1",
            {"textFormat": {"bold": True}},
        )

    def _worksheet(self) -> gspread.Worksheet:
        if self._ws is None:
            raise SheetsError(
                "Planilha não conectada. Chame `conectar()` antes de usar."
            )
        return self._ws

    # -- utilidades -----------------------------------------------------------

    async def _com_retry(self, funcao, *args, **kwargs):
        """Executa uma chamada síncrona do gspread, repetindo em falhas temporárias.

        Cada tentativa recebe uma CÓPIA dos argumentos, e isso não é zelo
        excessivo: `Worksheet.batch_update` do gspread altera os dicionários
        recebidos no lugar, prefixando cada intervalo com o nome da aba
        (`G57` -> `'Minha Aba'!G57`). Reenviar a mesma lista numa segunda
        tentativa faria o gspread prefixar de novo, gerando
        `'Minha Aba'!'Minha Aba'!G57` — que o Google recusa com 400.

        O sintoma era traiçoeiro: só aparecia quando o Google devolvia um erro
        temporário e o retry entrava em ação, e o 400 seguinte já não é
        temporário, então a resposta daquele candidato se perdia.
        """
        ultimo_erro: Exception | None = None
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            try:
                return await asyncio.to_thread(
                    funcao, *copy.deepcopy(args), **copy.deepcopy(kwargs)
                )
            except gspread.exceptions.APIError as exc:
                codigo = getattr(exc.response, "status_code", None)
                if codigo not in CODIGOS_TEMPORARIOS or tentativa == MAX_TENTATIVAS:
                    raise
                ultimo_erro = exc
                espera = ESPERA_BASE_S * (2 ** (tentativa - 1))
                logger.warning(
                    "Google Planilhas respondeu %s. Tentativa %d/%d em %.1fs.",
                    codigo,
                    tentativa,
                    MAX_TENTATIVAS,
                    espera,
                )
                await asyncio.sleep(espera)
        raise SheetsError("Falha ao acessar o Google Planilhas.") from ultimo_erro

    @staticmethod
    def _linha_do_append(resposta: dict) -> int:
        """Extrai o número da linha criada a partir da resposta do append."""
        intervalo = (resposta or {}).get("updates", {}).get("updatedRange", "")
        match = re.search(r"![A-Z]+(\d+)", intervalo)
        if not match:
            raise SheetsError(
                f"Não consegui identificar a linha criada na planilha ({intervalo!r})."
            )
        return int(match.group(1))

    # -- operações ------------------------------------------------------------

    async def carregar_todas(self) -> list[Solicitacao]:
        """Lê a aba inteira. Usado na inicialização e nas estatísticas."""
        valores = await self._com_retry(self._worksheet().get_all_values)
        solicitacoes: list[Solicitacao] = []
        for indice, linha in enumerate(valores[1:], start=2):  # pula o cabeçalho
            solicitacao = Solicitacao.de_linha(linha, indice)
            if solicitacao is not None:
                solicitacoes.append(solicitacao)
        return solicitacoes

    async def anexar(self, solicitacao: Solicitacao) -> int:
        """Cria uma linha nova e devolve o número dela."""
        async with self._lock:
            resposta = await self._com_retry(
                self._worksheet().append_row,
                solicitacao.para_linha(),
                value_input_option="RAW",
                insert_data_option="INSERT_ROWS",
                table_range="A1",
            )
        linha = self._linha_do_append(resposta)
        logger.info(
            "Solicitação de %s gravada na linha %d.", solicitacao.user_id, linha
        )
        return linha

    async def atualizar_celulas(self, linha: int, celulas: dict[str, str]) -> None:
        """Atualiza células avulsas de uma linha. `celulas` é {letra: valor}."""
        if not celulas or linha <= 1:
            return
        dados = [
            {"range": f"{coluna}{linha}", "values": [[valor]]}
            for coluna, valor in celulas.items()
        ]
        async with self._lock:
            await self._com_retry(
                self._worksheet().batch_update, dados, value_input_option="RAW"
            )

    async def substituir_linha(self, solicitacao: Solicitacao) -> None:
        """Reescreve a linha inteira (usado ao reiniciar uma solicitação)."""
        if solicitacao.linha <= 1:
            return
        async with self._lock:
            await self._com_retry(
                self._worksheet().update,
                range_name=f"A{solicitacao.linha}:{ULTIMA_COLUNA}{solicitacao.linha}",
                values=[solicitacao.para_linha()],
                value_input_option="RAW",
            )

    async def testar_escrita(self) -> None:
        """Verificação de permissão feita na inicialização.

        Reescreve o próprio cabeçalho: se a conta de serviço tiver apenas
        acesso de leitura, o erro aparece na subida do bot e não no meio de um
        atendimento a um candidato.
        """
        try:
            await self._com_retry(
                self._worksheet().update,
                range_name=f"A1:{ULTIMA_COLUNA}1",
                values=[list(CABECALHO)],
                value_input_option="RAW",
            )
        except gspread.exceptions.APIError as exc:
            raise SheetsError(
                "A conta de serviço consegue ler, mas não escrever na planilha. "
                "Compartilhe-a novamente com permissão de <b>Editor</b> para "
                f"{self._credenciais.get('client_email')}."
            ) from exc
