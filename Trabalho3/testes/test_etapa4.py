"""Etapa 4 - instancias()"""

import json
import time

from base import ENTRADA, R, TesteComDados, agente


class Etapa4(TesteComDados):
    def test_a_quantidade(self):
        """instancias tem 5 escalares + 4 dispositivos x 6 colunas = 29 itens"""
        self.assertEqual(len(agente.instancias()), 29)

    def test_b_ordenada(self):
        """instancias está ordenada por OID (tupla), sem repetições"""
        oids = [i[0] for i in agente.instancias()]
        self.assertEqual(oids, sorted(set(oids)))
        self.assertIsInstance(oids[0], tuple, "o OID deve ser uma tupla de inteiros, não texto")

    def test_c_escalares(self):
        """escalares com os tipos certos e valores do estado padrão (valores sempre como texto)"""
        d = {o: (t, v) for o, t, v in agente.instancias()}
        self.assertEqual(d[R + (1, 1, 0)], ("string", "wlp0s20f3"))
        self.assertEqual(d[R + (1, 2, 0)], ("integer", "1"))
        self.assertEqual(d[R + (1, 3, 0)], ("gauge", "0"))
        self.assertEqual(d[R + (1, 4, 0)], ("counter", "0"))
        self.assertEqual(d[R + (1, 5, 0)][0], "timeticks")

    def test_d_sem_write_only_e_sem_coluna_indice(self):
        """executarVarredura (write-only) e a coluna 1 (not-accessible) não aparecem"""
        oids = [i[0] for i in agente.instancias()]
        self.assertNotIn(R + (1, 6, 0), oids)
        self.assertFalse([o for o in oids if o[:10] == ENTRADA + (1,)])

    def test_e_tabela(self):
        """células da tabela: ENTRADA + (coluna, indice), com tipos string/ipaddress"""
        d = {o: (t, v) for o, t, v in agente.instancias()}
        self.assertEqual(d[ENTRADA + (2, 1)], ("string", "145120AAAA01"))
        self.assertEqual(d[ENTRADA + (3, 3)], ("ipaddress", "192.168.4.3"))
        self.assertEqual(d[ENTRADA + (4, 1)], ("string", "Roteador"))
        self.assertEqual(d[ENTRADA + (5, 4)], ("string", "Intelbras"))
        self.assertEqual(d[ENTRADA + (6, 2)], ("string", "Inativo"))
        self.assertEqual(d[ENTRADA + (7, 3)], ("string", "2026-10-30 18:30:00"))

    def test_f_dados_vivos(self):
        """mudar historico.json muda a próxima chamada de instancias (sem reiniciar nada)"""
        h = self.historico()
        h["145120AAAA01"]["status"] = "Dispositivo Ativo"
        self.gravar_historico(h)
        d = {o: v for o, t, v in agente.instancias()}
        self.assertEqual(d[R + (1, 3, 0)], "1")

    def test_g_timeticks(self):
        """tempoDesdeUltimaVarredura: centésimos de segundo desde ultima_varredura_epoch"""
        (self.dir / "estado.json").write_text(json.dumps({"ultima_varredura_epoch": time.time() - 10}))
        d = {o: v for o, t, v in agente.instancias()}
        self.assertTrue(900 <= int(d[R + (1, 5, 0)]) <= 1200, f"esperado ~1000, veio {d[R + (1, 5, 0)]}")

    def test_h_timeticks_sem_varredura(self):
        """sem ultima_varredura_epoch, usa o maior ultima_vez_visto; sem histórico, 0"""
        d = {o: v for o, t, v in agente.instancias()}
        self.assertGreater(int(d[R + (1, 5, 0)]), 0)
        self.gravar_historico({})
        d = {o: v for o, t, v in agente.instancias()}
        self.assertEqual(d[R + (1, 5, 0)], "0")
        self.assertEqual(len(d), 5)

    def test_i_counter_32_bits(self):
        """Counter32 dá a volta em 2**32"""
        (self.dir / "estado.json").write_text(json.dumps({"total_varreduras": 2**32 + 5}))
        d = {o: v for o, t, v in agente.instancias()}
        self.assertEqual(d[R + (1, 4, 0)], "5")

    def test_j_historico_sem_indice(self):
        """um historico.json do Trabalho 1 (sem 'indice') também funciona: índices 1..4"""
        h = self.historico()
        for r in h.values():
            r.pop("indice", None)
        self.gravar_historico(h)
        indices = sorted({o[-1] for o, t, v in agente.instancias() if o[:9] == ENTRADA})
        self.assertEqual(indices, [1, 2, 3, 4])
