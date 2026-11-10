#!/usr/bin/env python3
"""Teste de integração: sobe um snmpd real com o agente e consulta com as ferramentas
net-snmp (snmpget, snmpwalk, snmpbulkwalk, snmpset...). Grava a saída comentada em
evidencias/saida_testes.txt.

    python3 testes/integracao_snmpd.py

Usa a tabela ARP simulada de testes/dados_exemplo (ver AUTODESCOBERTA_ARP_FILE em
agente/autodescoberta.py), então não depende da rede onde você está.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLO = RAIZ / "testes" / "dados_exemplo"
PORTA = os.environ.get("PORTA", "1161")
ALVO = f"127.0.0.1:{PORTA}"
MIB = ["-M", str(RAIZ / "mibs"), "-m", "AUTODESCOBERTA-MIB"]

tmp = Path(tempfile.mkdtemp(prefix="autodescoberta-teste-"))
(tmp / "dados").mkdir()
shutil.copy(EXEMPLO / "historico.json", tmp / "dados" / "historico.json")
ARP_ATUAL = tmp / "arp_atual.txt"
shutil.copy(EXEMPLO / "arp_cenario1.txt", ARP_ATUAL)

evidencias = []
falhas = []


def registrar(texto=""):
    print(texto)
    evidencias.append(texto)


def snmp(ferramenta, *args, comunidade="teste", versao="2c", mib=True):
    cmd = [ferramenta, f"-v{versao}", "-c", comunidade, *(MIB if mib else []), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return (r.stdout + r.stderr).strip()


def caso(titulo, ferramenta, *args, esperado=(), proibido=(), **kw):
    saida = snmp(ferramenta, *args, **kw)
    registrar(f"\n### {titulo}")
    registrar("$ " + " ".join([ferramenta, f"-v{kw.get('versao', '2c')}", "-c", kw.get("comunidade", "teste"), *args]))
    registrar(saida)
    erros = [e for e in esperado if e not in saida] + [p for p in proibido if p in saida]
    registrar("=> OK" if not erros else f"=> FALHOU: {erros}")
    if erros:
        falhas.append(titulo)
    return saida


def esperar_varredura(total):
    """Aguarda o contador de varreduras chegar a `total` (a varredura roda em 2º plano)."""
    for _ in range(50):
        if f"= Counter32: {total}" in snmp("snmpget", ALVO, "totalVarredurasRealizadas.0"):
            return
        time.sleep(0.2)


env = dict(os.environ, PORTA=PORTA, DADOS=str(tmp / "dados"), RUN=str(tmp / "run"), INTERVALO="0",
           AUTODESCOBERTA_ARP_FILE=str(ARP_ATUAL), LOG_AGENTE=str(tmp / "agente.log"))
snmpd = subprocess.Popen([str(RAIZ / "scripts" / "iniciar_snmpd.sh")], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
try:
    for _ in range(50):  # espera o snmpd e o agente ficarem prontos
        if "Counter32" in snmp("snmpget", "-t", "0.3", "-r", "0", ALVO, "totalVarredurasRealizadas.0"):
            break
        time.sleep(0.2)

    registrar("# Evidências de teste do agente SNMP da AUTODESCOBERTA-MIB")
    registrar(f"# Alvo: {ALVO} | SNMPv2c | comunidades: teste (leitura), teste-rw (escrita)")

    registrar("\n## 1. Validação da MIB e dos OIDs")
    for nome, oid in [("autodescobertaMIB", ".1.3.6.1.3.99"), ("tempoEsperaPing", ".1.3.6.1.3.99.1.2"),
                      ("dispositivoIP", ".1.3.6.1.3.99.2.1.1.3")]:
        r = subprocess.run(["snmptranslate", *MIB, "-IR", "-On", nome], capture_output=True, text=True)
        saida = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr
        registrar(f"\n$ snmptranslate -M ./mibs -m AUTODESCOBERTA-MIB -IR -On {nome}\n{saida}\n=> {'OK' if saida == oid else 'FALHOU'}")
        if saida != oid:
            falhas.append("snmptranslate " + nome)

    registrar("\n## 2. GET dos escalares (estado inicial: nenhuma varredura feita)")
    caso("GET interfaceRede (OCTET STRING)", "snmpget", ALVO, "interfaceRede.0", esperado=["STRING: \"wlp0s20f3\""])
    caso("GET tempoEsperaPing (INTEGER)", "snmpget", ALVO, "tempoEsperaPing.0", esperado=["INTEGER: 1"])
    caso("GET totalDispositivosAtivos (Gauge)", "snmpget", ALVO, "totalDispositivosAtivos.0", esperado=["Gauge32: 0"])
    caso("GET totalVarredurasRealizadas (Counter)", "snmpget", ALVO, "totalVarredurasRealizadas.0", esperado=["Counter32: 0"])
    caso("GET tempoDesdeUltimaVarredura (TimeTicks)", "snmpget", ALVO, "tempoDesdeUltimaVarredura.0", esperado=["Timeticks:"])

    registrar("\n## 3. WALK e GETNEXT")
    saida = caso("WALK da MIB inteira", "snmpwalk", ALVO, "autodescobertaMIB",
                 esperado=["dispositivoMAC.1", "dispositivoMAC.4", "dispositivoUltimaVezVisto.4"], proibido=["executarVarredura"])
    linhas = [l for l in saida.splitlines() if "=" in l]
    registrar(f"Linhas retornadas: {len(linhas)} (esperado 29 = 5 escalares + 4 dispositivos x 6 colunas)")
    if len(linhas) != 29:
        falhas.append("contagem do WALK")
    caso("WALK da tabela (colunas em ordem, índices 1..4)", "snmpwalk", ALVO, "dispositivosTable", esperado=["dispositivoIP.3 = IpAddress: 192.168.4.3"])
    caso("GETNEXT a partir da raiz", "snmpgetnext", ALVO, "autodescobertaMIB", esperado=["interfaceRede.0"])
    caso("GETNEXT depois do último escalar legível (pula o write-only)", "snmpgetnext", ALVO, "tempoDesdeUltimaVarredura.0", esperado=["dispositivoMAC.1"])
    caso("GETNEXT após o fim do ramo (o snmpd segue para o próximo ramo registrado)", "snmpgetnext", ALVO, ".1.3.6.1.3.99.2.1.1.7.4", proibido=["AUTODESCOBERTA-MIB::"])

    registrar("\n## 4. GETBULK (SNMPv2c)")
    caso("snmpbulkwalk (max-repetitions=5)", "snmpbulkwalk", "-Cr5", ALVO, "dispositivosTable", esperado=["dispositivoMAC.1", "dispositivoUltimaVezVisto.4"])
    caso("snmpbulkwalk, 1 por vez (max-repetitions=1)", "snmpbulkwalk", "-Cr1", ALVO, "dispositivoStatus", esperado=["dispositivoStatus.4"])

    registrar("\n## 5. Objetos inexistentes, write-only e permissões")
    caso("GET de objeto inexistente", "snmpget", ALVO, ".1.3.6.1.3.99.1.9.0", esperado=["No Such"])
    caso("GET de linha inexistente (índice 99)", "snmpget", ALVO, "dispositivoMAC.99", esperado=["No Such Instance"])
    caso("GET de escalar sem .0", "snmpget", ALVO, "interfaceRede", esperado=["No Such Instance"])
    caso("GET de executarVarredura (write-only)", "snmpget", ALVO, "executarVarredura.0", esperado=["iniciar(1)"])
    caso("SET com comunidade somente-leitura", "snmpset", ALVO, "tempoEsperaPing.0", "i", "5", esperado=["Error"], comunidade="teste")

    registrar("\n## 6. SET")
    caso("SET tempoEsperaPing = 5 (read-write)", "snmpset", ALVO, "tempoEsperaPing.0", "i", "5", esperado=["INTEGER: 5"], comunidade="teste-rw")
    caso("GET confirma o novo valor", "snmpget", ALVO, "tempoEsperaPing.0", esperado=["INTEGER: 5"])
    registrar("\n(Os próximos SETs usam OIDs numéricos e nenhuma MIB no cliente: com a MIB, o snmpset já recusa")
    registrar("valores inválidos antes de enviar. Assim o erro vem do próprio agente.)")
    caso("SET fora da faixa (61) -> wrongValue", "snmpset", "-m", "", ALVO, ".1.3.6.1.3.99.1.2.0", "i", "61", esperado=["wrongValue"], comunidade="teste-rw", mib=False)
    caso("SET tempoEsperaPing = 0 -> wrongValue", "snmpset", "-m", "", ALVO, ".1.3.6.1.3.99.1.2.0", "i", "0", esperado=["wrongValue"], comunidade="teste-rw", mib=False)
    caso("SET com tipo errado (string) -> wrongType", "snmpset", "-m", "", ALVO, ".1.3.6.1.3.99.1.2.0", "s", "abc", esperado=["wrongType"], comunidade="teste-rw", mib=False)
    caso("SET em objeto read-only (interfaceRede) -> notWritable", "snmpset", ALVO, "interfaceRede.0", "s", "eth0", esperado=["notWritable"], comunidade="teste-rw")
    caso("SET em coluna da tabela (read-only) -> notWritable", "snmpset", ALVO, "dispositivoTipo.1", "s", "Host", esperado=["notWritable"], comunidade="teste-rw")
    caso("SET em OID inexistente -> notWritable", "snmpset", "-m", "", ALVO, ".1.3.6.1.3.99.1.9.0", "i", "1", esperado=["notWritable"], comunidade="teste-rw", mib=False)
    caso("SET executarVarredura = 2 (fora da enumeração) -> wrongValue", "snmpset", "-m", "", ALVO, ".1.3.6.1.3.99.1.6.0", "i", "2", esperado=["wrongValue"], comunidade="teste-rw", mib=False)
    caso("tempoEsperaPing continua 5 depois dos SETs inválidos", "snmpget", ALVO, "tempoEsperaPing.0", esperado=["INTEGER: 5"])

    registrar("\n## 7. Atualização dos valores: varredura 1 (ARP cenário 1: 1 novo conhecido + 2 dispositivos novos)")
    caso("SET executarVarredura = 1 (iniciar)", "snmpset", ALVO, "executarVarredura.0", "i", "1", esperado=["INTEGER: iniciar(1)"], comunidade="teste-rw")
    esperar_varredura(1)
    caso("totalVarredurasRealizadas = 1", "snmpget", ALVO, "totalVarredurasRealizadas.0", esperado=["Counter32: 1"])
    caso("totalDispositivosAtivos = 4", "snmpget", ALVO, "totalDispositivosAtivos.0", esperado=["Gauge32: 4"])
    caso("tempoDesdeUltimaVarredura é pequeno (< 10 s)", "snmpget", "-Oq", ALVO, "tempoDesdeUltimaVarredura.0")
    caso("Tabela agora tem 6 linhas (índices 5 e 6 são os novos)", "snmpwalk", ALVO, "dispositivoStatus",
         esperado=["dispositivoStatus.1 = STRING: \"Dispositivo Ativo\"", "dispositivoStatus.3 = STRING: \"Inativo\"",
                   "dispositivoStatus.5 = STRING: \"Dispositivo Novo\"", "dispositivoStatus.6 = STRING: \"Dispositivo Novo\""])
    caso("Fabricante resolvido pela base OUI / MAC privado", "snmpwalk", ALVO, "dispositivoFabricante",
         esperado=["Intel Corporate", "Fabricante Desconhecido || Mac Privado"])
    caso("Papel do dispositivo (Roteador = _gateway)", "snmpget", ALVO, "dispositivoTipo.1", esperado=["Roteador"])

    registrar("\n## 8. Atualização dos valores: varredura 2 (ARP cenário 2: só gateway e 1 host)")
    shutil.copy(EXEMPLO / "arp_cenario2.txt", ARP_ATUAL)
    snmp("snmpset", ALVO, "executarVarredura.0", "i", "1", comunidade="teste-rw")
    esperar_varredura(2)
    caso("totalVarredurasRealizadas = 2", "snmpget", ALVO, "totalVarredurasRealizadas.0", esperado=["Counter32: 2"])
    caso("totalDispositivosAtivos = 2", "snmpget", ALVO, "totalDispositivosAtivos.0", esperado=["Gauge32: 2"])
    caso("Status: Novo virou Ativo; ausentes viraram Inativo; índices preservados", "snmpwalk", ALVO, "dispositivoStatus",
         esperado=["dispositivoStatus.1 = STRING: \"Dispositivo Ativo\"", "dispositivoStatus.2 = STRING: \"Inativo\"",
                   "dispositivoStatus.5 = STRING: \"Dispositivo Ativo\"", "dispositivoStatus.6 = STRING: \"Inativo\""])
    caso("tempoEsperaPing continua 5 (SET anterior foi persistido)", "snmpget", ALVO, "tempoEsperaPing.0", esperado=["INTEGER: 5"])

    registrar("\n## 9. Interoperabilidade: SNMPv1")
    caso("snmpget em SNMPv1", "snmpget", ALVO, "totalVarredurasRealizadas.0", esperado=["Counter32: 2"], versao="1")
    caso("snmpwalk em SNMPv1", "snmpwalk", ALVO, "dispositivoIP", esperado=["IpAddress: 192.168.4.30"], versao="1")
finally:
    try:
        os.killpg(snmpd.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    snmpd.wait(timeout=10)

registrar("\n" + ("RESULTADO: todos os casos passaram." if not falhas else f"RESULTADO: {len(falhas)} caso(s) falharam: {falhas}"))
destino = RAIZ / "evidencias" / "saida_testes.txt"
destino.parent.mkdir(exist_ok=True)
destino.write_text("\n".join(evidencias) + "\n", encoding="utf-8")
shutil.copy(tmp / "agente.log", RAIZ / "evidencias" / "log_protocolo_agente.txt") if (tmp / "agente.log").exists() else None
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if falhas else 0)
