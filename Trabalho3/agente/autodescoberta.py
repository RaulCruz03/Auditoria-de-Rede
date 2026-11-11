import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

STATUS_NOVO = "Dispositivo Novo"
STATUS_ATIVO = "Dispositivo Ativo"
STATUS_INATIVO = "Inativo"
FABRICANTE_DESCONHECIDO = "Fabricante Desconhecido || Mac Privado"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

ESTADO_PADRAO = {
    "interface": "wlp0s20f3",
    "tempo_espera_ping": 1,
    "total_varreduras": 0,
    "ultima_varredura_epoch": None,
}


# ---------------------------------------------------------------------------
# 1a. Arquivos JSON
# ---------------------------------------------------------------------------
def carregar_json(caminho, padrao):
    try:
        with open(caminho,"r", encoding="utf-8") as f:
            dados = json.load(f)
    except FileNotFoundError:
        dados = padrao
    except json.JSONDecodeError:
        dados = padrao
    return dados  


def salvar_json(caminho, dados):
        with open(caminho,"w", encoding="utf-8") as f:
            json.dump(dados,f,indent=4,ensure_ascii=False)
  


def ler_estado(dir_dados):
    estado = dict(ESTADO_PADRAO)  # cópia
    estado.update(carregar_json(Path(dir_dados) / "estado.json", ESTADO_PADRAO))
    return estado


def atualizar_estado(dir_dados, **campos):
    estado = ler_estado(dir_dados)
    estado.update(campos)
    salvar_json(Path(dir_dados) / "estado.json", estado)
    return estado


def parse_arp(texto, gateways=frozenset()):
    _RE_ARP = re.compile(r'(?P<nome>\S+)\s+\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})')
    achados = []                                   # lista que vamos devolver
    for linha in texto.splitlines():               # uma linha de cada vez
        m = _RE_ARP.match(linha.strip())           # formatação do modelo
        if m is None:
            continue                             

        nome = m.group("nome")
        ip = m.group("ip")                        # (1)
        mac = m.group("mac").replace(":", "").upper()                     # (2)

        if nome == "_gateway" or ip in gateways:                         # (3)
            tipo = "Roteador"
        else:
            tipo = "Host"

        achados.append({"mac": mac, "ip": ip, "tipo": tipo})
    return achados


def garantir_indices(historico):
    maior = 0                                  
    for registro in historico.values():        # .values() dá o dicionário de cada dispositivo
        if isinstance(registro.get("indice"), int) and registro["indice"] > maior:
            maior = registro["indice"]

    # 2º for: dar número a quem não tem
    for registro in historico.values():
        if not isinstance(registro.get("indice"), int):                             # registro sem "indice"
            maior = maior + 1                     # avance o contador
            registro["indice"] = maior        # e dê o número ao registro

    return historico

def atualizar_historico(historico, achados, base_oui, data_hora):
    novo = {}
    for mac, reg in historico.items():
        novo[mac] = dict(reg)
    garantir_indices(novo)                                      # índices para os antigos sem número
    conhecidos = set(novo)                                      # MACs que existiam ANTES desta varredura

    for registro in novo.values():                              # (1) todo mundo começa Inativo
        registro["status"] = STATUS_INATIVO

    for achado in achados:
        mac = achado["mac"]
        if mac in conhecidos:
            indice = novo[mac]["indice"]                                     # (2) manter o índice antigo
            status = STATUS_ATIVO                                     # (3)
        else:
            indice = None                                       # será numerado depois
            status = STATUS_NOVO                                     # (4)

        novo[mac] = {
            "indice": indice,
            "ip": achado["ip"],                                       # (5)
            "tipo": achado["tipo"],                                     # (6)
            "fabricante": base_oui.get(mac[:6], FABRICANTE_DESCONHECIDO),   # (7)
            "status": status,
            "ultima_vez_visto": data_hora,                         # (8)
        }

    garantir_indices(novo)                                      # numera os novos: max + 1, + 2...
    return novo


# ---------------------------------------------------------------------------
# 1d. A varredura completa
# ---------------------------------------------------------------------------
def varredura(dir_dados, caminho_oui):
    """Executa uma varredura e grava os resultados. Não devolve nada.

    Passos:
      1. ler o estado (interface e tempo_espera_ping) e o histórico (historico.json);
      2. obter o texto do ARP com ler_tabela_arp(interface, tempo) (já pronta, abaixo);
      3. achados = parse_arp(texto, gateways_padrao());
      4. novo = atualizar_historico(...), com a base OUI e a data/hora atual;
      5. salvar historico.json;
      6. atualizar o estado: total_varreduras + 1 e ultima_varredura_epoch = time.time().

    Use Path(dir_dados) / "historico.json" para montar os caminhos.
    """
    raise NotImplementedError  # TODO


ENV_ARP_FILE = "AUTODESCOBERTA_ARP_FILE"


def ler_tabela_arp(interface, tempo):
    """Faz o ping sweep e devolve a saída do `arp -a`.

    Se a variável de ambiente AUTODESCOBERTA_ARP_FILE apontar para um arquivo, só lê
    esse arquivo (sem ping). É assim que os testes simulam uma rede.
    """
    if ENV_ARP_FILE in os.environ:
        return Path(os.environ[ENV_ARP_FILE]).read_text(encoding="utf-8")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", interface):
        raise ValueError(f"interface inválida: {interface!r}")
    r = subprocess.run(["ip", "-4", "addr", "show", interface], capture_output=True, text=True)
    m = re.search(r"inet (\d+\.\d+\.\d+)\.\d+/", r.stdout)
    if not m:
        raise ValueError(f"a interface {interface} não tem endereço IPv4")
    prefixo = m.group(1)
    # mesmo ping sweep do Trabalho 1, mas com `wait` em vez de sleep fixo
    subprocess.run(["bash", "-c", f"for i in $(seq 1 254); do ping -c 1 -W {int(tempo)} "
                    f"{prefixo}.$i >/dev/null 2>&1 & done; wait"])
    time.sleep(1)
    env = dict(os.environ, LC_ALL="C")  # garante "incomplete" em inglês
    return subprocess.run(["arp", "-a"], capture_output=True, text=True, env=env).stdout


def gateways_padrao():
    """IPs das rotas padrão (o roteador), via `ip route`. Vazio se não conseguir."""
    if ENV_ARP_FILE in os.environ:
        return frozenset()
    try:
        saida = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True).stdout
    except OSError:
        return frozenset()
    return frozenset(re.findall(r"default via (\d+\.\d+\.\d+\.\d+)", saida))


def agora_texto():
    return datetime.now().strftime(FORMATO_DATA)
