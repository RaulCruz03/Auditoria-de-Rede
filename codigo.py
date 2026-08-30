import subprocess
import json
import time
from datetime import datetime

interface =  input("Digite a interface de rede: -e é ethernet e -w é wireless: ")
if(interface == "w"):
     interface = "wlp0s20f3"
if(interface == "e"):
     interface = "eth0"

tempo = input("Digite o tempo máximo de espera do ping: ")

comando = "ip -4 addr show " + interface + " | grep inet"
resultado = subprocess.run(comando, shell=True, capture_output=True, text=True)
ip_local = ""
counter_dots = 0
palavras = resultado.stdout.split()
data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

for i in range(len(palavras[1])):
        ip_local = ip_local + palavras[1][i]
        if(palavras[1][i] == "."):
            counter_dots += 1
            if(counter_dots==3):
                break
        
def ping_sweep(ip_local):
    comando = f"for i in $(seq 1 254); do ping -c 1 -W {tempo} {ip_local}$i > /dev/null 2>&1 & done" # -c 1 é pacote e -W 1 é espera de 1 seg
                                                                                    # > /dev/null 2>&1 é silenciar a saída de comando
    subprocess.run(comando, shell=True)

with open("AuditorRede/oui_db.json","r", encoding="utf-8") as f:
     base_oui = json.load(f)

try:
    with open("AuditorRede/historico.json", "r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
except FileNotFoundError:
     dados = {}

ping_sweep(ip_local)
time.sleep(2)

mac_conhecidos = set(dados.keys())


resultado_arp = subprocess.run("arp -a", shell=True, capture_output=True, text=True)
for mac_salvo in dados:
     dados[mac_salvo]["status"] = "Inativo"
for i in resultado_arp.stdout.splitlines():
     
     if "<incompleto>" in i:
          continue
     linha = i.split()
     if(len(linha)>=4):
          ip  = linha[1].replace("(","").replace(")","")
          mac = linha[3].replace(":","").upper()
          tipo = "Roteador" if linha[0] == "_gateway" else "Host"
          prefixo_mac = mac[:6]
          fabricante = base_oui.get(prefixo_mac,"Fabricante Desconhecido || Mac Privado")

          dados[mac] = {
               "ip": ip,
               "tipo": tipo,
               "fabricante": fabricante,
               "status": "Dispositivo Novo" if mac not in mac_conhecidos else "Dispositivo Ativo",
               "ultima_vez_visto": data_hora
          }
          
          prefixo_mac = mac[:6]
          fabricante = base_oui.get(prefixo_mac,"Fabricante Desconhecido || Mac Privado")
          print(f"ip: {ip} | tipo: {tipo} | mac: {mac} | fabricante: {fabricante} | status: Ativo | ultima_vez_visto: {data_hora} \n")


with open("AuditorRede/historico.json", "w", encoding = "utf-8") as arquivo:
     json.dump(dados, arquivo, indent=4, ensure_ascii=False)