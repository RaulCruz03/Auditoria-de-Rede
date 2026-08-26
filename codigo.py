import subprocess
import json

interface =  input("Digite a interface de rede: -e é ethernet e -w é wireless: ")
if(interface == "-w"):
     interface = "wlp0s20f3"
comando = "ip -4 addr show " + interface + " | grep inet"
resultado = subprocess.run(comando, shell=True, capture_output=True, text=True)
ip_local = ""
counter_dots = 0
palavras = resultado.stdout.split()

for i in range(len(palavras[1])):
        ip_local = ip_local + palavras[1][i]
        if(palavras[1][i] == "."):
            counter_dots += 1
            if(counter_dots==3):
                break
        
def ping_sweep(ip_local):
    comando = f"for i in {{1..254}}; do ping -c 1 -W 1 {ip_local}$i > /dev/null 2>&1 & done" # -c 1 é pacote e -W 1 é espera de 1 seg
                                                                                    # > /dev/null 2>&1 é silenciar a saída de comando
    subprocess.run(comando, shell=True)

ping_sweep(ip_local)