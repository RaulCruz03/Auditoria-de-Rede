#!/usr/bin/env python3
"""Agente SNMP da AUTODESCOBERTA-MIB (ramo experimental 99 = 1.3.6.1.3.99).

Como funciona
-------------
Quem fala SNMP com a rede é o snmpd (Net-SNMP): ele decodifica os pacotes, trata
comunidades, SNMPv2c, GETBULK e erros do protocolo. Este script é a parte que sabe
*o que responder*: o snmpd o executa pela diretiva `pass_persist` e conversa com ele
por stdin/stdout, em texto, uma linha por vez:

    snmpd -> agente            agente -> snmpd
    PING                       PONG
    get                        (3 linhas: OID, tipo, valor)  ou  NONE
    <oid>
    getnext                    (3 linhas: OID, tipo, valor)  ou  NONE
    <oid>
    set                        DONE  ou  um código de erro (not-writable, wrong-type...)
    <oid>
    <tipo> <valor>

Este arquivo está dividido nas mesmas etapas do ROTEIRO.md:
  Etapa 1  OIDs como tuplas de inteiros
  Etapa 2  Instâncias: de onde vem cada valor (escalares e tabela)
  Etapa 3  GET e GETNEXT
  Etapa 4  SET
  Etapa 5  Laço de comunicação com o snmpd
"""

import argparse
import bisect
import ipaddress
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from autodescoberta import (  # noqa: E402
    FORMATO_DATA,
    STATUS_INATIVO,
    Autodescoberta,
    ErroVarredura,
)

# --------------------------------------------------------------------------
# Etapa 1 - OIDs como tuplas de inteiros
# --------------------------------------------------------------------------
# Comparar OIDs como texto dá a ordem errada ("...2.10" < "...2.9"). Como tuplas de
# inteiros, a comparação do Python já é a ordem lexicográfica numérica do SNMP.

RAIZ = (1, 3, 6, 1, 3, 99)  # experimental(3) . autodescobertaMIB(99)
GLOBAIS = RAIZ + (1,)  # objetosGlobais
ENTRADA = RAIZ + (2, 1, 1)  # tabelaDispositivos . dispositivosTable . dispositivoEntry

OID_INTERFACE = GLOBAIS + (1, 0)
OID_TEMPO_PING = GLOBAIS + (2, 0)
OID_TOTAL_ATIVOS = GLOBAIS + (3, 0)
OID_TOTAL_VARREDURAS = GLOBAIS + (4, 0)
OID_TEMPO_DESDE_ULTIMA = GLOBAIS + (5, 0)
OID_EXECUTAR = GLOBAIS + (6, 0)  # write-only: fora do GETNEXT/WALK (veja tratar_get)

# Colunas da tabela. A coluna 1 (dispositivoIndex) é not-accessible: o índice só
# aparece como último número do OID de cada célula, não como coluna consultável.
COLUNAS = {
    2: "mac",
    3: "ip",
    4: "tipo",
    5: "fabricante",
    6: "status",
    7: "ultima_vez_visto",
}

UINT32 = 2**32


def parse_oid(texto):
    """'.1.3.6.1' ou '1.3.6.1' -> (1, 3, 6, 1)."""
    return tuple(int(p) for p in texto.strip().strip(".").split(".") if p)


def formatar_oid(oid):
    return "." + ".".join(str(n) for n in oid)


# --------------------------------------------------------------------------
# Etapa 2 - Instâncias: de onde vem cada valor
# --------------------------------------------------------------------------
# Uma "instância" é um OID completo com tipo e valor. Em vez de guardar uma lista
# fixa, o agente a reconstrói a cada consulta a partir dos arquivos da autodescoberta:
# é isso que faz uma mudança na rede aparecer na consulta seguinte.


def _texto(valor):
    return str(valor).replace("\r", " ").replace("\n", " ")


def _ip_valido(texto):
    try:
        return str(ipaddress.IPv4Address(texto))
    except ValueError:
        return "0.0.0.0"


