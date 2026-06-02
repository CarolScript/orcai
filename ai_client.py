from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def interpretar_orcamento_com_ia(texto, servicos_disponiveis=None):
    """
    Usa OpenAI para interpretar orçamento.
    """

    lista_servicos = ""

    if servicos_disponiveis:
        lista_servicos = "\n".join(
            [f"- {s['nome']}" for s in servicos_disponiveis.values()]
        )

    prompt = f"""
Você é um sistema inteligente de geração de orçamentos chamado Orçai.

Sua função é interpretar mensagens de empresários e retornar SOMENTE um JSON válido.

Você deve entender:
- nome do cliente
- telefone
- itens
- quantidade
- materiais adicionais
- observação

SERVIÇOS DISPONÍVEIS:
{lista_servicos}

REGRAS:
- Nunca invente serviços.
- Tente associar palavras parecidas aos serviços disponíveis.
- Exemplo:
  "criação" pode virar "criação de chatbot comercial"
- Detecte telefone automaticamente.
- Detecte quantidades automaticamente.
- Detecte materiais adicionais.
- Detecte observação.
- Se não encontrar algo, deixe vazio.

FORMATO OBRIGATÓRIO:

{{
  "cliente": "",
  "telefone_cliente": "",
  "itens": [
    {{
      "servico": "",
      "quantidade": 1
    }}
  ],
  "materiais_adicionais": 0,
  "observacao": ""
}}

Mensagem do usuário:
{texto}
"""

    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Você é um interpretador de orçamentos."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1
    )

    conteudo = resposta.choices[0].message.content

    try:
        return json.loads(conteudo)
    except Exception:
        return {
            "cliente": "",
            "telefone_cliente": "",
            "itens": [],
            "materiais_adicionais": 0,
            "observacao": ""
        }