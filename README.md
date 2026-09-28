# AUTODESCOBERTA-MIB

MIB SNMPv1 que descreve as informações da ferramenta de **autodescoberta de dispositivos em rede** desenvolvida no Trabalho 1. Ela define, de forma padronizada, quais dados a ferramenta produz, de que tipo são, onde ficam na árvore de OIDs e o que pode ser lido ou alterado.

> Trabalho 2 — UFSM · Definição de uma MIB

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Onde a MIB fica na árvore](#2-onde-a-mib-fica-na-árvore)
3. [Estrutura completa](#3-estrutura-completa)
4. [Objetos globais](#4-objetos-globais)
5. [Tabela de dispositivos](#5-tabela-de-dispositivos)
6. [Tipos de dados e permissões de acesso](#6-tipos-de-dados-e-permissões-de-acesso)
7. [Relação com a ferramenta de autodescoberta](#7-relação-com-a-ferramenta-de-autodescoberta)
8. [Como validar e visualizar a MIB](#8-como-validar-e-visualizar-a-mib)
9. [Exemplos de uso com SNMP](#9-exemplos-de-uso-com-snmp)
10. [Avisos do validador](#10-avisos-do-validador)
11. [Limitações](#11-limitações)
12. [Atendimento aos requisitos do trabalho](#12-atendimento-aos-requisitos-do-trabalho)

---

## 1. Visão geral

A ferramenta do Trabalho 1 faz um *ping sweep* na sub-rede, consulta a tabela ARP, identifica o fabricante de cada dispositivo pelo prefixo do MAC (base OUI) e mantém um histórico com o status de cada um.

Sem uma MIB, esses dados existem apenas como saída de terminal e um arquivo JSON que só o próprio programa entende. Esta MIB descreve essas mesmas informações no formato do SNMP, o que permite que qualquer gerente SNMP saiba **o que consultar** e **como interpretar** as respostas.

**Importante:** uma MIB é apenas a *especificação*. Ela não contém dados nem executa comandos. Para consultar ou alterar esses objetos na prática, seria necessário um agente SNMP que ligasse a MIB à ferramenta (veja a seção [11](#11-limitações)).

A MIB oferece:

- **Configuração:** interface varrida e tempo de espera do ping.
- **Estatísticas:** total de dispositivos ativos, total de varreduras e tempo desde a última.
- **Controle:** gatilho para iniciar uma varredura.
- **Inventário:** tabela com todos os dispositivos já encontrados.

---

## 2. Onde a MIB fica na árvore

A MIB foi definida dentro do ramo `experimental`, como exigido no enunciado.

```
iso(1) . org(3) . dod(6) . internet(1) . experimental(3) . autodescobertaMIB(99)
```

| Nó | OID |
|---|---|
| `experimental` | `1.3.6.1.3` |
| `autodescobertaMIB` | `1.3.6.1.3.99` |
| `objetosGlobais` | `1.3.6.1.3.99.1` |
| `tabelaDispositivos` | `1.3.6.1.3.99.2` |

---

## 3. Estrutura completa

```
experimental (1.3.6.1.3)
└── autodescobertaMIB (99)
    ├── objetosGlobais (1)
    │   ├── interfaceRede (1)                  read-only    OCTET STRING
    │   ├── tempoEsperaPing (2)                read-write   INTEGER (1..60)
    │   ├── totalDispositivosAtivos (3)        read-only    Gauge
    │   ├── totalVarredurasRealizadas (4)      read-only    Counter
    │   ├── tempoDesdeUltimaVarredura (5)      read-only    TimeTicks
    │   └── executarVarredura (6)              write-only   INTEGER { iniciar(1) }
    └── tabelaDispositivos (2)
        └── dispositivosTable (1)
            └── dispositivoEntry (1)           INDEX { dispositivoIndex }
                ├── dispositivoIndex (1)       not-accessible  INTEGER (1..65535)
                ├── dispositivoMAC (2)         read-only    OCTET STRING
                ├── dispositivoIP (3)          read-only    IpAddress
                ├── dispositivoTipo (4)        read-only    OCTET STRING
                ├── dispositivoFabricante (5)  read-only    OCTET STRING
                ├── dispositivoStatus (6)      read-only    OCTET STRING
                └── dispositivoUltimaVezVisto (7) read-only OCTET STRING
```

Saída do `snmptranslate -Tp` para conferência (a legenda `-R--`, `-RW-`, `--W-` e `----` indica as permissões):

```
+--autodescobertaMIB(99)
   |
   +--objetosGlobais(1)
   |  |
   |  +-- -R-- String    interfaceRede(1)
   |  +-- -RW- INTEGER   tempoEsperaPing(2)
   |  |        Range: 1..60
   |  +-- -R-- Gauge     totalDispositivosAtivos(3)
   |  +-- -R-- Counter   totalVarredurasRealizadas(4)
   |  +-- -R-- TimeTicks tempoDesdeUltimaVarredura(5)
   |  +-- --W- EnumVal   executarVarredura(6)
   |           Values: iniciar(1)
   |
   +--tabelaDispositivos(2)
      |
      +--dispositivosTable(1)
         |
         +--dispositivoEntry(1)
            |  Index: dispositivoIndex
            |
            +-- ---- INTEGER   dispositivoIndex(1)
            |        Range: 1..65535
            +-- -R-- String    dispositivoMAC(2)
            +-- -R-- IpAddr    dispositivoIP(3)
            +-- -R-- String    dispositivoTipo(4)
            +-- -R-- String    dispositivoFabricante(5)
            +-- -R-- String    dispositivoStatus(6)
            +-- -R-- String    dispositivoUltimaVezVisto(7)
```

---

## 4. Objetos globais

Ficam em `objetosGlobais` (`1.3.6.1.3.99.1`). São **escalares**: cada um tem uma única instância, acessada com o sufixo `.0` (por exemplo, `1.3.6.1.3.99.1.3.0`).

| # | Objeto | Tipo | Acesso | Descrição |
|---|---|---|---|---|
| 1 | `interfaceRede` | OCTET STRING | read-only | Nome da interface de rede selecionada (ex.: `eth0`, `wlp0s20f3`). |
| 2 | `tempoEsperaPing` | INTEGER (1..60) | **read-write** | Tempo máximo de espera do ping, em segundos (parâmetro `-W`). |
| 3 | `totalDispositivosAtivos` | Gauge | read-only | Quantidade atual de dispositivos ativos detectados na sub-rede. |
| 4 | `totalVarredurasRealizadas` | Counter | read-only | Quantidade total de varreduras já realizadas. |
| 5 | `tempoDesdeUltimaVarredura` | TimeTicks | read-only | Tempo desde a última varredura, em centésimos de segundo. |
| 6 | `executarVarredura` | INTEGER { iniciar(1) } | **write-only** | Escrever `1` força o disparo de um *ping sweep*. |

### Por que cada tipo foi escolhido

- **Gauge** em `totalDispositivosAtivos`: o valor pode subir e descer (dispositivos entram e saem da rede).
- **Counter** em `totalVarredurasRealizadas`: só cresce, o que permite a um gerente calcular a taxa de varreduras.
- **TimeTicks** em `tempoDesdeUltimaVarredura`: representa duração em centésimos de segundo, unidade padrão do SNMP.
- **INTEGER (1..60)** em `tempoEsperaPing`: a faixa impede valores inválidos de timeout.
- **INTEGER com enumeração** em `executarVarredura`: o único valor aceito é `iniciar(1)`, o que evita comandos ambíguos.

---

## 5. Tabela de dispositivos

Fica em `tabelaDispositivos` (`1.3.6.1.3.99.2`) e funciona como o **inventário** da rede: cada linha é um dispositivo encontrado, e a tabela guarda o histórico, incluindo dispositivos hoje inativos.

| Elemento | OID |
|---|---|
| `dispositivosTable` | `1.3.6.1.3.99.2.1` |
| `dispositivoEntry` (linha) | `1.3.6.1.3.99.2.1.1` |
| Colunas | `1.3.6.1.3.99.2.1.1.N.<índice>` |

### Colunas

| # | Coluna | Tipo | Acesso | Conteúdo |
|---|---|---|---|---|
| 1 | `dispositivoIndex` | INTEGER (1..65535) | not-accessible | Índice único e sequencial da linha. |
| 2 | `dispositivoMAC` | OCTET STRING | read-only | MAC em hexadecimal, sem dois-pontos e em maiúsculas (ex.: `A1B2C3D4E5F6`). |
| 3 | `dispositivoIP` | IpAddress | read-only | Endereço IP associado ao dispositivo. |
| 4 | `dispositivoTipo` | OCTET STRING | read-only | Papel do dispositivo: `Host` ou `Roteador`. |
| 5 | `dispositivoFabricante` | OCTET STRING | read-only | Fabricante, obtido pelo prefixo do MAC (base OUI). |
| 6 | `dispositivoStatus` | OCTET STRING | read-only | `Dispositivo Ativo`, `Dispositivo Novo` ou `Inativo`. |
| 7 | `dispositivoUltimaVezVisto` | OCTET STRING | read-only | Data e hora do último registro, no formato `YYYY-MM-DD HH:MM:SS`. |

### Como o índice funciona

O `dispositivoIndex` é `not-accessible`: ele **não é lido como coluna**, mas é o último número do OID de cada célula. Por exemplo, o IP do terceiro dispositivo fica em:

```
dispositivoIP.3   →   1.3.6.1.3.99.2.1.1.3.3
                                          │ └─ índice da linha
                                          └─── coluna (3 = dispositivoIP)
```

### Significado do status

| Status | Quando ocorre |
|---|---|
| `Dispositivo Novo` | O MAC apareceu pela primeira vez nesta varredura. |
| `Dispositivo Ativo` | O MAC já era conhecido e respondeu nesta varredura. |
| `Inativo` | O MAC está no histórico, mas não foi encontrado nesta varredura. |

---

## 6. Tipos de dados e permissões de acesso

### Tipos de dados utilizados

| Tipo | Onde é usado |
|---|---|
| `INTEGER` | `tempoEsperaPing`, `executarVarredura`, `dispositivoIndex` |
| `OCTET STRING` | `interfaceRede`, MAC, tipo, fabricante, status, data |
| `IpAddress` | `dispositivoIP` |
| `Counter` | `totalVarredurasRealizadas` |
| `Gauge` | `totalDispositivosAtivos` |
| `TimeTicks` | `tempoDesdeUltimaVarredura` |

### Permissões de acesso

| Acesso | Significado | Objetos |
|---|---|---|
| `read-only` | O gerente só pode consultar. | `interfaceRede`, `totalDispositivosAtivos`, `totalVarredurasRealizadas`, `tempoDesdeUltimaVarredura` e as colunas 2 a 7 da tabela |
| `read-write` | O gerente pode consultar e alterar. | `tempoEsperaPing` |
| `write-only` | O gerente só pode escrever (é um comando, não um dado). | `executarVarredura` |
| `not-accessible` | Não pode ser lido nem escrito diretamente; existe só para estruturar a MIB. | `dispositivosTable`, `dispositivoEntry`, `dispositivoIndex` |

Todos os objetos usam `STATUS mandatory`.

---

## 7. Relação com a ferramenta de autodescoberta

| Objeto da MIB | Origem no script |
|---|---|
| `interfaceRede` | Interface informada pelo usuário (`eth0` ou `wlp0s20f3`). |
| `tempoEsperaPing` | Valor usado no `-W` do `ping`. |
| `totalDispositivosAtivos` | Contagem das entradas do histórico com status diferente de `Inativo`. |
| `totalVarredurasRealizadas` | Contador de execuções, guardado em arquivo (por exemplo, `global.json`). |
| `tempoDesdeUltimaVarredura` | Diferença entre o instante atual e o registro da varredura anterior. |
| `executarVarredura` | Equivale a executar o script (ping sweep). |
| `dispositivoIndex` | Posição sequencial do dispositivo no histórico. |
| `dispositivoMAC` | Saída do `arp -a`, sem `:` e em maiúsculas. |
| `dispositivoIP` | Saída do `arp -a`. |
| `dispositivoTipo` | `Roteador` se o nome é `_gateway`; `Host` nos demais. |
| `dispositivoFabricante` | Consulta do prefixo do MAC (6 primeiros caracteres) na base `oui_db.json`. |
| `dispositivoStatus` | Comparação entre a varredura atual e o `historico.json`. |
| `dispositivoUltimaVezVisto` | Data e hora da varredura em que o dispositivo respondeu. |

O `historico.json` alimenta a tabela; os objetos globais dependem de um registro global de varreduras, que precisa ser mantido pela ferramenta.

---

## 8. Como validar e visualizar a MIB

### Validação em navegador de MIBs

Importe o arquivo `AUTODESCOBERTA-MIB.txt` em um navegador de MIBs (por exemplo, o Mibble MIB Browser). A importação deve concluir sem erros; o único aviso esperado é o do `write-only` (seção [10](#10-avisos-do-validador)).

### Árvore pelo terminal (Linux)

Requer os MIBs padrão do net-snmp:

```bash
sudo apt install snmp-mibs-downloader
sudo download-mibs
```

Depois, comente a linha `mibs :` em `/etc/snmp/snmp.conf` (com um `#`) e rode, na pasta do arquivo:

```bash
# Árvore completa
snmptranslate -M +/usr/share/snmp/mibs -m +./AUTODESCOBERTA-MIB.txt -Tp -IR autodescobertaMIB

# OID numérico da raiz (esperado: .1.3.6.1.3.99)
snmptranslate -M +/usr/share/snmp/mibs -m +./AUTODESCOBERTA-MIB.txt -IR -On autodescobertaMIB
```

O `+` em `-m` e `-M` **soma** o seu arquivo e o diretório aos padrões, em vez de substituí-los. Sem os MIBs padrão instalados, o erro `Cannot find module (SNMPv2-SMI)` aparece, e isso não indica problema na MIB.

---

## 9. Exemplos de uso com SNMP

> **Atenção:** estes comandos só funcionam com um **agente SNMP** que implemente esta MIB e esteja em execução. A MIB sozinha não responde consultas. Os exemplos mostram como ela seria usada por um gerente.

**Ver toda a tabela de dispositivos:**

```bash
snmpwalk -v1 -c public -m +./AUTODESCOBERTA-MIB.txt localhost dispositivosTable
```

**Consultar objetos globais:**

```bash
snmpget -v1 -c public -m +./AUTODESCOBERTA-MIB.txt localhost totalDispositivosAtivos.0
snmpget -v1 -c public -m +./AUTODESCOBERTA-MIB.txt localhost totalVarredurasRealizadas.0
```

**Ler uma coluna específica (IP do dispositivo de índice 3):**

```bash
snmpget -v1 -c public -m +./AUTODESCOBERTA-MIB.txt localhost dispositivoIP.3
```

**Alterar o tempo de espera do ping (read-write):**

```bash
snmpset -v1 -c private -m +./AUTODESCOBERTA-MIB.txt localhost tempoEsperaPing.0 i 5
```

**Disparar uma varredura (write-only):**

```bash
snmpset -v1 -c private -m +./AUTODESCOBERTA-MIB.txt localhost executarVarredura.0 i 1
```

Os escalares levam o sufixo `.0`; as colunas da tabela levam o índice da linha.

---

## 10. Avisos do validador

Ao validar, o Mibble pode exibir avisos. Os dois primeiros foram corrigidos; o terceiro é esperado.

| Aviso | Situação |
|---|---|
| `dispositivoIndex` deveria ser `not-accessible` | **Corrigido.** O índice agora é `not-accessible`. |
| Nome do tipo `DispositivosEntry` fora da convenção | **Corrigido.** Renomeado para `DispositivoEntry`. |
| `write-only` limita a compatibilidade com SMIv2 | **Mantido.** O SMIv2 eliminou o `write-only`, mas o enunciado exige esse tipo de acesso, e o SMIv1 (RFC 1212) o permite. |

---

## 11. Limitações

- **É só a especificação.** Não há um agente SNMP: a MIB não responde a consultas nem executa varreduras por conta própria.
- **Implementação do agente.** Uma forma de fazê-lo é com o `pass_persist` do net-snmp, delegando o ramo `1.3.6.1.3.99` a um script que leia os arquivos JSON e chame a ferramenta de varredura. Outra é usar uma biblioteca de agentes, como `pysnmp`.
- **`executarVarredura`** só faz sentido com um agente: no script atual, executar o programa já equivale a disparar a varredura.
- **Ramo `experimental`.** O OID `1.3.6.1.3.99` é adequado para fins acadêmicos, mas não é um registro oficial.
- **Tabela sem remoção de linhas.** Como o histórico preserva dispositivos que não respondem mais, a tabela cresce ao longo do tempo (limite do índice: 65535 linhas).

---

## 12. Atendimento aos requisitos do trabalho

| Requisito do enunciado | Atendimento |
|---|---|
| Especificar uma MIB para a ferramenta de autodescoberta | `AUTODESCOBERTA-MIB` |
| Definida dentro de `experimental` | `{ experimental 99 }` |
| Usar tipos de dados variados | INTEGER, OCTET STRING, IpAddress, Counter, Gauge e TimeTicks |
| Ao menos uma tabela | `dispositivosTable` |
| Objetos read-only, write-only e read-write | `read-only` (vários), `write-only` (`executarVarredura`), `read-write` (`tempoEsperaPing`) |
| STATUS mandatory ou optional | Todos os objetos com `mandatory` |

---

## Arquivos

| Arquivo | Descrição |
|---|---|
| `AUTODESCOBERTA-MIB.txt` | Definição da MIB (SMIv1). |
| `README.md` | Este documento. |
