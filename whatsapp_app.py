from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from datetime import datetime
import requests
import os
import re
import base64
import tempfile

from ai_client import interpretar_orcamento_com_ia
from interpretador_ia import (
    interpretar_cadastro,
    normalizar_dados_orcamento_ia,
    corrigir_itens_orcamento,
)
from transcricao_audio import transcrever_audio
from orcamento import gerar_orcamento
from banco import (
    criar_tabelas,
    salvar_empresa,
    buscar_empresa_por_telegram,
    salvar_servicos,
    buscar_servicos_empresa,
    salvar_orcamento,
)

load_dotenv()

app = FastAPI()
criar_tabelas()

ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN", "")
BASE_URL = os.getenv("BASE_URL", "")

usuarios = {}

PASTA_ARQUIVOS = "arquivos"
os.makedirs(PASTA_ARQUIVOS, exist_ok=True)


def normalizar_numero(numero):
    return re.sub(r"\D", "", str(numero or ""))


def apenas_numeros(texto):
    return re.sub(r"\D", "", str(texto or ""))


def normalizar_texto(texto):
    return str(texto or "").lower().strip()


def eh_saudacao(texto):
    texto = normalizar_texto(texto)

    saudacoes = [
        "oi",
        "ola",
        "olá",
        "bom dia",
        "boa tarde",
        "boa noite",
        "opa",
        "e ai",
        "e aí",
        "hello",
        "hey",
    ]

    return texto in saudacoes


def nome_parece_invalido(texto):
    texto = normalizar_texto(texto)

    invalidos = [
        "oi",
        "ola",
        "olá",
        "bom dia",
        "boa tarde",
        "boa noite",
        "teste",
        "sim",
        "não",
        "nao",
        "ok",
    ]

    return texto in invalidos or len(texto) < 3


def zapi_headers():
    headers = {
        "Content-Type": "application/json"
    }

    if ZAPI_CLIENT_TOKEN:
        headers["Client-Token"] = ZAPI_CLIENT_TOKEN

    return headers


def enviar_mensagem(numero, mensagem):
    url = (
        f"https://api.z-api.io/instances/"
        f"{ZAPI_INSTANCE_ID}/token/"
        f"{ZAPI_TOKEN}/send-text"
    )

    payload = {
        "phone": normalizar_numero(numero),
        "message": mensagem,
    }

    resposta = requests.post(
        url,
        json=payload,
        headers=zapi_headers(),
        timeout=60,
    )

    print("\n====== ENVIO TEXTO ======")
    print(resposta.status_code)
    print(resposta.text)
    print("=========================\n")

    return resposta


def enviar_pdf(numero, caminho_pdf):
    print("\n====== ENVIANDO PDF ======")
    print(caminho_pdf)
    print("==========================\n")

    try:
        if not os.path.exists(caminho_pdf):
            enviar_mensagem(
                numero,
                "Não encontrei o PDF para envio."
            )
            return

        with open(caminho_pdf, "rb") as arquivo:
            conteudo_pdf = arquivo.read()

        if not conteudo_pdf.startswith(b"%PDF"):
            enviar_mensagem(
                numero,
                "O arquivo gerado não é um PDF válido."
            )
            return

        pdf_base64 = base64.b64encode(
            conteudo_pdf
        ).decode("utf-8")

        nome_arquivo = os.path.basename(caminho_pdf)

        tentativas = [
            {
                "endpoint": (
                    f"https://api.z-api.io/instances/"
                    f"{ZAPI_INSTANCE_ID}/token/"
                    f"{ZAPI_TOKEN}/send-document/pdf"
                ),
                "payload": {
                    "phone": normalizar_numero(numero),
                    "document": (
                        f"data:application/pdf;base64,"
                        f"{pdf_base64}"
                    ),
                    "fileName": nome_arquivo,
                    "caption": "📄 Orçamento Orçai"
                }
            },
            {
                "endpoint": (
                    f"https://api.z-api.io/instances/"
                    f"{ZAPI_INSTANCE_ID}/token/"
                    f"{ZAPI_TOKEN}/send-document"
                ),
                "payload": {
                    "phone": normalizar_numero(numero),
                    "base64": (
                        f"data:application/pdf;base64,"
                        f"{pdf_base64}"
                    ),
                    "fileName": nome_arquivo,
                    "caption": "📄 Orçamento Orçai"
                }
            }
        ]

        for tentativa in tentativas:
            resposta = requests.post(
                tentativa["endpoint"],
                json=tentativa["payload"],
                headers=zapi_headers(),
                timeout=90,
            )

            print("\n====== RESPOSTA PDF ======")
            print(resposta.status_code)
            print(resposta.text)
            print("==========================\n")

            if resposta.status_code in [200, 201]:
                return

        if BASE_URL:
            link = (
                f"{BASE_URL}/arquivos/"
                f"{nome_arquivo}"
            )

            enviar_mensagem(
                numero,
                "Não consegui anexar o PDF.\n\n"
                f"Acesse aqui:\n{link}"
            )

    except Exception as erro:
        print("ERRO PDF:", erro)

        enviar_mensagem(
            numero,
            f"Erro ao enviar PDF:\n{erro}"
        )


