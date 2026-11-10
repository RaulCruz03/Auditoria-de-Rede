# Roteiro de estudo — como o agente funciona, etapa por etapa

A ideia deste roteiro é você **entender cada peça mexendo nela**, não só rodar o resultado. Cada etapa tem:
o conceito, onde ele está no código, um experimento para fazer no terminal e perguntas/desafios para
responder sozinho. Faça na ordem; leva umas 2 a 3 horas no total.

Prepare dois terminais na pasta `Trabalho3/`. Em um, o agente: `INTERVALO=0 LOG_AGENTE=/tmp/agente.log ./scripts/iniciar_snmpd.sh`.
No outro, as consultas, com `MIB="-M ./mibs -m AUTODESCOBERTA-MIB"`.

---

## Etapa 0 — O que é a MIB e o que é o agente

**Conceito.** A MIB (Trabalho 2) só descreve *o que existe*: nomes, OIDs, tipos, permissões. O agente é o
programa que *responde* com valores reais. O gerente (`snmpget`...) faz perguntas; o agente responde.

**Experimento.**
```bash
snmptranslate $MIB -IR -On dispositivoIP        # nome -> OID
snmptranslate $MIB -Tp -IR autodescobertaMIB    # a árvore inteira, com tipos e acessos
```
**Responda:** por que todo escalar é consultado com sufixo `.0`? Por que a célula da tabela tem o OID
`coluna.índice` (por exemplo `dispositivoIP.3` = `1.3.6.1.3.99.2.1.1.3.3`)?

---

## Etapa 1 — Quem fala SNMP: o snmpd e o protocolo `pass_persist`

**Conceito.** Montar e decodificar pacotes SNMP (BER, comunidades, versões, GETBULK) é trabalho do `snmpd`.
Nosso script só recebe linhas de texto e responde linhas de texto (veja o cabeçalho de `agente/agente_snmp.py`).

**Onde:** `config/snmpd.conf.modelo` (a linha `pass_persist`) e a função `servir()` no fim de `agente_snmp.py`.

**Experimento 1: seja o snmpd.** Rode o agente direto no terminal e digite as linhas você mesmo:
```bash
python3 agente/agente_snmp.py --dados /tmp/meusdados --oui ../oui_db.json --log -
PING
get
.1.3.6.1.3.99.1.1.0
getnext
.1.3.6.1.3.99
```
**Experimento 2: veja a conversa real.** Faça um `snmpget` e depois `cat /tmp/agente.log`. Compare com o que você digitou.

**Responda:** por que o agente precisa dar `flush()` depois de cada resposta? O que o `snmpd` faz quando
recebe `NONE`?

---

## Etapa 2 — OIDs como tuplas de inteiros

**Conceito.** `"…2.10"` vem antes de `"…2.9"` como texto, mas depois como OID. Com tuplas de inteiros, o
`sorted()` e o `>` do Python já seguem a ordem do SNMP.

**Onde:** `parse_oid`, `formatar_oid` e as constantes `OID_*` no topo de `agente_snmp.py`.

**Experimento.**
```python
python3 -c "
a,b='1.3.6.1.3.99.2.1.1.2.9','1.3.6.1.3.99.2.1.1.2.10'
print(a<b)                                          # como texto
t=lambda s: tuple(map(int,s.split('.')))
print(t(a)<t(b))                                    # como tupla
"
```
**Desafio.** O teste `test_ordem_numerica_com_mais_de_9_linhas` (em `testes/test_unitario.py`) cobre isso.
Troque a ordenação do agente por uma ordenação de texto, rode os testes e veja qual quebra.

---

## Etapa 3 — Instâncias: de onde vem cada valor

**Conceito.** Uma *instância* é `(OID, tipo, valor)`. O agente **não** guarda uma lista fixa: reconstrói as
instâncias a cada consulta lendo `historico.json` e `estado.json`. É isso que torna os dados "vivos".

**Onde:** `Agente.instancias()`. Note os tipos do `pass_persist`: `string`, `integer`, `gauge`, `counter`,
`timeticks`, `ipaddress`. A tabela é gerada com `ENTRADA + (coluna, índice)`.

**Experimento: mude o dado e veja a MIB mudar.** Com o agente rodando:
```bash
snmpwalk -v2c -c teste $MIB 127.0.0.1:1161 dispositivoStatus
# edite dados/historico.json e troque um "status" por "Inativo"
snmpwalk -v2c -c teste $MIB 127.0.0.1:1161 dispositivoStatus      # mudou, sem reiniciar nada
snmpget  -v2c -c teste $MIB 127.0.0.1:1161 totalDispositivosAtivos.0
```
**Responda:** por que o índice está guardado no JSON (`indice`) em vez de ser a posição na lista? O que
quebraria para um gerente que guarda o índice de um dispositivo se ele mudasse entre consultas?

**Desafio.** Some uma coluna `dispositivoPrimeiraVezVisto` (`2.1.1.8`): o que você mudaria na MIB, em
`COLUNAS` e na varredura (`autodescoberta.py`)?

---

## Etapa 4 — GET e GETNEXT (e por que WALK e GETBULK "de graça")

**Conceito.** GET busca o OID exato. GETNEXT busca o **primeiro OID estritamente maior**. WALK é um laço de
GETNEXT feito pelo cliente; GETBULK é o mesmo laço feito pelo `snmpd` em lote. Por isso o agente só
implementa `get` e `getnext`.

