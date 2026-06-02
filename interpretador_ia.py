import re
from difflib import get_close_matches


def normalizar_texto(texto):
    return (
        texto.lower()
        .strip()
        .replace("-", " ")
    )


def interpretar_cadastro(texto, tipo):

    texto = texto.strip()

    if tipo == "nome":

        texto = re.sub(
            r"(?i)^(ol[aá]|eu sou|meu nome é)\s*",
            "",
            texto
        )

        return texto.strip()

    if tipo == "empresa":

        texto = re.sub(
            r"(?i)^(nome da empresa é|minha empresa é)\s*",
            "",
            texto
        )

        return texto.strip()

    if tipo == "cnpj":
        return re.sub(r"\D", "", texto)

    if tipo == "telefone":
        return re.sub(r"\D", "", texto)

    if tipo == "email":
        return texto.strip()

    if tipo == "endereco":
        return texto.strip()

    return texto


def normalizar_dados_orcamento_ia(dados):

    if not dados:
        return {}

    if "cliente" not in dados:
        dados["cliente"] = ""

    if "telefone_cliente" not in dados:
        dados["telefone_cliente"] = ""

    if "itens" not in dados:
        dados["itens"] = []

    if "materiais_adicionais" not in dados:
        dados["materiais_adicionais"] = 0

    if "observacao" not in dados:
        dados["observacao"] = ""

    return dados


def corrigir_itens_orcamento(
    dados_orc,
    tabela_servicos=None
):

    if not tabela_servicos:
        return dados_orc

    itens_corrigidos = []

    for item in dados_orc.get(
        "itens",
        []
    ):

        nome = item.get(
            "servico",
            ""
        )

        quantidade = item.get(
            "quantidade",
            1
        )

        nome_normalizado = (
            normalizar_texto(nome)
        )

        chaves = list(
            tabela_servicos.keys()
        )

        similares = get_close_matches(
            nome_normalizado,
            chaves,
            n=1,
            cutoff=0.3
        )

        servico_final = nome

        if similares:

            chave = similares[0]

            servico_final = (
                tabela_servicos[chave]["nome"]
            )

        else:

            for chave in chaves:

                if (
                    nome_normalizado in chave
                    or chave.startswith(
                        nome_normalizado
                    )
                ):

                    servico_final = (
                        tabela_servicos[chave]["nome"]
                    )

                    break

        itens_corrigidos.append({
            "servico": servico_final,
            "quantidade": quantidade
        })

    dados_orc["itens"] = itens_corrigidos

    return dados_orc


def interpretar_mensagem(
    texto,
    tabela_servicos=None
):

    texto = texto.lower()

    cliente = ""
    telefone = ""
    materiais = 0
    observacao = ""
    itens = []

    telefone_match = re.search(
        r"(\d{10,11})",
        texto
    )

    if telefone_match:
        telefone = telefone_match.group(1)

    cliente_match = re.search(
        r"para\s+([a-zA-ZÀ-ÿ\s]+)",
        texto
    )

    if cliente_match:
        cliente = cliente_match.group(1).strip()

    material_match = re.search(
        r"material\s+(\d+)",
        texto
    )

    if material_match:
        materiais = float(
            material_match.group(1)
        )

    if tabela_servicos:

        for chave, servico in (
            tabela_servicos.items()
        ):

            nome = servico["nome"]

            nome_normalizado = (
                normalizar_texto(nome)
            )

            if nome_normalizado in texto:

                quantidade = 1

                padrao = (
                    rf"{re.escape(nome_normalizado)}\s+(\d+)"
                )

                match_qtd = re.search(
                    padrao,
                    texto
                )

                if match_qtd:
                    quantidade = int(
                        match_qtd.group(1)
                    )

                itens.append({
                    "servico": nome,
                    "quantidade": quantidade
                })

    return {
        "cliente": cliente,
        "telefone_cliente": telefone,
        "itens": itens,
        "materiais_adicionais": materiais,
        "observacao": observacao
    }