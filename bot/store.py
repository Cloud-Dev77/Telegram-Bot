"""Estado das solicitações: cache em memória com escrita imediata na planilha.

Regras que este módulo garante:

* Uma solicitação por Telegram ID, identificada sempre pelo ID — nunca pelo
  @username, que o usuário pode trocar no meio do processo.
* Toda mudança vai para a planilha na hora ("gravação em tempo real"), de modo
  que reiniciar a hospedagem não perde nenhuma solicitação em andamento.
* Um `asyncio.Lock` por usuário serializa as operações. É o que impede que
  dois cliques rápidos em [Aprovar]/[Recusar], ou duas respostas enviadas
  quase juntas, produzam gravações duplicadas ou fora de ordem.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from .models import (
    COLUNA_POR_CAMPO,
    STATUS_AGUARDANDO,
    STATUS_APROVADO,
    STATUS_EM_ANDAMENTO,
    STATUS_FINAIS,
    STATUS_RECUSADO,
    STATUS_SEM_CONTATO,
    Solicitacao,
)
from .sheets import PlanilhaRepo
from .utils import agora_str

logger = logging.getLogger(__name__)


class Store:
    """Fachada única para ler e alterar solicitações."""

    def __init__(self, repo: PlanilhaRepo) -> None:
        self._repo = repo
        self._cache: dict[int, Solicitacao] = {}
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    # -- ciclo de vida --------------------------------------------------------

    async def carregar(self) -> None:
        """Reidrata o cache a partir da planilha, na subida do bot.

        Se um usuário tiver mais de uma linha (por exemplo, foi recusado e
        solicitou entrada de novo), vale a linha mais recente.
        """
        solicitacoes = await self._repo.carregar_todas()
        self._cache = {}
        for solicitacao in solicitacoes:
            anterior = self._cache.get(solicitacao.user_id)
            if anterior is None or solicitacao.linha > anterior.linha:
                self._cache[solicitacao.user_id] = solicitacao
        abertas = sum(
            1 for s in self._cache.values() if s.status == STATUS_EM_ANDAMENTO
        )
        logger.info(
            "Cache carregado: %d solicitações (%d em andamento).",
            len(self._cache),
            abertas,
        )

    def lock(self, user_id: int) -> asyncio.Lock:
        """Trava exclusiva do usuário. Use em toda operação de escrita."""
        return self._locks[user_id]

    # -- leitura --------------------------------------------------------------

    def obter(self, user_id: int) -> Solicitacao | None:
        return self._cache.get(user_id)

    def estatisticas(self) -> dict[str, int]:
        contagem = {
            STATUS_EM_ANDAMENTO: 0,
            STATUS_AGUARDANDO: 0,
            STATUS_APROVADO: 0,
            STATUS_RECUSADO: 0,
        }
        for solicitacao in self._cache.values():
            if solicitacao.status in contagem:
                contagem[solicitacao.status] += 1
        return contagem

    # -- escrita --------------------------------------------------------------

    async def criar_ou_reiniciar(
        self, user_id: int, username: str, nome_telegram: str
    ) -> Solicitacao:
        """Prepara uma solicitação limpa para o usuário.

        * Solicitação ainda aberta -> reaproveita a mesma linha, zerando as
          respostas. Evita poluir a planilha quando alguém cancela e volta.
        * Solicitação já decidida -> cria uma linha nova, preservando o
          histórico da decisão anterior.
        """
        existente = self._cache.get(user_id)
        agora = agora_str()

        if existente is not None and existente.status not in STATUS_FINAIS:
            solicitacao = Solicitacao(
                user_id=user_id,
                linha=existente.linha,
                data_hora=agora,
                username=username,
                nome_telegram=nome_telegram,
                status=STATUS_EM_ANDAMENTO,
            )
            self._cache[user_id] = solicitacao
            await self._repo.substituir_linha(solicitacao)
            logger.info(
                "Solicitação de %s reiniciada na linha %d.", user_id, solicitacao.linha
            )
            return solicitacao

        solicitacao = Solicitacao(
            user_id=user_id,
            data_hora=agora,
            username=username,
            nome_telegram=nome_telegram,
            status=STATUS_EM_ANDAMENTO,
        )
        solicitacao.linha = await self._repo.anexar(solicitacao)
        self._cache[user_id] = solicitacao
        return solicitacao

    async def salvar_resposta(
        self, solicitacao: Solicitacao, valores: dict[str, str], nova_etapa: int
    ) -> None:
        """Grava as respostas validadas e avança a etapa."""
        celulas: dict[str, str] = {}
        for campo, valor in valores.items():
            setattr(solicitacao, campo, valor)
            coluna = COLUNA_POR_CAMPO.get(campo)
            if coluna:
                celulas[coluna] = valor

        solicitacao.etapa = nova_etapa
        celulas["N"] = str(nova_etapa)
        await self._repo.atualizar_celulas(solicitacao.linha, celulas)

    async def marcar_aguardando(
        self, solicitacao: Solicitacao, msg_admin_id: int
    ) -> None:
        """Cadastro completo, card enviado ao grupo de administradores."""
        solicitacao.status = STATUS_AGUARDANDO
        solicitacao.msg_admin_id = msg_admin_id
        await self._repo.atualizar_celulas(
            solicitacao.linha, {"K": STATUS_AGUARDANDO, "O": str(msg_admin_id)}
        )

    async def marcar_decisao(
        self, solicitacao: Solicitacao, aprovado: bool, decidido_por: str
    ) -> None:
        solicitacao.status = STATUS_APROVADO if aprovado else STATUS_RECUSADO
        solicitacao.decidido_em = agora_str()
        solicitacao.decidido_por = decidido_por
        await self._repo.atualizar_celulas(
            solicitacao.linha,
            {
                "K": solicitacao.status,
                "L": solicitacao.decidido_em,
                "M": decidido_por,
            },
        )
        logger.info(
            "Solicitação de %s marcada como %s por %s.",
            solicitacao.user_id,
            solicitacao.status,
            decidido_por,
        )

    async def marcar_sem_contato(self, solicitacao: Solicitacao) -> None:
        """O bot não conseguiu iniciar a conversa privada com o candidato."""
        solicitacao.status = STATUS_SEM_CONTATO
        await self._repo.atualizar_celulas(
            solicitacao.linha, {"K": STATUS_SEM_CONTATO}
        )

    async def marcar_status(self, solicitacao: Solicitacao, status: str) -> None:
        solicitacao.status = status
        await self._repo.atualizar_celulas(solicitacao.linha, {"K": status})
