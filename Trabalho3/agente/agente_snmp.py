#!/usr/bin/env python3
"""Agente SNMP da AUTODESCOBERTA-MIB (ETAPAS 2 a 6).

O snmpd (Net-SNMP) recebe os pacotes SNMP e, para o ramo 1.3.6.1.3.99, conversa com
este script por stdin/stdout, em texto, uma linha por vez (diretiva pass_persist):

    snmpd -> agente            agente -> snmpd
    PING                       PONG
    get                        3 linhas: OID, tipo, valor    (ou NONE)
    <oid>
    getnext                    3 linhas: OID, tipo, valor    (ou NONE)
    <oid>
    set                        DONE  ou um código de erro (not-writable, wrong-type,
    <oid>                            wrong-value, inconsistent-value)
    <tipo> <valor>

Tipos aceitos pelo pass_persist: string, integer, gauge, counter, timeticks, ipaddress.

Implemente os TODOs etapa por etapa e verifique com:  python3 verificar.py <etapa>
"""

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import autodescoberta as ad  # noqa: E402

# Definidos por main() (ou pelos testes) antes de qualquer consulta
DIR_DADOS = None
CAMINHO_OUI = None


def log(msg):
    """Substituída por main() quando o agente roda com --log."""


# ===========================================================================
# ETAPA 3 - OIDs
# ===========================================================================
RAIZ_MIB = (1, 3, 6, 1, 3, 99)  # experimental(3) . autodescobertaMIB(99)

OID_INTERFACE = (RAIZ_MIB + (1,1,0))  # interfaceRede.0
OID_TEMPO_PING = (RAIZ_MIB + (1,2,0))  # tempoEsperaPing.0
OID_TOTAL_ATIVOS = (RAIZ_MIB + (1,3,0))  # totalDispositivosAtivos.0
OID_TOTAL_VARREDURAS = (RAIZ_MIB + (1,4,0))  # totalVarredurasRealizadas.0
OID_TEMPO_DESDE_ULTIMA = (RAIZ_MIB + (1,5,0))  # tempoDesdeUltimaVarredura.0
OID_EXECUTAR = (RAIZ_MIB + (1,6,0))  # executarVarredura.0
# Tabela: o OID de dispositivoEntry. Uma célula é ENTRADA + (coluna, indice).
ENTRADA = (RAIZ_MIB + (2,1,1))  # dispositivoEntry.1.1


def parse_oid(texto):
    texto = texto.strip().strip(".")    # formata string tirando espaços vazios e pontos
    texto = texto.split(".")            # separa a cada ponto
    return tuple(int(x) for x in texto) # transforma em tupla de inteiros 


def formatar_oid(oid):
    return "." + ".".join(str(x) for x in oid)  # transforma a tupla em string, separando por pontos
    

