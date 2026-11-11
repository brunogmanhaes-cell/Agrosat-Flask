"""
banco.py - Acesso ao banco de dados Oracle.

Concentra a conexão e todas as operações de leitura/gravação, para que os
outros módulos não precisem conhecer SQL. As tabelas devem ser criadas
previamente no Oracle com o script criar_tabelas.sql.

As credenciais NÃO ficam neste arquivo: são lidas do arquivo .env (que não vai
para o GitHub). Use o .env.example como modelo.
"""

import os
from pathlib import Path

import oracledb

# O .env fica na mesma pasta deste arquivo, não importa de onde o programa rode
ARQUIVO_ENV = Path(__file__).parent / ".env"

# Conexão única, compartilhada por todas as funções do módulo
_conexao = None


# ---------------------------------------------------------------------------
# Credenciais e conexão
# ---------------------------------------------------------------------------

def carregar_env():
    """
    Lê o arquivo .env (linhas CHAVE=valor) e coloca os valores nas variáveis de
    ambiente. Variáveis que já existem no sistema têm prioridade.
    """
    if not ARQUIVO_ENV.exists():
        return
    for linha in ARQUIVO_ENV.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def iniciar_banco():
    """Abre a conexão com o Oracle usando as credenciais do .env."""
    global _conexao
    carregar_env()

    usuario = os.getenv("ORACLE_USER")
    senha = os.getenv("ORACLE_PASSWORD")
    dsn = os.getenv("ORACLE_DSN", "oracle.fiap.com.br:1521/ORCL")

    if not usuario or not senha:
        raise RuntimeError("Credenciais do banco não configuradas. "
                           "Crie o arquivo .env a partir do .env.example.")

    _conexao = oracledb.connect(user=usuario, password=senha, dsn=dsn)


def fechar_conexao():
    """Fecha a conexão, se estiver aberta."""
    global _conexao
    if _conexao is not None:
        _conexao.close()
        _conexao = None


# ---------------------------------------------------------------------------
# Funções auxiliares internas
# ---------------------------------------------------------------------------

def _consultar(sql, parametros=None):
    """Executa um SELECT e devolve uma lista de dicionários (uma por linha)."""
    with _conexao.cursor() as cursor:
        cursor.execute(sql, parametros or {})
        colunas = [coluna[0].lower() for coluna in cursor.description]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def _executar(sql, parametros=None):
    """Executa INSERT/UPDATE/DELETE e confirma a transação."""
    with _conexao.cursor() as cursor:
        cursor.execute(sql, parametros or {})
    _conexao.commit()


def _inserir_retornando_id(sql, parametros):
    """Executa um INSERT que devolve o id gerado (coluna identity)."""
    with _conexao.cursor() as cursor:
        id_gerado = cursor.var(int)
        parametros = dict(parametros, id_gerado=id_gerado)
        cursor.execute(sql, parametros)
        valor = id_gerado.getvalue()
    _conexao.commit()
    return valor[0] if isinstance(valor, list) else valor


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------

def criar_usuario(nome):
    """Insere um usuário e devolve o id gerado."""
    sql = ("INSERT INTO usuario (nome) VALUES (:nome) "
           "RETURNING id_usuario INTO :id_gerado")
    return _inserir_retornando_id(sql, {"nome": nome})


def listar_usuarios():
    """Devolve todos os usuários, ordenados por id."""
    return _consultar("SELECT id_usuario, nome FROM usuario ORDER BY id_usuario")


def buscar_usuario(id_usuario):
    """Devolve o usuário (dict) ou None se não existir."""
    resultado = _consultar(
        "SELECT id_usuario, nome FROM usuario WHERE id_usuario = :id",
        {"id": id_usuario})
    return resultado[0] if resultado else None


def atualizar_usuario(id_usuario, nome):
    """Altera o nome do usuário."""
    _executar("UPDATE usuario SET nome = :nome WHERE id_usuario = :id",
              {"nome": nome, "id": id_usuario})


def deletar_usuario(id_usuario):
    """Remove o usuário (as plantações e recomendações são removidas junto)."""
    _executar("DELETE FROM usuario WHERE id_usuario = :id", {"id": id_usuario})


# ---------------------------------------------------------------------------
# Plantações
# ---------------------------------------------------------------------------

