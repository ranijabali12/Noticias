# Notícias do dia

Todo dia às 7:30, o GitHub roda `noticias.py` de graça. O script lê os feeds públicos de 12 veículos, escolhe as 15 notícias mais cobertas e publica uma página e um arquivo para o widget. Não usa chave de API nem IA.

## Como funciona

- **Principais**: uma notícia sobe no ranking quanto mais veículos de linhas editoriais diferentes a publicaram.
- **Imparcialidade**: o título escolhido é o mais parecido com os dos outros veículos, sem exclamação ou pergunta. O resumo usa só as frases com os fatos que se repetem entre eles, descartando termos opinativos. Cada notícia mostra quais veículos a publicaram.
- **Sem repetição**: `historico.json` guarda 60 dias do que já saiu. Uma matéria já mostrada nunca volta. Um fato novo sobre um caso antigo aparece marcado como "Atualização do caso de dd/mm".

## Instalação (uma vez, uns 10 minutos)

1. Crie uma conta em github.com e um repositório **público** novo, por exemplo `noticias`.
2. Envie todos os arquivos desta pasta, incluindo a pasta oculta `.github`. Pelo site: "Add file" > "Upload files" e arraste a pasta inteira.
3. Em **Settings > Pages**, escolha "Deploy from a branch", branch `main`, pasta `/docs`, e salve.
4. Em **Actions**, abra "Notícias do dia" e clique em "Run workflow" para gerar a primeira edição.
5. Em um ou dois minutos a página estará em `https://SEU-USUARIO.github.io/noticias/`.

Daí em diante ela se atualiza sozinha às 7:30. O GitHub às vezes atrasa execuções agendadas em alguns minutos.

## Widget no Android

O jeito mais simples é um widget de atalho: no Chrome, abra a página, toque nos três pontos e em "Adicionar à tela inicial".

Para ver as manchetes direto na tela inicial, use o app **KWGT** (Play Store):

1. Segure na tela inicial > Widgets > KWGT, e adicione um widget 4x4.
2. Toque nele para editar e adicione um item de texto.
3. No texto, use a fórmula abaixo trocando o endereço:
   `$wg("https://SEU-USUARIO.github.io/noticias/widget.json", json, ".itens[0].t")$`
4. Repita para mais linhas trocando `[0]` por `[1]`, `[2]`... Para o número de veículos, use `.itens[0].f`. Para a data da edição, use `.edicao`.
5. Em "Touch" do widget, escolha "Abrir link" com o endereço da página.

O KWGT atualiza o widget sozinho. Algumas funções do app pedem a versão Pro paga.

## Ajustes

Em `noticias.py`:
- `FEEDS`: adicione ou troque veículos. Se um feed sair do ar, ele é ignorado e a página avisa.
- `QTD`: quantidade de notícias.
- Para mudar o horário, edite `cron` em `.github/workflows/noticias.yml` (o horário é em UTC, 3 horas à frente de Brasília).
