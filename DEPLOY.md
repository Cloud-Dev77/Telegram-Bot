# Guia de Deploy — Render (plano gratuito)

Passo a passo para colocar o bot rodando 24 horas. Leva cerca de 15 minutos.

Os valores secretos que você vai colar estão em **`deploy-valores.txt`**, na
raiz do projeto. Esse arquivo não vai para o GitHub.

---

## Antes de começar: de quem são as contas?

Esta decisão vem primeiro porque é difícil desfazer depois.

O Render exige verificação por e-mail no cadastro. Ter só o endereço do
cliente não basta — alguém precisa abrir o link de confirmação que chega
naquela caixa de entrada.

| Caminho | Quando usar | Consequência |
|---|---|---|
| **A. Conta no e-mail do cliente** | O cliente consegue te encaminhar o e-mail de confirmação, ou vocês fazem juntos | A conta já nasce dele. Sem migração depois. |
| **B. Conta sua, migrar depois** | Você quer subir hoje sem depender dele | Funciona na hora. Na entrega, o cliente cria a conta dele e você refaz o serviço lá — são 5 minutos, os valores são os mesmos. |

**Recomendado: A**, se ele conseguir te passar o código de confirmação. Evita
o retrabalho e o cliente nunca fica dependente da sua conta.

O mesmo vale para o GitHub. Como o código é o seu entregável, o caminho
prático é: repositório **privado na sua conta** agora, e na entrega você
manda o ZIP ou transfere o repositório.

---

## Passo 1 — Subir o código para o GitHub

O Render lê o código de um repositório Git.

```bash
cd "Telegram bot"

git add -A
git commit -m "Bot de triagem e aprovacao de membros no Telegram"
```

Antes de enviar, confirme que nenhum segredo entrou:

```bash
git ls-files | grep -E "\.env$|credentials|service-worker|deploy-valores"
```

**A saída precisa ser vazia.** Se aparecer qualquer arquivo, pare e revise o
`.gitignore` antes de continuar.

Crie um repositório **privado** em <https://github.com/new> (sem README, sem
`.gitignore` — o projeto já tem), e envie:

```bash
git remote add origin https://github.com/SEU_USUARIO/telegram-triagem-bot.git
git branch -M main
git push -u origin main
```

---

## Passo 2 — Criar a conta no Render

1. <https://render.com> → **Get Started**
2. Escolha **GitHub** (mais simples: já autoriza o acesso ao repositório) ou
   e-mail, conforme a decisão do quadro acima.
3. Confirme o e-mail.

O plano gratuito não pede cartão de crédito.

---

## Passo 3 — Criar o serviço

O projeto já traz um `render.yaml` com toda a configuração pronta.

1. No painel: **New +** → **Blueprint**
2. Conecte o repositório que você acabou de enviar
3. O Render lê o `render.yaml` e mostra o serviço `telegram-triagem-bot`
4. Ele vai pedir os valores marcados como secretos — é o Passo 4

Se o Blueprint não aparecer, dá para fazer manualmente: **New +** →
**Web Service** → conecte o repositório → e preencha:

| Campo | Valor |
|---|---|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python main.py` |
| Health Check Path | `/health` |
| Plan | Free |

---

## Passo 4 — Cadastrar as variáveis de ambiente

Abra **`deploy-valores.txt`** e cadastre cada uma no painel
(**Environment** → **Add Environment Variable**):

| Variável | Observação |
|---|---|
| `BOT_TOKEN` | token do BotFather |
| `MAIN_GROUP_ID` | número negativo |
| `ADMIN_GROUP_ID` | número negativo |
| `SPREADSHEET_ID` | ID ou URL da planilha |
| `GOOGLE_CREDENTIALS_JSON` | **o JSON inteiro em uma linha só** |
| `WEBHOOK_SECRET` | já gerado aleatoriamente |
| `WORKSHEET_NAME` | `Solicitações Telegram` |
| `TIMEZONE` | `America/Sao_Paulo` |
| `LOG_LEVEL` | `INFO` |

São 9 variáveis. `PYTHON_VERSION` não entra na lista — vem do arquivo
`.python-version`.

**Não cadastre `WEBHOOK_URL` nem `PORT`.** O Render define `RENDER_EXTERNAL_URL`
e `PORT` sozinho, e o bot já lê esses valores — foi assim que ele decide entrar
em modo webhook. Criar essas variáveis em branco não quebra mais nada (o bot
trata vazio como não definido), mas continua sendo ruído desnecessário.

Também não é preciso cadastrar `PYTHON_VERSION`: o arquivo `.python-version`
no repositório já fixa a versão, e o Render o lê sozinho. Sem ele, o Render
usa a versão mais nova que tiver — que pode ser mais recente do que as
bibliotecas suportam.

> ⚠️ O `GOOGLE_CREDENTIALS_JSON` é longo (mais de 2000 caracteres) e precisa
> ficar em **uma linha só**. Copie do `deploy-valores.txt` de uma vez. Se o
> editor quebrar a linha, a chave privada corrompe e o bot sobe com erro de
> autenticação no Google.

---

## Passo 5 — Conferir se subiu

Acompanhe a aba **Logs**. O que você quer ver:

```
Abas na planilha: 'Respostas ao formulário 1', 'Solicitações Telegram'
Planilha conectada: aba 'Solicitações Telegram'
Cache carregado: N solicitações
Iniciando em modo WEBHOOK: https://SEU-SERVICO.onrender.com/telegram
Conectado como @Validador_Titular_bot
Grupo principal: 'Grupo Nacional dos Titulares...'
Permissões no grupo principal: OK.
Grupo de administradores: '...'
```

Se aparecer **`modo POLLING`**, o Render não expôs a URL — confira se o
serviço é do tipo **Web Service** (não Background Worker).

Depois, dois testes rápidos:

**a) A rota de saúde**, no navegador:
`https://SEU-SERVICO.onrender.com/health` — deve responder algo como:

