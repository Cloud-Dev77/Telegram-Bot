"""Testes das validações das 5 perguntas."""

from __future__ import annotations

import unittest

from bot.questions import (
    validar_categoria,
    validar_nome_completo,
    validar_registro,
    validar_uf_municipio,
    validar_unidade,
)


class TestCategoria(unittest.TestCase):
    def test_aceita_opcao_valida(self):
        resultado = validar_categoria("Membro Efetivo")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["categoria"], "Membro Efetivo")

    def test_ignora_maiusculas_e_espacos(self):
        resultado = validar_categoria("  membro   efetivo ")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["categoria"], "Membro Efetivo")

    def test_recusa_opcao_desconhecida(self):
        self.assertFalse(validar_categoria("Visitante").ok)


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


class TestUfMunicipio(unittest.TestCase):
    def test_formato_com_virgula(self):
        resultado = validar_uf_municipio("SP, Campinas")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores, {"uf": "SP", "municipio": "Campinas"})

    def test_formato_com_hifen_e_ordem_invertida(self):
        resultado = validar_uf_municipio("belo horizonte - mg")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["uf"], "MG")
        self.assertEqual(resultado.valores["municipio"], "Belo Horizonte")

    def test_formato_sem_separador(self):
        resultado = validar_uf_municipio("RJ Nova Iguacu")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["uf"], "RJ")

    def test_preposicoes_ficam_minusculas(self):
        resultado = validar_uf_municipio("SP, São José dos Campos")
        self.assertEqual(resultado.valores["municipio"], "São José dos Campos")

    def test_recusa_uf_inexistente(self):
        self.assertFalse(validar_uf_municipio("XX, Cidade").ok)

    def test_recusa_apenas_o_estado(self):
        self.assertFalse(validar_uf_municipio("SP").ok)


class TestUnidade(unittest.TestCase):
    def test_aceita_texto_livre(self):
        resultado = validar_unidade("  Hospital  Municipal  ")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["unidade"], "Hospital Municipal")

    def test_recusa_vazio(self):
        self.assertFalse(validar_unidade(" ").ok)


class TestRegistro(unittest.TestCase):
    def test_aceita_codigo_comum(self):
        resultado = validar_registro("crm-sp 123456")
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.valores["registro"], "CRM-SP 123456")

    def test_recusa_curto_demais(self):
        self.assertFalse(validar_registro("12").ok)

    def test_recusa_simbolos(self):
        self.assertFalse(validar_registro("123@456").ok)

    def test_recusa_formula(self):
        """Resposta começando com '=' não pode virar fórmula na planilha."""
        self.assertFalse(validar_registro("=SOMA(A1:A9)").ok)


if __name__ == "__main__":
    unittest.main()
