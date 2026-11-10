"""Etapa 5 - tratar_get e tratar_getnext"""

from base import ENTRADA, R, TesteComDados, agente

F = lambda t: "." + ".".join(map(str, t))  # noqa: E731


class Etapa5(TesteComDados):
    def test_a_get_escalar(self):
        """GET de um escalar existente devolve [oid, tipo, valor]"""
        self.assertEqual(agente.tratar_get(F(R + (1, 1, 0))), [F(R + (1, 1, 0)), "string", "wlp0s20f3"])

    def test_b_get_celula(self):
        """GET de uma célula da tabela"""
        self.assertEqual(agente.tratar_get(F(ENTRADA + (3, 2))), [F(ENTRADA + (3, 2)), "ipaddress", "192.168.4.5"])

    def test_c_get_inexistentes(self):
        """GET de OID inexistente devolve ['NONE'] (objeto que não existe, escalar sem .0, linha 99, coluna 1)"""
        for oid in (R + (1, 9, 0), R + (1, 1), ENTRADA + (2, 99), ENTRADA + (1, 1), R):
            self.assertEqual(agente.tratar_get(F(oid)), ["NONE"], F(oid))

    def test_d_getnext_da_raiz(self):
        """GETNEXT da raiz (que não é instância) devolve a primeira instância"""
        self.assertEqual(agente.tratar_getnext(F(R))[0], F(R + (1, 1, 0)))
        self.assertEqual(agente.tratar_getnext(".1.3.6.1.3")[0], F(R + (1, 1, 0)))

    def test_e_getnext_estritamente_maior(self):
        """GETNEXT de uma instância devolve a SEGUINTE, não ela mesma"""
        self.assertEqual(agente.tratar_getnext(F(R + (1, 1, 0)))[0], F(R + (1, 2, 0)))

    def test_f_getnext_pula_para_a_tabela(self):
        """GETNEXT depois do último escalar vai para a 1ª célula da tabela (coluna 2, linha 1)"""
        self.assertEqual(agente.tratar_getnext(F(R + (1, 5, 0)))[0], F(ENTRADA + (2, 1)))
        self.assertEqual(agente.tratar_getnext(F(R + (1, 6, 0)))[0], F(ENTRADA + (2, 1)))

    def test_g_getnext_fim(self):
        """GETNEXT depois da última instância devolve ['NONE']"""
        self.assertEqual(agente.tratar_getnext(F(ENTRADA + (7, 4))), ["NONE"])
        self.assertEqual(agente.tratar_getnext(".1.3.6.1.3.100"), ["NONE"])

    def test_h_walk(self):
        """Um WALK (GETNEXT repetido) percorre as 29 instâncias em ordem"""
        oid, vistos = F(R), []
        for _ in range(100):
            r = agente.tratar_getnext(oid)
            if r == ["NONE"]:
                break
            vistos.append(r[0])
            oid = r[0]
        self.assertEqual(len(vistos), 29)

    def test_i_ordem_com_mais_de_9_linhas(self):
        """Com 12 dispositivos, o WALK da coluna 2 vem na ordem 1, 2, ..., 9, 10, 11, 12"""
        self.gravar_historico({f"0000000000{i:02d}": {"indice": i, "ip": f"10.0.0.{i}", "tipo": "Host",
                                                      "fabricante": "x", "status": "Inativo",
                                                      "ultima_vez_visto": "2026-11-01 10:00:00"} for i in range(12, 0, -1)})
        oid, linhas = F(ENTRADA + (2,)), []
        while True:
            r = agente.tratar_getnext(oid)
            if r == ["NONE"] or not r[0].startswith(F(ENTRADA + (2,)) + "."):
                break
            linhas.append(int(r[0].rsplit(".", 1)[1]))
            oid = r[0]
        self.assertEqual(linhas, list(range(1, 13)))
