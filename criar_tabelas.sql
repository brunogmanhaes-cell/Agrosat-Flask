-- Esquema deduzido do banco.py. Ajuste se o seu for diferente.
CREATE TABLE usuario (
  id_usuario NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nome VARCHAR2(100) NOT NULL);

CREATE TABLE plantacao (
  id_plantacao NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_usuario NUMBER NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  nome_fazenda VARCHAR2(100) NOT NULL,
  latitude NUMBER(9,6) NOT NULL,
  longitude NUMBER(9,6) NOT NULL,
  tipo_solo VARCHAR2(40),
  capacidade_campo NUMBER(5,3),
  ponto_murcha NUMBER(5,3));

CREATE TABLE recomendacao (
  id_recomendacao NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_plantacao NUMBER NOT NULL REFERENCES plantacao(id_plantacao) ON DELETE CASCADE,
  data_hora TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  decisao VARCHAR2(20) NOT NULL,
  justificativa VARCHAR2(500));
