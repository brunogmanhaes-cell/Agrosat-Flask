"""
recomendacao.py - Motor de decisão de irrigação do AgroSat.

Cruza solo (SoilGrids), umidade atual e chuva prevista (Open-Meteo) e devolve
REGAR, NÃO REGAR ou AGUARDAR com uma justificativa. Versão web: não usa
input() nem print(); quem chama (app.py) recebe um dicionário.
"""

import api_clima
import api_solo
import banco

# Água disponível no solo (%): 0% = ponto de murcha, 100% = capacidade de campo
LIMITE_SOLO_SECO = 35.0
LIMITE_SOLO_UMIDO = 60.0

# Chuva prevista nos 3 dias: (mm acumulados, probabilidade máxima em %)
CHUVA_FORTE = (10.0, 60)
CHUVA_MODERADA = (5.0, 40)


def calcular_agua_disponivel(umidade, capacidade_campo, ponto_murcha):
    """Converte a umidade (m³/m³) em % de água disponível para a planta."""
    faixa = capacidade_campo - ponto_murcha
    if faixa <= 0:
        return 0.0
    percentual = (umidade - ponto_murcha) / faixa * 100
    return max(0.0, min(100.0, percentual))


def classificar_chuva(chuva_total_mm, prob_max):
    """Classifica a chuva prevista como 'forte', 'moderada' ou 'fraca'."""
    if chuva_total_mm >= CHUVA_FORTE[0] and prob_max >= CHUVA_FORTE[1]:
        return "forte"
    elif chuva_total_mm >= CHUVA_MODERADA[0] and prob_max >= CHUVA_MODERADA[1]:
        return "moderada"
    return "fraca"


def decidir(agua_disponivel, chuva_total_mm, prob_max):
    """Regra de decisão. Devolve (decisao, justificativa)."""
    chuva = classificar_chuva(chuva_total_mm, prob_max)
    resumo = (f"chuva prevista de {chuva_total_mm:.1f} mm em 3 dias "
              f"(probabilidade máxima {prob_max}%)")
    a = f"{agua_disponivel:.0f}"

    if agua_disponivel >= LIMITE_SOLO_UMIDO:
        return "NÃO REGAR", (f"O solo está bem abastecido ({a}% da água disponível) "
                             f"e há {resumo}. Regar agora desperdiçaria água.")
    if agua_disponivel >= LIMITE_SOLO_SECO:
        if chuva in ("forte", "moderada"):
            return "NÃO REGAR", (f"O solo está em nível de atenção ({a}%), mas há "
                                 f"{resumo}, o que deve repor a umidade.")
        return "AGUARDAR", (f"O solo está em nível de atenção ({a}%) e a {resumo} "
                            f"é fraca. Reavalie em 24 horas.")
    if chuva == "forte":
        return "NÃO REGAR", (f"O solo está seco ({a}%), mas há {resumo}. A chuva "
                             f"deve resolver sem gastar água de irrigação.")
    if chuva == "moderada":
        return "AGUARDAR", (f"O solo está seco ({a}%) e há {resumo}. Aguarde a "
                            f"chuva e reavalie em 24 horas.")
    return "REGAR", (f"O solo está seco ({a}%) e a {resumo} não será suficiente. "
                     f"Recomenda-se irrigar.")


def montar_alertas(umidade, capacidade_campo, ponto_murcha, prob_max):
    """Reúne alertas extras em uma lista ordenada, sem repetições."""
    alertas = set()
    if umidade < ponto_murcha:
        alertas.add("Umidade abaixo do ponto de murcha: risco para a cultura.")
    if umidade > capacidade_campo:
        alertas.add("Solo acima da capacidade de campo: risco de encharcamento.")
    if prob_max >= 80:
        alertas.add("Alta probabilidade de chuva nos próximos dias.")
    return sorted(alertas)


def obter_solo(plantacao):
    """
    Devolve o solo da plantação como dicionário. Se ainda não foi identificado,
    consulta o SoilGrids e grava no banco (argila/areia/silte só vêm nesse caso).
    """
    if plantacao["tipo_solo"] is None:
        solo = api_solo.identificar_e_gravar_solo(
            plantacao["id_plantacao"], plantacao["latitude"], plantacao["longitude"])
        return {"tipo": solo["tipo_solo"], "capacidade_campo": solo["capacidade_campo"],
                "ponto_murcha": solo["ponto_murcha"], "argila": solo["argila"],
                "areia": solo["areia"], "silte": solo["silte"]}
    return {"tipo": plantacao["tipo_solo"],
            "capacidade_campo": float(plantacao["capacidade_campo"]),
            "ponto_murcha": float(plantacao["ponto_murcha"]),
            "argila": None, "areia": None, "silte": None}


def gerar_para_plantacao(id_plantacao):
    """
    Gera, grava no histórico e devolve a recomendação de uma plantação.
    Levanta LookupError se a plantação não existir e RuntimeError se uma
    API externa falhar (a mensagem já é amigável).
    """
    plantacao = banco.buscar_plantacao(id_plantacao)
    if plantacao is None:
        raise LookupError("Plantação não encontrada.")

    solo = obter_solo(plantacao)
    clima = api_clima.buscar_clima(plantacao["latitude"], plantacao["longitude"])

    cc, pmp = solo["capacidade_campo"], solo["ponto_murcha"]
    agua = calcular_agua_disponivel(clima["umidade_solo"], cc, pmp)
    decisao, motivo = decidir(agua, clima["chuva_total_mm"], clima["prob_max"])
    alertas = montar_alertas(clima["umidade_solo"], cc, pmp, clima["prob_max"])

    banco.gravar_recomendacao(id_plantacao, decisao, motivo)
    return {"decisao": decisao, "motivo": motivo, "alertas": alertas,
            "agua_disponivel": agua, "solo": solo, "clima": clima}
