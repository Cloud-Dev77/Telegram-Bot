"""Ponto de entrada do bot.

    python main.py

O modo de execução (polling ou webhook) é escolhido automaticamente a partir
das variáveis de ambiente — veja `bot/app.py`.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from bot.app import build_application, run_polling, run_webhook
from bot.config import ConfigError, configurar_logging, load_config
from bot.sheets import PlanilhaRepo, SheetsError
from bot.store import Store

logger = logging.getLogger("bot.main")


async def _executar() -> None:
    config = load_config()
    configurar_logging(config.log_level)

    logger.info("Conta de serviço em uso: %s", config.service_account_email)

    # A planilha é preparada ANTES de o bot ficar no ar. Se as credenciais ou
    # o compartilhamento estiverem errados, o erro aparece agora — e não no
    # meio do atendimento a um candidato.
    repo = PlanilhaRepo(
        credenciais=config.google_credentials,
        spreadsheet_id=config.spreadsheet_id,
        worksheet_name=config.worksheet_name,
    )
    await repo.conectar()
    await repo.testar_escrita()

    store = Store(repo)
    await store.carregar()

    application = build_application(config, store, repo)

    if config.modo_webhook:
        await run_webhook(application, config)
    else:
        await run_polling(application)


def main() -> int:
    configurar_logging()
    try:
        asyncio.run(_executar())
    except ConfigError as exc:
        print(f"\n❌ Erro de configuração\n\n{exc}\n", file=sys.stderr)
        return 2
    except SheetsError as exc:
        print(f"\n❌ Erro no Google Planilhas\n\n{exc}\n", file=sys.stderr)
        return 3
    except (KeyboardInterrupt, SystemExit):
        logger.info("Encerrado pelo usuário.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
