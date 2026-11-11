"""
api_clima.py - Previsão de chuva e umidade do solo (Open-Meteo Forecast API).

Uma única requisição traz:
  - chuva prevista para os próximos 3 dias (mm e probabilidade);
  - umidade do solo por camada, de 0 a 81 cm, em m³/m³.

Este módulo só busca e organiza os dados; a decisão fica em recomendacao.py.
"""

from datetime import datetime, timedelta, timezone

import requests

URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"

# Camadas de umidade do solo do Open-Meteo e sua espessura em cm.
# A espessura é usada como peso na média (camadas mais profundas pesam mais,
# pois representam melhor a zona das raízes).
CAMADAS_UMIDADE = (
    ("soil_moisture_0_to_1cm", 1),
    ("soil_moisture_1_to_3cm", 2),
    ("soil_moisture_3_to_9cm", 6),
    ("soil_moisture_9_to_27cm", 18),
    ("soil_moisture_27_to_81cm", 54),
)


def _indice_hora_atual(dados):
    """Encontra, na lista de horas da previsão, a posição da hora atual local."""
    deslocamento = dados.get("utc_offset_seconds", 0)
    agora_local = datetime.now(timezone.utc) + timedelta(seconds=deslocamento)
    chave = agora_local.strftime("%Y-%m-%dT%H:00")
    horas = dados["hourly"]["time"]
    return horas.index(chave) if chave in horas else 0


def _umidade_media(dados, indice):
    """Média da umidade do solo (0-81 cm) ponderada pela espessura das camadas."""
    soma, peso_total = 0.0, 0
    for nome, espessura in CAMADAS_UMIDADE:
        valores = dados["hourly"].get(nome) or []
        if indice < len(valores) and valores[indice] is not None:
            soma += valores[indice] * espessura
            peso_total += espessura
    if peso_total == 0:
        raise RuntimeError("O Open-Meteo não tem dados de umidade do solo "
                           "para esta localização.")
    return soma / peso_total


def buscar_clima(latitude, longitude):
    """
    Consulta o Open-Meteo e devolve um dicionário com:
      "umidade_solo": umidade média atual de 0 a 81 cm (m³/m³)
      "chuva_total_mm": chuva acumulada prevista nos 3 dias
      "prob_max": maior probabilidade de chuva entre os 3 dias (%)
      "previsao_diaria": lista de {"data", "chuva_mm", "prob"} (um por dia)
    Levanta RuntimeError com mensagem clara se algo der errado.
    """
    parametros = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(nome for nome, _ in CAMADAS_UMIDADE),
        "daily": "precipitation_sum,precipitation_probability_max",
        "forecast_days": 3,
        "timezone": "auto",
    }
    try:
        resposta = requests.get(URL_PREVISAO, params=parametros, timeout=20)
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.exceptions.Timeout:
        raise RuntimeError("O Open-Meteo demorou demais para responder. "
                           "Tente novamente em alguns instantes.")
    except (requests.exceptions.RequestException, ValueError):
        raise RuntimeError("Não foi possível obter a previsão do Open-Meteo "
                           "(serviço indisponível ou sem internet).")

    if "hourly" not in dados or "daily" not in dados:
        raise RuntimeError("Resposta inesperada do Open-Meteo.")

    umidade = _umidade_media(dados, _indice_hora_atual(dados))

    previsao = []
    diario = dados["daily"]
    for i, data in enumerate(diario["time"]):
        chuva = diario["precipitation_sum"][i]
        prob = diario["precipitation_probability_max"][i]
        previsao.append({
            "data": data,
            "chuva_mm": chuva if chuva is not None else 0.0,
            "prob": prob if prob is not None else 0,
        })

    return {
        "umidade_solo": umidade,
        "chuva_total_mm": sum(dia["chuva_mm"] for dia in previsao),
        "prob_max": max(dia["prob"] for dia in previsao),
        "previsao_diaria": previsao,
    }
