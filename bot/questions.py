"""As 5 perguntas do processo de triagem, com validação de cada resposta.

=============================================================================
ESTE É O SEGUNDO ARQUIVO PENSADO PARA PERSONALIZAÇÃO.
=============================================================================

Para trocar o texto de uma pergunta, edite o campo `pergunta` da entrada
correspondente em `PERGUNTAS`, no fim do arquivo.

Para trocar as opções de categoria, edite a lista `CATEGORIAS`.

A validação existe para que nenhuma linha da planilha chegue incompleta ou com
lixo aos administradores: cada resposta é conferida antes de o candidato
avançar para a próxima pergunta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------------------
# Opções da pergunta 1 (botões). Edite à vontade — a ordem é a que aparece.
# ---------------------------------------------------------------------------

CATEGORIAS: list[str] = [
    "Membro Efetivo",
    "Associado",
    "Outros",
]

# Unidades da federação válidas, usadas para validar a pergunta 3.
UFS: frozenset[str] = frozenset(
    """AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI
       RJ RN RS RO RR SC SP SE TO""".split()
)


@dataclass(frozen=True)
class Resultado:
    """Resultado de uma validação.

    `valores` mapeia nome do campo -> valor já limpo e pronto para a planilha.
    Uma pergunta pode preencher mais de um campo (é o caso de UF + Município).
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


def validar_categoria(texto: str) -> Resultado:
    """Aceita o texto exato de um dos botões (ou o mesmo texto digitado)."""
    limpo = _normalizar_espacos(texto)
    for opcao in CATEGORIAS:
        if limpo.casefold() == opcao.casefold():
            return Resultado(True, {"categoria": opcao})
    opcoes = " • ".join(CATEGORIAS)
    return Resultado(
        False, erro=f"Escolha uma das opções usando os botões acima: {opcoes}."
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


def validar_uf_municipio(texto: str) -> Resultado:
    """Aceita 'SP, Campinas', 'SP - Campinas', 'SP/Campinas', 'Campinas SP'..."""
    limpo = _normalizar_espacos(texto)
    partes = re.split(r"\s*[,;/|\-–—]\s*", limpo, maxsplit=1)

    if len(partes) == 1:
        # Sem separador: tenta identificar a UF no início ou no fim.
        tokens = limpo.split()
        if len(tokens) >= 2 and tokens[0].upper() in UFS:
            partes = [tokens[0], " ".join(tokens[1:])]
        elif len(tokens) >= 2 and tokens[-1].upper() in UFS:
            partes = [tokens[-1], " ".join(tokens[:-1])]
        else:
            return Resultado(
                False,
                erro="Não consegui identificar o estado. Responda no formato "
                "<b>UF, Município</b> — por exemplo: <code>SP, Campinas</code>.",
            )

    a, b = partes[0].strip(), partes[1].strip()
    if a.upper() in UFS:
        uf, municipio = a.upper(), b
    elif b.upper() in UFS:
        uf, municipio = b.upper(), a
    else:
        return Resultado(
            False,
            erro=f"<b>{a[:20]}</b> não é uma sigla de estado válida. Use a sigla "
            "de 2 letras — por exemplo: <code>MG, Belo Horizonte</code>.",
        )

    if len(municipio) < 3:
        return Resultado(False, erro="O nome do município parece incompleto.")
    if len(municipio) > 80:
        return Resultado(False, erro="O nome do município é longo demais.")
    if not _RE_NOME.match(municipio):
        return Resultado(
            False, erro="O município deve conter apenas letras e espaços."
        )
    return Resultado(True, {"uf": uf, "municipio": _titulo(municipio)})


def validar_unidade(texto: str) -> Resultado:
    limpo = _normalizar_espacos(texto)
    if len(limpo) < 2:
        return Resultado(False, erro="A resposta é curta demais.")
    if len(limpo) > 120:
        return Resultado(
            False, erro="A resposta é longa demais (máximo 120 caracteres)."
        )
    return Resultado(True, {"unidade": limpo})


def validar_registro(texto: str) -> Resultado:
    limpo = _normalizar_espacos(texto)
    if not 3 <= len(limpo) <= 40:
        return Resultado(False, erro="O código deve ter entre 3 e 40 caracteres.")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9\s\.\-/]*$", limpo):
        return Resultado(
            False,
            erro="Use apenas letras, números e os sinais <code>. - /</code>.",
        )
    return Resultado(True, {"registro": limpo.upper()})


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
        chave="categoria",
        pergunta=(
            "<b>Pergunta 1 de 5</b>\n\n"
            "Qual é o seu perfil na comunidade?\n\n"
            "<i>Toque em uma das opções abaixo.</i>"
        ),
        validar=validar_categoria,
        opcoes=tuple(CATEGORIAS),
    ),
    Pergunta(
        chave="nome_completo",
        pergunta=(
            "<b>Pergunta 2 de 5</b>\n\n"
            "Qual é o seu <b>nome completo</b>?\n\n"
            "<i>Exemplo: Maria Aparecida de Souza</i>"
        ),
        validar=validar_nome_completo,
    ),
    Pergunta(
        chave="uf_municipio",
        pergunta=(
            "<b>Pergunta 3 de 5</b>\n\n"
            "Em qual <b>estado e município</b> você atua?\n\n"
            "<i>Responda no formato UF, Município — exemplo: SP, Campinas</i>"
        ),
        validar=validar_uf_municipio,
    ),
    Pergunta(
        chave="unidade",
        pergunta=(
            "<b>Pergunta 4 de 5</b>\n\n"
            "Qual é o nome da sua <b>unidade, empresa ou entidade</b>?\n\n"
            "<i>Se não houver, responda: Não se aplica</i>"
        ),
        validar=validar_unidade,
    ),
    Pergunta(
        chave="registro",
        pergunta=(
            "<b>Pergunta 5 de 5</b>\n\n"
            "Informe o seu <b>código de registro profissional ou de cadastro</b>.\n\n"
            "<i>Última pergunta!</i>"
        ),
        validar=validar_registro,
    ),
)

TOTAL_PERGUNTAS = len(PERGUNTAS)
