"""Infraestrutura comum dos testes (não precisa alterar)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLO = RAIZ / "testes" / "dados_exemplo"
OUI = RAIZ.parent / "oui_db.json"
sys.path.insert(0, str(RAIZ / "agente"))

import agente_snmp as agente  # noqa: E402
import autodescoberta as ad  # noqa: E402

R = (1, 3, 6, 1, 3, 99)
ENTRADA = R + (2, 1, 1)


class TesteComDados(unittest.TestCase):
    """Cria uma pasta de dados temporária com o histórico de exemplo (4 dispositivos)."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="t3-"))
        shutil.copy(EXEMPLO / "historico.json", self.dir / "historico.json")
        agente.DIR_DADOS, agente.CAMINHO_OUI = str(self.dir), str(OUI)
        os.environ.pop(ad.ENV_ARP_FILE, None)

    def tearDown(self):
        os.environ.pop(ad.ENV_ARP_FILE, None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def usar_arp(self, nome):
        os.environ[ad.ENV_ARP_FILE] = str(EXEMPLO / nome)

    def historico(self):
        return json.loads((self.dir / "historico.json").read_text(encoding="utf-8"))

    def gravar_historico(self, dados):
        (self.dir / "historico.json").write_text(json.dumps(dados), encoding="utf-8")

    def estado(self):
        return json.loads((self.dir / "estado.json").read_text(encoding="utf-8"))
