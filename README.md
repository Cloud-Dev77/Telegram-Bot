# Bot de Triagem e Aprovação de Membros — Telegram

Bot em Python que automatiza a entrada de novos membros em um grupo fechado do
Telegram: recebe a solicitação, conversa com a pessoa no privado, coleta 5
informações, grava tudo no Google Planilhas em tempo real e envia um card para
os administradores aprovarem ou recusarem com um toque.

---

## Índice

1. [Como o bot funciona](#1-como-o-bot-funciona)
2. [Passo 1 — Criar o bot no Telegram](#2-passo-1--criar-o-bot-no-telegram)
3. [Passo 2 — Preparar os dois grupos](#3-passo-2--preparar-os-dois-grupos)
4. [Passo 3 — Google Planilhas (conta de serviço)](#4-passo-3--google-planilhas-conta-de-serviço)
5. [Passo 4 — Configurar o bot](#5-passo-4--configurar-o-bot)
6. [Passo 5 — Testar no seu computador](#6-passo-5--testar-no-seu-computador)
7. [Passo 6 — Colocar no ar (hospedagem gratuita)](#7-passo-6--colocar-no-ar-hospedagem-gratuita)
8. [Personalizar textos e perguntas](#8-personalizar-textos-e-perguntas)
9. [A planilha](#9-a-planilha)
10. [Variáveis de ambiente](#10-variáveis-de-ambiente)
11. [Solução de problemas](#11-solução-de-problemas)
12. [Estrutura do código](#12-estrutura-do-código)

---

## 1. Como o bot funciona

```
  Pessoa toca em "Solicitar entrada" no link do grupo
                      │
                      ▼
  ┌──────────────────────────────────────────────┐
  │ O bot grava a solicitação na planilha         │  ← acontece ANTES de
  │ (Telegram ID, @usuário, data/hora)            │    qualquer mensagem
  └──────────────────────────────────────────────┘
                      │
                      ▼
  ┌──────────────────────────────────────────────┐
  │ Mensagem privada + 5 perguntas, uma por vez   │
  │ Cada resposta é validada e gravada na hora    │
  └──────────────────────────────────────────────┘
                      │
                      ▼
  ┌──────────────────────────────────────────────┐
  │ Resumo para a pessoa conferir e confirmar     │
  └──────────────────────────────────────────────┘
                      │
                      ▼
  ┌──────────────────────────────────────────────┐
  │ Card no grupo de administradores              │
  │        [ ✅ Aprovar ]   [ ❌ Recusar ]         │
  └──────────────────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
   Entra no grupo          Solicitação recusada
   + aviso no privado      + aviso no privado
          └───────────┬───────────┘
                      ▼
        Planilha atualizada com o status,
        a data/hora e quem decidiu
```

### O detalhe do Telegram que todo mundo esquece

Quando alguém pede entrada, o Telegram autoriza o bot a **iniciar** a conversa
privada apenas por alguns minutos. Se a pessoa demorar para abrir o Telegram,
esse contato falha.

Este bot lida com isso de duas formas:

* a linha na planilha é criada **antes** da tentativa de contato, então a
  solicitação nunca se perde;
* quando a pessoa finalmente abre o bot e toca em **INICIAR**, ela é
  reconhecida pelo Telegram ID e o cadastro continua exatamente de onde parou.

Nos casos em que o contato falha, o status na planilha fica **"Sem contato"** e
um aviso vai para o grupo de administradores.

> **Recomendação:** ao divulgar o link do grupo, escreva algo como
> *"Ao solicitar entrada você receberá uma mensagem do @SeuBot no privado. Abra
> e responda as perguntas para validar seu cadastro."* Isso aumenta bastante a
> taxa de conclusão.

---

## 2. Passo 1 — Criar o bot no Telegram

1. No Telegram, procure por **@BotFather**.
2. Envie `/newbot`.
3. Escolha um nome (aparece nas conversas) e um `@usuário` (precisa terminar
   em `bot`).
4. O BotFather responde com o **token**, algo como
   `1234567890:AAF...`. Guarde — é a senha do bot.

> ⚠️ Nunca publique o token. Se ele vazar, envie `/revoke` ao BotFather para
> gerar um novo e atualize a variável `BOT_TOKEN` na hospedagem.

---

## 3. Passo 2 — Preparar os dois grupos

### 3.1 Grupo principal (a comunidade)

1. Adicione o bot ao grupo.
2. Toque no nome do grupo → **Administradores** → **Adicionar administrador**
   → escolha o bot.
3. Deixe ligada a permissão **"Adicionar membros"**
   (`can_invite_users`). É exatamente ela que autoriza o bot a aprovar
   solicitações — sem ela, nada funciona.

### 3.2 O link de convite — a etapa mais esquecida

No Telegram, **"aprovar novos membros" não é uma configuração do grupo: é uma
propriedade do link de convite.** Um link comum deixa a pessoa entrar direto e
o bot nem chega a ser chamado — é o erro que mais derruba esse tipo de
instalação.

**Jeito fácil (recomendado):** com o bot já rodando, envie **`/link`** no grupo
de administradores. O bot cria um link com aprovação obrigatória já ativada e
devolve pronto para divulgar.

**Jeito manual:**

1. Nome do grupo → **Editar** → **Links de convite**.
2. **Criar um novo link**.
3. Ative **"Solicitar aprovação do administrador"** (em algumas versões,
   *"Aprovar novos membros"*).
4. Salve e **divulgue esse link** — não o antigo.

> ⚠️ Depois de criar o link certo, **revogue os links antigos**. Enquanto um
> link sem aprovação continuar circulando, qualquer pessoa entra sem passar
> pela triagem.

### 3.3 Grupo de administradores

Um grupo comum do Telegram já serve.

1. Crie o grupo e adicione os administradores humanos.
2. Adicione o bot e **promova-o a administrador** — assim o Telegram converte o
   grupo em supergrupo e o ID dele para de mudar.
3. Todos os dados dos candidatos aparecerão aqui, então mantenha o grupo
   restrito a quem deve ter acesso.

### 3.4 Descobrir o ID dos grupos

Você **não precisa** procurar esse número manualmente:

* ao ser adicionado a um grupo, o bot anuncia o ID automaticamente;
* a qualquer momento, envie **`/id`** dentro do grupo.

IDs de grupo são negativos, no formato `-1001234567890`.

---

## 4. Passo 3 — Google Planilhas (conta de serviço)

A "conta de serviço" é um usuário robô do Google. É ele que grava na planilha —
por isso a planilha precisa ser **compartilhada com o e-mail dele**.

1. Acesse <https://console.cloud.google.com/> e crie um projeto
   (ex.: `bot-telegram-comunidade`).
2. Menu **APIs e serviços → Biblioteca**: procure **Google Sheets API** e clique
   em **Ativar**.
3. Menu **APIs e serviços → Credenciais** → **Criar credenciais** →
   **Conta de serviço**. Dê um nome e conclua.
4. Abra a conta de serviço criada → aba **Chaves** → **Adicionar chave** →
   **Criar nova chave** → **JSON**. O arquivo é baixado. **Ele é secreto.**
5. Dentro do arquivo há um campo `client_email`, parecido com
   `bot-planilha@projeto-123.iam.gserviceaccount.com`. **Copie esse e-mail.**
6. Abra a planilha no Google Planilhas → **Compartilhar** → cole esse e-mail →
   permissão **Editor** → **Enviar**.

> 💡 **Se a planilha estiver ligada a um Formulário Google:** não use a aba de
> respostas do formulário. O Google reorganiza aquela aba sozinho e isso
> quebraria a integração. O bot cria e usa uma aba própria
> (`Solicitações Telegram`), sem interferir no formulário.

---

## 5. Passo 4 — Configurar o bot

Copie o arquivo de exemplo e preencha:

```bash
cp .env.example .env
```

Preenchimento mínimo:

```dotenv
BOT_TOKEN=1234567890:AAF...
MAIN_GROUP_ID=-1001111111111
ADMIN_GROUP_ID=-1002222222222
SPREADSHEET_ID=https://docs.google.com/spreadsheets/d/SEU_ID_AQUI/edit
GOOGLE_CREDENTIALS_FILE=credentials.json
```

Renomeie o JSON baixado do Google para `credentials.json` e coloque-o na raiz
do projeto.

> `.env` e `credentials.json` já estão no `.gitignore` — nunca vão para o
> GitHub por acidente.

---

## 6. Passo 5 — Testar no seu computador

Requer **Python 3.10 ou superior**.

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### Conferir a instalação

```bash
python tools/diagnostico.py
```

O diagnóstico verifica o token, lista os IDs de chat visíveis, confere se o bot
é administrador com a permissão certa e testa leitura e escrita na planilha.
Cada falha vem acompanhada da instrução de correção.

### Rodar

```bash
python main.py
```

Sem `WEBHOOK_URL` definida, o bot roda em **modo polling** — perfeito para
testar. Peça entrada no grupo com uma segunda conta e acompanhe o fluxo.

### Testes automatizados

```bash
python -m unittest discover -s tests -t .
```

55 testes cobrem as validações, o fluxo completo, a retomada após reinício da
hospedagem, o clique duplo nos botões administrativos e as solicitações que
deixam de existir no Telegram. Nenhum deles usa rede.

---

## 7. Passo 6 — Colocar no ar (hospedagem gratuita)

Assim que existe uma URL pública, o bot passa sozinho para **modo webhook**: o
Telegram entrega as atualizações via HTTPS, o que também faz o serviço acordar
em hospedagens que hibernam por inatividade.

### Render (recomendado)

1. Envie o projeto para um repositório no GitHub (pode ser privado).
2. Em <https://render.com> → **New** → **Blueprint** → aponte para o
   repositório. O arquivo `render.yaml` já traz toda a configuração.
3. O Render pedirá os valores secretos. Preencha:

   | Variável | Valor |
   |---|---|
   | `BOT_TOKEN` | o token do BotFather |
   | `MAIN_GROUP_ID` | ID do grupo principal |
   | `ADMIN_GROUP_ID` | ID do grupo de administradores |
   | `SPREADSHEET_ID` | ID ou URL da planilha |
   | `GOOGLE_CREDENTIALS_JSON` | **todo o conteúdo** do arquivo `.json`, colado |

   O `WEBHOOK_SECRET` é gerado automaticamente pelo Render.

4. Aguarde o deploy. Nos logs deve aparecer:

   ```
   Conectado como @seu_bot (id ...).
   Permissões no grupo principal: OK.
   Iniciando em modo WEBHOOK: https://....onrender.com/telegram
   ```

> No plano gratuito do Render, `GOOGLE_CREDENTIALS_JSON` deve ser colado em uma
> linha só. Copie o conteúdo do arquivo inteiro, das chaves `{` até `}`.

### Manter o serviço acordado (já vem embutido)

O plano gratuito do Render hiberna o serviço após alguns minutos sem tráfego, e
a primeira requisição depois disso demora para responder. Para evitar isso:

1. Crie uma conta gratuita em <https://uptimerobot.com>.
2. **Add New Monitor** → tipo **HTTP(s)**.
3. URL: `https://SEU-SERVICO.onrender.com/health`
4. Intervalo: 5 minutos.

O endereço `/health` responde um JSON com o status do bot e o total de
solicitações por situação.

### Outras hospedagens

Funciona em qualquer lugar que rode Python e exponha uma porta HTTP
(Fly.io, Railway, Google Cloud Run, VPS). Basta definir `WEBHOOK_URL` com a URL
pública do serviço e `PORT` se a plataforma não a definir sozinha.

> ⚠️ **PythonAnywhere no plano gratuito não serve:** contas gratuitas não
> executam processos contínuos, apenas tarefas agendadas.

---

## 8. Personalizar textos e perguntas

Dois arquivos, ambos comentados em português:

### `bot/texts.py` — todas as mensagens

Boas-vindas, confirmação, aprovação, recusa, card administrativo, avisos de
erro. Regras ao editar:

* Marcadores como `{nome}`, `{grupo}`, `{categoria}` são preenchidos pelo bot.
  Mantenha-os escritos exatamente assim.
* A formatação usa HTML do Telegram: `<b>negrito</b>`, `<i>itálico</i>`,
  `<code>fonte fixa</code>`.

### `bot/questions.py` — as 5 perguntas

* Para mudar o texto de uma pergunta, edite o campo `pergunta` da entrada
  correspondente na lista `PERGUNTAS`, no fim do arquivo.
* Para mudar as opções do primeiro botão, edite a lista `CATEGORIAS` no começo
  do arquivo.
* Cada pergunta tem um validador. Para aceitar qualquer texto em uma delas,
  troque o validador por `validar_unidade`, que só confere o tamanho.

Depois de editar, rode os testes (`python -m unittest discover -s tests -t .`) e
reinicie o bot.

---

## 9. A planilha

O bot cria a aba **`Solicitações Telegram`** com estas colunas:

| Coluna | Conteúdo |
|---|---|
| A | Data/Hora da solicitação |
| B | Telegram ID |
| C | @username |
| D | Nome no Telegram |
| E | Categoria |
| F | Nome Completo |
| G | UF |
| H | Município |
| I | Unidade / Empresa / Entidade |
| J | Código de Registro |
| K | **Status** |
| L | Data/Hora da Decisão |
| M | Decidido por |
| N | Etapa (controle interno) |
| O | ID Msg Admin (controle interno) |

Status possíveis: `Em andamento`, `Aguardando aprovação`, `Aprovado`,
`Recusado`, `Sem contato`.

**A planilha é a memória do bot.** Cada resposta é gravada no instante em que
chega, sempre na mesma linha. Por isso o bot pode ser reiniciado a qualquer
momento — inclusive pela hibernação do plano gratuito — sem perder nenhum
cadastro em andamento.

As colunas **N** e **O** são de controle interno; pode escondê-las, mas não as
apague. Colunas extras à direita da O são preservadas.

---

## 10. Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|:---:|---|
| `BOT_TOKEN` | ✅ | Token do @BotFather |
| `MAIN_GROUP_ID` | ✅ | ID do grupo da comunidade (negativo) |
| `ADMIN_GROUP_ID` | ✅ | ID do grupo dos administradores (negativo) |
| `SPREADSHEET_ID` | ✅ | ID **ou** URL completa da planilha |
| `GOOGLE_CREDENTIALS_JSON` | ✅¹ | Conteúdo do JSON da conta de serviço |
| `GOOGLE_CREDENTIALS_FILE` | ✅¹ | Caminho do arquivo JSON (alternativa) |
| `WORKSHEET_NAME` | | Aba usada. Padrão: `Solicitações Telegram` |
| `WEBHOOK_URL` | | URL pública. Vazio = modo polling |
| `WEBHOOK_SECRET` | | Senha que valida a origem das atualizações |
| `PORT` | | Porta HTTP. Padrão: `8080` |
| `TIMEZONE` | | Padrão: `America/Sao_Paulo` |
| `LOG_LEVEL` | | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `KEEPALIVE_MINUTES` | | Auto-ping em `/health` para não hibernar. `0` desliga. Padrão: `10` |

¹ Uma das duas. No Render, use `GOOGLE_CREDENTIALS_JSON`.

---

## 11. Solução de problemas

**A pessoa entra no grupo sem passar pelo bot**
O link divulgado não tem aprovação ligada. Envie **`/link`** no grupo de
administradores para gerar o link correto, divulgue-o e **revogue os antigos**.

**O bot não fala com quem pediu entrada**
A janela de contato do Telegram expirou. A solicitação está salva: peça à
pessoa para abrir o bot e tocar em **INICIAR** — o cadastro retoma sozinho. O
status na planilha fica *"Sem contato"*.

**"O bot NÃO é administrador do grupo principal" nos logs**
Promova o bot a administrador e ligue a permissão **"Adicionar membros"**.

**Clicar em Aprovar não faz nada / dá erro**
Rode `python tools/diagnostico.py`. Quase sempre é a permissão "Adicionar
membros" desligada, ou o `MAIN_GROUP_ID` errado.

**"A solicitação não existe mais no Telegram"**
A pessoa cancelou, entrou por outro caminho ou um administrador decidiu direto
pela tela do grupo. A decisão fica registrada na planilha mesmo assim.

**Erro 403 ao abrir a planilha**
A planilha não foi compartilhada com a conta de serviço. Compartilhe como
**Editor** com o `client_email` do arquivo JSON.

**"Planilha não encontrada"**
`SPREADSHEET_ID` errado, ou a Google Sheets API não foi ativada no projeto do
Google Cloud.

**O bot demora a responder a primeira mensagem do dia**
Hibernação do plano gratuito. Configure o monitor descrito no
[passo 6](#manter-o-serviço-acordado).

**Dois administradores clicaram ao mesmo tempo**
Não é problema: só o primeiro clique vale. O segundo recebe um aviso dizendo
quem já decidiu e quando.

---

## 12. Estrutura do código

```
.
├── main.py                    Ponto de entrada
├── requirements.txt           Dependências
├── render.yaml                Deploy no Render
├── .env.example               Modelo de configuração
│
├── bot/
│   ├── config.py              Variáveis de ambiente, validadas na subida
│   ├── texts.py               ✏️ Todas as mensagens (personalizável)
│   ├── questions.py           ✏️ As 5 perguntas e suas validações
│   ├── models.py              A solicitação e o mapeamento das colunas
│   ├── sheets.py              Google Planilhas via conta de serviço
│   ├── store.py               Estado das solicitações (cache + travas)
│   ├── app.py                 Montagem da aplicação; polling e webhook
│   └── handlers/
│       ├── onboarding.py      Do pedido de entrada ao envio para análise
│       ├── admin.py           Botões Aprovar/Recusar e comandos
│       ├── errors.py          Tratamento global de erros
│       └── common.py          Teclados e envio de mensagens
│
├── tools/
│   └── diagnostico.py         Verificação da instalação
│
└── tests/                     55 testes, sem rede
```

### Comandos do bot

| Comando | Onde | O que faz |
|---|---|---|
| `/start` | privado | Inicia ou retoma o cadastro |
| `/cancelar` | privado | Recomeça o cadastro do zero |
| `/link` | grupo de admins | Cria o link de convite com aprovação obrigatória |
| `/status` | grupo de admins | Configuração e totais por situação |
| `/id` | qualquer chat | Mostra o ID do chat |
| `/ajuda` | qualquer chat | Lista de comandos |

### Decisões de projeto

* **A planilha é a única fonte da verdade.** Sem banco de dados e sem arquivo
  local, o bot sobrevive a reinícios — condição essencial em hospedagem
  gratuita, que reinicia com frequência.
* **Uma trava por usuário** (`asyncio.Lock`) serializa cada operação. É o que
  impede aprovação dupla, resposta fora de ordem e gravação concorrente.
* **Escrita com `RAW` na planilha:** uma resposta começando com `=` é gravada
  como texto, nunca interpretada como fórmula.
* **Escape de HTML em tudo que vem do usuário:** um nome com `<` não quebra o
  card administrativo.
* **Modo webhook em produção:** além de mais rápido, é o que permite ao serviço
  hibernar e acordar sozinho no plano gratuito.
