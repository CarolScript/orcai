from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def limpar_json(conteudo):
    if not conteudo:
        return ""

    conteudo = conteudo.strip()
    conteudo = re.sub(r"^json", "", conteudo, flags=re.IGNORECASE).strip()
    conteudo = re.sub(r"^", "", conteudo).strip()
    conteudo = re.sub(r"```$", "", conteudo).strip()

    return conteudo


def interpretar_orcamento_com_ia(texto, servicos_disponiveis=None, dados_emitente=None):
    lista_servicos = ""

    if servicos_disponiveis:
        lista_servicos = "\n".join(
            [f"- {s['nome']} | R$ {s.get('valor', '')}" for s in servicos_disponiveis.values()]
        )

    if dados_emitente is None:
        dados_emitente = {}

    prompt = f"""
Você é o Orçaí, um sistema inteligente que transforma mensagens em orçamentos profissionais.

O usuário está pedindo para gerar um orçamento para o cliente dele.

DADOS DO EMITENTE:
{json.dumps(dados_emitente, ensure_ascii=False, indent=2)}

SERVIÇOS CADASTRADOS:
{lista_servicos}

Sua função é interpretar a mensagem do usuário e retornar SOMENTE JSON válido.

Extraia:
- nome do cliente
- telefone do cliente
- CPF ou CNPJ do cliente, se informado
- endereço do serviço, se informado
- itens do orçamento
- quantidade de cada item
- valor unitário de cada item, se informado
- materiais adicionais, se informado
- observação, se houver

REGRAS:
- Não invente dados.
- Se o valor não foi informado, deixe valor_unitario como null.
- Se a quantidade não foi informada, use 1.
- Se o usuário informar "tomada 200", entenda que o valor da tomada é 200.
- Se o usuário informar "2 tomadas de 150", quantidade 2 e valor_unitario 150.
- Se o serviço existir nos serviços cadastrados, use o nome mais parecido.
- Se não existir serviço cadastrado, aceite a descrição livre.
- Responda SOMENTE JSON.

FORMATO:

{{
  "cliente": "",
  "telefone_cliente": "",
  "cpf_cnpj_cliente": "",
  "endereco_servico": "",
  "itens": [
    {{
      "servico": "",
      "quantidade": 1,
      "valor_unitario": null
    }}
  ],
  "materiais_adicionais": 0,
  "observacao": ""
}}

Mensagem:
{texto}
"""

    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Você interpreta pedidos de orçamento e responde somente JSON válido."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    conteudo = limpar_json(resposta.choices[0].message.content)

    try:
        return json.loads(conteudo)
    except Exception as erro:
        print("ERRO JSON ORÇAMENTO:", erro)
        print("CONTEÚDO:", conteudo)

        return {
            "cliente": "",
            "telefone_cliente": "",
            "cpf_cnpj_cliente": "",
            "endereco_servico": "",
            "itens": [],
            "materiais_adicionais": 0,
            "observacao": ""
        }


def interpretar_valores_itens_com_ia(texto, itens_pendentes):
    prompt = f"""
Você é o Orçaí.

O usuário está informando valores para itens de um orçamento.

ITENS PENDENTES:
{json.dumps(itens_pendentes, ensure_ascii=False, indent=2)}

MENSAGEM DO USUÁRIO:
{texto}

Sua função:
- Identificar o valor unitário de cada item.
- Associar corretamente o valor ao serviço correspondente.
- Se não encontrar valor para algum item, deixe null.
- Retorne somente JSON válido.

FORMATO:

{{
  "itens": [
    {{
      "servico": "",
      "valor_unitario": null
    }}
  ]
}}
"""

    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Você interpreta valores de itens de orçamento e responde somente JSON válido."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    conteudo = limpar_json(resposta.choices[0].message.content)

    try:
        return json.loads(conteudo)
    except Exception as erro:
        print("ERRO JSON VALORES:", erro)
        print("CONTEÚDO:", conteudo)

        return {"itens": []}


def interpretar_comando_usuario(texto):
    prompt = f"""
Você é o Orçaí.

Analise a mensagem do usuário e identifique a intenção.

MENSAGEM:
{texto}

Ações possíveis:
- "novo_orcamento"
- "editar_cadastro"
- "editar_nome"
- "editar_empresa"
- "editar_cnpj"
- "editar_email"
- "editar_endereco"
- "editar_telefone"
- "cadastrar_servicos"
- "ajuda"
- "desconhecido"

Retorne SOMENTE JSON válido.

FORMATO:
{{
  "acao": "desconhecido"
}}
"""

    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Você identifica comandos do usuário e responde somente JSON válido."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    conteudo = limpar_json(resposta.choices[0].message.content)

    try:
        return json.loads(conteudo)
    except Exception:
        return {"acao": "desconhecido"}
    
def interpretar_servicos_com_ia(texto):
    prompt = f"""
Você é o Orçaí.

O usuário está cadastrando serviços ou produtos com valores.

Sua função é interpretar a mensagem mesmo que esteja escrita de forma natural.

Exemplos:
"instalação de ar condicionado mil reais" = 1000
"limpeza de ar condicionado trezentos e cinquenta reais" = 350
"ensaio fotográfico 1.500,00" = 1500
"vídeo institucional - 2500" = 2500
"instalação de ar-condicionado 1000 reais limpeza de ar-condicionado 350 reais" = dois serviços

REGRAS:
- Retorne somente serviços/produtos com valor.
- Não invente serviços.
- Converta valores por extenso para número.
- "mil reais" = 1000
- "trezentos e cinquenta reais" = 350
- Aceite vírgula decimal: 850,50 = 850.50
- Aceite ponto de milhar: 1.500,00 = 1500.00
- Responda SOMENTE JSON válido.

FORMATO:
{{
  "servicos": [
    {{
      "nome": "",
      "valor": 0
    }}
  ]
}}

Mensagem:
{texto}
"""

    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Você interpreta cadastro de serviços e produtos e responde somente JSON válido."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1
    )

    conteudo = limpar_json(resposta.choices[0].message.content)

    try:
        dados = json.loads(conteudo)
        servicos_lista = dados.get("servicos", [])

        servicos = {}

        for item in servicos_lista:
            nome = str(item.get("nome") or "").strip()
            valor = item.get("valor")

            if not nome or valor is None:
                continue

            try:
                valor = str(valor).replace("R$", "").replace(" ", "")

                if "," in valor and "." in valor:
                    valor = valor.replace(".", "").replace(",", ".")
                elif "," in valor:
                    valor = valor.replace(",", ".")

                valor = float(valor)

            except Exception:
                continue

            chave = re.sub(r"\s+", " ", nome.lower().strip())

            servicos[chave] = {
                "nome": nome,
                "valor": valor
            }

        return servicos

    except Exception as erro:
        print("ERRO JSON SERVIÇOS IA:", erro)
        print("CONTEÚDO:", conteudo)
        return {}
    
    