# ===========================================================================
# ETAPA 4 - Instâncias: o que existe agora e com qual valor
# ===========================================================================
def instancias():
    estado = ad.ler_estado(DIR_DADOS)                                   # carrega o arquivo autodescoberta.py e devolve o estado atual do agente
    historico = ad.garantir_indices(
        ad.carregar_json(Path(DIR_DADOS) / "historico.json", {}))       # carrega o json do histórico de dispositivos e garante que cada registro tenha um índice único 

    lista = []

    # ---------- escalares ----------
    lista.append((OID_INTERFACE, "string", estado["interface"]))                    # anexa o OID da interface de rede, tipo string e o valor da interface atual 
    lista.append((OID_TEMPO_PING, "integer", str(estado["tempo_espera_ping"])))     # anexa o OID do tempo de espera do ping, tipo integer e o valor do tempo de espera atual 

    ativos = 0
    for reg in historico.values():
        if ad.STATUS_INATIVO != reg["status"]:                                      # checa quantos dispositivos estão ativos no histórico, comparando o status de cada registro com o status inativo definido em autodescoberta.py 
            ativos += 1
    lista.append((OID_TOTAL_ATIVOS, "gauge", str(ativos)))                          # anexa o OID do total de dispositivos ativos, tipo gauge e o valor do total de dispositivos ativos encontrados no histórico

    lista.append((OID_TOTAL_VARREDURAS, "counter", str(estado["total_varreduras"] % 2**32)))   # anexa o OID do total de varreduras, tipo counter e o valor do total de varreduras encontradas no histórico

    # ---------- tempo desde a última varredura (timeticks) ----------
    epoch = estado["ultima_varredura_epoch"]
    datas = [reg["ultima_vez_visto"] for reg in historico.values()]
    if epoch is not None:
        segundos = time.time() - epoch                      # calcula o tempo em segundos desde a última varredura, subtraindo o epoch atual do tempo atual 
    elif datas:
        mais_recente = max(datas)                           # se não houver epoch, mas houver datas, pega a data mais recente do histórico
        segundos = time.time() - datetime.strptime(mais_recente, ad.FORMATO_DATA).timestamp()
    else:
        segundos = 0
    ticks = int(segundos * 100) % 2**32                     # devolve o tempo em timeticks (1/100 de segundo) desde a última varredura, convertendo os segundos em timeticks e limitando o valor a 32 bits
    lista.append((OID_TEMPO_DESDE_ULTIMA, "timeticks", str(ticks)))

    # ---------- tabela ----------
    for mac, reg in historico.items():
        i = reg["indice"]
        lista.append((ENTRADA + (2, i), "string", mac))
        lista.append((ENTRADA + (3, i), "ipaddress", reg["ip"]))            
        lista.append((ENTRADA + (4, i), "string", reg["tipo"]))
        lista.append((ENTRADA + (5, i), "string", reg["fabricante"]))
        lista.append((ENTRADA + (6, i), "string", reg["status"]))
        lista.append((ENTRADA + (7, i), "string", reg["ultima_vez_visto"]))

    return sorted(lista, key=lambda item: item[0])           # retorna a lista de instâncias ordenada pelo OID, para que o agente possa responder corretamente às consultas GET e GETNEXT do snmpd


# ===========================================================================
# ETAPA 5 - GET e GETNEXT
# ===========================================================================
def tratar_get(texto_oid):
    """GET: a instância com OID EXATAMENTE igual.

    Devolve [oid_formatado, tipo, valor] ou ["NONE"] se não existir.
    """
    pedido = parse_oid(texto_oid)                           # formata o oid para uma tupla de inteiros, para que possa ser comparado com os OIDs das instâncias
    for oid, tipo, valor in instancias():
        if pedido == oid:                                   # se o oid do pedido for igual ao oid da instância
            return [formatar_oid(oid), tipo, valor]         # devolve a instância formatada
    return ["NONE"]


def tratar_getnext(texto_oid):
    pedido = parse_oid(texto_oid)                              # formata o oid para uma tupla de inteiros, para que possa ser comparado com os OIDs das instâncias
    for oid, tipo, valor in instancias():
        if pedido < oid:                               # se o oid do pedido for menor que o oid da instância, significa que a instância é a próxima na ordem
            return [formatar_oid(oid), tipo, valor]
    return ["NONE"]

# ===========================================================================
# ETAPA 6 - SET e varredura em segundo plano
# ===========================================================================
_trava_varredura = threading.Lock()


def disparar_varredura():
    if not _trava_varredura.acquire(blocking=False):   #  tenta pegar a trava sem esperar
        return False

    def tarefa():
        try:
            ad.varredura(DIR_DADOS , CAMINHO_OUI)             # realiza a varredura, atualizando o histórico e o estado do agente
        except Exception as erro:
            log(f"varredura falhou: {erro}")
        finally:
            _trava_varredura.release()                               # solta a trava, permitindo que outra varredura seja iniciada

    threading.Thread(target=tarefa, daemon=True).start()   # inicia a varredura em segundo plano, para que o agente possa continuar respondendo às consultas do snmpd enquanto a varredura é realizada
    return True


