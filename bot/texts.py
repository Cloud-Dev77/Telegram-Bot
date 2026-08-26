"""Todos os textos enviados pelo bot.

=============================================================================
ESTE É UM DOS DOIS ARQUIVOS QUE VOCÊ PODE EDITAR PARA PERSONALIZAR O BOT.
(o outro é `questions.py`, que contém as 5 perguntas)
=============================================================================

Regras ao editar:

* Marcadores entre chaves, como {nome} ou {grupo}, são substituídos
  automaticamente pelo bot. Mantenha-os escritos exatamente assim.
* A formatação usa HTML do Telegram:
      <b>negrito</b>   <i>itálico</i>   <u>sublinhado</u>
      <code>fonte fixa</code>   <a href="https://exemplo.com">link</a>
  Não use outras tags — o Telegram recusa a mensagem inteira.
* Se precisar escrever os sinais < > & como texto comum, escreva
  &lt; &gt; &amp;
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Mensagens no chat privado com o candidato
# ---------------------------------------------------------------------------

BOAS_VINDAS = (
    "Olá, {nome}! 👋\n\n"
    "Recebemos a sua solicitação para entrar no grupo <b>{grupo}</b>.\n\n"
    "Para concluir, preciso confirmar alguns dados. São <b>5 perguntas rápidas</b> "
    "e leva menos de um minuto.\n\n"
    "Suas respostas serão analisadas pela administração, que aprovará ou "
    "recusará a entrada.\n\n"
    "Vamos começar? 👇"
)

# Mostrada quando o candidato abre o bot depois da janela inicial ter passado,
# ou quando envia /start no meio do processo.
RETOMAR = (
    "Olá de novo, {nome}! Sua solicitação está em andamento.\n\n"
    "Vamos continuar de onde paramos. 👇"
)

# /start de alguém que nunca solicitou entrada no grupo.
SEM_SOLICITACAO = (
    "Olá! 👋\n\n"
    "Eu sou o assistente de cadastro da comunidade e não encontrei nenhuma "
    "solicitação de entrada em seu nome.\n\n"
    "Para participar, use o link de convite do grupo e toque em "
    "<b>Solicitar entrada</b>. Assim que fizer isso, eu envio as perguntas "
    "aqui mesmo."
)

# Já respondeu tudo e está na fila da administração.
JA_ENVIADO = (
    "Seu cadastro já foi enviado para análise. ✅\n\n"
    "Assim que a administração avaliar, eu aviso você por aqui. "
    "Não é preciso responder novamente."
)

JA_APROVADO = (
    "Sua solicitação já foi <b>aprovada</b>. ✅\n\n"
    "Você já pode acessar o grupo normalmente. Boas-vindas!"
)

JA_RECUSADO = (
    "Sua solicitação anterior foi <b>recusada</b> pela administração.\n\n"
    "Em caso de dúvida, procure um administrador da comunidade."
)

# Erro de validação: o texto específico vem de `questions.py`.
RESPOSTA_INVALIDA = "⚠️ {motivo}\n\nPor favor, responda novamente."

# Enviada quando o candidato responde a última pergunta.
RESUMO_CONFIRMACAO = (
    "Perfeito! Confira os dados que você enviou:\n\n"
    "{resumo}\n\n"
    "Está tudo certo?"
)

BOTAO_CONFIRMAR = "✅ Sim, enviar para análise"
BOTAO_REFAZER = "🔄 Não, refazer"

ENVIADO_PARA_ANALISE = (
    "Cadastro enviado para a administração! 📨\n\n"
    "Sua solicitação está em análise. Assim que houver uma decisão, "
    "eu aviso você aqui mesmo.\n\n"
    "Obrigado pela paciência. 🙏"
)

REFAZER = "Sem problema! Vamos preencher tudo de novo. 👇"

# Resultado da decisão dos administradores.
APROVADO = (
    "🎉 <b>Solicitação aprovada!</b>\n\n"
    "Você já faz parte do grupo <b>{grupo}</b>. Seja muito bem-vindo(a)!\n\n"
    "Abra o Telegram e o grupo já estará na sua lista de conversas."
)

RECUSADO = (
    "❌ <b>Solicitação não aprovada</b>\n\n"
    "Sua entrada no grupo <b>{grupo}</b> não foi autorizada pela administração.\n\n"
    "Se acredita que houve engano, entre em contato com um administrador da "
    "comunidade."
)

CANCELADO = (
    "Cadastro cancelado. Se mudar de ideia, envie /start para recomeçar."
)

# Resposta a foto, áudio, figurinha etc. durante o cadastro.
APENAS_TEXTO = (
    "Preciso da resposta em <b>texto</b>, por favor — não consigo ler "
    "imagens, áudios ou arquivos.\n\nVamos tentar de novo? 👇"
)

ERRO_GENERICO = (
    "😕 Tivemos um problema técnico ao processar sua resposta.\n\n"
    "Por favor, tente novamente em alguns instantes. Se o erro continuar, "
    "procure um administrador da comunidade."
)

# ---------------------------------------------------------------------------
# Card de verificação enviado ao grupo dos administradores
# ---------------------------------------------------------------------------

CARD_ADMIN = (
    "🆕 <b>Nova solicitação de entrada</b>\n\n"
    "🏷 <b>Categoria:</b> {categoria}\n"
    "👤 <b>Nome completo:</b> {nome_completo}\n"
    "📍 <b>Local:</b> {municipio} / {uf}\n"
    "🏢 <b>Unidade / Empresa:</b> {unidade}\n"
    "🪪 <b>Registro:</b> <code>{registro}</code>\n\n"
    "───────────────\n"
    "🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
    "🔗 <b>Usuário:</b> {username}\n"
    "📛 <b>Nome no Telegram:</b> {nome_telegram}\n"
    "🕒 <b>Solicitado em:</b> {data_hora}\n"
    "📄 <b>Linha na planilha:</b> {linha}"
)

BOTAO_APROVAR = "✅ Aprovar"
BOTAO_RECUSAR = "❌ Recusar"

# Acrescentado ao card depois que alguém decide.
CARD_DECIDIDO_APROVADO = "\n\n✅ <b>APROVADO</b> por {admin} em {data_hora}"
CARD_DECIDIDO_RECUSADO = "\n\n❌ <b>RECUSADO</b> por {admin} em {data_hora}"

# Aviso curto (popup) mostrado a quem clica no botão.
ALERTA_JA_PROCESSADO = "Esta solicitação já foi {status} por {admin}."
ALERTA_APROVADO_OK = "Aprovado! O usuário já entrou no grupo."
ALERTA_RECUSADO_OK = "Solicitação recusada."
ALERTA_ERRO = "Erro ao processar. Veja os detalhes na mensagem."

# Casos em que o Telegram recusa a operação.
CARD_SOLICITACAO_EXPIRADA = (
    "\n\n⚠️ <b>Não foi possível concluir</b>\n"
    "A solicitação não existe mais no Telegram (o usuário cancelou, já entrou "
    "ou foi processada por outro administrador direto no grupo).\n"
    "Status na planilha: <b>{status}</b>."
)

AVISO_DM_BLOQUEADA = (
    "\n\n⚠️ Não consegui avisar o usuário no privado (ele bloqueou o bot ou "
    "nunca abriu a conversa). A ação no grupo foi executada normalmente."
)

# Enviado ao grupo de administradores quando o bot não consegue falar com o
# candidato no privado dentro da janela permitida pelo Telegram.
ALERTA_SEM_CONTATO = (
    "⚠️ <b>Solicitação sem contato</b>\n\n"
    "{nome} ({username}) pediu entrada no grupo, mas não consegui iniciar a "
    "conversa no privado — provavelmente o bot está bloqueado ou as "
    "configurações de privacidade impedem o contato.\n\n"
    "🆔 Telegram ID: <code>{user_id}</code>\n\n"
    "Se quiser, peça à pessoa para abrir <a href=\"https://t.me/{bot_username}\">"
    "@{bot_username}</a> e tocar em INICIAR."
)

# ---------------------------------------------------------------------------
# Comandos administrativos
# ---------------------------------------------------------------------------

STATUS_BOT = (
    "🤖 <b>Status do bot</b>\n\n"
    "Bot: @{bot_username}\n"
    "Grupo principal: <code>{main_group}</code>\n"
    "Grupo de administradores: <code>{admin_group}</code>\n"
    "Planilha: <a href=\"{planilha_url}\">abrir</a>\n"
    "Aba: <b>{aba}</b>\n"
    "Conta de serviço: <code>{service_account}</code>\n\n"
    "📊 <b>Solicitações</b>\n"
    "Em andamento: {em_andamento}\n"
    "Aguardando aprovação: {aguardando}\n"
    "Aprovadas: {aprovadas}\n"
    "Recusadas: {recusadas}"
)

APENAS_ADMIN = "Este comando só funciona no grupo de administradores."

AJUDA_ADMIN = (
    "🤖 <b>Comandos disponíveis</b>\n\n"
    "/link — gera o link de convite correto para divulgar\n"
    "/status — resumo da configuração e das solicitações\n"
    "/id — mostra o ID deste chat\n"
    "/ajuda — esta mensagem"
)

# Resposta do comando /link.
LINK_GERADO = (
    "🔗 <b>Link de convite para divulgar</b>\n\n"
    "{link}\n\n"
    "Este link foi criado com <b>aprovação obrigatória</b>: quem tocar nele não "
    "entra direto — gera uma solicitação e cai no fluxo de cadastro do bot.\n\n"
    "⚠️ Divulgue <b>somente este link</b>. Links antigos, sem aprovação, deixam "
    "qualquer pessoa entrar sem passar pela triagem — revogue-os nas "
    "configurações do grupo."
)

LINK_ERRO = (
    "❌ Não consegui criar o link: {erro}\n\n"
    "Confirme que o bot é administrador do grupo principal com a permissão "
    "<b>Adicionar membros</b>."
)

ID_DO_CHAT = (
    "🆔 ID deste chat: <code>{chat_id}</code>\n"
    "Tipo: {tipo}\n\n"
    "Use este número nas variáveis de ambiente do bot."
)
