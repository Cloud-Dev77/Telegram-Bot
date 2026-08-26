"""As 5 perguntas do processo de triagem, com validação de cada resposta.

=============================================================================
ESTE É O SEGUNDO ARQUIVO PENSADO PARA PERSONALIZAÇÃO.
=============================================================================

As perguntas reproduzem o formulário "Cadastro - Grupo Titulares Telegram":

    1. Você é titular de Serventia Extrajudicial?  (Sim / Não)
    2. Qual o seu nome completo?
    3. Qual seu Município/UF?
    4. Nome da Serventia
    5. CNS do Cartório

Para trocar o texto de uma pergunta, edite o campo `pergunta` da entrada
correspondente em `PERGUNTAS`, no fim do arquivo.

A validação existe para que nenhuma linha da planilha chegue incompleta ou com
lixo aos administradores: cada resposta é conferida antes de o candidato
avançar para a próxima pergunta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------------------
# Opções da pergunta 1 (botões). A ordem é a que aparece na conversa.
# ---------------------------------------------------------------------------

OPCOES_TITULAR: list[str] = ["Sim", "Não"]

# Resposta que indica que a pessoa NÃO atende ao critério do grupo. O cadastro
# continua mesmo assim — quem decide são os administradores —, mas o card de
# verificação recebe um destaque para que ninguém aprove por distração.
RESPOSTA_NAO_ELEGIVEL = "Não"

# Unidades da federação válidas, usadas para validar a pergunta 3.
UFS: frozenset[str] = frozenset(
    """AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI
       RJ RN RS RO RR SC SP SE TO""".split()
)


@dataclass(frozen=True)
class Resultado:
    """Resultado de uma validação.

    `valores` mapeia nome do campo -> valor já limpo e pronto para a planilha.
    Uma pergunta pode preencher mais de um campo (é o caso de Município + UF).
    """

    ok: bool
    valores: dict[str, str] = field(default_factory=dict)
    erro: str = ""


def _normalizar_espacos(texto: str) -> str:
    return " ".join(texto.split())


def _titulo(texto: str) -> str:
    """Capitaliza respeitando as preposições comuns em nomes brasileiros."""
    minusculas = {"de", "da", "do", "das", "dos", "e"}
    palavras = _normalizar_espacos(texto).lower().split()
    saida = []
    for i, palavra in enumerate(palavras):
        if i > 0 and palavra in minusculas:
            saida.append(palavra)
        else:
            saida.append(palavra[:1].upper() + palavra[1:])
    return " ".join(saida)


# ---------------------------------------------------------------------------
# Validadores
# ---------------------------------------------------------------------------

# Letras (com acento), espaços, apóstrofos, hífens e pontos.
_RE_NOME = re.compile(r"^[A-Za-zÀ-ɏ'’\-\s\.]+$")


def validar_titular(texto: str) -> Resultado:
    """Aceita o texto exato de um dos botões (ou o mesmo texto digitado)."""
    limpo = _normalizar_espacos(texto)
    for opcao in OPCOES_TITULAR:
        if limpo.casefold() == opcao.casefold():
            return Resultado(True, {"titular": opcao})
    return Resultado(
        False,
        erro="Responda usando os botões acima: <b>Sim</b> ou <b>Não</b>.",
    )


def validar_nome_completo(texto: str) -> Resultado:
    limpo = _normalizar_espacos(texto)
    if len(limpo) < 5:
        return Resultado(False, erro="O nome informado é curto demais.")
    if len(limpo) > 120:
        return Resultado(
            False, erro="O nome informado é longo demais (máximo 120 caracteres)."
        )
    if not _RE_NOME.match(limpo):
        return Resultado(
            False, erro="Use apenas letras e espaços — sem números ou símbolos."
        )
    partes = [p for p in limpo.split() if len(p) >= 2]
    if len(partes) < 2:
        return Resultado(
            False,
            erro="Informe o nome <b>completo</b>, com pelo menos nome e sobrenome.",
        )
    return Resultado(True, {"nome_completo": _titulo(limpo)})


def validar_municipio_uf(texto: str) -> Resultado:
    """Aceita 'Campinas/SP', 'Campinas - SP', 'SP, Campinas'...

    O formulário pede "Município/UF", mas a ordem inversa é comum na prática.
    Como a UF é reconhecida pela sigla, as duas formas funcionam.
    """
    limpo = _normalizar_espacos(texto)
    partes = re.split(r"\s*[,;/|\-–—]\s*", limpo, maxsplit=1)

    if len(partes) == 1:
        # Sem separador: tenta identificar a UF no início ou no fim.
        tokens = limpo.split()
        if len(tokens) >= 2 and tokens[-1].upper() in UFS:
            partes = [" ".join(tokens[:-1]), tokens[-1]]
        elif len(tokens) >= 2 and tokens[0].upper() in UFS:
            partes = [" ".join(tokens[1:]), tokens[0]]
        else:
            return Resultado(
                False,
                erro="Não consegui identificar o estado. Responda no formato "
                "<b>Município/UF</b> — por exemplo: <code>Campinas/SP</code>.",
            )

    a, b = partes[0].strip(), partes[1].strip()
    if b.upper() in UFS:
        municipio, uf = a, b.upper()
    elif a.upper() in UFS:
        municipio, uf = b, a.upper()
    else:
        return Resultado(
            False,
            erro="Não encontrei uma sigla de estado válida. Use a sigla de 2 "
            "letras — por exemplo: <code>Belo Horizonte/MG</code>.",
        )

    if len(municipio) < 3:
        return Resultado(False, erro="O nome do município parece incompleto.")
    if len(municipio) > 80:
        return Resultado(False, erro="O nome do município é longo demais.")
    if not _RE_NOME.match(municipio):
        return Resultado(
            False, erro="O município deve conter apenas letras e espaços."
        )
    return Resultado(True, {"municipio": _titulo(municipio), "uf": uf})


def validar_serventia(texto: str) -> Resultado:
    limpo = _normalizar_espacos(texto)
    if len(limpo) < 3:
        return Resultado(
            False, erro="O nome da serventia parece curto demais."
        )
    if len(limpo) > 150:
        return Resultado(
            False, erro="A resposta é longa demais (máximo 150 caracteres)."
        )
    return Resultado(True, {"serventia": limpo})


def validar_cns(texto: str) -> Resultado:
    """CNS — Código Nacional da Serventia.

    A validação é deliberadamente tolerante quanto à pontuação: aceita
    `123456-7`, `12.3456-7` ou `1234567`, conferindo apenas a quantidade de
    dígitos. Recusar um CNS válido por causa do formato deixaria a pessoa
    presa no meio do cadastro, enquanto um código estranho apenas chega ao
    card e o administrador avalia.
    """
    limpo = _normalizar_espacos(texto)
    if not limpo:
        return Resultado(False, erro="Informe o CNS do cartório.")

    if not re.fullmatch(r"[0-9][0-9\.\-/\s]*", limpo):
        return Resultado(
            False,
            erro="O CNS é numérico. Use apenas números e, se quiser, "
            "os separadores <code>. -</code> — por exemplo: <code>123456-7</code>.",
        )

    digitos = re.sub(r"\D", "", limpo)
    if len(digitos) < 6:
        return Resultado(
            False,
            erro=f"O CNS informado tem só {len(digitos)} dígitos. "
            "O código costuma ter 6 dígitos mais o dígito verificador.",
        )
    if len(digitos) > 12:
        return Resultado(False, erro="O CNS informado tem dígitos demais.")

    return Resultado(True, {"cns": limpo})


# ---------------------------------------------------------------------------
# Definição das perguntas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pergunta:
    chave: str
    pergunta: str
    validar: Callable[[str], Resultado]
    # Quando preenchido, a pergunta é feita com botões em vez de texto livre.
    opcoes: tuple[str, ...] = ()


PERGUNTAS: tuple[Pergunta, ...] = (
    Pergunta(
        chave="titular",
        pergunta=(
            "<b>Pergunta 1 de 5</b>\n\n"
            "Você é titular de Serventia Extrajudicial?\n\n"
            "<i>Toque em uma das opções abaixo.</i>"
        ),
        validar=validar_titular,
        opcoes=tuple(OPCOES_TITULAR),
    ),
    Pergunta(
        chave="nome_completo",
        pergunta=(
            "<b>Pergunta 2 de 5</b>\n\n"
            "Qual o seu <b>nome completo</b>?\n\n"
            "<i>Exemplo: Maria Aparecida de Souza</i>"
        ),
        validar=validar_nome_completo,
    ),
    Pergunta(
        chave="municipio_uf",
        pergunta=(
            "<b>Pergunta 3 de 5</b>\n\n"
            "Qual seu <b>Município/UF</b>?\n\n"
            "<i>Exemplo: Campinas/SP</i>"
        ),
        validar=validar_municipio_uf,
    ),
    Pergunta(
        chave="serventia",
        pergunta=(
            "<b>Pergunta 4 de 5</b>\n\n"
            "Qual o <b>nome da Serventia</b>?"
        ),
        validar=validar_serventia,
    ),
    Pergunta(
        chave="cns",
        pergunta=(
            "<b>Pergunta 5 de 5</b>\n\n"
            "Informe o <b>CNS do Cartório</b>.\n\n"
            "<i>Código Nacional da Serventia — última pergunta!</i>"
        ),
        validar=validar_cns,
    ),
)

TOTAL_PERGUNTAS = len(PERGUNTAS)
