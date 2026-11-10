"""Etapa 3 - OIDs"""

import unittest

from base import ENTRADA, R, agente


class Etapa3(unittest.TestCase):
    def test_a_constantes(self):
        """As constantes OID_* e ENTRADA batem com a MIB (escalares com .0 no final)"""
        esperado = {
            "OID_INTERFACE": R + (1, 1, 0), "OID_TEMPO_PING": R + (1, 2, 0),
            "OID_TOTAL_ATIVOS": R + (1, 3, 0), "OID_TOTAL_VARREDURAS": R + (1, 4, 0),
            "OID_TEMPO_DESDE_ULTIMA": R + (1, 5, 0), "OID_EXECUTAR": R + (1, 6, 0), "ENTRADA": ENTRADA,
        }
        for nome, valor in esperado.items():
            if getattr(agente, nome) is None:
                raise NotImplementedError(f"defina {nome} (ainda é None)")
            self.assertEqual(getattr(agente, nome), valor, f"{nome} está errado")

    def test_b_parse_oid(self):
        """parse_oid aceita com ou sem ponto inicial e ignora espaços/quebras nas pontas"""
        self.assertEqual(agente.parse_oid(".1.3.6.1"), (1, 3, 6, 1))
        self.assertEqual(agente.parse_oid("1.3.6.1"), (1, 3, 6, 1))
        self.assertEqual(agente.parse_oid(" .1.3.6.1.3.99.2.1.1.2.10\n"), R + (2, 1, 1, 2, 10))

    def test_c_formatar_oid(self):
        """formatar_oid devolve o texto com ponto inicial"""
        self.assertEqual(agente.formatar_oid((1, 3, 6, 1, 3, 99, 1, 1, 0)), ".1.3.6.1.3.99.1.1.0")

    def test_d_ida_e_volta(self):
        """formatar_oid(parse_oid(x)) == x"""
        x = ".1.3.6.1.3.99.2.1.1.7.12"
        self.assertEqual(agente.formatar_oid(agente.parse_oid(x)), x)

    def test_e_ordem(self):
        """Com tuplas, ...2.9 vem ANTES de ...2.10 (como texto seria o contrário!)"""
        nove, dez = ".1.3.6.1.3.99.2.1.1.2.9", ".1.3.6.1.3.99.2.1.1.2.10"
        self.assertGreater(nove, dez, "isto é só uma demonstração: como texto, '9' > '1'")
        self.assertLess(agente.parse_oid(nove), agente.parse_oid(dez))
