# Guia do Trabalho 3: você implementa, o Claude revisa

Você vai construir um agente SNMP para a sua MIB do Trabalho 2, com os dados da sua autodescoberta do
Trabalho 1. A infraestrutura (scripts, testes, configuração do snmpd) já está pronta. **A lógica é sua**:
todo `raise NotImplementedError  # TODO` em `agente/` é para você substituir.

## Como cada etapa funciona

```
 1. Ler          o conceito da etapa (curto)
 2. Prever       responder a pergunta "Antes de codar" ANTES de implementar
 3. Implementar  as funções indicadas (a docstring de cada uma é a especificação)
 4. Verificar    python3 verificar.py <etapa>      (repita até tudo dar [OK])
 5. Experimentar o que a etapa sugere no terminal
 6. Checkpoint   mandar ao Claude: seu código + respostas das perguntas
```

**No checkpoint**, cole na conversa as funções da etapa e as suas respostas. Eu reviso o que os testes não
pegam: clareza, casos de borda, nomes, e se você entendeu o *porquê*. Só então siga para a próxima.

**Travou?** Primeiro abra as dicas da etapa aqui no guia, em ordem; cada uma revela um pouco mais. Se ainda
assim travar, me peça "dica da etapa N" e diga o que já tentou. Eu respondo com perguntas e pistas, não com o
código pronto, a menos que você peça explicitamente.

**Regra de ouro:** se um teste passou e você não sabe explicar por quê, ainda não acabou.

## Preparação

```bash
sudo apt install snmpd snmp          # Net-SNMP (servidor e ferramentas)
cd Trabalho3
python3 verificar.py                 # mostra o progresso de todas as etapas
```

Mapa dos arquivos:

| Arquivo | De quem é |
|---|---|
| `agente/autodescoberta.py` | **seu** (etapa 1); no fim há funções prontas de ping/ARP |
| `agente/agente_snmp.py` | **seu** (etapas 2 a 6); `main()` já está pronta |
| `config/snmpd.conf.modelo` | **seu** (etapa 7: uma linha) |
| `mibs/AUTODESCOBERTA-MIB.txt` | **seu** (etapa 0: revisar) |
| `README.md` | **seu** (etapa 8: escrever do zero) |
| `testes/`, `scripts/`, `verificar.py` | prontos; leia à vontade, são a especificação |

---

## Etapa 0: a MIB (≈20 min)

**Conceito.** A MIB é o contrato: diz quais objetos existem, com qual OID, tipo e acesso. O agente vai
cumprir esse contrato à risca, e o professor avalia exatamente essa conformidade.

**Faça.**
```bash
python3 verificar.py 0               # valida a MIB e imprime a árvore
```
1. Compare `mibs/AUTODESCOBERTA-MIB.txt` com o README do seu Trabalho 2. O README diz que duas correções
   foram feitas. O `.txt` confirma? Decida o que corrigir. O enunciado permite correções "identificadas e
   justificadas"; anote a justificativa, ela vai para o README na etapa 8.
2. Desenhe no papel a árvore com os OIDs completos de `interfaceRede.0`, `executarVarredura.0` e da
   célula `dispositivoIP` da linha 3.

**Checkpoint.**
- O que significa o `.0` no fim de um escalar? E os dois últimos números de `1.3.6.1.3.99.2.1.1.3.3`?
- Quais objetos o agente vai poder ler? Quais vai poder alterar? Qual nunca deveria ser lido?
- Que correções você fez na MIB e por quê?

<details><summary>Dica 1</summary>

Procure no `.txt` o `ACCESS` de `dispositivoIndex` e o nome do tipo `SEQUENCE` da linha da tabela; depois
procure os mesmos itens no README do Trabalho 2.
</details>

---

## Etapa 1: autodescoberta como biblioteca (≈1h30)

