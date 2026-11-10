# Trabalho 3 — Agente SNMP da AUTODESCOBERTA-MIB

Agente SNMP que publica, via **SNMPv2c** (e v1), os objetos da MIB do Trabalho 2 com os dados reais da
ferramenta de autodescoberta do Trabalho 1. O agente usa **Net-SNMP**: o `snmpd` cuida do protocolo e
delega o ramo `1.3.6.1.3.99` a um script Python (`pass_persist`) que lê o histórico de dispositivos.

> Quer entender o código passo a passo? Leia o [`ROTEIRO.md`](ROTEIRO.md).

```
 snmpget / snmpwalk / snmpset            snmpd (Net-SNMP)              agente_snmp.py
 ───────────────────────────►   UDP 1161  v1/v2c, GETBULK    stdin/    get / getnext / set
 (gerente)                      comunidades, erros SNMP ───► stdout ──► monta as instâncias a partir de
                                                                         historico.json + estado.json
                                                                                  ▲
                                           autodescoberta.py (varredura: ping + ARP + base OUI) ──┘
```

## Requisitos

- Linux com Python 3.8+ e Net-SNMP: `sudo apt install snmpd snmp`
- Os arquivos `oui_db.json` (base de fabricantes) na raiz do repositório, como no Trabalho 1
- O projeto **deve estar em uma pasta sem espaços** no caminho (limitação de parsing do `snmpd`)

Não há dependências Python além da biblioteca padrão.

## Executar o agente

```bash
cd Trabalho3
INTERFACE=wlp0s20f3 ./scripts/iniciar_snmpd.sh      # ou INTERFACE=eth0
```

Isso gera `run/snmpd.conf` a partir de `config/snmpd.conf.modelo` e inicia o `snmpd` em primeiro plano em
`127.0.0.1:1161` (não precisa de root). Deixe esse terminal aberto e consulte em outro.

| Variável | Padrão | Função |
|---|---|---|
| `PORTA` | `1161` | porta UDP |
| `ESCUTA` | `127.0.0.1` | `0.0.0.0` aceita consultas de outras máquinas |
| `INTERFACE` | valor em `estado.json` (`wlp0s20f3`) | interface varrida |
| `INTERVALO` | `60` | varredura automática a cada N s (`0` = só quando houver SET) |
| `DADOS` | `Trabalho3/dados` | pasta de `historico.json` e `estado.json` |
| `LOG_AGENTE` | — | arquivo onde registrar a conversa `snmpd` ↔ agente |

Comunidades (só para teste): `teste` = leitura, `teste-rw` = leitura e escrita.

Para começar com o histórico que você já tem do Trabalho 1: `cp ../historico.json dados/`
(o agente adiciona o campo `indice` e mantém o formato).

## Consultar

Todos os comandos usam a MIB (`-M ./mibs -m AUTODESCOBERTA-MIB`) para mostrar nomes em vez de OIDs.

```bash
cd Trabalho3
MIB="-M ./mibs -m AUTODESCOBERTA-MIB"

# Validar a MIB / OIDs
snmptranslate $MIB -IR -On autodescobertaMIB                  # .1.3.6.1.3.99

# GET de escalares
snmpget  -v2c -c teste $MIB 127.0.0.1:1161 totalDispositivosAtivos.0 totalVarredurasRealizadas.0

# WALK da MIB inteira e só da tabela
snmpwalk -v2c -c teste $MIB 127.0.0.1:1161 autodescobertaMIB
snmpwalk -v2c -c teste $MIB 127.0.0.1:1161 dispositivosTable

# GETNEXT e GETBULK
snmpgetnext  -v2c -c teste $MIB 127.0.0.1:1161 dispositivoMAC.2
snmpbulkwalk -v2c -c teste $MIB -Cr5 127.0.0.1:1161 dispositivosTable

# Uma célula da tabela: coluna.índice
snmpget -v2c -c teste $MIB 127.0.0.1:1161 dispositivoIP.3

# SET: mudar o tempo de espera do ping e disparar uma varredura
snmpset -v2c -c teste-rw $MIB 127.0.0.1:1161 tempoEsperaPing.0 i 2
snmpset -v2c -c teste-rw $MIB 127.0.0.1:1161 executarVarredura.0 i 1
```

Os testes do roteiro oficial (`snmpget -v2c -c teste 127.0.0.1:1161 OID.0`) também funcionam, com OIDs numéricos.

## Testes e evidências

```bash
python3 -m unittest discover -s testes -v     # 18 testes unitários (milissegundos, sem snmpd)
python3 testes/integracao_snmpd.py            # sobe um snmpd real e consulta com snmpget/walk/bulkwalk/set
```

O teste de integração usa uma tabela ARP simulada (`testes/dados_exemplo/arp_cenario*.txt`, via a variável
`AUTODESCOBERTA_ARP_FILE`), então é reproduzível em qualquer máquina, e grava em `evidencias/`:

- `saida_testes.txt` — cada comando executado, a resposta e o veredito (GET, WALK, GETNEXT, GETBULK, objetos
  inexistentes, SET válido e inválido, duas varreduras mostrando as mudanças refletidas, SNMPv1).
- `log_protocolo_agente.txt` — a conversa real entre o `snmpd` e o agente.

> Para evidências na **sua** rede, rode o agente normalmente (sem `AUTODESCOBERTA_ARP_FILE`), dispare uma
> varredura com `executarVarredura.0` e anexe a saída dos `snmpwalk` antes e depois.

## Origem dos dados de cada objeto