class Agente:
    def __init__(self, descoberta, log=None):
        self.ad = descoberta
        self.log = log or (lambda msg: None)
        self.inicio = time.time()

    def _ticks_desde_ultima_varredura(self, estado, historico, agora):
        """TimeTicks = centésimos de segundo desde a última varredura."""
        ref = estado.get("ultima_varredura_epoch")
        if ref is None:  # nenhuma varredura feita pelo agente: usa o maior "visto" do histórico
            vistos = []
            for r in historico.values():
                try:
                    vistos.append(datetime.strptime(r["ultima_vez_visto"], FORMATO_DATA).timestamp())
                except (KeyError, ValueError):
                    pass
            ref = max(vistos, default=self.inicio)
        return int(max(0.0, agora - ref) * 100) % UINT32

    def instancias(self):
        """Lista ordenada de (oid, tipo, valor) com tudo o que existe agora."""
        estado = self.ad.estado()
        historico = self.ad.historico()
        agora = time.time()
        itens = []

        # Escalares (sufixo .0)
        itens.append((OID_INTERFACE, "string", _texto(estado["interface"])))
        itens.append((OID_TEMPO_PING, "integer", str(int(estado["tempo_espera_ping"]))))
        ativos = sum(1 for r in historico.values() if r.get("status") != STATUS_INATIVO)
        itens.append((OID_TOTAL_ATIVOS, "gauge", str(ativos)))
        itens.append((OID_TOTAL_VARREDURAS, "counter", str(int(estado["total_varreduras"]) % UINT32)))
        itens.append((OID_TEMPO_DESDE_ULTIMA, "timeticks",
                      str(self._ticks_desde_ultima_varredura(estado, historico, agora))))

        # Tabela: OID = ENTRADA + (coluna, índice). Uma linha do histórico gera 6 células.
        for mac, reg in historico.items():
            for coluna, campo in COLUNAS.items():
                if campo == "mac":
                    tipo, valor = "string", mac
                elif campo == "ip":
                    tipo, valor = "ipaddress", _ip_valido(reg.get("ip", ""))
                else:
                    tipo, valor = "string", _texto(reg.get(campo, ""))
                itens.append((ENTRADA + (coluna, reg["indice"]), tipo, valor))

        itens.sort(key=lambda item: item[0])
        return itens

    # ----------------------------------------------------------------------
    # Etapa 3 - GET e GETNEXT
    # ----------------------------------------------------------------------
    def tratar_get(self, texto_oid):
        """GET: devolve a instância exata ou NONE (noSuchObject/noSuchInstance)."""
        oid = parse_oid(texto_oid)
        if oid == OID_EXECUTAR:
            # Limitação do pass_persist: o snmpd só aceita um SET se o objeto responder a
            # GET (ele faz um "get" antes de repassar o "set"). Por isso o objeto
            # write-only devolve o único valor da enumeração, iniciar(1). Ele continua
            # fora do GETNEXT/WALK, então não aparece ao percorrer a MIB.
            return [formatar_oid(OID_EXECUTAR), "integer", "1"]
        for inst_oid, tipo, valor in self.instancias():
            if inst_oid == oid:
                return [formatar_oid(inst_oid), tipo, valor]
        return ["NONE"]

    def tratar_getnext(self, texto_oid):
        """GETNEXT: devolve a primeira instância com OID estritamente maior.

        WALK e GETBULK são só GETNEXTs repetidos pelo snmpd/cliente. Se não houver
        próxima instância no nosso ramo, NONE faz o snmpd seguir para o ramo seguinte.
        """
        oid = parse_oid(texto_oid)
        itens = self.instancias()
        pos = bisect.bisect_right([i[0] for i in itens], oid)
        if pos >= len(itens):
            return ["NONE"]
        inst_oid, tipo, valor = itens[pos]
        return [formatar_oid(inst_oid), tipo, valor]

    # ----------------------------------------------------------------------
    # Etapa 4 - SET
    # ----------------------------------------------------------------------
    def tratar_set(self, texto_oid, texto_valor):
        """Devolve 'DONE' ou o código de erro que o snmpd traduz para o cliente."""
        oid = parse_oid(texto_oid)
        partes = texto_valor.strip().split(None, 1)
        tipo = partes[0].lower() if partes else ""
        valor = partes[1].strip() if len(partes) > 1 else ""

        if oid == OID_TEMPO_PING:  # read-write, INTEGER (1..60)
            if tipo != "integer":
                return "wrong-type"
            try:
                n = int(valor)
            except ValueError:
                return "wrong-value"
            if not 1 <= n <= 60:
                return "wrong-value"
            self.ad.atualizar_estado(tempo_espera_ping=n)
            return "DONE"

        if oid == OID_EXECUTAR:  # write-only, INTEGER { iniciar(1) }
            if tipo != "integer":
                return "wrong-type"
            if valor != "1":
                return "wrong-value"
            if self.ad.varredura_em_andamento():
                return "inconsistent-value"
            threading.Thread(target=self._varrer_em_segundo_plano, daemon=True).start()
            return "DONE"

        # Qualquer outro objeto (read-only, colunas da tabela ou OID inexistente)
        return "not-writable"

    def _varrer_em_segundo_plano(self):
        # A varredura leva segundos; o snmpd não pode ficar esperando a resposta do SET.
        try:
            self.ad.executar_varredura()
        except ErroVarredura as erro:
            self.log(f"varredura falhou: {erro}")
        except Exception as erro:  # uma thread que morre em silêncio é difícil de depurar
            self.log(f"erro inesperado na varredura: {erro!r}")

    def varredura_periodica(self, intervalo):
        while True:
            time.sleep(intervalo)
            self._varrer_em_segundo_plano()


