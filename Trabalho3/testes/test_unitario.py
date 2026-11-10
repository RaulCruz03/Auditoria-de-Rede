"""Testes unitários do agente (sem snmpd): rodam em milissegundos.

    python3 -m unittest discover -s testes -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "agente"))

import agente_snmp as A  # noqa: E402
from autodescoberta import Autodescoberta, parse_arp  # noqa: E402

OUI = RAIZ.parent / "oui_db.json"
EXEMPLO = RAIZ / "testes" / "dados_exemplo"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(EXEMPLO / "historico.json", self.tmp / "historico.json")
        self.ad = Autodescoberta(self.tmp, OUI)
        self.ag = A.Agente(self.ad)
        os.environ.pop("AUTODESCOBERTA_ARP_FILE", None)

    def tearDown(self):
        os.environ.pop("AUTODESCOBERTA_ARP_FILE", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def varrer(self, arquivo_arp):
        os.environ["AUTODESCOBERTA_ARP_FILE"] = str(EXEMPLO / arquivo_arp)
        self.assertTrue(self.ad.executar_varredura())

    def percorrer(self, inicio="." + ".".join(map(str, A.RAIZ))):
        """Faz um WALK completo usando só GETNEXT, como snmpwalk faz."""
        oid, saida = inicio, []
        while True:
            r = self.ag.tratar_getnext(oid)
            if r == ["NONE"]:
                return saida
            saida.append(r)
            oid = r[0]


class TestOids(unittest.TestCase):
    def test_parse_e_formatacao(self):
        self.assertEqual(A.parse_oid(".1.3.6.1.3.99.1.1.0"), (1, 3, 6, 1, 3, 99, 1, 1, 0))
        self.assertEqual(A.formatar_oid((1, 3, 6)), ".1.3.6")

    def test_ordem_numerica_e_nao_textual(self):
        # como texto, "...2.10" < "...2.9"; como tupla, a ordem é a numérica
        self.assertLess(A.parse_oid("1.3.6.1.3.99.2.1.1.2.9"), A.parse_oid("1.3.6.1.3.99.2.1.1.2.10"))


class TestArp(unittest.TestCase):
    def test_parse_arp(self):
        texto = (EXEMPLO / "arp_cenario1.txt").read_text()
        achados = parse_arp(texto)
        self.assertEqual(len(achados), 4)  # a linha "<incomplete>" é ignorada
        self.assertEqual(achados[0], {"mac": "145120AAAA01", "ip": "192.168.4.1", "tipo": "Roteador"})
        self.assertEqual(achados[1]["tipo"], "Host")

    def test_gateway_pelo_ip_da_rota_padrao(self):
        texto = "? (10.0.0.1) at aa:bb:cc:dd:ee:ff [ether] on eth0\n"
        self.assertEqual(parse_arp(texto, frozenset({"10.0.0.1"}))[0]["tipo"], "Roteador")


class TestGetGetnext(Base):
    def test_get_escalares_e_tipos(self):
        r = self.ag.tratar_get(".1.3.6.1.3.99.1.1.0")
        self.assertEqual(r[1:], ["string", "wlp0s20f3"])
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.2.0")[1:], ["integer", "1"])
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.3.0")[1:], ["gauge", "0"])
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.4.0")[1:], ["counter", "0"])
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.5.0")[1], "timeticks")

    def test_inexistentes(self):
        for oid in (
            ".1.3.6.1.3.99.1.9.0",  # objeto que não existe
            ".1.3.6.1.3.99.1.1",  # escalar sem o sufixo .0
            ".1.3.6.1.3.99.2.1.1.2.99",  # linha inexistente
            ".1.3.6.1.3.99.2.1.1.1.1",  # coluna 1 é not-accessible
        ):
            self.assertEqual(self.ag.tratar_get(oid), ["NONE"], oid)

    def test_write_only_responde_ao_get_mas_nao_aparece_no_walk(self):
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.6.0")[1:], ["integer", "1"])
        self.assertNotIn(".1.3.6.1.3.99.1.6.0", [i[0] for i in self.percorrer()])

    def test_walk_completo_ordenado_e_sem_write_only(self):
        itens = self.percorrer()
        oids = [A.parse_oid(i[0]) for i in itens]
        self.assertEqual(oids, sorted(oids))
        self.assertEqual(len(itens), 5 + 4 * 6)  # 5 escalares legíveis + 4 dispositivos x 6 colunas
        self.assertNotIn(A.OID_EXECUTAR, oids)

    def test_getnext_a_partir_de_prefixo_e_fim_da_arvore(self):
        self.assertEqual(self.ag.tratar_getnext(".1.3.6.1.3")[0], ".1.3.6.1.3.99.1.1.0")
        self.assertEqual(self.ag.tratar_getnext(".1.3.6.1.3.99.1.6.0")[0], ".1.3.6.1.3.99.2.1.1.2.1")
        self.assertEqual(self.ag.tratar_getnext(".1.3.6.1.3.100"), ["NONE"])

    def test_tabela_indices_e_colunas(self):
        mac1 = self.ag.tratar_get(".1.3.6.1.3.99.2.1.1.2.1")
        ip3 = self.ag.tratar_get(".1.3.6.1.3.99.2.1.1.3.3")
        self.assertEqual(mac1[1:], ["string", "145120AAAA01"])
        self.assertEqual(ip3[1:], ["ipaddress", "192.168.4.3"])

    def test_ordem_numerica_com_mais_de_9_linhas(self):
        hist = {f"0000000000{i:02d}": {"ip": f"10.0.0.{i}", "tipo": "Host", "fabricante": "x",
                                        "status": "Dispositivo Ativo", "ultima_vez_visto": "2026-11-01 10:00:00"}
                for i in range(1, 13)}
        (self.tmp / "historico.json").write_text(json.dumps(hist))
        col2 = [i for i in self.percorrer() if i[0].startswith(".1.3.6.1.3.99.2.1.1.2.")]
        self.assertEqual([A.parse_oid(i[0])[-1] for i in col2], list(range(1, 13)))  # 9 vem antes de 10


class TestSet(Base):
    def test_tempo_espera_ping(self):
        self.assertEqual(self.ag.tratar_set(".1.3.6.1.3.99.1.2.0", "integer 5"), "DONE")
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.2.0")[2], "5")
        self.assertEqual(self.ag.tratar_set(".1.3.6.1.3.99.1.2.0", "integer 0"), "wrong-value")
        self.assertEqual(self.ag.tratar_set(".1.3.6.1.3.99.1.2.0", "integer 61"), "wrong-value")
        self.assertEqual(self.ag.tratar_set(".1.3.6.1.3.99.1.2.0", "string 5"), "wrong-type")
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.2.0")[2], "5")  # valor inválido não altera

    def test_somente_leitura_e_inexistente(self):
        for oid in (".1.3.6.1.3.99.1.1.0", ".1.3.6.1.3.99.1.3.0", ".1.3.6.1.3.99.2.1.1.2.1", ".1.3.6.1.3.99.1.9.0"):
            self.assertEqual(self.ag.tratar_set(oid, "integer 1"), "not-writable", oid)

    def test_executar_varredura_valida_valor_e_tipo(self):
        self.assertEqual(self.ag.tratar_set(".1.3.6.1.3.99.1.6.0", "integer 2"), "wrong-value")
        self.assertEqual(self.ag.tratar_set(".1.3.6.1.3.99.1.6.0", "string 1"), "wrong-type")


class TestVarredura(Base):
    def test_status_novo_ativo_inativo_e_indices(self):
        self.varrer("arp_cenario1.txt")
        h = self.ad.historico()
        self.assertEqual(h["145120AAAA01"]["status"], "Dispositivo Ativo")
        self.assertEqual(h["E0D464000005"]["status"], "Dispositivo Novo")
        self.assertEqual(h["E85A8B000003"]["status"], "Inativo")
        self.assertEqual({r["indice"] for r in h.values()}, {1, 2, 3, 4, 5, 6})
        self.assertEqual(h["E0D464000005"]["fabricante"], "Intel Corporate")
        self.assertIn("Desconhecido", h["F21122334455"]["fabricante"])  # MAC privado (administrado localmente)

        self.varrer("arp_cenario2.txt")
        h = self.ad.historico()
        self.assertEqual(h["E0D464000005"]["status"], "Dispositivo Ativo")  # Novo -> Ativo
        self.assertEqual(h["9CC7D3000002"]["status"], "Inativo")
        self.assertEqual(h["E0D464000005"]["indice"], 5)  # o índice não muda entre varreduras

    def test_escalares_refletem_a_varredura(self):
        self.varrer("arp_cenario1.txt")
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.3.0")[2], "4")  # ativos
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.4.0")[2], "1")  # varreduras
        self.varrer("arp_cenario2.txt")
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.3.0")[2], "2")
        self.assertEqual(self.ag.tratar_get(".1.3.6.1.3.99.1.4.0")[2], "2")
        self.assertLess(int(self.ag.tratar_get(".1.3.6.1.3.99.1.5.0")[2]), 500)  # < 5 s desde a última

    def test_varredura_simultanea_e_recusada(self):
        self.ad._trava_varredura.acquire()
        try:
            self.assertEqual(self.ag.tratar_set(".1.3.6.1.3.99.1.6.0", "integer 1"), "inconsistent-value")
            self.assertFalse(self.ad.executar_varredura())
        finally:
            self.ad._trava_varredura.release()


class TestProtocolo(Base):
    def test_laco_pass_persist(self):
        import io

        entrada = io.StringIO("PING\nget\n.1.3.6.1.3.99.1.1.0\ngetnext\n.1.3.6.1.3.100\nset\n.1.3.6.1.3.99.1.1.0\nstring x\n")
        saida = io.StringIO()
        A.servir(self.ag, entrada, saida, lambda m: None)
        self.assertEqual(
            saida.getvalue().splitlines(),
            ["PONG", ".1.3.6.1.3.99.1.1.0", "string", "wlp0s20f3", "NONE", "not-writable"],
        )


if __name__ == "__main__":
    unittest.main()
