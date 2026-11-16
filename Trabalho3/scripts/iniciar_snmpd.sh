#!/usr/bin/env bash
# Inicia um snmpd (em primeiro plano) com o agente da AUTODESCOBERTA-MIB.
#
# Variáveis opcionais:
#   PORTA=1161        porta UDP
#   ESCUTA=127.0.0.1  endereço de escuta (0.0.0.0 aceita consultas de outras máquinas)
#   DADOS=<dir>       pasta de historico.json / estado.json (padrão: Trabalho3/dados)
#   INTERVALO=60      varredura automática a cada N segundos (0 = só por SET)
#   INTERFACE=wlp0s20f3  interface varrida (grava em estado.json)
#   LOG_AGENTE=arq    registra no arquivo a conversa snmpd <-> agente (útil para estudar o protocolo)
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORTA="${PORTA:-1161}"
ESCUTA="${ESCUTA:-127.0.0.1}"
DADOS="${DADOS:-$RAIZ/dados}"
INTERVALO="${INTERVALO:-60}"
OUI="${OUI:-$RAIZ/../oui_db.json}"
RUN="${RUN:-$RAIZ/run}"
FONTE="127.0.0.1"
[ "$ESCUTA" = "127.0.0.1" ] || FONTE="default"

case "$RAIZ$DADOS$OUI" in *" "*) echo "Erro: o snmpd não aceita espaços nos caminhos (mova o projeto para uma pasta sem espaços)." >&2; exit 1;; esac

COMANDO_AGENTE="$(command -v python3) $RAIZ/agente/agente_snmp.py --dados $DADOS --oui $OUI --intervalo $INTERVALO"
[ -z "${INTERFACE:-}" ] || COMANDO_AGENTE="$COMANDO_AGENTE --interface $INTERFACE"
[ -z "${LOG_AGENTE:-}" ] || COMANDO_AGENTE="$COMANDO_AGENTE --log $LOG_AGENTE"

command -v snmpd >/dev/null || { echo "snmpd não encontrado: sudo apt install snmpd snmp" >&2; exit 1; }
mkdir -p "$RUN" "$DADOS"

sed -e "s|@ESCUTA@|$ESCUTA|g" -e "s|@PORTA@|$PORTA|g" -e "s|@FONTE@|$FONTE|g" \
    -e "s|@COMANDO_AGENTE@|$COMANDO_AGENTE|g" \
    "$RAIZ/config/snmpd.conf.modelo" > "$RUN/snmpd.conf"

# Sem root o snmpd não consegue gravar em /var/lib/net-snmp; usamos uma pasta local.
export SNMP_PERSISTENT_DIR="$RUN/persistente"
mkdir -p "$SNMP_PERSISTENT_DIR"

echo "snmpd em $ESCUTA:$PORTA  (comunidades: teste = leitura, teste-rw = leitura/escrita)" >&2
exec snmpd -f -C -c "$RUN/snmpd.conf" -Lo -p "$RUN/snmpd.pid"
