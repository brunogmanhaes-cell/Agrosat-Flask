"""
api_solo.py - Identificação do solo a partir do SoilGrids (ISRIC).

Fluxo:
  1. busca argila, areia e silte da localização (média ponderada até ~81 cm,
     a mesma profundidade usada pela umidade do solo do Open-Meteo);
  2. classifica a textura do solo (triângulo textural do USDA);
  3. associa à classe a retenção de água (capacidade de campo e ponto de murcha);
  4. grava o resultado na tabela PLANTACAO.

A textura do solo não muda, por isso a busca é feita uma única vez por
plantação (e de novo apenas se a localização for alterada).
"""

import requests

import banco

URL_SOILGRIDS = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Propriedades pedidas ao SoilGrids (percentual de argila, areia e silte)
PROPRIEDADES = ("clay", "sand", "silt")

# Camadas do SoilGrids e espessura (cm) considerada em cada uma.
# A última camada (60-100 cm) conta só até 81 cm, para casar com o Open-Meteo.
ESPESSURAS_CM = {
    "0-5cm": 5,
    "5-15cm": 10,
    "15-30cm": 15,
    "30-60cm": 30,
    "60-100cm": 21,
}

# Retenção de água por classe de solo: (capacidade de campo, ponto de murcha),
# em m³/m³. São valores típicos de referência (aproximados), usados para
# estimar quanta água o solo segura e quanta fica disponível para a planta.
RETENCAO_POR_SOLO = {
    "Areia": (0.12, 0.05),
    "Areia franca": (0.14, 0.06),
    "Franco arenoso": (0.23, 0.10),
    "Franco": (0.31, 0.15),
    "Franco siltoso": (0.33, 0.13),
    "Silte": (0.31, 0.09),
    "Franco argilo-arenoso": (0.27, 0.17),
    "Franco argiloso": (0.36, 0.21),
    "Franco argilo-siltoso": (0.38, 0.22),
    "Argila arenosa": (0.36, 0.23),
    "Argila siltosa": (0.41, 0.27),
    "Argila": (0.42, 0.30),
}


def buscar_textura(latitude, longitude):
    """
    Consulta o SoilGrids e devolve a textura média do perfil (0-81 cm):
    {"argila": %, "areia": %, "silte": %}.
    Levanta RuntimeError com mensagem clara se algo der errado.
    """
    parametros = {
        "lat": latitude,
        "lon": longitude,
        "property": list(PROPRIEDADES),
        "depth": list(ESPESSURAS_CM),
        "value": "mean",
    }
    try:
        resposta = requests.get(URL_SOILGRIDS, params=parametros, timeout=60)
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.exceptions.Timeout:
        raise RuntimeError("O SoilGrids demorou demais para responder. "
                           "Tente novamente em alguns instantes.")
    except (requests.exceptions.RequestException, ValueError):
        raise RuntimeError("Não foi possível obter os dados do SoilGrids "
                           "(serviço indisponível ou sem internet).")

    medias = {}  # ex.: {"clay": 31.2, "sand": 40.1, "silt": 28.7}
    for camada in dados.get("properties", {}).get("layers", []):
        nome = camada.get("name")
        fator = (camada.get("unit_measure") or {}).get("d_factor") or 10
        soma, peso_total = 0.0, 0
        for profundidade in camada.get("depths", []):
            valor = (profundidade.get("values") or {}).get("mean")
            peso = ESPESSURAS_CM.get(profundidade.get("label"))
            if valor is None or peso is None:
                continue
            soma += (valor / fator) * peso  # g/kg -> % e ponderação
            peso_total += peso
        if peso_total > 0:
            medias[nome] = soma / peso_total

    if not all(propriedade in medias for propriedade in PROPRIEDADES):
        raise RuntimeError("O SoilGrids não tem dados de solo para esta "
                           "localização (confira a latitude e a longitude).")

    # Normaliza para somar 100%, corrigindo pequenos erros de arredondamento
    total = medias["clay"] + medias["sand"] + medias["silt"]
    return {
        "argila": medias["clay"] * 100 / total,
        "areia": medias["sand"] * 100 / total,
        "silte": medias["silt"] * 100 / total,
    }


def classificar_solo(argila, areia, silte):
    """Classifica a textura pelo triângulo textural do USDA (% de cada fração)."""
    if silte + 1.5 * argila < 15:
        return "Areia"
    elif silte + 1.5 * argila >= 15 and silte + 2 * argila < 30:
        return "Areia franca"
    elif ((7 <= argila < 20 and areia > 52 and silte + 2 * argila >= 30)
          or (argila < 7 and silte < 50 and silte + 2 * argila >= 30)):
        return "Franco arenoso"
    elif 7 <= argila < 27 and 28 <= silte < 50 and areia <= 52:
        return "Franco"
    elif ((silte >= 50 and 12 <= argila < 27)
          or (50 <= silte < 80 and argila < 12)):
        return "Franco siltoso"
    elif silte >= 80 and argila < 12:
        return "Silte"
    elif 20 <= argila < 35 and silte < 28 and areia > 45:
        return "Franco argilo-arenoso"
    elif 27 <= argila < 40 and 20 < areia <= 45:
        return "Franco argiloso"
    elif 27 <= argila < 40 and areia <= 20:
        return "Franco argilo-siltoso"
    elif argila >= 35 and areia > 45:
        return "Argila arenosa"
    elif argila >= 40 and silte >= 40:
        return "Argila siltosa"
    elif argila >= 40 and areia <= 45 and silte < 40:
        return "Argila"
    else:
        # Raros casos de fronteira entre classes: usa a mais próxima
        return "Franco"


def calcular_retencao(tipo_solo):
    """Devolve (capacidade_de_campo, ponto_de_murcha) da classe de solo."""
    return RETENCAO_POR_SOLO[tipo_solo]


def identificar_solo(latitude, longitude):
    """Busca a textura, classifica e calcula a retenção. Não grava nada."""
    textura = buscar_textura(latitude, longitude)
    tipo = classificar_solo(textura["argila"], textura["areia"], textura["silte"])
    capacidade_campo, ponto_murcha = calcular_retencao(tipo)
    return {
        "tipo_solo": tipo,
        "capacidade_campo": capacidade_campo,
        "ponto_murcha": ponto_murcha,
        "argila": textura["argila"],
        "areia": textura["areia"],
        "silte": textura["silte"],
    }


def salvar_solo(id_plantacao, solo):
    """Grava na tabela PLANTACAO o solo identificado."""
    banco.gravar_solo(id_plantacao, solo["tipo_solo"],
                      solo["capacidade_campo"], solo["ponto_murcha"])


def identificar_e_gravar_solo(id_plantacao, latitude, longitude):
    """Identifica o solo da plantação, grava no banco e devolve o resultado."""
    solo = identificar_solo(latitude, longitude)
    salvar_solo(id_plantacao, solo)
    return solo
