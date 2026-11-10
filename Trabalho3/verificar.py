#!/usr/bin/env python3
"""Verificador de progresso do Trabalho 3.

    python3 verificar.py        resumo de todas as etapas
    python3 verificar.py 3      detalhes da etapa 3 (o que passou, o que falta e dicas)
"""

import os
import shutil
import subprocess
import sys
import traceback
import unittest
from pathlib import Path
PASTA = Path(__file__).resolve().parent      # devolve Trabalho3
RAIZ = PASTA.parent                          # devolve a raiz   
sys.path.insert(0, str(PASTA / "testes"))     # permite importar test_etapa1, ...
os.chdir(PASTA)                              # caminhos relativos partem do Trabalho3 

TITULOS = {
    0: "MIB carrega no Net-SNMP",
    1: "autodescoberta.py (varredura como biblioteca)",
    2: "servir(): conversa com o snmpd",
    3: "OIDs",
    4: "instancias()",
    5: "GET e GETNEXT",
    6: "SET e varredura em segundo plano",
    7: "snmpd de verdade (integração)",
}


class Resultado(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.itens = []  # (teste, "ok" | "falta" | "falhou", detalhe)

    def addSuccess(self, test):
        self.itens.append((test, "ok", ""))

    def addFailure(self, test, err):
        self.itens.append((test, "falhou", str(err[1]).strip().splitlines()[-1][:300]))

    def addError(self, test, err):
        tipo, valor, tb = err
        quadros = traceback.extract_tb(tb)
        nosso = [q for q in quadros if "/agente/" in q.filename.replace("\\", "/")]
        if tipo is NotImplementedError and nosso:
            q = nosso[-1]
            self.itens.append((test, "falta", f"falta implementar {q.name}() em agente/{Path(q.filename).name}"))
        elif tipo is NotImplementedError:
            self.itens.append((test, "falta", str(valor) or "ainda não implementado"))
        elif tipo is TypeError and "NoneType" in str(valor):
            self.itens.append((test, "falta", "alguma constante ainda é None (etapa 3: OID_* e ENTRADA)"))
        else:
            onde = f" (agente/{Path(nosso[-1].filename).name}, linha {nosso[-1].lineno})" if nosso else ""
            self.itens.append((test, "falhou", f"{tipo.__name__}: {valor}{onde}"))


def rodar_testes(n):
    suite = unittest.defaultTestLoader.loadTestsFromName(f"test_etapa{n}")
    r = Resultado()
    suite.run(r)
    return r.itens


def etapa0(detalhe):
    if not shutil.which("snmptranslate"):
        return [("snmptranslate instalado", "falta", "sudo apt install snmp")]
    mib = ["-M", str(RAIZ / "mib"), "-m", "AUTODESCOBERTA-MIB"]
    r = subprocess.run(["snmptranslate", *mib, "-IR", "-On", "autodescobertaMIB"], capture_output=True, text=True)
    itens = [("a MIB carrega e autodescobertaMIB = .1.3.6.1.3.99",
              "ok" if r.stdout.strip() == ".1.3.6.1.3.99" else "falhou", r.stderr.strip()[-300:])]
    if detalhe:
        arvore = subprocess.run(["snmptranslate", *mib, "-Tp", "-IR", "autodescobertaMIB"], capture_output=True, text=True)
        print(arvore.stdout)
    return itens


def etapa7(detalhe):
    itens = []
    for prog in ("snmpd", "snmpget", "snmpwalk"):
        itens.append((f"{prog} instalado", "ok" if shutil.which(prog) else "falta", "sudo apt install snmpd snmp"))
    conf = (RAIZ / "config" / "snmpd.conf.modelo").read_text(encoding="utf-8")
    linha = [l for l in conf.splitlines() if l.strip().startswith("pass_persist")]
    ok = bool(linha) and ".1.3.6.1.3.99" in linha[0] and "@COMANDO_AGENTE@" in linha[0]
    itens.append(("linha pass_persist no config/snmpd.conf.modelo", "ok" if ok else "falta",
                  "escreva: pass_persist <OID da raiz da MIB> @COMANDO_AGENTE@"))
    if all(s == "ok" for _, s, _ in itens):
        if not detalhe:
            itens.append(("teste de integração", "falta", "rode: python3 verificar.py 7 (leva ~15 s)"))
        else:
            r = subprocess.run([sys.executable, "testes/integracao_snmpd.py"], capture_output=True, text=True)
            falhas = [l for l in (RAIZ / "evidencias" / "saida_testes.txt").read_text(encoding="utf-8").splitlines()
                      if l.startswith("### ")] if r.returncode else []
            itens.append(("teste de integração (evidencias/saida_testes.txt)", "ok" if r.returncode == 0 else "falhou",
                          "veja os casos com '=> FALHOU' em evidencias/saida_testes.txt" if falhas else r.stderr[-300:]))
    return itens


def avaliar(n, detalhe=False):
    if n == 0:
        return etapa0(detalhe)
    if n == 7:
        return etapa7(detalhe)
    return rodar_testes(n)


def nome(item):
    t = item[0]
    if isinstance(t, str):
        return t
    return t.shortDescription() or t.id().split(".")[-1]


MARCA = {"ok": "[OK]    ", "falta": "[ -- ]  ", "falhou": "[FALHOU]"}


def resumo():
    print("Progresso do Trabalho 3\n")
    for n, titulo in TITULOS.items():
        itens = avaliar(n)
        ok = sum(1 for i in itens if i[1] == "ok")
        if ok == len(itens):
            marca = "[OK]    "
        elif ok == 0 and all(i[1] == "falta" for i in itens):
            marca = "[ -- ]  "
        else:
            marca = "[ .. ]  "
        print(f"  {marca} Etapa {n}: {titulo:<48} {ok}/{len(itens)}")
    print("\nDetalhes de uma etapa: python3 verificar.py <número>")


def detalhar(n):
    print(f"Etapa {n}: {TITULOS[n]}\n")
    itens = avaliar(n, detalhe=True)
    for item in itens:
        print(f"  {MARCA[item[1]]} {nome(item)}")
        if item[1] != "ok" and item[2]:
            print(f"             -> {item[2]}")
    ok = sum(1 for i in itens if i[1] == "ok")
    print(f"\n{ok}/{len(itens)} verificações passaram.")
    if ok == len(itens):
        print("Etapa concluída. Antes de seguir, responda as perguntas da etapa no GUIA.md.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].isdigit() and int(sys.argv[1]) in TITULOS:
        detalhar(int(sys.argv[1]))
    else:
        resumo()
