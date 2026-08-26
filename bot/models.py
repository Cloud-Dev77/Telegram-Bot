"""Modelo de dados de uma solicitação e o mapeamento para a planilha.

A planilha é a única fonte da verdade: cada solicitação ocupa exatamente uma
linha, do primeiro contato até a decisão final. Isso faz com que o bot
sobreviva a reinícios da hospedagem — algo comum em planos gratuitos — sem
perder nenhuma solicitação em andamento.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Status possíveis de uma solicitação (coluna K)
# ---------------------------------------------------------------------------

STATUS_EM_ANDAMENTO = "Em andamento"
STATUS_AGUARDANDO = "Aguardando aprovação"
STATUS_APROVADO = "Aprovado"
STATUS_RECUSADO = "Recusado"
STATUS_SEM_CONTATO = "Sem contato"

# Status que já receberam decisão dos administradores.
STATUS_FINAIS = frozenset({STATUS_APROVADO, STATUS_RECUSADO})

# ---------------------------------------------------------------------------
# Cabeçalho da aba. A ordem define a ordem das colunas — não reordene sem
# ajustar `Solicitacao.para_linha` e `Solicitacao.de_linha` juntos.
# ---------------------------------------------------------------------------

CABECALHO: tuple[str, ...] = (
    "Data/Hora",                      # A
    "Telegram ID",                    # B
    "Username",                       # C
    "Nome no Telegram",               # D
    "Titular de Serventia?",          # E
    "Nome Completo",                  # F
    "Município",                      # G
    "UF",                             # H
    "Nome da Serventia",              # I
    "CNS do Cartório",                # J
    "Status",                         # K
    "Data/Hora da Decisão",           # L
    "Decidido por",                   # M
    "Etapa",                          # N
    "ID Msg Admin",                   # O
)

NUM_COLUNAS = len(CABECALHO)
ULTIMA_COLUNA = "O"

# Índices (0-based) usados na leitura de linhas cruas.
COL_DATA_HORA = 0
COL_USER_ID = 1
COL_USERNAME = 2
COL_NOME_TELEGRAM = 3
COL_TITULAR = 4
COL_NOME_COMPLETO = 5
COL_MUNICIPIO = 6
COL_UF = 7
COL_SERVENTIA = 8
COL_CNS = 9
COL_STATUS = 10
COL_DECIDIDO_EM = 11
COL_DECIDIDO_POR = 12
COL_ETAPA = 13
COL_MSG_ADMIN = 14

# Colunas escritas conforme o candidato responde (chave -> letra da coluna).
COLUNA_POR_CAMPO: dict[str, str] = {
    "titular": "E",
    "nome_completo": "F",
    "municipio": "G",
    "uf": "H",
    "serventia": "I",
    "cns": "J",
}


@dataclass
class Solicitacao:
    """Uma solicitação de entrada, espelhando uma linha da planilha."""

    user_id: int
    linha: int = 0  # número da linha na planilha (1-based); 0 = ainda não gravada
    data_hora: str = ""
    username: str = ""
    nome_telegram: str = ""

    # Respostas das 5 perguntas
    titular: str = ""
    nome_completo: str = ""
    municipio: str = ""
    uf: str = ""
    serventia: str = ""
    cns: str = ""

    # Controle
    status: str = STATUS_EM_ANDAMENTO
    decidido_em: str = ""
    decidido_por: str = ""
    etapa: int = 0
    msg_admin_id: int = 0

    # --- estado derivado -----------------------------------------------------

    @property
    def concluida(self) -> bool:
        """True quando as 5 perguntas já foram respondidas."""
        from .questions import TOTAL_PERGUNTAS

        return self.etapa >= TOTAL_PERGUNTAS

    @property
    def decidida(self) -> bool:
        return self.status in STATUS_FINAIS

    @property
    def elegivel(self) -> bool:
        """False quando a pessoa declarou NÃO ser titular de serventia.

        Não bloqueia nada — quem decide são os administradores. Serve para
        destacar o caso no card, de modo que ninguém aprove por distração.
        """
        from .questions import RESPOSTA_NAO_ELEGIVEL

        return self.titular.casefold() != RESPOSTA_NAO_ELEGIVEL.casefold()

    @property
    def username_exibicao(self) -> str:
        return f"@{self.username}" if self.username else "(sem @usuário)"

    # --- conversão planilha <-> objeto ---------------------------------------

    def para_linha(self) -> list[str]:
        """Serializa para uma linha completa da planilha (colunas A..O)."""
        return [
            self.data_hora,
            str(self.user_id),
            self.username,
            self.nome_telegram,
            self.titular,
            self.nome_completo,
            self.municipio,
            self.uf,
            self.serventia,
            self.cns,
            self.status,
            self.decidido_em,
            self.decidido_por,
            str(self.etapa),
            str(self.msg_admin_id or ""),
        ]

    @classmethod
    def de_linha(cls, valores: list[str], linha: int) -> "Solicitacao | None":
        """Reconstrói a solicitação a partir de uma linha lida da planilha.

        Retorna None para linhas sem Telegram ID válido (linhas em branco ou
        editadas manualmente), que são simplesmente ignoradas.
        """
        celulas = list(valores) + [""] * (NUM_COLUNAS - len(valores))

        def como_int(texto: str) -> int:
            try:
                return int(str(texto).strip())
            except (TypeError, ValueError):
                return 0

        user_id = como_int(celulas[COL_USER_ID])
        if user_id == 0:
            return None

        return cls(
            user_id=user_id,
            linha=linha,
            data_hora=celulas[COL_DATA_HORA].strip(),
            username=celulas[COL_USERNAME].strip().lstrip("@"),
            nome_telegram=celulas[COL_NOME_TELEGRAM].strip(),
            titular=celulas[COL_TITULAR].strip(),
            nome_completo=celulas[COL_NOME_COMPLETO].strip(),
            municipio=celulas[COL_MUNICIPIO].strip(),
            uf=celulas[COL_UF].strip(),
            serventia=celulas[COL_SERVENTIA].strip(),
            cns=celulas[COL_CNS].strip(),
            status=celulas[COL_STATUS].strip() or STATUS_EM_ANDAMENTO,
            decidido_em=celulas[COL_DECIDIDO_EM].strip(),
            decidido_por=celulas[COL_DECIDIDO_POR].strip(),
            etapa=como_int(celulas[COL_ETAPA]),
            msg_admin_id=como_int(celulas[COL_MSG_ADMIN]),
        )

    def resumo_para_candidato(self) -> str:
        """Resumo em HTML mostrado ao candidato antes do envio."""
        from html import escape

        return (
            f"📋 <b>Titular de Serventia:</b> {escape(self.titular)}\n"
            f"👤 <b>Nome:</b> {escape(self.nome_completo)}\n"
            f"📍 <b>Município/UF:</b> {escape(self.municipio)}/{escape(self.uf)}\n"
            f"🏛 <b>Serventia:</b> {escape(self.serventia)}\n"
            f"🪪 <b>CNS:</b> {escape(self.cns)}"
        )