```json
{"status":"ok","bot":"Validador_Titular_bot","pronto":true,"solicitacoes":{...}}
```

**b) O que o Telegram enxerga**, na sua máquina:

```bash
python tools/diagnostico.py
```

A etapa 6 mostra a URL registrada, se `chat_join_request` está entre as
atualizações permitidas e se houve erro de entrega.

---

## Passo 6 — Impedir a hibernação

No plano gratuito o Render desliga o serviço após ~15 minutos sem tráfego, e
a primeira chamada seguinte demora para responder. Como a janela de contato
do Telegram é de apenas ~5 minutos, esse atraso pode custar um cadastro.

1. Conta gratuita em <https://uptimerobot.com>
2. **Add New Monitor** → tipo **HTTP(s)**
3. URL: `https://SEU-SERVICO.onrender.com/health`
4. Intervalo: **5 minutos**

O plano gratuito do Render dá 750 horas de execução por mês — suficiente para
um único serviço ligado o mês inteiro.

---

## Passo 7 — Teste ponta a ponta

Com o bot no ar, gere o link definitivo:

1. No **grupo dos administradores**, envie `/link`
2. O bot devolve um link com aprovação obrigatória garantida
3. **Revogue os links antigos** no Telegram (Editar → Links de convite →
   tocar no link → Revogar). Enquanto um link sem aprovação estiver
   circulando, entra gente sem passar pela triagem.

Agora o teste, com uma conta que **não** esteja no grupo:

| # | Ação | Resultado esperado |
|---|---|---|
| 1 | Tocar no link e pedir entrada | Não entra; fica "aguardando aprovação" |
| 2 | — | Chega mensagem privada do bot em segundos |
| 3 | Responder as 5 perguntas | Cada resposta validada; linha preenchendo na planilha |
| 4 | Confirmar o resumo | Card aparece no grupo dos administradores |
| 5 | Tocar em **✅ Aprovar** | A conta entra no grupo e recebe aviso no privado |
| 6 | Conferir a planilha | Status `Aprovado`, data/hora e nome de quem decidiu |
| 7 | Tocar em **Aprovar** de novo | Aviso: "já foi aprovada por ..." |

Passou nos 7? Está entregue.

---

## Entrega ao cliente

- [ ] Trocar o token: `/revoke` no @BotFather e atualizar `BOT_TOKEN` no Render
      (assim o token que circulou por conversa deixa de valer)
- [ ] Entregar login e senha do Render, e orientar a trocar a senha
- [ ] Entregar o código (ZIP ou repositório)
- [ ] Confirmar que a planilha segue compartilhada com a conta de serviço
- [ ] Mostrar `/status` e `/link` no grupo dos administradores
- [ ] Avisar: se o projeto do Google Cloud usado for apagado, o bot para

---

## Problemas comuns

**Sobe em modo POLLING**
O serviço não é Web Service, ou `RENDER_EXTERNAL_URL` não existe. Recrie como
Web Service.

**`Erro de configuração` no log e o serviço morre**
Falta variável de ambiente. A mensagem diz qual — é proposital: o bot recusa
subir mal configurado em vez de falhar no meio de um atendimento.

**`Acesso negado à planilha` / erro 403**
A planilha não está compartilhada como Editor com a conta de serviço, ou a
Google Sheets API não está ativada no projeto do Google Cloud.

**JSON do Google inválido**
`GOOGLE_CREDENTIALS_JSON` quebrou em várias linhas. Cole de novo em uma só.

**Bot no ar mas não responde a quem pede entrada**
O link divulgado não exige aprovação. Envie `/link` no grupo dos
administradores e revogue os antigos.

**Alguém pediu entrada e ficou "Sem contato"**
O bot estava dormindo e a janela de ~5 minutos do Telegram expirou. Nada se
perde: peça à pessoa para abrir o bot e tocar em **INICIAR**. Para não voltar
a acontecer, confira o monitor do Passo 6.

**`ValueError: invalid literal for int()` na subida**
Versão antiga do código. Uma variável numérica foi criada em branco no
painel e o padrão não era aplicado. Corrigido — atualize o repositório.

**`last_error_message` no diagnóstico**
Serviço dormindo, URL errada ou `WEBHOOK_SECRET` diferente do que o Telegram
tem registrado. Um novo deploy reconfigura o webhook.