def criar_plantacao(id_usuario, nome_fazenda, latitude, longitude):
    """Insere uma plantação (solo ainda não identificado) e devolve o id."""
    sql = ("INSERT INTO plantacao (id_usuario, nome_fazenda, latitude, longitude) "
           "VALUES (:id_usuario, :nome_fazenda, :latitude, :longitude) "
           "RETURNING id_plantacao INTO :id_gerado")
    return _inserir_retornando_id(sql, {
        "id_usuario": id_usuario, "nome_fazenda": nome_fazenda,
        "latitude": latitude, "longitude": longitude})


def listar_plantacoes(id_usuario):
    """Devolve as plantações de um usuário."""
    return _consultar(
        "SELECT * FROM plantacao WHERE id_usuario = :id ORDER BY id_plantacao",
        {"id": id_usuario})


def buscar_plantacao(id_plantacao):
    """Devolve a plantação (dict) ou None se não existir."""
    resultado = _consultar(
        "SELECT * FROM plantacao WHERE id_plantacao = :id",
        {"id": id_plantacao})
    return resultado[0] if resultado else None


def atualizar_plantacao(id_plantacao, nome_fazenda, latitude, longitude):
    """Altera nome e localização da plantação (não mexe nos dados do solo)."""
    _executar(
        "UPDATE plantacao SET nome_fazenda = :nome_fazenda, "
        "latitude = :latitude, longitude = :longitude "
        "WHERE id_plantacao = :id",
        {"nome_fazenda": nome_fazenda, "latitude": latitude,
         "longitude": longitude, "id": id_plantacao})


def deletar_plantacao(id_plantacao):
    """Remove a plantação e seu histórico de recomendações."""
    _executar("DELETE FROM plantacao WHERE id_plantacao = :id",
              {"id": id_plantacao})


def gravar_solo(id_plantacao, tipo_solo, capacidade_campo, ponto_murcha):
    """Grava o tipo de solo e a retenção de água na plantação."""
    _executar(
        "UPDATE plantacao SET tipo_solo = :tipo, "
        "capacidade_campo = :cc, ponto_murcha = :pmp "
        "WHERE id_plantacao = :id",
        {"tipo": tipo_solo, "cc": capacidade_campo,
         "pmp": ponto_murcha, "id": id_plantacao})


def limpar_solo(id_plantacao):
    """Apaga os dados de solo (usado quando a localização muda)."""
    _executar(
        "UPDATE plantacao SET tipo_solo = NULL, capacidade_campo = NULL, "
        "ponto_murcha = NULL WHERE id_plantacao = :id",
        {"id": id_plantacao})


# ---------------------------------------------------------------------------
# Recomendações (histórico)
# ---------------------------------------------------------------------------

def gravar_recomendacao(id_plantacao, decisao, justificativa):
    """Guarda uma recomendação gerada no histórico."""
    _executar(
        "INSERT INTO recomendacao (id_plantacao, decisao, justificativa) "
        "VALUES (:id, :decisao, :justificativa)",
        {"id": id_plantacao, "decisao": decisao,
         "justificativa": justificativa[:500]})


def listar_recomendacoes(id_plantacao, limite=10):
    """Devolve as recomendações mais recentes de uma plantação."""
    return _consultar(
        "SELECT data_hora, decisao, justificativa FROM recomendacao "
        "WHERE id_plantacao = :id ORDER BY data_hora DESC, id_recomendacao DESC "
        "FETCH FIRST :limite ROWS ONLY",
        {"id": id_plantacao, "limite": limite})


def contar_decisoes(id_plantacao):
    """Devolve um dicionário {decisao: quantidade} do histórico da plantação."""
    linhas = _consultar(
        "SELECT decisao, COUNT(*) AS total FROM recomendacao "
        "WHERE id_plantacao = :id GROUP BY decisao",
        {"id": id_plantacao})
    return {linha["decisao"]: linha["total"] for linha in linhas}


# ---------------------------------------------------------------------------
# Consulta usada pela interface web
# ---------------------------------------------------------------------------

def listar_todas_plantacoes():
    """Devolve todas as plantações, já com o nome do produtor (usuário)."""
    return _consultar(
        "SELECT p.*, u.nome AS produtor FROM plantacao p "
        "JOIN usuario u ON u.id_usuario = p.id_usuario "
        "ORDER BY p.id_plantacao")
