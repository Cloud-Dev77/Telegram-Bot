"""Testes das validações das 5 perguntas.

As perguntas espelham o formulário "Cadastro - Grupo Titulares Telegram":
titular de serventia (Sim/Não), nome completo, Município/UF, nome da
serventia e CNS do cartório.
"""

from __future__ import annotations

import unittest

from bot.questions import (
    validar_cns,
    validar_municipio_uf,
    validar_nome_completo,
    validar_serventia,
    validar_titular,
)


class TestTitularDeServentia(unittest.TestCase):
    def test_aceita_sim(self):
        resultado = validar_titular("Sim")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["titular"], "Sim")

    def test_aceita_nao(self):
        resultado = validar_titular("Não")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["titular"], "Não")

    def test_ignora_maiusculas_e_espacos(self):
        resultado = validar_titular("  sim  ")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["titular"], "Sim")

    def test_recusa_qualquer_outra_coisa(self):
        for texto in ("talvez", "Membro Efetivo", "S", "1"):
            with self.subTest(texto=texto):
                self.assertFalse(validar_titular(texto).ok)


class TestNomeCompleto(unittest.TestCase):
    def test_aceita_nome_com_sobrenome(self):
        resultado = validar_nome_completo("maria aparecida de souza")
        self.assertTrue(resultado.ok)
        self.assertEqual(
            resultado.valores["nome_completo"], "Maria Aparecida de Souza"
        )

    def test_recusa_nome_unico(self):
        self.assertFalse(validar_nome_completo("Maria").ok)

    def test_recusa_numeros(self):
        self.assertFalse(validar_nome_completo("Joao 123 Silva").ok)

    def test_aceita_acentos_e_hifen(self):
        self.assertTrue(validar_nome_completo("Ana-Luíza Gonçalves").ok)

    def test_recusa_texto_gigante(self):
        self.assertFalse(validar_nome_completo("Ana " + "Silva " * 40).ok)


class TestMunicipioUf(unittest.TestCase):
    def test_formato_do_formulario(self):
        """O formulário pede exatamente 'Município/UF'."""
        resultado = validar_municipio_uf("Campinas/SP")
        self.assertTrue(resultado.ok)
        self.assertEqual(
            resultado.valores, {"municipio": "Campinas", "uf": "SP"}
        )

    def test_aceita_virgula(self):
        resultado = validar_municipio_uf("Belo Horizonte, MG")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["uf"], "MG")
        self.assertEqual(resultado.valores["municipio"], "Belo Horizonte")

    def test_aceita_ordem_invertida(self):
        """Muita gente escreve 'SP, Campinas' por hábito."""
        resultado = validar_municipio_uf("SP, Campinas")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["municipio"], "Campinas")
        self.assertEqual(resultado.valores["uf"], "SP")

    def test_formato_sem_separador(self):
        resultado = validar_municipio_uf("Nova Iguacu RJ")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["uf"], "RJ")

    def test_preposicoes_ficam_minusculas(self):
        resultado = validar_municipio_uf("São José dos Campos/SP")
        self.assertEqual(resultado.valores["municipio"], "São José dos Campos")

    def test_recusa_uf_inexistente(self):
        self.assertFalse(validar_municipio_uf("Cidade/XX").ok)

    def test_recusa_apenas_o_estado(self):
        self.assertFalse(validar_municipio_uf("SP").ok)


class TestServentia(unittest.TestCase):
    def test_aceita_nome_de_cartorio(self):
        resultado = validar_serventia("  1º  Tabelionato de Notas  ")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["serventia"], "1º Tabelionato de Notas")

    def test_recusa_curto_demais(self):
        self.assertFalse(validar_serventia("x").ok)

    def test_recusa_vazio(self):
        self.assertFalse(validar_serventia(" ").ok)


class TestCns(unittest.TestCase):
    """CNS — Código Nacional da Serventia."""

    def test_aceita_com_hifen(self):
        resultado = validar_cns("123456-7")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["cns"], "123456-7")

    def test_aceita_so_digitos(self):
        self.assertTrue(validar_cns("1234567").ok)

    def test_aceita_com_ponto_e_hifen(self):
        self.assertTrue(validar_cns("12.3456-7").ok)

    def test_recusa_curto_demais(self):
        resultado = validar_cns("123")
        self.assertFalse(resultado.ok)
        self.assertIn("3 dígitos", resultado.erro)

    def test_recusa_letras(self):
        self.assertFalse(validar_cns("CNS123456").ok)

    def test_recusa_digitos_demais(self):
        self.assertFalse(validar_cns("1234567890123456").ok)

    def test_recusa_formula(self):
        """Resposta começando com '=' não pode virar fórmula na planilha."""
        self.assertFalse(validar_cns("=SOMA(A1:A9)").ok)

    def test_recusa_vazio(self):
        self.assertFalse(validar_cns("").ok)


if __name__ == "__main__":
    unittest.main()