def formatar_telefone(telefone):
    numeros = apenas_numeros(telefone)

    if len(numeros) == 11:
        return (
            f"({numeros[:2]}) "
            f"{numeros[2:7]}-"
            f"{numeros[7:]}"
        )

    return telefone or ""


def formatar_cnpj(cnpj):
    numeros = apenas_numeros(cnpj)

    if len(numeros) == 14:
        return (
            f"{numeros[:2]}."
            f"{numeros[2:5]}."
            f"{numeros[5:8]}/"
            f"{numeros[8:12]}-"
            f"{numeros[12:]}"
        )

    return cnpj or ""


def validar_cnpj(cnpj):
    return len(apenas_numeros(cnpj)) == 14


def parse_servicos(texto):
    servicos = {}

    for linha in str(texto or "").splitlines():

        if "-" not in linha:
            continue

        try:
            nome, valor = linha.split("-", 1)

            nome = nome.strip()

            valor = float(
                valor.strip().replace(",", ".")
            )

            servicos[
                normalizar_texto(nome)
            ] = {
                "nome": nome,
                "valor": valor,
            }

        except Exception:
            pass

    return servicos


def gerar_exemplo_orcamento(servicos):
    lista = list(servicos.values())

    if len(lista) >= 1:
        return (
            "Cadastro concluído ✅\n\n"
            "Agora envie um orçamento.\n\n"
            "Exemplo:\n"
            f"Orçamento para João "
            f"{lista[0]['nome']} 2 "
            f"material 50"
        )

    return (
        "Cadastro concluído ✅"
    )


def resumo_confirmacao(dados):
    linhas = [
        "Confirme os dados:\n",
        f"Cliente: {dados.get('cliente')}",
        "",
        "Itens:"
    ]

    for item in dados.get("itens", []):
        linhas.append(
            f"- {item.get('servico')} "
            f"x {item.get('quantidade', 1)}"
        )

    linhas.extend([
        "",
        "Está correto?",
        "Responda SIM ou NÃO."
    ])

    return "\n".join(linhas)


def carregar_usuario(numero):
    numero = normalizar_numero(numero)

    if numero in usuarios:
        return

    empresa_db = buscar_empresa_por_telegram(numero)

    if empresa_db:
        usuarios[numero] = {
            "etapa": "concluido",
            "empresa_id": empresa_db["id"],
            "responsavel": empresa_db["responsavel"],
            "empresa": empresa_db["empresa"],
            "cnpj": empresa_db["cnpj"],
            "telefone": empresa_db["telefone"],
            "email": empresa_db["email"],
            "endereco": empresa_db["endereco"],
            "servicos": buscar_servicos_empresa(
                empresa_db["id"]
            ),
        }

    else:
        usuarios[numero] = {
            "etapa": "responsavel"
        }


