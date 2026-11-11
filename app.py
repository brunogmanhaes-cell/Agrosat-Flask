"""
app.py - Servidor web do AgroSat (Flask).

Renderiza templates/index.html e expõe uma API JSON que o static/js/app.js usa.
Rode com:  python app.py   e abra http://127.0.0.1:5000
"""

from flask import Flask, jsonify, render_template, request

import banco
import recomendacao

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def _plantacao_json(p):
    """Converte uma linha do banco em JSON simples (números como float)."""
    return {
        "id_plantacao": p["id_plantacao"],
        "produtor": p.get("produtor"),
        "nome_fazenda": p["nome_fazenda"],
        "latitude": float(p["latitude"]),
        "longitude": float(p["longitude"]),
        "tipo_solo": p["tipo_solo"],
    }


def _ler_campos(dados, exige_produtor):
    """Valida o corpo da requisição. Levanta ValueError com mensagem clara."""
    produtor = str(dados.get("produtor", "")).strip()
    fazenda = str(dados.get("nome_fazenda", "")).strip()
    if exige_produtor and not produtor:
        raise ValueError("Informe o nome do produtor.")
    if not fazenda:
        raise ValueError("Informe o nome da fazenda.")
    try:
        lat = float(str(dados.get("latitude", "")).replace(",", "."))
        lon = float(str(dados.get("longitude", "")).replace(",", "."))
    except ValueError:
        raise ValueError("Latitude e longitude devem ser números.")
    if not -90 <= lat <= 90:
        raise ValueError("A latitude deve estar entre -90 e 90.")
    if not -180 <= lon <= 180:
        raise ValueError("A longitude deve estar entre -180 e 180.")
    return produtor, fazenda, lat, lon


def _id_do_produtor(nome):
    """Reaproveita o usuário com esse nome ou cria um novo."""
    for usuario in banco.listar_usuarios():
        if usuario["nome"].lower() == nome.lower():
            return usuario["id_usuario"]
    return banco.criar_usuario(nome)


def _erro(mensagem, codigo):
    return jsonify({"erro": mensagem}), codigo


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

@app.get("/")
def pagina_inicial():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/plantacoes")
def api_listar():
    return jsonify([_plantacao_json(p) for p in banco.listar_todas_plantacoes()])


@app.post("/api/plantacoes")
def api_criar():
    try:
        produtor, fazenda, lat, lon = _ler_campos(request.get_json(silent=True) or {}, True)
    except ValueError as erro:
        return _erro(str(erro), 400)
    id_usuario = _id_do_produtor(produtor)
    id_plantacao = banco.criar_plantacao(id_usuario, fazenda, lat, lon)
    return jsonify({"id_plantacao": id_plantacao}), 201


@app.put("/api/plantacoes/<int:id_plantacao>")
def api_atualizar(id_plantacao):
    atual = banco.buscar_plantacao(id_plantacao)
    if atual is None:
        return _erro("Plantação não encontrada.", 404)
    try:
        _, fazenda, lat, lon = _ler_campos(request.get_json(silent=True) or {}, False)
    except ValueError as erro:
        return _erro(str(erro), 400)
    local_mudou = (lat, lon) != (float(atual["latitude"]), float(atual["longitude"]))
    banco.atualizar_plantacao(id_plantacao, fazenda, lat, lon)
    if local_mudou:  # o solo salvo deixa de valer; será identificado de novo
        banco.limpar_solo(id_plantacao)
    return jsonify({"ok": True, "solo_reiniciado": local_mudou})


@app.delete("/api/plantacoes/<int:id_plantacao>")
def api_deletar(id_plantacao):
    banco.deletar_plantacao(id_plantacao)
    return jsonify({"ok": True})


@app.post("/api/plantacoes/<int:id_plantacao>/recomendacao")
def api_recomendar(id_plantacao):
    try:
        return jsonify(recomendacao.gerar_para_plantacao(id_plantacao))
    except LookupError as erro:
        return _erro(str(erro), 404)
    except RuntimeError as erro:  # falha de SoilGrids ou Open-Meteo
        return _erro(str(erro), 502)


@app.get("/api/plantacoes/<int:id_plantacao>/historico")
def api_historico(id_plantacao):
    itens = banco.listar_recomendacoes(id_plantacao)
    return jsonify({
        "itens": [{"data_hora": i["data_hora"].isoformat(), "decisao": i["decisao"],
                   "justificativa": i["justificativa"]} for i in itens],
        "contagem": banco.contar_decisoes(id_plantacao),
    })


@app.errorhandler(Exception)
def erro_inesperado(erro):
    if hasattr(erro, "code") and isinstance(erro.code, int):  # 404, 405 etc.
        return _erro(getattr(erro, "description", "Erro."), erro.code)
    return _erro("Algo deu errado no servidor. Tente novamente.", 500)


if __name__ == "__main__":
    try:
        banco.iniciar_banco()
    except RuntimeError as erro:
        raise SystemExit(f"[ERRO] {erro}")
    except Exception as erro:
        raise SystemExit(f"[ERRO] Não foi possível conectar ao Oracle: {erro}")
    app.run(debug=False)
