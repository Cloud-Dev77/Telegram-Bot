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
    "Categoria",                      # E
    "Nome Completo",                  # F
    "UF",                             # G
    "Município",                      # H
    "Unidade / Empresa / Entidade",   # I
    "Código de Registro",             # J
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
COL_CATEGORIA = 4
COL_NOME_COMPLETO = 5
COL_UF = 6
COL_MUNICIPIO = 7
COL_UNIDADE = 8
COL_REGISTRO = 9
COL_STATUS = 10
COL_DECIDIDO_EM = 11
COL_DECIDIDO_POR = 12
COL_ETAPA = 13
COL_MSG_ADMIN = 14

# Colunas escritas conforme o candidato responde (chave -> letra da coluna).
COLUNA_POR_CAMPO: dict[str, str] = {
    "categoria": "E",
    "nome_completo": "F",
    "uf": "G",
    "municipio": "H",
    "unidade": "I",
    "registro": "J",
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
    categoria: str = ""
    nome_completo: str = ""
    uf: str = ""
    municipio: str = ""
    unidade: str = ""
    registro: str = ""

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
            self.categoria,
            self.nome_completo,
            self.uf,
            self.municipio,
            self.unidade,
            self.registro,
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
            categoria=celulas[COL_CATEGORIA].strip(),
            nome_completo=celulas[COL_NOME_COMPLETO].strip(),
            uf=celulas[COL_UF].strip(),
            municipio=celulas[COL_MUNICIPIO].strip(),
            unidade=celulas[COL_UNIDADE].strip(),
            registro=celulas[COL_REGISTRO].strip(),
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
            f"🏷 <b>Categoria:</b> {escape(self.categoria)}\n"
            f"👤 <b>Nome:</b> {escape(self.nome_completo)}\n"
            f"📍 <b>Local:</b> {escape(self.municipio)} / {escape(self.uf)}\n"
            f"🏢 <b>Unidade:</b> {escape(self.unidade)}\n"
            f"🪪 <b>Registro:</b> {escape(self.registro)}"
        )