# --------------------------------------------------------------------------
# Etapa 5 - Laço de comunicação com o snmpd
# --------------------------------------------------------------------------
def servir(agente, entrada, saida, log):
    def ler():
        return entrada.readline().rstrip("\r\n")

    def responder(linhas):
        log("<- " + " | ".join(linhas))
        saida.write("\n".join(linhas) + "\n")
        saida.flush()  # sem flush o snmpd fica esperando a resposta

    while True:
        linha = entrada.readline()
        if linha == "":  # EOF: o snmpd encerrou
            return
        comando = linha.strip()
        if not comando:
            continue
        if comando == "PING":
            log("-> PING")
            responder(["PONG"])
        elif comando == "get":
            oid = ler()
            log(f"-> get {oid}")
            responder(agente.tratar_get(oid))
        elif comando == "getnext":
            oid = ler()
            log(f"-> getnext {oid}")
            responder(agente.tratar_getnext(oid))
        elif comando == "set":
            oid, valor = ler(), ler()
            log(f"-> set {oid} {valor}")
            responder([agente.tratar_set(oid, valor)])
        else:
            log(f"comando desconhecido ignorado: {comando!r}")


def main():
    raiz = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Agente pass_persist da AUTODESCOBERTA-MIB")
    ap.add_argument("--dados", default=str(raiz / "dados"), help="pasta de historico.json e estado.json")
    ap.add_argument("--oui", default=str(raiz.parent / "oui_db.json"), help="base de fabricantes (OUI)")
    ap.add_argument("--interface", help="interface a varrer (grava em estado.json)")
    ap.add_argument("--intervalo", type=int, default=0, help="varredura automática a cada N s (0 = só por SET)")
    ap.add_argument("--log", help="arquivo de log do protocolo ('-' = stderr)")
    args = ap.parse_args()

    destino = None
    if args.log == "-":
        destino = sys.stderr
    elif args.log:
        destino = open(args.log, "a", buffering=1, encoding="utf-8")

    def log(msg):
        if destino:
            destino.write(f"{datetime.now():%H:%M:%S} {msg}\n")

    # snmpd lê o que escrevemos em UTF-8 (fabricantes podem ter acentos)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

    ad = Autodescoberta(args.dados, args.oui)
    if args.interface:
        ad.atualizar_estado(interface=args.interface)
    agente = Agente(ad, log)
    if args.intervalo > 0:
        threading.Thread(target=agente.varredura_periodica, args=(args.intervalo,), daemon=True).start()
    servir(agente, sys.stdin, sys.stdout, log)


if __name__ == "__main__":
    main()
