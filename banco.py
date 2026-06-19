import mysql.connector
from mysql.connector import Error


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "orcai"
}


def conectar():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as erro:
        print(f"Erro ao conectar MySQL: {erro}")
        return None


def coluna_existe(cursor, tabela, coluna):
    cursor.execute(f"SHOW COLUMNS FROM {tabela} LIKE %s", (coluna,))
    return cursor.fetchone() is not None


def criar_tabelas():
    conexao = conectar()

    if not conexao:
        return

    cursor = conexao.cursor()

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
            logo_path VARCHAR(255),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS servicos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            empresa_id INT,
            nome VARCHAR(255),
            valor DECIMAL(10,2),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id)
            REFERENCES empresas(id)
            ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            empresa_id INT,
            cliente VARCHAR(255),
            telefone_cliente VARCHAR(30),
            materiais_adicionais DECIMAL(10,2),
            observacao TEXT,
            pdf_path TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id)
            REFERENCES empresas(id)
            ON DELETE CASCADE
        )
    """)

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

    if not coluna_existe(cursor, "empresas", "logo_path"):
        cursor.execute("""
            ALTER TABLE empresas
            ADD COLUMN logo_path VARCHAR(255) NULL
        """)

    conexao.commit()
    cursor.close()
    conexao.close()

    print("Tabelas criadas/atualizadas com sucesso ✅")


def salvar_empresa(
    telegram_id,
    responsavel,
    empresa,
    cnpj,
    telefone,
    email,
    endereco,
    logo_path=None
):
    conexao = conectar()

    if not conexao:
        return None

    cursor = conexao.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id
        FROM empresas
        WHERE telegram_id = %s
        LIMIT 1
        """,
        (telegram_id,)
    )

    existente = cursor.fetchone()

    if existente:
        empresa_id = existente["id"]

        cursor.execute(
            """
            UPDATE empresas
            SET
                responsavel = %s,
                empresa = %s,
                cnpj = %s,
                telefone = %s,
                email = %s,
                endereco = %s,
                logo_path = COALESCE(%s, logo_path)
            WHERE id = %s
            """,
            (
                responsavel,
                empresa,
                cnpj,
                telefone,
                email,
                endereco,
                logo_path,
                empresa_id
            )
        )

    else:
        cursor.execute(
            """
            INSERT INTO empresas (
                telegram_id,
                responsavel,
                empresa,
                cnpj,
                telefone,
                email,
                endereco,
                logo_path
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                telegram_id,
                responsavel,
                empresa,
                cnpj,
                telefone,
                email,
                endereco,
                logo_path
            )
        )

        empresa_id = cursor.lastrowid

    conexao.commit()
    cursor.close()
    conexao.close()

    return empresa_id


def buscar_empresa_por_telegram(telegram_id):
    conexao = conectar()

    if not conexao:
        return None

    cursor = conexao.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM empresas
        WHERE telegram_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (telegram_id,)
    )

    empresa = cursor.fetchone()

    cursor.close()
    conexao.close()

    return empresa


def atualizar_logo_empresa(telegram_id, logo_path):
    conexao = conectar()

    if not conexao:
        return False

    cursor = conexao.cursor()

    cursor.execute(
        """
        UPDATE empresas
        SET logo_path = %s
        WHERE telegram_id = %s
        """,
        (
            logo_path,
            telegram_id
        )
    )

    conexao.commit()

    atualizado = cursor.rowcount > 0

    cursor.close()
    conexao.close()

    return atualizado


def salvar_servicos(empresa_id, tabela_servicos):
    conexao = conectar()

    if not conexao:
        return

    cursor = conexao.cursor()

    for chave, servico in tabela_servicos.items():
        cursor.execute(
            """
            INSERT INTO servicos (
                empresa_id,
                nome,
                valor
            )
            VALUES (%s,%s,%s)
            """,
            (
                empresa_id,
                servico["nome"],
                servico["valor"]
            )
        )

    conexao.commit()
    cursor.close()
    conexao.close()


def buscar_servicos_empresa(empresa_id):
    conexao = conectar()

    if not conexao:
        return {}

    cursor = conexao.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM servicos
        WHERE empresa_id = %s
        """,
        (empresa_id,)
    )

    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()

    servicos = {}

    for item in resultados:
        chave = item["nome"].lower().strip()

        servicos[chave] = {
            "nome": item["nome"],
            "valor": float(item["valor"])
        }

    return servicos


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

    cursor.execute(
        """
        INSERT INTO orcamentos (
            empresa_id,
            cliente,
            telefone_cliente,
            materiais_adicionais,
            observacao,
            pdf_path
        )
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (
            empresa_id,
            dados_orc.get("cliente"),
            dados_orc.get("telefone_cliente"),
            dados_orc.get("materiais_adicionais", 0),
            dados_orc.get("observacao", ""),
            pdf_path
        )
    )

    conexao.commit()

    orcamento_id = cursor.lastrowid

    for item in dados_orc.get("itens", []):
        nome_servico = item.get("servico") or "Serviço"
        quantidade = item.get("quantidade", 1) or 1

        valor_unitario = item.get("valor_unitario")

        if valor_unitario is None:
            valor_unitario = 0

            for _, servico_db in tabela_servicos.items():
                if servico_db["nome"].lower() == nome_servico.lower():
                    valor_unitario = servico_db["valor"]
                    break

        try:
            valor_unitario = float(valor_unitario)
        except Exception:
            valor_unitario = 0

        try:
            quantidade = int(quantidade)
        except Exception:
            quantidade = 1

        valor_total = valor_unitario * quantidade

        cursor.execute(
            """
            INSERT INTO itens_orcamento (
                orcamento_id,
                servico,
                quantidade,
                valor_unitario,
                valor_total
            )
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                orcamento_id,
                nome_servico,
                quantidade,
                valor_unitario,
                valor_total
            )
        )

    conexao.commit()
    cursor.close()
    conexao.close()

    return orcamento_id


def listar_orcamentos_empresa(empresa_id):
    conexao = conectar()

    if not conexao:
        return []

    cursor = conexao.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM orcamentos
        WHERE empresa_id = %s
        ORDER BY criado_em DESC
        """,
        (empresa_id,)
    )

    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()

    return resultados


if __name__ == "__main__":
    criar_tabelas()