def tratar_set(texto_oid, texto_valor):
    oid = parse_oid(texto_oid)                         # formata o oid para uma tupla de inteiros, para que possa ser comparado com os OIDs das instâncias
    tipo, valor = texto_valor.split(maxsplit=1)      # "integer 5" -> "integer", "5"

    if oid == OID_TEMPO_PING:
        if tipo != "integer":
            return "wrong-type"   
        try:                        
            numero = int(valor)
        except ValueError:
            return "wrong-value"
        if not (1 <= numero <= 60):                                   # fora de 1..60?
            return "wrong-value"
        ad.atualizar_estado(DIR_DADOS, tempo_espera_ping=numero)          # atualiza o estado do agente com o novo tempo de espera do ping
        return "DONE"

    elif oid == OID_EXECUTAR:                              # o pedido é para executarVarredura.0
        if tipo != "integer":
            return "wrong-type"
        try:
            numero = int(valor)
        except ValueError:
            return "wrong-value"
        if numero != 1:                                   # o valor é diferente de 1 (iniciar)? só 1 é aceito
            return "wrong-value"
        if not disparar_varredura():                               # tenta iniciar a varredura em segundo plano
            return "inconsistent-value"
        return "DONE"

    return "not-writable"                                    # varredura disparada; o resultado aparece nas próximas consultas


# ===========================================================================
# ETAPA 2 - Laço de comunicação com o snmpd
# ===========================================================================
def servir(entrada, saida):
    while True:
        linha = entrada.readline()
        if linha == "":                  # fim da entrada
            return
        comando = linha.strip()          # remove espaços e quebras de linha

        if comando == "PING":
            resposta = ["PONG"]             # Responde PONG para o snmpd, que sabe que o agente está vivo
        elif comando == "get":
            oid = entrada.readline().strip()
            log(f"<- get {oid}")
            resposta = tratar_get(oid)
        elif comando == "getnext":
            oid = entrada.readline().strip()
            resposta = tratar_getnext(oid)
        elif comando == "set":
            oid = entrada.readline().strip()
            valor = entrada.readline().strip()
            resposta = [tratar_set(oid, valor)]
        else:
            continue # se não for nenhum dos comandos acima, ignora e espera o próximo
                            
        log(f"-> {resposta}")
        for l in resposta:               # buffer de saída: escreve cada linha da resposta no stdout, seguido de uma quebra de linha
            saida.write(l + "\n")
        saida.flush()


# ===========================================================================
# Pronto: inicialização (leia para entender de onde vêm DIR_DADOS e CAMINHO_OUI)
# ===========================================================================
def main():
    global DIR_DADOS, CAMINHO_OUI, log
    raiz = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="Agente pass_persist da AUTODESCOBERTA-MIB")
    p.add_argument("--dados", default=str(raiz / "dados"))
    p.add_argument("--oui", default=str(raiz.parent / "oui_db.json"))
    p.add_argument("--interface")
    p.add_argument("--intervalo", type=int, default=0, help="varredura automática a cada N s (0 = desligada)")
    p.add_argument("--log", help="arquivo de log ('-' = stderr)")
    args = p.parse_args()

    DIR_DADOS, CAMINHO_OUI = args.dados, args.oui
    Path(DIR_DADOS).mkdir(parents=True, exist_ok=True)
    if args.interface:
        ad.atualizar_estado(DIR_DADOS, interface=args.interface)

    if args.log:
        destino = sys.stderr if args.log == "-" else open(args.log, "a", buffering=1, encoding="utf-8")

        def log(msg):  # noqa: F811
            destino.write(f"{datetime.now():%H:%M:%S} {msg}\n")

    if args.intervalo > 0:
        def periodica():
            while True:
                time.sleep(args.intervalo)
                disparar_varredura()

        threading.Thread(target=periodica, daemon=True).start()

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    servir(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
