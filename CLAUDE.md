# Jarvis AEG

Painel matinal da operação AEG (espaço "Operacional AEG" no ClickUp).

- Quando pedirem para "rodar o Jarvis", "atualizar o painel" ou a leitura do dia,
  siga `jarvis/JARVIS.md` passo a passo.
- `jarvis/build.py` só usa a biblioteca padrão do Python; não precisa instalar nada.
- `jarvis/out/` é gerado e não é versionado. Os snapshots em `jarvis/data/snapshots/`
  são versionados: eles formam o histórico usado nas comparações dia a dia.
- Textos do painel e respostas ao usuário em português do Brasil.