**Conceito.** O agente precisa *chamar* a varredura e *ler* o resultado. Seu `codigo.py` mistura tudo
(input, ping, ARP, JSON, print). Separar em funções pequenas permite testar cada parte. Repare que
`parse_arp` e `atualizar_historico` não tocam em rede nem em disco: recebem dados e devolvem dados. Funções
assim ("puras") são as mais fáceis de testar.

**Antes de codar.** Um dispositivo apareceu como "Dispositivo Novo" na varredura 1. Na varredura 2 ele
responde de novo. Qual o status? E se na varredura 3 ele não responder? E o índice dele em cada caso?

**Implemente**, na ordem: `carregar_json`, `salvar_json`, `ler_estado`, `atualizar_estado`, `parse_arp`,
`garantir_indices`, `atualizar_historico`, `varredura`. Rode `python3 verificar.py 1` a cada função.

**Experimente** com a sua rede de verdade:
```bash
arp -a                                                   # o texto que o parse_arp recebe
python3 -c "import sys; sys.path.insert(0,'agente'); import autodescoberta as ad, subprocess
print(ad.parse_arp(subprocess.run(['arp','-a'],capture_output=True,text=True).stdout))"
mkdir -p dados
python3 -c "import sys; sys.path.insert(0,'agente'); import autodescoberta as ad
ad.atualizar_estado('dados', interface='wlp0s20f3'); ad.varredura('dados', '../oui_db.json')"
cat dados/historico.json dados/estado.json
```

**Checkpoint.**
- Por que `atualizar_historico` não pode alterar o dicionário que recebe? Que bug isso evitaria no agente?
não faço ideia
- Por que o índice precisa ser estável? O que aconteceria com um gerente SNMP que guardou
  "`dispositivoIP.5` é a impressora" se o índice mudasse a cada varredura?
  perderíamos informações de contexto daquela mesma rede
- Sua regex do `parse_arp`: explique cada pedaço.
não consigo.
<details><summary>Dica 1 (parse_arp)</summary>

Uma regex com três grupos: o nome (tudo até o primeiro espaço), o IP entre parênteses e o MAC
(6 pares de hex separados por `:`). Linhas com `<incomplete>` simplesmente não casam com a parte do MAC.
</details>
<details><summary>Dica 2 (atualizar_historico)</summary>

Três passos: (1) copie e garanta índices; (2) marque todo mundo como Inativo, lembrando quem já existia
(`conhecidos = set(novo)`); (3) para cada achado, sobrescreva o registro mantendo o índice antigo se houver.
No fim, `garantir_indices` dá número aos novos.
</details>

---

## Etapa 2: a conversa com o snmpd (≈40 min)

**Conceito.** O snmpd faz o trabalho pesado do SNMP (pacotes, versões, comunidades). Com o seu script ele
conversa em texto, por stdin/stdout. O protocolo está no topo de `agente_snmp.py`. Nesta etapa, as funções
`tratar_*` ainda não existem; os testes usam versões falsas delas, então você testa só o laço.

**Antes de codar.** Quantas linhas o seu script lê depois de receber `get`? E depois de `set`? O que ele
deve fazer quando `readline()` devolve `""`?

**Implemente:** `servir`.

**Experimente.** Faça o papel do snmpd, digitando no terminal:
```bash
python3 agente/agente_snmp.py --dados dados --log -
PING
```
(Ctrl+D encerra. `get` ainda vai dar erro, porque `tratar_get` vem na etapa 5.)

**Checkpoint.**
- Por que `flush()` depois de cada resposta? O que aconteceria sem ele?
- O que o `--log -` mostrou? Para que vai servir na etapa 7?

<details><summary>Dica 1</summary>

`while True:` + `linha = entrada.readline()`. Compare `linha == ""` antes de fazer `strip()`, senão você
confunde "fim da entrada" com "linha vazia".
</details>

---

## Etapa 3: OIDs (≈20 min)

