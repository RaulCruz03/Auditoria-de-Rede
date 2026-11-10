"""Etapa 6 - tratar_set e disparar_varredura"""

import time

from base import ENTRADA, R, TesteComDados, ad, agente

F = lambda t: "." + ".".join(map(str, t))  # noqa: E731
TEMPO, EXECUTAR = F(R + (1, 2, 0)), F(R + (1, 6, 0))


class Etapa6(TesteComDados):
    def esperar(self, condicao, segundos=3):
        fim = time.time() + segundos
        while time.time() < fim:
            if condicao():
                return True
            time.sleep(0.05)
        return False

    def test_a_set_tempo_ok(self):
        """SET tempoEsperaPing 'integer 5' -> DONE e o valor é gravado em estado.json"""
        self.assertEqual(agente.tratar_set(TEMPO, "integer 5"), "DONE")
        self.assertEqual(ad.ler_estado(self.dir)["tempo_espera_ping"], 5)

    def test_b_set_tempo_fora_da_faixa(self):
        """SET tempoEsperaPing fora de 1..60 (ou não numérico) -> wrong-value, e nada muda"""
        for v in ("integer 0", "integer 61", "integer -3", "integer abc"):
            self.assertEqual(agente.tratar_set(TEMPO, v), "wrong-value", v)
        self.assertEqual(ad.ler_estado(self.dir)["tempo_espera_ping"], 1)

    def test_c_set_tempo_tipo_errado(self):
        """SET tempoEsperaPing com tipo diferente de integer -> wrong-type"""
        self.assertEqual(agente.tratar_set(TEMPO, "string 5"), "wrong-type")

    def test_d_somente_leitura(self):
        """SET em objeto read-only, célula da tabela ou OID inexistente -> not-writable"""
        for oid in (R + (1, 1, 0), R + (1, 3, 0), ENTRADA + (2, 1), R + (1, 9, 0)):
            self.assertEqual(agente.tratar_set(F(oid), "integer 1"), "not-writable", F(oid))

    def test_e_executar_validacoes(self):
        """SET executarVarredura: valor != 1 -> wrong-value; tipo != integer -> wrong-type"""
        self.assertEqual(agente.tratar_set(EXECUTAR, "integer 2"), "wrong-value")
        self.assertEqual(agente.tratar_set(EXECUTAR, "string 1"), "wrong-type")

    def test_f_executar_dispara_varredura(self):
        """SET executarVarredura 1 -> DONE na hora, e a varredura roda em segundo plano"""
        self.usar_arp("arp_cenario1.txt")
        self.assertEqual(agente.tratar_set(EXECUTAR, "integer 1"), "DONE")
        self.assertTrue(self.esperar(lambda: ad.ler_estado(self.dir)["total_varreduras"] == 1),
                        "total_varreduras não chegou a 1 em 3 s")

    def test_g_nao_bloqueia(self):
        """disparar_varredura volta imediatamente, mesmo que a varredura demore"""
        original = ad.varredura
        ad.varredura = lambda *a: time.sleep(0.6)
        try:
            t0 = time.time()
            self.assertTrue(agente.disparar_varredura())
            self.assertLess(time.time() - t0, 0.3, "a varredura deve rodar numa thread")
        finally:
            time.sleep(0.7)
            ad.varredura = original

    def test_h_uma_de_cada_vez(self):
        """com uma varredura em andamento, disparar_varredura devolve False e o SET inconsistent-value"""
        original = ad.varredura
        ad.varredura = lambda *a: time.sleep(0.5)
        try:
            self.assertTrue(agente.disparar_varredura())
            self.assertFalse(agente.disparar_varredura())
            self.assertEqual(agente.tratar_set(EXECUTAR, "integer 1"), "inconsistent-value")
            self.assertTrue(self.esperar(agente.disparar_varredura, 2), "a trava não foi liberada no fim")
        finally:
            time.sleep(0.6)
            ad.varredura = original

    def test_i_trava_liberada_mesmo_com_erro(self):
        """se a varredura der erro, a trava é liberada (try/finally) e a próxima pode rodar"""
        original = ad.varredura

        def falha(*a):
            raise RuntimeError("erro simulado (é esperado ver isto no teste)")

        ad.varredura = falha
        try:
            agente.disparar_varredura()
            self.assertTrue(self.esperar(agente.disparar_varredura, 2), "a trava ficou presa depois do erro")
        finally:
            time.sleep(0.2)
            ad.varredura = original
