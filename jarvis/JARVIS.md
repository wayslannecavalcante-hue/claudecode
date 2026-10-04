# Jarvis AEG — roteiro da leitura matinal

Este é o roteiro que a rotina diária executa (seg–sex, 7h de Brasília). Ele lê o
ClickUp pelo conector MCP, grava um snapshot compacto, gera o painel e republica
o artifact **Jarvis AEG** no mesmo link.

- Painel: https://claude.ai/artifact/5fEvikzqzx13Qx2yXLTLQS
- Branch: `claude/jarvis-aeg-operational-dashboard-f76c5x`
- IDs de listas, campos e status: `jarvis/config.json`

O acesso direto à API do ClickUp (`api.clickup.com`) é bloqueado neste ambiente,
por isso toda a coleta é feita pelas ferramentas `mcp__ClickUp__*`.

## 0. Preparar os arquivos

O código e o histórico ficam publicados junto com o próprio artifact (assim a
rotina funciona mesmo sem acesso ao GitHub). Numa sessão nova:

1. `Artifact` `action: "list"`, `scope: "files"`, `url` = painel. Isso lista
   `jarvis/build.py`, `jarvis/template.html`, `jarvis/config.json`,
   `jarvis/JARVIS.md` e `jarvis/data/snapshots/*.json`.
2. `Artifact` `action: "read"` com `paths` = todos esses arquivos e
   `out_dir` = o diretório de trabalho atual, para que caiam em `./jarvis/...`.
   Se o repositório já tiver a pasta `jarvis/`, prefira os snapshots mais
   recentes entre os dois.

## Passo a passo

`HOJE` = data de hoje em America/Sao_Paulo (AAAA-MM-DD). Todas as chamadas de
`clickup_filter_tasks` devem ser paginadas até `has_more = false`.

### 1. Carteira de clientes (lista GESTÃO DE CLIENTES `901408581641`)

`clickup_filter_tasks` com `list_ids=["901408581641"]`, `subtasks=false` e
`statuses` = todos os itens de `status_order` do config **mais** `"churn"`.

Para cada tarefa grave uma linha em `clients`:

```
[id, nome, status, nome completo do 1º responsável (ou ""), "tag1|tag2|..."]
```

Inclua todas as tags exatamente como vêm (o script usa `mrr`, `arr`, `venda.ia`,
`crm.ia`, `onboarding <mês>/26`, `churn <mês>/26`, `renovação/<mês>`). Linhas
com nome começando em "MODELO" podem ficar; o script ignora.

### 2. Clientes sem reunião há 15+ dias

`clickup_filter_tasks` na mesma lista, mesmos `statuses` do passo 1 **sem**
`"churn"`, com
`custom_fields=[{"field_id":"f4213d4c-13a5-4878-958a-9f84b1fafc69","operator":"<","value":"<HOJE − 15 dias>"}]`.
Grave só os IDs em `no_meeting_15d`.

### 3. CRM Retenção (lista `901413635330`)

- Abertos: filtre cada status `requisitou cancelamento`, `tentativa de contato`,
  `reunião marcada`, `reunião realizada` e conte (todas as páginas) →
  `retention.open`. Se não conseguir paginar tudo, marque `open_truncated: true`.
- Fechados: conte os status `retido` e `perdido` (com `include_closed=true`) →
  `retention.closed_total`.

### 4. Tarefas atrasadas

`clickup_filter_tasks` com `list_ids` = `tarefas_athena`, `tarefas_cronos`,
`obrigacoes_supervisao`, `obrigacoes_lideranca`; `statuses=["pendente","priorizada/urgente"]`;
`due_date_to` = ontem; `subtasks=true`. Para cada tarefa:

```
[nome completo do 1º responsável (ou ""), vencimento AAAA-MM-DD em America/Sao_Paulo, 1 se status "priorizada/urgente" ou prioridade urgent/high, senão 0]
```

O `due_date` vem em milissegundos UTC; converta com fuso −03:00. Se precisar
parar antes da última página, grave `overdue_truncated: true`.

### 4b. Skalo.IA (resultados dos clientes)

Procure as ferramentas do conector com `ToolSearch` (`skalo`). Se não houver nenhuma,
pule este passo e registre em `notes`: "Conector Skalo.IA não disponível nesta leitura".

Se houver, explore o que elas oferecem e colete, para os clientes AEG, os indicadores
das últimas 24h e dos últimos 7 dias que existirem, por exemplo: leads recebidos,
conversas atendidas pela IA, tempo de resposta, visitas agendadas, vendas, clientes
sem uso ou com queda forte. Grave em `skalo`:

```json
{"period": "últimos 7 dias (até HOJE)",
 "headline": "1 frase com o principal resultado, ex.: 'Foram 1.240 leads, 8% a mais que na semana anterior.'",
 "kpis": [{"label": "Leads", "value": "1.240", "detail": "+8% vs semana anterior", "tone": "good|warn|bad|null"}],
 "alerts": [{"name": "Cliente", "info": "o problema, com número", "url": "link se houver"}],
 "top": [{"name": "Cliente", "info": "o destaque, com número", "url": null}]}
```

No máximo 8 `kpis`, 8 `alerts` e 5 `top`. Use só números que vieram do conector.
Ao cruzar com o ClickUp, prefira citar clientes ativos da carteira.

### 4c. Agenda da Wayslanne (Google Agenda)

Procure as ferramentas com `ToolSearch` (`calendar`). Se houver, liste os eventos de HOJE
(00:00–23:59, America/Sao_Paulo) da agenda principal, em ordem de horário, e grave:

```json
"agenda": {"date": "HOJE", "events": [{"start": "HH:MM", "end": "HH:MM", "title": "...",
  "location": "..." ou null, "url": "link do evento" ou null, "all_day": false}]}
```

Agenda sem eventos: `"events": []` (o Jarvis diz que a agenda está livre). Sem ferramentas
de agenda: não grave `agenda` e registre em `notes` "Google Agenda não disponível nesta leitura".
Só compromissos do Google Agenda; nada de tarefas do ClickUp aqui.

### 5. Radar de mercado (notícias do dia)

Use `WebSearch` (modo `extended`) com buscas em português sobre os últimos 7 dias, por exemplo:
- `seminovos usados vendas Fenauto <mês atual> <ano>`
- `emplacamentos Fenabrave <mês atual> <ano>`
- `Tabela Fipe <mês atual> <ano> carros usados preço`
- `financiamento de veículos usados B3 <ano>`
- `revenda de carros seminovos lojistas notícias`
- `carros chineses elétricos revenda desvalorização`

Escolha de 6 a 10 notícias relevantes para lojas de carros seminovos e para o mercado
automotivo no Brasil. Prefira as mais recentes e fontes conhecidas (Fenauto, Fenabrave,
B3, InfoMoney, Autoesporte, Valor, Estadão, O Tempo, Garagem360). Não repita notícias que
já estavam no snapshot anterior, a não ser que tragam dado novo. Para cada uma, grave em `news`:

```json
{"cat": "Seminovos | Mercado 0km | Preços & Fipe | Crédito | Tecnologia & Varejo",
 "date": "AAAA-MM-DD ou null se não souber",
 "source": "Veículo / fonte do dado",
 "url": "link da matéria",
 "title": "título fiel à matéria",
 "summary": "1–2 frases com os números principais, sem inventar",
 "impact": "1 frase: o que isso muda para os lojistas clientes da AEG (anúncios, estoque, Venda.IA, crédito)"}
```

Nunca invente número, data ou link: use só o que veio da busca. Se a busca falhar,
grave `"news": []` e registre em `notes`.

### 5b. Clima de Sanharó e Belo Jardim (PE)

As APIs de clima são bloqueadas neste ambiente, então use `WebSearch` (modo `extended`):
`previsão do tempo Sanharó PE hoje temperatura mínima máxima chuva` e o mesmo para
`Belo Jardim PE`. Grave em `weather`:

```json
{"date": "HOJE", "cities": [
  {"city": "Sanharó", "uf": "PE", "now": 19 ou null, "min": 18, "max": 28, "rain_prob": 37,
   "wind_kmh": 12 ou null, "humidity": "49–92%" ou null, "condition": "Nublado",
   "source": "Climatempo", "url": "link da previsão"},
  {"city": "Belo Jardim", ...}
]}
```

Só números que vieram da busca; o que não vier fica `null`. Se a busca falhar para
uma cidade, deixe-a fora da lista e registre em `notes`.

### 5c. Brasil e mundo (manchetes gerais)

`WebSearch` (modo `extended`) com `principais notícias do Brasil e do mundo hoje <data>`
e `notícias internacionais hoje <data>`. Escolha de 3 a 6 manchetes de fontes conhecidas
(Agência Brasil, g1, CNN Brasil, Folha, Estadão, BBC, Reuters, Euronews). Tom neutro em
política, sem opinião. Grave em `world`:

```json
{"cat": "Brasil | Mundo", "date": "AAAA-MM-DD ou null", "source": "veículo", "url": "link",
 "title": "manchete fiel", "summary": "1–2 frases factuais"}
```

### 6. Snapshot, painel e publicação

1. Grave `jarvis/data/snapshots/HOJE.json`:

   ```json
   {
     "date": "HOJE",
     "source": "ClickUp MCP (Operacional AEG)",
     "clients": [...],
     "no_meeting_15d": [...],
     "retention": {"open": {...}, "open_truncated": false, "closed_total": {"retido": 0, "perdido": 0}},
     "overdue_truncated": false,
     "overdue": [...],
     "news": [...],
     "skalo": {...},
     "agenda": {...},
     "weather": {...},
     "world": [...],
     "notes": []
   }
   ```

   `notes` é opcional: frases curtas com algo fora do padrão que você notou
   (ex.: "3 clientes novos entraram ontem sem CS"). Viram itens "Info" no topo.
2. Rode `python3 jarvis/build.py`. Ele compara com o snapshot anterior e gera
   `jarvis/out/jarvis.html`.
3. Leia o artifact (`Artifact` com `action: "read"` e a URL acima) e publique
   `jarvis/out/jarvis.html` com `url` = a URL acima e
   `files` = `{"jarvis/data/snapshots/HOJE.json": "jarvis/data/snapshots/HOJE.json"}`
   (mais qualquer arquivo de código que tenha mudado). Não crie um artifact novo.
4. Se o repositório estiver disponível, também faça `git add jarvis/data/snapshots/HOJE.json`,
   commit e `git push -u origin claude/jarvis-aeg-operational-dashboard-f76c5x`.
   Se o push falhar, siga em frente: o histórico já está salvo no artifact.
5. Responda com um resumo de 4 a 6 linhas em português: os números do dia,
   o que mudou desde a última leitura e as 3 prioridades. Termine com o link do painel.

## Se algo falhar

- Conector ClickUp indisponível: não invente dados. Responda dizendo que a
  leitura de hoje não rodou e por quê; o painel continua com a última leitura.
- Um passo isolado falhou (ex.: retenção): grave o snapshot sem aquela chave e
  registre o motivo em `notes`.