def gerar_pdf_orcamento(numero, dados_orc):
    dados_empresa = {
        "responsavel": usuarios[numero]["responsavel"],
        "empresa": usuarios[numero]["empresa"],
        "cnpj": usuarios[numero]["cnpj"],
        "telefone": usuarios[numero]["telefone"],
        "email": usuarios[numero]["email"],
        "endereco": usuarios[numero]["endereco"],
    }

    tabela_servicos = usuarios[numero].get(
        "servicos",
        {}
    )

    nome_pdf = (
        f"orcamento_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    caminho_pdf = os.path.join(
        PASTA_ARQUIVOS,
        nome_pdf
    )

    gerar_orcamento(
        dados_orcamento=dados_orc,
        dados_empresa=dados_empresa,
        tabela_servicos=tabela_servicos,
        nome_arquivo=caminho_pdf,
    )

    empresa_db = buscar_empresa_por_telegram(
        numero
    )

    if empresa_db:
        try:
            salvar_orcamento(
                empresa_db["id"],
                dados_orc,
                tabela_servicos,
                caminho_pdf,
            )
        except Exception as erro:
            print("ERRO MYSQL:", erro)

    return caminho_pdf


def processar_texto(numero, texto):
    numero = normalizar_numero(numero)
    texto_limpo = str(texto or "").strip()

    carregar_usuario(numero)

    etapa = usuarios[numero]["etapa"]

    if etapa == "responsavel":

        if eh_saudacao(texto_limpo):
            enviar_mensagem(
                numero,
                "Olá! Eu sou o Orçai 🤖\n\n"
                "Vou te ajudar a criar "
                "orçamentos profissionais.\n\n"
                "Qual é o seu nome?"
            )
            return

        nome = interpretar_cadastro(
            texto_limpo,
            "nome"
        )

        if nome_parece_invalido(nome):
            enviar_mensagem(
                numero,
                "Me diga seu nome 😊"
            )
            return

        usuarios[numero]["responsavel"] = nome
        usuarios[numero]["etapa"] = "empresa"

        enviar_mensagem(
            numero,
            "Qual é o nome da sua empresa?"
        )

        return

    if etapa == "empresa":
        usuarios[numero]["empresa"] = texto_limpo
        usuarios[numero]["etapa"] = "cnpj"

        enviar_mensagem(
            numero,
            "Qual é o CNPJ?"
        )

        return

    if etapa == "cnpj":
        cnpj = formatar_cnpj(texto_limpo)

        if not validar_cnpj(cnpj):
            enviar_mensagem(
                numero,
                "CNPJ inválido."
            )
            return

        usuarios[numero]["cnpj"] = cnpj
        usuarios[numero]["etapa"] = "telefone"

        enviar_mensagem(
            numero,
            "Qual é o telefone?"
        )

        return

    if etapa == "telefone":
        usuarios[numero]["telefone"] = (
            formatar_telefone(texto_limpo)
        )

        usuarios[numero]["etapa"] = "email"

        enviar_mensagem(
            numero,
            "Qual é o e-mail?"
        )

        return

    if etapa == "email":
        usuarios[numero]["email"] = texto_limpo
        usuarios[numero]["etapa"] = "endereco"

        enviar_mensagem(
            numero,
            "Qual é o endereço?"
        )

        return

    if etapa == "endereco":
        usuarios[numero]["endereco"] = texto_limpo
        usuarios[numero]["etapa"] = "servicos"

        enviar_mensagem(
            numero,
            "Envie os serviços assim:\n\n"
            "Instalação - 150\n"
            "Manutenção - 300"
        )

        return

    if etapa == "servicos":
        servicos = parse_servicos(texto_limpo)

        if not servicos:
            enviar_mensagem(
                numero,
                "Formato inválido."
            )
            return

        usuarios[numero]["servicos"] = servicos

        empresa_id = salvar_empresa(
            numero,
            usuarios[numero]["responsavel"],
            usuarios[numero]["empresa"],
            usuarios[numero]["cnpj"],
            usuarios[numero]["telefone"],
            usuarios[numero]["email"],
            usuarios[numero]["endereco"],
        )

        salvar_servicos(
            empresa_id,
            servicos
        )

        usuarios[numero]["empresa_id"] = empresa_id
        usuarios[numero]["etapa"] = "concluido"

        enviar_mensagem(
            numero,
            gerar_exemplo_orcamento(servicos)
        )

        return

    if etapa == "confirmando_orcamento":

        resposta = normalizar_texto(texto_limpo)

        if resposta in [
            "sim",
            "s",
            "ok",
            "confirmar"
        ]:

            dados = usuarios[numero].get(
                "orcamento_pendente"
            )

            if not dados:
                enviar_mensagem(
                    numero,
                    "Nenhum orçamento pendente."
                )
                return

            enviar_mensagem(
                numero,
                "Gerando PDF..."
            )

            caminho_pdf = gerar_pdf_orcamento(
                numero,
                dados
            )

            enviar_pdf(
                numero,
                caminho_pdf
            )

            usuarios[numero]["etapa"] = "concluido"
            usuarios[numero].pop(
                "orcamento_pendente",
                None
            )

            return

        if resposta in [
            "não",
            "nao",
            "n"
        ]:
            usuarios[numero]["etapa"] = "concluido"

            enviar_mensagem(
                numero,
                "Envie novamente o orçamento."
            )

            return

        enviar_mensagem(
            numero,
            "Responda apenas SIM ou NÃO."
        )

        return

    if etapa == "concluido":

        servicos = usuarios[numero].get(
            "servicos",
            {}
        )

        try:
            dados = interpretar_orcamento_com_ia(
                texto_limpo,
                servicos
            )

            dados = normalizar_dados_orcamento_ia(
                dados
            )

            dados = corrigir_itens_orcamento(
                dados,
                servicos
            )

        except Exception as erro:
            print("ERRO IA:", erro)

            enviar_mensagem(
                numero,
                "Erro ao interpretar orçamento."
            )

            return

        usuarios[numero][
            "orcamento_pendente"
        ] = dados

        usuarios[numero][
            "etapa"
        ] = "confirmando_orcamento"

        enviar_mensagem(
            numero,
            resumo_confirmacao(dados)
        )


