"""Etapa 2 - servir(): o laço de comunicação com o snmpd"""

import io
import unittest

from base import agente


class SaidaQueContaFlush(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1


class Etapa2(unittest.TestCase):
    """Aqui tratar_get/getnext/set são substituídas por versões falsas: só o laço é testado."""

    def setUp(self):
        self.originais = (agente.tratar_get, agente.tratar_getnext, agente.tratar_set)
        self.chamadas = []
        agente.tratar_get = lambda oid: self.chamadas.append(("get", oid)) or [oid, "string", "G"]
        agente.tratar_getnext = lambda oid: self.chamadas.append(("getnext", oid)) or ["NONE"]
        agente.tratar_set = lambda oid, v: self.chamadas.append(("set", oid, v)) or "DONE"

    def tearDown(self):
        agente.tratar_get, agente.tratar_getnext, agente.tratar_set = self.originais

    def rodar(self, texto):
        saida = SaidaQueContaFlush()
        agente.servir(io.StringIO(texto), saida)
        return saida

    def test_a_ping(self):
        """servir responde PONG a PING e retorna quando a entrada acaba"""
        self.assertEqual(self.rodar("PING\n").getvalue(), "PONG\n")

    def test_b_get(self):
        """servir lê o OID da linha seguinte ao 'get' (sem o \\n) e escreve as 3 linhas da resposta"""
        s = self.rodar("get\n.1.3.6.1.3.99.1.1.0\n")
        self.assertEqual(self.chamadas, [("get", ".1.3.6.1.3.99.1.1.0")])
        self.assertEqual(s.getvalue(), ".1.3.6.1.3.99.1.1.0\nstring\nG\n")

    def test_c_getnext(self):
        """servir trata 'getnext' e escreve NONE quando é isso que tratar_getnext devolve"""
        s = self.rodar("getnext\n.1.3.6.1.3.99\n")
        self.assertEqual(self.chamadas, [("getnext", ".1.3.6.1.3.99")])
        self.assertEqual(s.getvalue(), "NONE\n")

    def test_d_set(self):
        """servir lê DUAS linhas depois de 'set' (OID e '<tipo> <valor>') e responde em uma linha"""
        s = self.rodar("set\n.1.3.6.1.3.99.1.2.0\ninteger 5\n")
        self.assertEqual(self.chamadas, [("set", ".1.3.6.1.3.99.1.2.0", "integer 5")])
        self.assertEqual(s.getvalue(), "DONE\n")

    def test_e_sequencia_e_flush(self):
        """servir atende vários comandos em sequência e dá flush() depois de CADA resposta"""
        s = self.rodar("PING\nget\n.1.3\nPING\n")
        self.assertEqual(s.getvalue(), "PONG\n.1.3\nstring\nG\nPONG\n")
        self.assertGreaterEqual(s.flushes, 3, "sem flush o snmpd fica esperando a resposta para sempre")

    def test_f_ignora_vazias_e_desconhecidos(self):
        """servir ignora linhas vazias e comandos desconhecidos sem travar"""
        self.assertEqual(self.rodar("\nBLA\nPING\n").getvalue(), "PONG\n")
