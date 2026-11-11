# Agrosat-Python-RenderHtml

AgroSat com interface web: o Python (Flask) renderiza o HTML e expõe a API; CSS e JS ficam em arquivos separados.

```
app.py              rotas Flask (renderiza o HTML e a API JSON)
recomendacao.py     motor de decisão (sem input/print)
api_clima.py        Open-Meteo
api_solo.py         SoilGrids
banco.py            Oracle
templates/index.html
static/css/style.css
static/js/app.js
```

## Como rodar
1. `pip install -r requirements.txt`
2. Copie `.env.example` para `.env` e preencha as credenciais do Oracle
3. Rode `criar_tabelas.sql` no Oracle (uma vez)
4. `python app.py` e abra http://127.0.0.1:5000