def baixar_arquivo_url(url, sufixo):
    resposta = requests.get(url)

    resposta.raise_for_status()

    temp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=sufixo
    )

    temp.write(resposta.content)
    temp.close()

    return temp.name


def extrair_texto_mensagem(payload):

    if payload.get("fromMe") is True:
        return None, None, None

    if payload.get("isGroup") is True:
        return None, None, None

    numero = (
        payload.get("phone")
        or payload.get("from")
        or ""
    )

    texto = ""

    if isinstance(payload.get("text"), dict):
        texto = payload["text"].get(
            "message",
            ""
        )

    if not texto:
        texto = (
            payload.get("message")
            or payload.get("body")
            or ""
        )

    audio_url = (
        payload.get("audioUrl")
        or payload.get("url")
    )

    return (
        normalizar_numero(numero),
        texto,
        audio_url
    )


@app.get("/")
def home():
    return {
        "status": "Orçai rodando"
    }


@app.get("/arquivos/{nome_arquivo}")
def servir_arquivo(nome_arquivo: str):

    caminho = os.path.join(
        PASTA_ARQUIVOS,
        nome_arquivo
    )

    if os.path.exists(caminho):
        return FileResponse(
            caminho,
            media_type="application/pdf",
            filename=nome_arquivo,
        )

    return {
        "erro": "arquivo não encontrado"
    }


@app.post("/webhook")
async def webhook(request: Request):

    payload = await request.json()

    print("\n====== WEBHOOK Z-API ======")
    print(payload)
    print("===========================\n")

    numero, texto, audio_url = (
        extrair_texto_mensagem(payload)
    )

    if not numero:
        return {
            "status": "ignorado"
        }

    if audio_url:

        try:
            enviar_mensagem(
                numero,
                "Transcrevendo áudio..."
            )

            caminho_audio = baixar_arquivo_url(
                audio_url,
                ".ogg"
            )

            texto = transcrever_audio(
                caminho_audio
            )

            if os.path.exists(caminho_audio):
                os.remove(caminho_audio)

            enviar_mensagem(
                numero,
                f"Áudio transcrito:\n\n{texto}"
            )

        except Exception as erro:
            print("ERRO ÁUDIO:", erro)

            enviar_mensagem(
                numero,
                "Erro ao transcrever áudio."
            )

            return {
                "status": "erro"
            }

    if texto:
        processar_texto(
            numero,
            texto
        )

    return {
        "status": "ok"
    }