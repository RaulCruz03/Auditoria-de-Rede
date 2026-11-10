"""Núcleo da autodescoberta de rede (Trabalho 1 reorganizado como biblioteca).

O script original (codigo.py) fazia tudo em sequência e pedia dados com input().
Aqui a mesma lógica vira funções reutilizáveis para que o agente SNMP possa:

  * ler o histórico de dispositivos e o estado global (para responder GET/GETNEXT);
  * disparar uma varredura (para o SET em executarVarredura e para a varredura periódica).

Arquivos mantidos em --dados (por padrão, Trabalho3/dados):

  historico.json  um registro por MAC: indice, ip, tipo, fabricante, status, ultima_vez_visto
  estado.json     interface, tempo_espera_ping, total_varreduras, ultima_varredura_epoch

Gancho de teste: se a variável de ambiente AUTODESCOBERTA_ARP_FILE apontar para um
arquivo, a varredura lê a tabela ARP dele em vez de rodar ping + `arp -a`. Isso permite
reproduzir cenários de rede sem depender de uma rede real.
"""

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

STATUS_NOVO = "Dispositivo Novo"
STATUS_ATIVO = "Dispositivo Ativo"
STATUS_INATIVO = "Inativo"
FABRICANTE_DESCONHECIDO = "Fabricante Desconhecido || Mac Privado"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
ENV_ARP_FILE = "AUTODESCOBERTA_ARP_FILE"

ESTADO_PADRAO = {
    "interface": "wlp0s20f3",
    "tempo_espera_ping": 1,
    "total_varreduras": 0,
    "ultima_varredura_epoch": None,
}

# Exemplo de linha do `arp -a`:  _gateway (192.168.4.1) at 14:51:20:62:c5:c2 [ether] on wlp0s20f3
# Linhas sem MAC (ex.: "at <incomplete>") não casam com a expressão e são ignoradas.
_RE_ARP = re.compile(
    r"^(?P<nome>\S+)\s+\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+"
    r"(?P<mac>[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})"
)
_RE_INTERFACE = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")


class ErroVarredura(Exception):
    """Falha ao executar a varredura (interface inválida, sem IP etc.)."""


