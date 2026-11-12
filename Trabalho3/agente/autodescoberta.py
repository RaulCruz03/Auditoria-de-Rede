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
    estado.update(carregar_json(Path(dir_dados) / "estado.json", {}))
    return estado


def atualizar_estado(dir_dados, **campos):  # todos os argumentos de um dicionário
    estado = ler_estado(dir_dados)          # ler o estado atual
    estado.update(campos)                   # atualizar com os campos passados    
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
        ip = m.group("ip")                        
        mac = m.group("mac").replace(":", "").upper()                     

        if nome == "_gateway" or ip in gateways:                         
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
            maior = maior + 1                     # avança o contador
            registro["indice"] = maior        # da o número ao registro

    return historico

def atualizar_historico(historico, achados, base_oui, data_hora):
    novo = {}
    for mac, reg in historico.items():
        novo[mac] = dict(reg)
    garantir_indices(novo)                                 # índices para os antigos sem número
    conhecidos = set(novo)                                 # MACs que existiam ANTES desta varredura

    for registro in novo.values():                         # começa Inativo
        registro["status"] = STATUS_INATIVO

    for achado in achados:
        mac = achado["mac"]
        if mac in conhecidos:
            indice = novo[mac]["indice"]                   # manter o índice antigo
            status = STATUS_ATIVO                                     
        else:
            indice = None                                  # será numerado depois
            status = STATUS_NOVO                                  

        novo[mac] = {
            "indice": indice,
            "ip": achado["ip"],                                       
            "tipo": achado["tipo"],                                   
            "fabricante": base_oui.get(mac[:6], FABRICANTE_DESCONHECIDO), 
            "status": status,
            "ultima_vez_visto": data_hora,                         
        }

    garantir_indices(novo)                                      # numera os novos: max + 1, + 2...
    return novo



def varredura(dir_dados, caminho_oui):
    caminho_hist = Path(dir_dados) / "historico.json"
    estado = ler_estado(dir_dados)                          
    historico = carregar_json(caminho_hist, {})                  
    base_oui = carregar_json(caminho_oui, {})                     

    texto = ler_tabela_arp(estado["interface"], estado["tempo_espera_ping"] )                  
    achados = parse_arp(texto, gateways_padrao())                      
    novo = atualizar_historico(historico, achados, base_oui, agora_texto())  

    salvar_json(caminho_hist, novo)                             
    atualizar_estado(dir_dados, total_varreduras=estado["total_varreduras"] + 1, ultima_varredura_epoch=time.time())   


ENV_ARP_FILE = "AUTODESCOBERTA_ARP_FILE"


def ler_tabela_arp(interface, tempo):
    if ENV_ARP_FILE in os.environ:
        return Path(os.environ[ENV_ARP_FILE]).read_text(encoding="utf-8")  
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", interface):              # valida se é uma interface de rede plausível
        raise ValueError(f"interface inválida: {interface!r}")
    r = subprocess.run(["ip", "-4", "addr", "show", interface], capture_output=True, text=True)  # captura da interface
    m = re.search(r"inet (\d+\.\d+\.\d+)\.\d+/", r.stdout)                                       # pesquisa o prefixo da rede (ex: 192.168.1)
    if not m:
        raise ValueError(f"a interface {interface} não tem endereço IPv4")
    prefixo = m.group(1)
    # mesmo ping sweep do Trabalho 1, mas com `wait` em vez de sleep fixo
    subprocess.run(["bash", "-c", f"for i in $(seq 1 254); do ping -c 1 -W {int(tempo)} "    #realiza o ping sweep, com timeout de 1 segundo, para cada host do prefixo da rede
                    f"{prefixo}.$i >/dev/null 2>&1 & done; wait"])
    time.sleep(1)
    env = dict(os.environ, LC_ALL="C")  # pega o idioma do pc atual
    return subprocess.run(["arp", "-a"], capture_output=True, text=True, env=env).stdout  # retorna a saída do comando arp -a, que lista os dispositivos conectados na rede


def gateways_padrao():
    """IPs das rotas padrão (o roteador), via `ip route`. Vazio se não conseguir."""
    if ENV_ARP_FILE in os.environ:
        return frozenset()   # conjunto imutável
    try:
        saida = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True).stdout   # mostra a rota padrão do sistema, que é o roteador
    except OSError:
        return frozenset()
    return frozenset(re.findall(r"default via (\d+\.\d+\.\d+\.\d+)", saida))    # extrai o IP do roteador da saída do comando, e retorna como um conjunto imutável


def agora_texto():
    return datetime.now().strftime(FORMATO_DATA) # FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
