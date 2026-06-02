import mysql.connector
from mysql.connector import Error
from datetime import datetime


# =====================================================
# CONFIGURAÇÃO MYSQL
# =====================================================

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "orcai"
}


# =====================================================
# CONEXÃO
# =====================================================

def conectar():

    try:

        conexao = mysql.connector.connect(
            **DB_CONFIG
        )

        return conexao

    except Error as erro:

        print(
            f"Erro ao conectar MySQL: {erro}"
        )

        return None


# =====================================================
# CRIAR TABELAS
# =====================================================

def criar_tabelas():

    conexao = conectar()

    if not conexao:
        return

    cursor = conexao.cursor()

    # ==========================
    # EMPRESAS
    # ==========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas (

            id INT AUTO_INCREMENT PRIMARY KEY,

            telegram_id BIGINT,

            responsavel VARCHAR(255),

            empresa VARCHAR(255),

            cnpj VARCHAR(30),

            telefone VARCHAR(30),

            email VARCHAR(255),

            endereco TEXT,

            criado_em TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # ==========================
    # SERVIÇOS
    # ==========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS servicos (

            id INT AUTO_INCREMENT PRIMARY KEY,

            empresa_id INT,

            nome VARCHAR(255),

            valor DECIMAL(10,2),

            criado_em TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (empresa_id)
            REFERENCES empresas(id)
            ON DELETE CASCADE

        )
    """)

    # ==========================
    # ORÇAMENTOS
    # ==========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (

            id INT AUTO_INCREMENT PRIMARY KEY,

            empresa_id INT,

            cliente VARCHAR(255),

            telefone_cliente VARCHAR(30),

            materiais_adicionais DECIMAL(10,2),

            observacao TEXT,

            pdf_path TEXT,

            criado_em TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (empresa_id)
            REFERENCES empresas(id)
            ON DELETE CASCADE

        )
    """)

    # ==========================
    # ITENS ORÇAMENTO
    # ==========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS itens_orcamento (

            id INT AUTO_INCREMENT PRIMARY KEY,

            orcamento_id INT,

            servico VARCHAR(255),

            quantidade INT,

            valor_unitario DECIMAL(10,2),

            valor_total DECIMAL(10,2),

            FOREIGN KEY (orcamento_id)
            REFERENCES orcamentos(id)
            ON DELETE CASCADE

        )
    """)

    conexao.commit()

    cursor.close()

    conexao.close()

    print(
        "Tabelas criadas com sucesso ✅"
    )


# =====================================================
# SALVAR EMPRESA
# =====================================================

def salvar_empresa(
    telegram_id,
    responsavel,
    empresa,
    cnpj,
    telefone,
    email,
    endereco
):

    conexao = conectar()

    if not conexao:
        return None

    cursor = conexao.cursor()

    sql = """
        INSERT INTO empresas (

            telegram_id,
            responsavel,
            empresa,
            cnpj,
            telefone,
            email,
            endereco

        )

        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """

    valores = (
        telegram_id,
        responsavel,
        empresa,
        cnpj,
        telefone,
        email,
        endereco
    )

    cursor.execute(
        sql,
        valores
    )

    conexao.commit()

    empresa_id = cursor.lastrowid

    cursor.close()

    conexao.close()

    return empresa_id


# =====================================================
# BUSCAR EMPRESA
# =====================================================

def buscar_empresa_por_telegram(
    telegram_id
):

    conexao = conectar()

    if not conexao:
        return None

    cursor = conexao.cursor(
        dictionary=True
    )

    sql = """
        SELECT *
        FROM empresas
        WHERE telegram_id = %s
        LIMIT 1
    """

    cursor.execute(
        sql,
        (telegram_id,)
    )

    empresa = cursor.fetchone()

    cursor.close()

    conexao.close()

    return empresa


# =====================================================
# SALVAR SERVIÇOS
# =====================================================

def salvar_servicos(
    empresa_id,
    tabela_servicos
):

    conexao = conectar()

    if not conexao:
        return

    cursor = conexao.cursor()

    for chave, servico in (
        tabela_servicos.items()
    ):

        sql = """
            INSERT INTO servicos (

                empresa_id,
                nome,
                valor

            )

            VALUES (%s,%s,%s)
        """

        valores = (
            empresa_id,
            servico["nome"],
            servico["valor"]
        )

        cursor.execute(
            sql,
            valores
        )

    conexao.commit()

    cursor.close()

    conexao.close()


# =====================================================
# BUSCAR SERVIÇOS
# =====================================================

def buscar_servicos_empresa(
    empresa_id
):

    conexao = conectar()

    if not conexao:
        return {}

    cursor = conexao.cursor(
        dictionary=True
    )

    sql = """
        SELECT *
        FROM servicos
        WHERE empresa_id = %s
    """

    cursor.execute(
        sql,
        (empresa_id,)
    )

    resultados = cursor.fetchall()

    cursor.close()

    conexao.close()

    servicos = {}

    for item in resultados:

        chave = (
            item["nome"]
            .lower()
            .strip()
        )

        servicos[chave] = {
            "nome": item["nome"],
            "valor": float(
                item["valor"]
            )
        }

    return servicos


# =====================================================
# SALVAR ORÇAMENTO
# =====================================================

def salvar_orcamento(
    empresa_id,
    dados_orc,
    tabela_servicos,
    pdf_path=None
):

    conexao = conectar()

    if not conexao:
        return None

    cursor = conexao.cursor()

    sql = """
        INSERT INTO orcamentos (

            empresa_id,
            cliente,
            telefone_cliente,
            materiais_adicionais,
            observacao,
            pdf_path

        )

        VALUES (%s,%s,%s,%s,%s,%s)
    """

    valores = (

        empresa_id,

        dados_orc.get(
            "cliente"
        ),

        dados_orc.get(
            "telefone_cliente"
        ),

        dados_orc.get(
            "materiais_adicionais",
            0
        ),

        dados_orc.get(
            "observacao",
            ""
        ),

        pdf_path

    )

    cursor.execute(
        sql,
        valores
    )

    conexao.commit()

    orcamento_id = (
        cursor.lastrowid
    )

    # ==========================
    # ITENS
    # ==========================

    for item in dados_orc.get(
        "itens",
        []
    ):

        nome_servico = item.get(
            "servico"
        )

        quantidade = item.get(
            "quantidade",
            1
        )

        valor_unitario = 0

        for _, servico_db in (
            tabela_servicos.items()
        ):

            if (
                servico_db["nome"]
                .lower()
                ==
                nome_servico.lower()
            ):

                valor_unitario = (
                    servico_db["valor"]
                )

                break

        valor_total = (
            valor_unitario
            * quantidade
        )

        sql_item = """
            INSERT INTO itens_orcamento (

                orcamento_id,
                servico,
                quantidade,
                valor_unitario,
                valor_total

            )

            VALUES (%s,%s,%s,%s,%s)
        """

        valores_item = (

            orcamento_id,

            nome_servico,

            quantidade,

            valor_unitario,

            valor_total

        )

        cursor.execute(
            sql_item,
            valores_item
        )

    conexao.commit()

    cursor.close()

    conexao.close()

    return orcamento_id


# =====================================================
# HISTÓRICO ORÇAMENTOS
# =====================================================

def listar_orcamentos_empresa(
    empresa_id
):

    conexao = conectar()

    if not conexao:
        return []

    cursor = conexao.cursor(
        dictionary=True
    )

    sql = """
        SELECT *
        FROM orcamentos
        WHERE empresa_id = %s
        ORDER BY criado_em DESC
    """

    cursor.execute(
        sql,
        (empresa_id,)
    )

    resultados = cursor.fetchall()

    cursor.close()

    conexao.close()

    return resultados


# =====================================================
# TESTE LOCAL
# =====================================================

if __name__ == "__main__":

    criar_tabelas()