def _ler_json(caminho, padrao):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def _escrever_json_atomico(caminho, objeto):
    """Grava em arquivo temporário e troca de nome.

    os.replace é atômico: quem lê o arquivo (o agente) enxerga a versão antiga
    inteira ou a nova inteira, nunca um JSON pela metade.
    """
    caminho = Path(caminho)
    fd, tmp = tempfile.mkstemp(dir=caminho.parent, prefix=caminho.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(objeto, f, indent=4, ensure_ascii=False)
        os.replace(tmp, caminho)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def parse_arp(texto, gateways=frozenset()):
    """Converte a saída do `arp -a` em uma lista de dicts {mac, ip, tipo}."""
    achados = []
    for linha in texto.splitlines():
        m = _RE_ARP.match(linha.strip())
        if not m:
            continue
        ip = m.group("ip")
        tipo = "Roteador" if (m.group("nome") == "_gateway" or ip in gateways) else "Host"
        achados.append({"mac": m.group("mac").replace(":", "").upper(), "ip": ip, "tipo": tipo})
    return achados


class Autodescoberta:
    def __init__(self, dir_dados, caminho_oui):
        self.dir_dados = Path(dir_dados)
        self.dir_dados.mkdir(parents=True, exist_ok=True)
        self.caminho_hist = self.dir_dados / "historico.json"
        self.caminho_estado = self.dir_dados / "estado.json"
        self.caminho_oui = Path(caminho_oui)
        self._oui = None
        self._trava_varredura = threading.Lock()  # impede duas varreduras simultâneas
        self._trava_estado = threading.Lock()  # protege o ciclo ler-modificar-gravar do estado
        self._cache_hist = (None, {})  # ((mtime_ns, tamanho), dados)

    # ------------------------------------------------------------------ leitura
    def historico(self):
        """Histórico {mac: registro}, relido do disco só quando o arquivo muda.

        Todo registro sai com o campo "indice". Registros antigos (do Trabalho 1)
        não têm esse campo: recebem o próximo número livre, na ordem do arquivo.
        Como nenhum dispositivo é removido do histórico, o índice é estável.
        """
        try:
            st = self.caminho_hist.stat()
            chave = (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            return {}
        if self._cache_hist[0] != chave:
            dados = _ler_json(self.caminho_hist, {})
            usados = [r["indice"] for r in dados.values() if isinstance(r.get("indice"), int)]
            proximo = max(usados, default=0) + 1
            for registro in dados.values():
                if not isinstance(registro.get("indice"), int):
                    registro["indice"] = proximo
                    proximo += 1
            self._cache_hist = (chave, dados)
        return self._cache_hist[1]

    def estado(self):
        estado = dict(ESTADO_PADRAO)
        estado.update(_ler_json(self.caminho_estado, {}))
        return estado

    def atualizar_estado(self, **campos):
        with self._trava_estado:
            estado = self.estado()
            estado.update(campos)
            _escrever_json_atomico(self.caminho_estado, estado)
            return estado

    def _base_oui(self):
        if self._oui is None:
            self._oui = _ler_json(self.caminho_oui, {})
        return self._oui

    # ---------------------------------------------------------------- varredura
    def varredura_em_andamento(self):
        return self._trava_varredura.locked()

    def executar_varredura(self):
        """Faz uma varredura completa. Retorna False se já havia outra em curso."""
        if not self._trava_varredura.acquire(blocking=False):
            return False
        try:
            self._varredura()
            return True
        finally:
            self._trava_varredura.release()

    def _varredura(self):
        estado = self.estado()
        interface, tempo = estado["interface"], int(estado["tempo_espera_ping"])
        usando_arquivo = ENV_ARP_FILE in os.environ

        if usando_arquivo:
            texto_arp = Path(os.environ[ENV_ARP_FILE]).read_text(encoding="utf-8")
            gateways = frozenset()
        else:
            self._ping_sweep(interface, tempo)
            time.sleep(1)  # dá tempo da tabela ARP assentar
            env = dict(os.environ, LC_ALL="C")
            try:
                texto_arp = subprocess.run(["arp", "-a"], capture_output=True, text=True, env=env).stdout
            except FileNotFoundError:
                raise ErroVarredura("comando 'arp' não encontrado (sudo apt install net-tools)")
            gateways = self._gateways_padrao()

        agora = time.time()
        data_hora = datetime.fromtimestamp(agora).strftime(FORMATO_DATA)
        base_oui = self._base_oui()

        dados = {mac: dict(reg) for mac, reg in self.historico().items()}
        conhecidos = set(dados)
        proximo_indice = max((r["indice"] for r in dados.values()), default=0) + 1

        for registro in dados.values():  # todos viram Inativo; quem responder volta a Ativo
            registro["status"] = STATUS_INATIVO

        for achado in parse_arp(texto_arp, gateways):
            mac = achado["mac"]
            if mac in dados:
                indice = dados[mac]["indice"]
            else:
                indice, proximo_indice = proximo_indice, proximo_indice + 1
            dados[mac] = {
                "indice": indice,
                "ip": achado["ip"],
                "tipo": achado["tipo"],
                "fabricante": base_oui.get(mac[:6], FABRICANTE_DESCONHECIDO),
                "status": STATUS_ATIVO if mac in conhecidos else STATUS_NOVO,
                "ultima_vez_visto": data_hora,
            }

        _escrever_json_atomico(self.caminho_hist, dados)
        self.atualizar_estado(
            total_varreduras=int(self.estado()["total_varreduras"]) + 1,
            ultima_varredura_epoch=agora,
        )

    @staticmethod
    def _ping_sweep(interface, tempo):
        if not _RE_INTERFACE.match(interface):
            raise ErroVarredura(f"nome de interface inválido: {interface!r}")
        try:
            r = subprocess.run(["ip", "-4", "addr", "show", interface], capture_output=True, text=True)
        except FileNotFoundError:
            raise ErroVarredura("comando 'ip' não encontrado (sudo apt install iproute2)")
        m = re.search(r"inet (\d+\.\d+\.\d+)\.\d+/", r.stdout)
        if not m:
            raise ErroVarredura(f"a interface {interface} não tem endereço IPv4")
        prefixo = m.group(1)  # varre o /24 do host, como no Trabalho 1
        comando = (
            f"for i in $(seq 1 254); do ping -c 1 -W {int(tempo)} {prefixo}.$i "
            ">/dev/null 2>&1 & done; wait"
        )
        subprocess.run(["bash", "-c", comando])

    @staticmethod
    def _gateways_padrao():
        try:
            saida = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True).stdout
        except OSError:  # sem o comando `ip`: só o nome _gateway identifica o roteador
            return frozenset()
        return frozenset(re.findall(r"default via (\d+\.\d+\.\d+\.\d+)", saida))


if __name__ == "__main__":
    # Uso avulso (equivalente ao Trabalho 1): uma varredura e impressão do histórico.
    import argparse

    ap = argparse.ArgumentParser(description="Executa uma varredura e imprime o histórico.")
    ap.add_argument("--dados", default=str(Path(__file__).resolve().parent.parent / "dados"))
    ap.add_argument("--oui", default=str(Path(__file__).resolve().parent.parent.parent / "oui_db.json"))
    ap.add_argument("--interface")
    ap.add_argument("--tempo", type=int)
    args = ap.parse_args()

    ad = Autodescoberta(args.dados, args.oui)
    novos = {k: v for k, v in (("interface", args.interface), ("tempo_espera_ping", args.tempo)) if v}
    if novos:
        ad.atualizar_estado(**novos)
    ad.executar_varredura()
    for mac, r in ad.historico().items():
        print(f"{r['indice']:>3} | {mac} | {r['ip']:<15} | {r['tipo']:<8} | {r['status']:<16} | {r['fabricante']}")