**Conceito.** O SNMP ordena OIDs número a número. Como texto, `"…2.10"` vem antes de `"…2.9"`, e um WALK
com mais de 9 dispositivos sairia fora de ordem. Representar o OID como tupla de inteiros resolve: o Python
compara tuplas elemento a elemento.

**Antes de codar.** Qual o resultado de `sorted(["1.10", "1.9", "1.2"])`? E de
`sorted([(1, 10), (1, 9), (1, 2)])`? Teste no `python3` depois de prever.

**Implemente:** as constantes `OID_*` e `ENTRADA`, `parse_oid`, `formatar_oid`.

**Checkpoint.** Por que `OID_INTERFACE` termina em `0`, mas `ENTRADA` não tem índice?

---

## Etapa 4: instâncias (≈1h)

**Conceito.** Uma *instância* é (OID, tipo, valor). A MIB define objetos; o agente expõe instâncias. A cada
consulta, o agente relê os arquivos e monta a lista inteira, ordenada. É isso que faz uma mudança na rede
aparecer na consulta seguinte, um requisito explícito do enunciado.

**Antes de codar.** Com 4 dispositivos no histórico, quantas instâncias existem? Quais objetos da MIB *não*
geram instância, e por quê?

**Implemente:** `instancias`.

**Checkpoint.**
- Reconstruir a lista a cada consulta tem custo. Com 38 dispositivos (o seu histórico real) e um WALK
  completo, quantas vezes `instancias()` roda? Isso é um problema? Como você otimizaria se fosse?
- Por que Gauge para dispositivos ativos e Counter para varreduras?

<details><summary>Dica 1</summary>

Monte uma lista de tuplas: primeiro os 5 escalares, depois um `for mac, reg in historico.items()` gerando 6
células por dispositivo com `ENTRADA + (coluna, reg["indice"])`. No fim, `sorted(lista)`: tuplas se ordenam
pelo primeiro elemento, o OID.
</details>

---

## Etapa 5: GET e GETNEXT (≈40 min)

**Conceito.** GET busca o OID exato. GETNEXT busca o **primeiro OID estritamente maior** que o pedido, que
pode ser um OID que nem existe, como a raiz. WALK é um laço de GETNEXT feito pelo cliente; GETBULK é o mesmo
laço feito pelo snmpd. Por isso, com essas duas funções, WALK e GETBULK funcionam sem código extra.

**Antes de codar.** Qual a resposta de GETNEXT para `.1.3.6.1.3.99.1.5.0`? E para `.1.3.6.1.3.99.1.6.0`,
que é write-only e não está na lista?

**Implemente:** `tratar_get`, `tratar_getnext`.

**Experimente.** Agora o agente conversa de verdade. Faça um WALK na mão:
```bash
python3 agente/agente_snmp.py --dados dados
getnext
.1.3.6.1.3.99
getnext
<cole o OID que voltou>
```

**Checkpoint.**
- Por que "estritamente maior" e não "maior ou igual"? O que aconteceria com o WALK?
- Desafio opcional: o seu GETNEXT percorre a lista inteira. Pesquise `bisect.bisect_right` e explique como
  ele faria isso em O(log n).

---

## Etapa 6: SET e a varredura em segundo plano (≈1h)

**Conceito.** Um SET valida antes de alterar: tipo (`wrong-type`), valor (`wrong-value`) e permissão
(`not-writable`). O SET em `executarVarredura` dispara uma varredura, que leva segundos. O snmpd não pode
ficar esperando, então ela roda numa **thread** e o SET responde `DONE` na hora. Uma **trava** (`Lock`)
impede duas varreduras ao mesmo tempo.

**Antes de codar.** O que acontece se a varredura der uma exceção e você não liberar a trava? Como o
`try/finally` resolve isso?

**Implemente:** `disparar_varredura`, `tratar_set`.

**Checkpoint.**
- `DONE` no `executarVarredura` significa "varredura concluída"? Como um gerente sabe que ela terminou?
  (Pista: olhe os escalares da sua MIB.)
