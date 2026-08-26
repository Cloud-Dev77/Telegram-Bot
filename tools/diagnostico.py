"""Verificação da instalação — rode antes de colocar o bot no ar.

    python tools/diagnostico.py

Confere, em ordem:

1. o token do bot;
2. os IDs de chat visíveis (ajuda a descobrir o número dos grupos);
3. se o bot é administrador do grupo principal com a permissão certa;
4. o acesso à planilha pela conta de serviço, incluindo escrita.

Cada falha vem com a instrução do que corrigir. Nada é alterado no grupo nem
na planilha, exceto a reescrita do próprio cabeçalho no teste de escrita.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Bot  # noqa: E402
from telegram.constants import ChatMemberStatus  # noqa: E402
from telegram.error import InvalidToken, TelegramError  # noqa: E402

from bot.config import TIMEZONE, ConfigError, _carregar_credenciais_google  # noqa: E402
from bot.sheets import PlanilhaRepo, SheetsError  # noqa: E402

OK = "  [OK]  "
ERRO = "  [ERRO]"
AVISO = "  [!]   "
INFO = "  [ ]   "

falhas = 0


def titulo(texto: str) -> None:
    print(f"\n{texto}\n" + "-" * len(texto))


def falhar(mensagem: str) -> None:
    global falhas
    falhas += 1
    print(f"{ERRO} {mensagem}")


async def checar_telegram() -> Bot | None:
    titulo("1. Token do bot")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        falhar("BOT_TOKEN não definido. Coloque no arquivo .env.")
        return None

    bot = Bot(token)
    try:
        await bot.initialize()
        eu = await bot.get_me()
    except InvalidToken:
        falhar("Token inválido. Copie novamente a linha enviada pelo @BotFather.")
        return None
    except TelegramError as exc:
        falhar(f"Não consegui falar com o Telegram: {exc}")
        return None

    print(f"{OK} Bot @{eu.username} (id {eu.id})")
    return bot


async def listar_chats(bot: Bot) -> None:
    titulo("2. Chats visíveis (para descobrir os IDs dos grupos)")
    try:
        atualizacoes = await bot.get_updates(limit=100, timeout=0)
    except TelegramError as exc:
        print(f"{AVISO} Não consegui ler as atualizações: {exc}")
        print(f"{INFO} Se o bot já estiver rodando com webhook, isso é esperado.")
        return

    vistos: dict[int, str] = {}
    for atualizacao in atualizacoes:
        chat = atualizacao.effective_chat
        if chat is not None:
            vistos[chat.id] = f"{chat.type}: {chat.title or chat.full_name or ''}"

    if not vistos:
        print(f"{INFO} Nenhum chat recente.")
        print(f"{INFO} Adicione o bot ao grupo e envie /id lá dentro — ou apenas")
        print(f"{INFO} mande qualquer mensagem no grupo e rode este script de novo.")
        return

    for chat_id, descricao in vistos.items():
        print(f"{INFO} {chat_id}  ->  {descricao}")


async def checar_grupo_principal(bot: Bot) -> None:
    titulo("3. Grupo principal")
    bruto = os.getenv("MAIN_GROUP_ID", "").strip()
    if not bruto:
        falhar("MAIN_GROUP_ID não definido.")
        return
    try:
        grupo_id = int(bruto)
    except ValueError:
        falhar(f"MAIN_GROUP_ID deve ser um número (recebido: {bruto!r}).")
        return

    try:
        chat = await bot.get_chat(grupo_id)
    except TelegramError as exc:
        falhar(f"Não consegui acessar o grupo {grupo_id}: {exc}")
        print(f"{INFO} Confirme o ID e se o bot foi adicionado ao grupo.")
        return
    print(f"{OK} Grupo encontrado: {chat.title!r}")

    try:
        membro = await bot.get_chat_member(grupo_id, bot.id)
    except TelegramError as exc:
        falhar(f"Não consegui verificar as permissões: {exc}")
        return

    if membro.status != ChatMemberStatus.ADMINISTRATOR:
        falhar("O bot NÃO é administrador deste grupo.")
        print(f"{INFO} Grupo -> Administradores -> Adicionar administrador -> o bot.")
        return
    print(f"{OK} O bot é administrador.")

    if not getattr(membro, "can_invite_users", False):
        falhar("Falta a permissão 'Adicionar membros'.")
        print(f"{INFO} É ela que autoriza aprovar solicitações de entrada.")
        return
    print(f"{OK} Permissão 'Adicionar membros': ativa.")
    print(f"{INFO} Lembrete: o link de convite divulgado precisa ter")
    print(f"{INFO} 'Solicitar aprovação do administrador' ligado, senão o")
    print(f"{INFO} Telegram deixa a pessoa entrar direto e o bot nem é chamado.")


async def checar_grupo_admin(bot: Bot) -> None:
    titulo("4. Grupo de administradores")
    bruto = os.getenv("ADMIN_GROUP_ID", "").strip()
    if not bruto:
        falhar("ADMIN_GROUP_ID não definido.")
        return
    try:
        grupo_id = int(bruto)
    except ValueError:
        falhar(f"ADMIN_GROUP_ID deve ser um número (recebido: {bruto!r}).")
        return

    try:
        chat = await bot.get_chat(grupo_id)
    except TelegramError as exc:
        falhar(f"Não consegui acessar o grupo {grupo_id}: {exc}")
        return
    print(f"{OK} Grupo encontrado: {chat.title!r}")

    try:
        mensagem = await bot.send_message(
            grupo_id, "✅ Teste de diagnóstico: consigo escrever aqui."
        )
        await bot.delete_message(grupo_id, mensagem.message_id)
        print(f"{OK} O bot consegue enviar mensagens neste grupo.")
    except TelegramError as exc:
        falhar(f"O bot não consegue escrever no grupo: {exc}")


async def checar_webhook(bot: Bot) -> None:
    """Depois do deploy: confere o que o Telegram sabe sobre o serviço."""
    titulo("6. Webhook (depois do deploy)")
    try:
        info = await bot.get_webhook_info()
    except TelegramError as exc:
        print(f"{AVISO} Não consegui consultar: {exc}")
        return

    if not info.url:
        print(f"{INFO} Nenhum webhook configurado.")
        print(f"{INFO} Normal antes do deploy — em modo polling não se usa webhook.")
        return

    print(f"{OK} URL: {info.url}")
    print(f"{INFO} Atualizações na fila: {info.pending_update_count}")
    print(f"{INFO} Certificado próprio: {info.has_custom_certificate}")

    permitidas = info.allowed_updates or []
    if "chat_join_request" in permitidas:
        print(f"{OK} 'chat_join_request' está entre as atualizações permitidas.")
    else:
        falhar("'chat_join_request' NÃO está nas atualizações permitidas.")
        print(f"{INFO} Sem isso o Telegram nunca entrega o evento principal.")
        print(f"{INFO} Recebidas: {permitidas or '(padrão)'}")

    if info.last_error_message:
        falhar(f"Último erro do Telegram: {info.last_error_message}")
        print(f"{INFO} Em: {info.last_error_date}")
        print(f"{INFO} Serviço dormindo, URL errada ou segredo divergente.")
    else:
        print(f"{OK} Nenhum erro de entrega registrado.")


async def checar_planilha() -> None:
    titulo("5. Google Planilhas")
    bruto = os.getenv("SPREADSHEET_ID", "").strip()
    if not bruto:
        falhar("SPREADSHEET_ID não definido.")
        return

    try:
        credenciais = _carregar_credenciais_google()
    except ConfigError as exc:
        falhar(str(exc))
        return

    email = credenciais.get("client_email", "?")
    print(f"{INFO} Conta de serviço: {email}")

    import re

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", bruto)
    spreadsheet_id = match.group(1) if match else bruto

    repo = PlanilhaRepo(
        credenciais=credenciais,
        spreadsheet_id=spreadsheet_id,
        worksheet_name=os.getenv("WORKSHEET_NAME", "Solicitações Telegram"),
    )
    try:
        await repo.conectar()
        print(f"{OK} Planilha aberta: {repo.url}")
        print(f"{OK} Aba em uso: {repo.aba!r}")
        outras = [a for a in repo.abas_existentes if a != repo.aba]
        if outras:
            print(f"{INFO} Outras abas (nao serao tocadas): "
                  + ", ".join(repr(a) for a in outras))
        await repo.testar_escrita()
        print(f"{OK} A conta de serviço consegue escrever.")
        linhas = await repo.carregar_todas()
        print(f"{INFO} Solicitações já registradas: {len(linhas)}")
    except SheetsError as exc:
        falhar(str(exc))
    except Exception as exc:  # erro inesperado da API do Google
        falhar(f"{type(exc).__name__}: {exc}")


async def principal() -> int:
    from dotenv import load_dotenv

    load_dotenv()

    print("=" * 62)
    print(" DIAGNÓSTICO DO BOT DE TRIAGEM")
    print("=" * 62)
    print(f"{INFO} Fuso horário: {TIMEZONE}")

    bot = await checar_telegram()
    if bot is not None:
        await listar_chats(bot)
        await checar_grupo_principal(bot)
        await checar_grupo_admin(bot)
        await checar_webhook(bot)
        await bot.shutdown()

    await checar_planilha()

    print("\n" + "=" * 62)
    if falhas:
        print(f" {falhas} problema(s) encontrado(s). Corrija antes de subir o bot.")
    else:
        print(" Tudo certo! O bot está pronto para rodar: python main.py")
    print("=" * 62 + "\n")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
