"""Etapa 1 - autodescoberta.py"""

import copy
import json
import time

from base import EXEMPLO, OUI, TesteComDados, ad


class Etapa1(TesteComDados):
    def test_a_carregar_json_inexistente(self):
        """carregar_json devolve o padrão se o arquivo não existe (FileNotFoundError)"""
        self.assertEqual(ad.carregar_json(self.dir / "nao_existe.json", {"x": 1}), {"x": 1})

    def test_b_carregar_json_corrompido(self):
        """carregar_json devolve o padrão se o JSON é inválido (json.JSONDecodeError)"""
        (self.dir / "ruim.json").write_text("{ isto não é json", encoding="utf-8")
        self.assertEqual(ad.carregar_json(self.dir / "ruim.json", []), [])

    def test_c_salvar_e_carregar_com_acentos(self):
        """salvar_json grava em UTF-8 sem escapar acentos (ensure_ascii=False) e carregar_json lê de volta"""
        dados = {"fabricante": "Xiaomi Communicações Ltda"}
        ad.salvar_json(self.dir / "a.json", dados)
        self.assertIn("Communicações", (self.dir / "a.json").read_text(encoding="utf-8"))
        self.assertEqual(ad.carregar_json(self.dir / "a.json", None), dados)

    def test_d_ler_estado(self):
        """ler_estado: sem estado.json devolve ESTADO_PADRAO; com ele, mistura os dois"""
        self.assertEqual(ad.ler_estado(self.dir), ad.ESTADO_PADRAO)
        (self.dir / "estado.json").write_text('{"total_varreduras": 3}', encoding="utf-8")
        e = ad.ler_estado(self.dir)
        self.assertEqual(e["total_varreduras"], 3)
        self.assertEqual(e["interface"], "wlp0s20f3")

    def test_e_atualizar_estado(self):
        """atualizar_estado grava os campos em estado.json sem estragar ESTADO_PADRAO"""
        original = dict(ad.ESTADO_PADRAO)
        ad.atualizar_estado(self.dir, tempo_espera_ping=5)
        self.assertEqual(ad.ler_estado(self.dir)["tempo_espera_ping"], 5)
        self.assertEqual(ad.ler_estado(self.dir)["interface"], "wlp0s20f3")
        self.assertEqual(ad.ESTADO_PADRAO, original, "ESTADO_PADRAO foi modificado: use dict(ESTADO_PADRAO)")

    def test_f_parse_arp(self):
        """parse_arp extrai mac (sem ':' e maiúsculo), ip e tipo de cada linha válida"""
        achados = ad.parse_arp((EXEMPLO / "arp_cenario1.txt").read_text())
        self.assertEqual(achados[0], {"mac": "145120AAAA01", "ip": "192.168.4.1", "tipo": "Roteador"})
        self.assertEqual(achados[1], {"mac": "9CC7D3000002", "ip": "192.168.4.5", "tipo": "Host"})

    def test_g_parse_arp_ignora_incompletas(self):
        """parse_arp ignora '<incomplete>' e linhas vazias (o arp_cenario1 tem 4 válidas de 5)"""
        texto = (EXEMPLO / "arp_cenario1.txt").read_text() + "\n\n"
        self.assertEqual(len(ad.parse_arp(texto)), 4)

    def test_h_parse_arp_gateway_por_ip(self):
        """parse_arp marca como Roteador o IP que estiver em `gateways`, mesmo sem o nome _gateway"""
        texto = "? (10.0.0.1) at aa:bb:cc:dd:ee:ff [ether] on eth0\n"
        self.assertEqual(ad.parse_arp(texto, frozenset({"10.0.0.1"}))[0]["tipo"], "Roteador")
        self.assertEqual(ad.parse_arp(texto)[0]["tipo"], "Host")

    def test_i_garantir_indices(self):
        """garantir_indices mantém índices existentes e dá max+1, max+2... aos que faltam, na ordem"""
        h = {"A": {"indice": 4}, "B": {}, "C": {"indice": 2}, "D": {}}
        ad.garantir_indices(h)
        self.assertEqual([h[k]["indice"] for k in "ABCD"], [4, 5, 2, 6])
        self.assertEqual(ad.garantir_indices({}), {})

    def _varrer_em_memoria(self, cenario, historico):
        achados = ad.parse_arp((EXEMPLO / cenario).read_text())
        return ad.atualizar_historico(historico, achados, ad.carregar_json(OUI, {}), "2026-11-10 10:00:00")

    def test_j_atualizar_historico_status(self):
        """atualizar_historico: Ativo (já conhecido), Novo (primeira vez), Inativo (não respondeu)"""
        novo = self._varrer_em_memoria("arp_cenario1.txt", self.historico())
        self.assertEqual(novo["145120AAAA01"]["status"], "Dispositivo Ativo")
        self.assertEqual(novo["E0D464000005"]["status"], "Dispositivo Novo")
        self.assertEqual(novo["E85A8B000003"]["status"], "Inativo")
        self.assertEqual(novo["E0D464000005"]["ultima_vez_visto"], "2026-11-10 10:00:00")
        self.assertEqual(novo["E85A8B000003"]["ultima_vez_visto"], "2026-10-30 18:30:00", "quem não respondeu mantém a data antiga")

    def test_k_atualizar_historico_fabricante(self):
        """atualizar_historico: fabricante pelos 6 primeiros hex do MAC na base OUI, ou o texto padrão"""
        novo = self._varrer_em_memoria("arp_cenario1.txt", self.historico())
        self.assertEqual(novo["E0D464000005"]["fabricante"], "Intel Corporate")
        self.assertEqual(novo["F21122334455"]["fabricante"], ad.FABRICANTE_DESCONHECIDO)

    def test_l_atualizar_historico_indices(self):
        """atualizar_historico: antigos ficam com 1..4 (ordem do arquivo), novos recebem 5 e 6"""
        novo = self._varrer_em_memoria("arp_cenario1.txt", self.historico())
        self.assertEqual(novo["145120AAAA01"]["indice"], 1)
        self.assertEqual(novo["54BAD9000004"]["indice"], 4)
        self.assertEqual({novo["E0D464000005"]["indice"], novo["F21122334455"]["indice"]}, {5, 6})
        novo2 = self._varrer_em_memoria("arp_cenario2.txt", novo)
        self.assertEqual(novo2["E0D464000005"]["indice"], novo["E0D464000005"]["indice"], "índice mudou entre varreduras")

    def test_m_atualizar_historico_nao_altera_a_entrada(self):
        """atualizar_historico NÃO pode modificar o dicionário recebido (copie antes)"""
        h = self.historico()
        antes = copy.deepcopy(h)
        self._varrer_em_memoria("arp_cenario1.txt", h)
        self.assertEqual(h, antes)

    def test_n_varredura_completa(self):
        """varredura grava historico.json e atualiza total_varreduras e ultima_varredura_epoch"""
        self.usar_arp("arp_cenario1.txt")
        ad.varredura(self.dir, OUI)
        self.assertEqual(self.historico()["E0D464000005"]["status"], "Dispositivo Novo")
        self.assertEqual(self.estado()["total_varreduras"], 1)
        self.assertLess(abs(self.estado()["ultima_varredura_epoch"] - time.time()), 5)
        self.usar_arp("arp_cenario2.txt")
        ad.varredura(self.dir, OUI)
        self.assertEqual(self.historico()["E0D464000005"]["status"], "Dispositivo Ativo")
        self.assertEqual(self.historico()["9CC7D3000002"]["status"], "Inativo")
        self.assertEqual(self.estado()["total_varreduras"], 2)
        json.loads((self.dir / "historico.json").read_text(encoding="utf-8"))