- Por que `inconsistent-value` e não `wrong-value` quando já há uma varredura rodando?

<details><summary>Dica 1 (disparar_varredura)</summary>

Crie `_trava = threading.Lock()` fora da função. Dentro: `if not _trava.acquire(blocking=False): return False`.
Defina uma função interna que chama `ad.varredura(...)` dentro de `try/finally: _trava.release()`, e passe
essa função como `target` de um `threading.Thread(..., daemon=True)`.
</details>

---

## Etapa 7: o snmpd de verdade (≈1h)

**Conceito.** Agora o seu script vira parte de um agente SNMP real, consultado com `snmpget`/`snmpwalk`,
como o professor vai fazer.

**Faça.**
1. Escreva a linha `pass_persist` em `config/snmpd.conf.modelo` (instruções no próprio arquivo).
2. Terminal 1: `INTERVALO=0 LOG_AGENTE=/tmp/agente.log ./scripts/iniciar_snmpd.sh`
3. Terminal 2:
   ```bash
   MIB="-M ./mibs -m AUTODESCOBERTA-MIB"
   snmpget  -v2c -c teste $MIB 127.0.0.1:1161 interfaceRede.0
   snmpwalk -v2c -c teste $MIB 127.0.0.1:1161 autodescobertaMIB
   snmpset  -v2c -c teste-rw $MIB 127.0.0.1:1161 tempoEsperaPing.0 i 5
   snmpset  -v2c -c teste-rw $MIB 127.0.0.1:1161 executarVarredura.0 i 1
   cat /tmp/agente.log
   ```
4. `python3 verificar.py 7` (sobe um snmpd próprio na porta 1161, então pare o do terminal 1 antes).

**O mistério.** Pelo menos um SET vai falhar no snmpd real, mesmo com todos os testes das etapas 1 a 6
passando. Investigue pelo log antes de abrir as dicas.

<details><summary>Dica 1</summary>

Compare, no `/tmp/agente.log`, o que o snmpd mandou no SET de `tempoEsperaPing.0` (funciona) e no de
`executarVarredura.0` (falha). Ele mandou o `set`?
</details>
<details><summary>Dica 2</summary>

Antes de repassar um `set`, o snmpd do `pass_persist` faz um `get` no mesmo OID para saber se o objeto
existe. Seu agente respondeu o quê?
</details>
<details><summary>Dica 3</summary>

O objeto write-only precisa responder ao GET para o SET funcionar. Que valor ele poderia devolver, sem
violar a MIB? E ele deve aparecer no WALK? Documente a sua decisão: é uma limitação do `pass_persist` e
vale a pena explicar no README.
</details>

**Checkpoint.**
- O que você descobriu no mistério e qual foi a sua decisão?
- Explique o caminho completo de um `snmpget`: do pacote UDP até a sua função e de volta.
- Por que o GET de um OID inexistente responde `No Such Instance` e não `No Such Object`?

---

## Etapa 8: rede real, evidências e README (≈1h)

1. Rode na sua rede com `INTERFACE=wlp0s20f3 ./scripts/iniciar_snmpd.sh`. Faça um `snmpwalk`, conecte ou
   desconecte um celular do Wi-Fi, dispare `executarVarredura.0` e faça outro `snmpwalk`. Salve as duas
   saídas em `evidencias/`.
2. `python3 testes/integracao_snmpd.py` gera `evidencias/saida_testes.txt`.
3. Escreva o `README.md` **do zero**, com o que o enunciado pede:
   - instalação, execução e consulta (comandos que funcionem copiando e colando);
   - a origem dos dados de cada objeto da MIB (uma tabela objeto → de onde vem o valor);
   - as correções da MIB, com justificativa;
   - as limitações e decisões (o mistério da etapa 7 entra aqui);
   - como rodar os testes e onde estão as evidências.