| Objeto (OID sob `1.3.6.1.3.99`) | Tipo SNMP | Acesso | Origem |
|---|---|---|---|
| `interfaceRede` (1.1.0) | OCTET STRING | read-only | `estado.json`: interface informada em `INTERFACE`/`--interface` |
| `tempoEsperaPing` (1.2.0) | INTEGER (1..60) | read-write | `estado.json`; é o `-W` do `ping`. O SET valida a faixa e persiste |
| `totalDispositivosAtivos` (1.3.0) | Gauge32 | read-only | Contagem de registros de `historico.json` com status ≠ `Inativo` |
| `totalVarredurasRealizadas` (1.4.0) | Counter32 | read-only | `estado.json`: incrementado a cada varredura concluída |
| `tempoDesdeUltimaVarredura` (1.5.0) | TimeTicks | read-only | (agora − `ultima_varredura_epoch`) × 100; sem varredura própria, usa o maior `ultima_vez_visto` |
| `executarVarredura` (1.6.0) | INTEGER {iniciar(1)} | write-only | SET `1` dispara `Autodescoberta.executar_varredura()` em segundo plano |
| `dispositivoIndex` (2.1.1.1) | INTEGER (1..65535) | not-accessible | Campo `indice` do histórico: sequencial, atribuído quando o MAC é visto pela 1ª vez e nunca reutilizado. Aparece como último número do OID |
| `dispositivoMAC` (2.1.1.2.i) | OCTET STRING | read-only | Chave do registro em `historico.json` (de `arp -a`, sem `:`, maiúsculo) |
| `dispositivoIP` (2.1.1.3.i) | IpAddress | read-only | `ip` do registro (de `arp -a`) |
| `dispositivoTipo` (2.1.1.4.i) | OCTET STRING | read-only | `Roteador` se `_gateway` ou IP da rota padrão; senão `Host` |
| `dispositivoFabricante` (2.1.1.5.i) | OCTET STRING | read-only | Prefixo de 6 dígitos do MAC consultado em `oui_db.json` |
| `dispositivoStatus` (2.1.1.6.i) | OCTET STRING | read-only | `Dispositivo Novo` (1ª vez), `Dispositivo Ativo` (respondeu) ou `Inativo` (não respondeu na varredura) |
| `dispositivoUltimaVezVisto` (2.1.1.7.i) | OCTET STRING | read-only | Data/hora da última varredura em que respondeu |

A tabela é reconstruída **a cada consulta** a partir dos arquivos (com cache por data de modificação do arquivo),
e o histórico é gravado de forma atômica; por isso qualquer varredura — por SET, periódica ou rodando
`python3 agente/autodescoberta.py` à mão — aparece na consulta seguinte.

## Revisão da MIB

O arquivo usado é `mibs/AUTODESCOBERTA-MIB.txt`. O original do repositório está em
`mibs/AUTODESCOBERTA-MIB.original.txt`. Duas correções, ambas já descritas como feitas no README do Trabalho 2,
mas ausentes no arquivo `.txt` versionado:

| Mudança | Justificativa |
|---|---|
| `dispositivoIndex`: `ACCESS read-only` → `not-accessible` | Aviso do validador (Mibble) já registrado no Trabalho 2. O índice só identifica a linha e seu valor já está no OID de cada célula; expô-lo como coluna seria redundante. O README do Trabalho 2 já o documenta como `not-accessible`. |
| Tipo `DispositivosEntry` → `DispositivoEntry` | Convenção do SMIv1: o tipo SEQUENCE da linha leva o nome do objeto `dispositivoEntry` com inicial maiúscula. Também era aviso do validador. |

Nenhum OID, tipo ou semântica foi alterado. A MIB importa `RFC-1212` e `RFC1155-SMI`, copiados para `mibs/`.

## Decisões e limitações

- **`executarVarredura` (write-only) responde a GET com `iniciar(1)`.** O `pass_persist` só repassa um SET se o objeto
  responder a um GET (o `snmpd` faz um `get` antes do `set`). O objeto **não** aparece em GETNEXT/WALK. Uma
  alternativa sem essa limitação é um subagente AgentX ou o `pysnmp`, ao custo de muito mais código de protocolo.
- GET de um OID inexistente dentro do ramo devolve `No Such Instance` (o `snmpd` não distingue de `No Such Object`).
- GETNEXT depois do último objeto segue para o próximo ramo registrado no `snmpd` (comportamento correto).
- Counter e Gauge são SMIv1 na MIB e aparecem como `Counter32`/`Gauge32` no v2c.
- A varredura cobre o `/24` do IP da interface (igual ao Trabalho 1) e depende de `ip`, `ping` e `arp` (`net-tools`).
- Comunidades `teste`/`teste-rw` e escuta em `127.0.0.1` são para ambiente de teste, não para produção.
- Uma varredura simultânea a outra é recusada com `inconsistentValue` no SET.

## Estrutura

```
Trabalho3/
├── agente/autodescoberta.py    varredura, histórico e estado (Trabalho 1 como biblioteca)
├── agente/agente_snmp.py       agente pass_persist: GET, GETNEXT, SET
├── config/snmpd.conf.modelo    configuração do snmpd (preenchida pelo script)
├── scripts/iniciar_snmpd.sh    gera a configuração e inicia o snmpd
├── mibs/                       MIB revisada, original e as RFCs importadas
├── testes/                     unitários, integração e dados de exemplo
├── evidencias/                 saída dos testes (gerada por integracao_snmpd.py)
├── ROTEIRO.md                  roteiro de estudo por etapas
└── README.md
```
