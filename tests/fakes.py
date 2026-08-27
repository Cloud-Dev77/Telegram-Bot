"""Dublês usados nos testes: uma planilha em memória e objetos do Telegram.

A planilha falsa implementa a mesma interface de `PlanilhaRepo`, guardando as
linhas em uma lista. Isso permite testar o fluxo inteiro — inclusive reinício
do processo — sem rede, sem credenciais e sem tocar na planilha real.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.models import CABECALHO, NUM_COLUNAS, Solicitacao

_COLUNAS = {letra: indice for indice, letra in enumerate("ABCDEFGHIJKLMNOP")}


class PlanilhaFalsa:
    """Planilha em memória com a mesma interface do repositório real."""

    def __init__(self) -> None:
        self.linhas: list[list[str]] = [list(CABECALHO)]
        self.url = "https://exemplo/planilha"
        self.aba = "Solicitações Telegram"
        self.escritas = 0

    async def conectar(self) -> None:
        pass

    async def testar_escrita(self) -> None:
        pass

    async def carregar_todas(self) -> list[Solicitacao]:
        resultado = []
        for indice, linha in enumerate(self.linhas[1:], start=2):
            solicitacao = Solicitacao.de_linha(linha, indice)
            if solicitacao is not None:
                resultado.append(solicitacao)
        return resultado

    async def anexar(self, solicitacao: Solicitacao) -> int:
        self.linhas.append(solicitacao.para_linha())
        self.escritas += 1
        return len(self.linhas)

    async def atualizar_celulas(self, linha: int, celulas: dict[str, str]) -> None:
        alvo = self.linhas[linha - 1]
        alvo.extend([""] * (NUM_COLUNAS - len(alvo)))
        for coluna, valor in celulas.items():
            alvo[_COLUNAS[coluna]] = valor
        self.escritas += 1

    async def substituir_linha(self, solicitacao: Solicitacao) -> None:
        self.linhas[solicitacao.linha - 1] = solicitacao.para_linha()
        self.escritas += 1

    # -- auxiliares de teste --------------------------------------------------

    def celula(self, linha: int, coluna: str) -> str:
        alvo = self.linhas[linha - 1]
        indice = _COLUNAS[coluna]
        return alvo[indice] if indice < len(alvo) else ""

    def clonar(self) -> "PlanilhaFalsa":
        """Simula reiniciar o bot: mesma planilha, cache zerado."""
        nova = PlanilhaFalsa()
        nova.linhas = [list(linha) for linha in self.linhas]
        return nova


def config_falsa(**extra):
    """Config mínima para os testes, sem carregar variáveis de ambiente."""
    base = dict(
        bot_token="123:TESTE",
        main_group_id=-1001111111111,
        admin_group_id=-1002222222222,
        spreadsheet_id="planilha-teste",
        worksheet_name="Solicitações Telegram",
        google_credentials={"client_email": "teste@exemplo.iam.gserviceaccount.com"},
        webhook_url="",
        webhook_secret="",
        port=8080,
        log_level="CRITICAL",
        keepalive_minutos=0,
        anunciar_entrada=True,
    )
    base.update(extra)
    from bot.config import Config

    return Config(**base)


def usuario_falso(user_id: int = 555, username: str = "fulano", nome: str = "Fulano"):
    return SimpleNamespace(
        id=user_id, username=username, first_name=nome, last_name=None
    )


def contexto_falso(config, store, repo):
    """Contexto do PTB com um bot cujas chamadas de rede são gravadas."""
    bot = AsyncMock()
    bot.username = "bot_teste"
    bot.id = 42
    bot.send_message = AsyncMock(
        return_value=SimpleNamespace(message_id=9001, chat_id=config.admin_group_id)
    )
    return SimpleNamespace(
        bot=bot,
        bot_data={
            "config": config,
            "store": store,
            "repo": repo,
            "grupo_nome": "Comunidade Teste",
        },
    )


def query_falsa(data: str, chat_id: int, texto_html: str = "card"):
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        message=SimpleNamespace(
            chat_id=chat_id, text_html=texto_html, reply_markup=None
        ),
    )
    return query


def update_falso(query=None, usuario=None, chat_id=None):
    return SimpleNamespace(
        callback_query=query,
        effective_user=usuario,
        effective_chat=SimpleNamespace(id=chat_id, type="supergroup"),
        message=None,
    )


def texto_falso(texto: str, usuario, chat_id: int):
    """Update de mensagem de texto no chat privado."""
    return SimpleNamespace(
        callback_query=None,
        effective_user=usuario,
        effective_chat=SimpleNamespace(id=chat_id, type="private"),
        message=SimpleNamespace(text=texto, reply_text=AsyncMock()),
    )



def mensagens_para(bot, chat_id: int) -> list[str]:
    return [
        c.kwargs.get("text", "")
        for c in bot.send_message.await_args_list
        if c.kwargs.get("chat_id") == chat_id
    ]


def join_request_falso(usuario, chat_id: int, titulo: str = "Comunidade Teste"):
    """Update de `chat_join_request`, o evento que inicia todo o fluxo."""
    pedido = SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, title=titulo, type="supergroup"),
        from_user=usuario,
        user_chat_id=usuario.id,
    )
    return SimpleNamespace(
        chat_join_request=pedido,
        callback_query=None,
        effective_user=usuario,
        effective_chat=pedido.chat,
        message=None,
    )