**Onde:** `tratar_get` e `tratar_getnext` (note o `bisect_right`).

**Experimento: faça o WALK na mão.**
```bash
snmpgetnext -v2c -c teste -On $MIB 127.0.0.1:1161 .1.3.6.1.3.99
snmpgetnext -v2c -c teste -On $MIB 127.0.0.1:1161 .1.3.6.1.3.99.1.1.0     # use a resposta como próxima entrada...
snmpwalk -v2c -c teste -On $MIB 127.0.0.1:1161 autodescobertaMIB
snmpbulkwalk -v2c -c teste $MIB -Cr3 127.0.0.1:1161 autodescobertaMIB
```
Veja no `log` quantos `getnext` o `snmpbulkwalk -Cr3` provocou.

**Responda:** por que `GET interfaceRede` (sem `.0`) dá `No Such Instance`? Por que o WALK não mostra
`executarVarredura`? O que acontece com um GETNEXT depois do último objeto da nossa MIB?

---

## Etapa 5 — SET

**Conceito.** Um SET precisa validar *tipo* (`wrongType`), *valor* (`wrongValue`) e *permissão*
(`notWritable`) antes de alterar algo. Validação do lado do cliente (a MIB no `snmpset`) e do lado do agente
são coisas diferentes.

**Onde:** `tratar_set`.

**Experimento.**
```bash
snmpset -v2c -c teste-rw $MIB 127.0.0.1:1161 tempoEsperaPing.0 i 5          # ok
snmpset -v2c -c teste-rw $MIB 127.0.0.1:1161 tempoEsperaPing.0 i 61         # o CLIENTE recusa (a MIB diz 1..60)
snmpset -v2c -c teste-rw -m "" 127.0.0.1:1161 .1.3.6.1.3.99.1.2.0 i 61      # sem MIB: o AGENTE recusa (wrongValue)
snmpset -v2c -c teste    $MIB 127.0.0.1:1161 tempoEsperaPing.0 i 5          # comunidade só de leitura
```
**Responda:** onde ficou gravado o valor 5? O que acontece se você reiniciar o agente?

**Desafio.** Faça o SET de `tempoEsperaPing` falhar com `inconsistent-value` se uma varredura estiver em curso.

---

## Etapa 6 — Dados vivos: varredura, threads e escrita atômica

**Conceito.** Uma varredura leva segundos; o `snmpd` não espera tanto por uma resposta. Por isso o SET de
`executarVarredura` só **inicia uma thread** e responde `DONE`. Duas coisas evitam bugs:
uma `Lock` impede duas varreduras simultâneas, e o JSON é gravado em arquivo temporário + `os.replace`
(atômico), para o agente nunca ler um arquivo pela metade.

**Onde:** `Autodescoberta.executar_varredura`, `_varredura`, `_escrever_json_atomico` e `Agente._varrer_em_segundo_plano`.

**Experimento (rede de verdade).**
```bash
INTERFACE=wlp0s20f3 INTERVALO=0 ./scripts/iniciar_snmpd.sh          # terminal 1
snmpget -v2c -c teste $MIB 127.0.0.1:1161 totalVarredurasRealizadas.0 tempoDesdeUltimaVarredura.0
snmpset -v2c -c teste-rw $MIB 127.0.0.1:1161 executarVarredura.0 i 1
sleep 5
snmpwalk -v2c -c teste $MIB 127.0.0.1:1161 dispositivoStatus        # dispositivos reais da sua rede
```
Conecte/desconecte um celular do Wi-Fi, dispare outra varredura e veja o status mudar
(`Dispositivo Novo` → `Dispositivo Ativo` → `Inativo`).

**Responda:** por que `executarVarredura` devolve `DONE` antes de a varredura terminar? O que o SET faz se
você mandar dois seguidos?

---

## Etapa 7 — Testes e evidências

**Conceito.** Teste de unidade (rápido, sem rede, sem `snmpd`) e teste de integração (o `snmpd` real e as
ferramentas que o professor vai usar). A tabela ARP simulada torna o teste reproduzível.

```bash
python3 -m unittest discover -s testes -v
python3 testes/integracao_snmpd.py && less evidencias/saida_testes.txt
```
**Desafio de mutação.** Quebre o agente de propósito (inverta o `!=` em `totalDispositivosAtivos`, tire o
`% UINT32` do contador, troque `bisect_right` por `bisect_left`) e veja **quais** testes acusam. Teste que
nunca falha não prova nada.

---

## Desafios finais

1. Faça `dispositivoStatus` seguir uma regra nova: `Inativo` só depois de 3 varreduras sem resposta.
2. Implemente SNMPv3 (usuário e senha) no `snmpd.conf` e consulte com `snmpget -v3`.
3. Reescreva o agente com a biblioteca `pysnmp` e compare: o que você ganhou em controle e o que teve de
   implementar a mais? (Pista: o `GETBULK`, as comunidades e os códigos de erro.)
4. Trate o `GET` de `executarVarredura`: como fazê-lo responder `No Such Object` e ainda aceitar o SET? (Pista: o
   porquê de ele hoje responder `iniciar(1)` está em `tratar_get`.)
