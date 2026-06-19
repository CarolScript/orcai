from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from dotenv import load_dotenv
from datetime import datetime
import traceback
import requests
import os
import re
import tempfile
import time
import unicodedata

from ai_client import (
    interpretar_orcamento_com_ia,
    interpretar_valores_itens_com_ia,
    interpretar_comando_usuario,
    interpretar_servicos_com_ia,
)

from interpretador_ia import normalizar_dados_orcamento_ia
from transcricao_audio import transcrever_audio
from orcamento import gerar_orcamento

from banco import (
    criar_tabelas,
    salvar_empresa,
    buscar_empresa_por_telegram,
    salvar_orcamento,
    atualizar_logo_empresa,
    buscar_servicos_empresa,
    salvar_servicos,
)

load_dotenv()

app = FastAPI()
criar_tabelas()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
BASE_URL = os.getenv("BASE_URL", "")

usuarios = {}

PASTA_ARQUIVOS = "arquivos"
PASTA_LOGOS = os.path.join(PASTA_ARQUIVOS, "logos")

os.makedirs(PASTA_ARQUIVOS, exist_ok=True)
os.makedirs(PASTA_LOGOS, exist_ok=True)


# =========================
# UTILITÁRIOS
# =========================

def normalizar_numero(numero):
    return re.sub(r"\D", "", str(numero or ""))


def apenas_numeros(texto):
    return re.sub(r"\D", "", str(texto or ""))


def normalizar_texto(texto):
    texto = str(texto or "").lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.replace("ç", "c")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def resposta_sim(texto):
    return normalizar_texto(texto) in [
        "sim", "s", "ok", "okay", "aceito", "concordo",
        "continuar", "quero", "pode", "bora", "vamos", "positivo"
    ]


def resposta_nao(texto):
    return normalizar_texto(texto) in [
        "nao", "n", "agora nao", "depois", "negativo", "nao quero"
    ]


def resposta_pular(texto):
    return normalizar_texto(texto) in [
        "pular", "nao", "n", "agora nao", "depois", "deixar para depois"
    ]


def eh_saudacao(texto):
    return normalizar_texto(texto) in [
        "oi", "ola", "bom dia", "boa tarde", "boa noite", "opa", "e ai", "eae"
    ]


def validar_email(email):
    email = str(email or "").strip()
    return re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email) is not None


def validar_cnpj(cnpj):
    return len(apenas_numeros(cnpj)) == 14


def validar_telefone(telefone):
    qtd = len(apenas_numeros(telefone))
    return qtd in [10, 11, 12, 13]


def formatar_moeda(valor):
    try:
        return f"R$ {float(valor):.2f}"
    except Exception:
        return "R$ 0.00"


def valor_para_float(valor):
    if valor is None:
        return None

    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace("r$", "").replace(" ", "")

    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except Exception:
        return None


def parece_comando_orcamento_generico(texto):
    t = normalizar_texto(texto)

    comandos = [
        "quero gerar orcamento",
        "quero gerar um orcamento",
        "gerar orcamento",
        "novo orcamento",
        "fazer orcamento",
        "preciso gerar orcamento",
        "preciso gerar um orcamento",
        "orcamento",
        "novo",
        "fazer um novo",
    ]

    return t in comandos


def parece_pedido_orcamento_com_dados(texto):
    t = normalizar_texto(texto)

    if parece_comando_orcamento_generico(t):
        return False

    palavras_orcamento = [
        "orcamento", "cliente", "telefone", "servico", "servico para",
        "preciso de um orcamento", "para o cliente", "para cliente",
        "instalacao", "troca", "manutencao", "reparo", "conserto",
        "tomada", "chuveiro", "ar condicionado", "filmagem", "foto",
        "ensaio", "video", "pacote"
    ]

    tem_palavra = any(p in t for p in palavras_orcamento)
    tem_valor = bool(re.search(r"(r\$|\d+[,.]\d{1,2}|\d+\s*reais|\d+\s*cada)", t))
    tem_quantidade = bool(re.search(r"\b\d+\s+[a-zA-ZÀ-ÿ]", texto))

    return tem_palavra and (tem_valor or tem_quantidade or "cliente" in t or "telefone" in t)


def mensagem_tem_dados_minimos_orcamento(dados):
    cliente = str(dados.get("cliente") or "").strip()
    itens = dados.get("itens") or []
    itens_validos = [i for i in itens if str(i.get("servico") or "").strip()]
    return bool(cliente or itens_validos)


def texto_transcricao_invalido(texto):
    t = str(texto or "").strip().lower()
    return (
        not t
        or t.startswith("erro ao transcrever")
        or "erro ao transcrever" in t
    )


# =========================
# META
# =========================

def meta_headers():
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }


def enviar_mensagem(numero, mensagem):
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": normalizar_numero(numero),
        "type": "text",
        "text": {"body": mensagem}
    }

    resposta = requests.post(url, json=payload, headers=meta_headers(), timeout=60)

    print("\n====== ENVIO META TEXTO ======")
    print(resposta.status_code)
    print(resposta.text)
    print("==============================\n")

    return resposta

def subir_pdf_para_meta(caminho_pdf):
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/media"

    with open(caminho_pdf, "rb") as arquivo:
        files = {
            "file": (
                os.path.basename(caminho_pdf),
                arquivo,
                "application/pdf"
            )
        }

        data = {
            "messaging_product": "whatsapp",
            "type": "application/pdf"
        }

        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}"
        }

        resposta = requests.post(
            url,
            headers=headers,
            data=data,
            files=files,
            timeout=120
        )

    print("\n====== UPLOAD PDF META ======")
    print(resposta.status_code)
    print(resposta.text)
    print("=============================\n")

    resposta.raise_for_status()

    return resposta.json().get("id")


def enviar_pdf(numero, caminho_pdf):
    if not os.path.exists(caminho_pdf):
        enviar_mensagem(numero, "Não encontrei o PDF para envio.")
        return None

    nome_arquivo = os.path.basename(caminho_pdf)

    try:
        media_id = subir_pdf_para_meta(caminho_pdf)

        if not media_id:
            enviar_mensagem(numero, "PDF gerado, mas não consegui obter o ID da Meta.")
            return None

        url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": normalizar_numero(numero),
            "type": "document",
            "document": {
                "id": media_id,
                "filename": nome_arquivo
            }
        }

        resposta = requests.post(
            url,
            json=payload,
            headers=meta_headers(),
            timeout=60
        )

        print("\n====== ENVIO PDF POR ID META ======")
        print(resposta.status_code)
        print(resposta.text)
        print("===================================\n")

        return resposta

    except Exception as erro:
        print("ERRO AO ENVIAR PDF POR ID:", erro)
        enviar_mensagem(numero, "PDF gerado, mas tive problema ao enviar pelo WhatsApp.")
        return None


# =========================
# MENSAGENS
# =========================

def mensagem_lgpd():
    return (
        "Olá! Sou o Orçaí ✅\n\n"
        "Transformo mensagens e áudios em orçamentos profissionais em PDF.\n\n"
        "Antes de começar, preciso da sua autorização para armazenar os dados necessários "
        "para gerar seus orçamentos e organizar seu histórico.\n\n"
        "Responda SIM para continuar ou NÃO para encerrar."
    )


def mensagem_primeiro_orcamento(nome):
    return (
        f"Prazer, {nome} 😊\n\n"
        "Vamos gerar seu primeiro orçamento.\n\n"
        "Envie uma mensagem ou áudio explicando o orçamento do seu jeito.\n\n"
        "Exemplo:\n\n"
        "Cliente João Silva\n"
        "Telefone 65 99999-9999\n"
        "Instalação de 2 tomadas - R$ 150 cada\n"
        "Troca de 1 chuveiro - R$ 120"
    )


def exemplo_orcamento_com_servicos(numero=None):
    exemplo_base = (
        "Cliente João Silva\n"
        "Telefone 65 99999-9999\n"
    )

    if numero and numero in usuarios and usuarios[numero].get("servicos"):
        servicos = list(usuarios[numero]["servicos"].values())
        ultimos_servicos = servicos[-2:]

        linhas = [exemplo_base]

        for i, servico in enumerate(ultimos_servicos):
            qtd = 2 if i == 0 else 1
            linhas.append(f"{qtd} {servico['nome']}")

        return "\n".join(linhas)

    return (
        "Cliente João Silva\n"
        "Telefone 65 99999-9999\n"
        "Nome do serviço/produto\n"
        "Nome do serviço/produto"
    )


def mensagem_pedir_orcamento(numero=None):
    return (
        "Certo 😊\n\n"
        "Me envie os dados do orçamento por texto ou áudio.\n\n"
        "Exemplo:\n\n"
        f"{exemplo_orcamento_com_servicos(numero)}"
    )


def mensagem_pdf_gerado():
    return (
        "Orçamento gerado com sucesso ✅\n\n"
        "Se precisar alterar alguma informação, é só me avisar.\n"
        "Para gerar outro orçamento, mande os dados por texto ou áudio."
    )


def mensagem_pos_primeiro_pdf():
    return (
        "Agora que você já viu o Orçaí funcionando na prática, quer deixar seus próximos "
        "orçamentos com os dados da sua empresa?\n\n"
        "Isso ajuda o PDF a sair mais completo e profissional.\n\n"
        "Você pode adicionar:\n"
        "• Nome da empresa\n"
        "• Logo\n"
        "• CNPJ\n"
        "• E-mail\n"
        "• Endereço\n\n"
        "Responda SIM para continuar.\n"
        "Responda NÃO para deixar para depois."
    )


def mensagem_ajuda():
    return (
        "Posso te ajudar com:\n\n"
        "• Gerar orçamento\n"
        "• Editar cadastro\n"
        "• Adicionar ou trocar logo\n"
        "• Adicionar CNPJ\n"
        "• Adicionar e-mail\n"
        "• Adicionar endereço\n"
        "• Cadastrar serviços\n"
        "• Adicionar novo serviço\n\n"
        "Exemplos:\n"
        "“Quero editar meu CNPJ”\n"
        "“Quero adicionar minha logo”\n"
        "“Cadastrar meus serviços”\n"
        "“Novo orçamento para João”"
    )


def mensagem_final_servicos(numero):
    return (
        "Serviços cadastrados ✅\n\n"
        "Agora, quando precisar gerar um orçamento, é só me enviar algo assim:\n\n"
        f"{exemplo_orcamento_com_servicos(numero)}\n\n"
        "Se o serviço já estiver cadastrado, eu uso o valor salvo. Se faltar algo, eu te pergunto."
    )


def mensagem_perguntar_servicos():
    return (
        "Deseja cadastrar seus serviços ou produtos com valores para agilizar os próximos orçamentos?\n\n"
        "Responda SIM ou NÃO."
    )


def mensagem_cadastrar_servicos():
    return (
        "Perfeito 😊\n\n"
        "Me envie seus serviços ou produtos com os valores.\n\n"
        "Pode mandar um por linha ou separados por vírgula:\n\n"
        "Nome do serviço/produto - valor\n"
        "Nome do serviço/produto - valor\n"
        "Nome do serviço/produto - valor"
    )


# =========================
# CADASTRO / ESTADO
# =========================

def cadastro_basico(numero):
    return {
        "lgpd_aceito": False,
        "nome_usuario": None,
        "nome_empresa": None,
        "cnpj": None,
        "telefone": numero,
        "email": None,
        "endereco": None,
        "logo_path": None,
        "primeiro_pdf_gerado": False,
        "perguntou_complemento": False,
    }


def carregar_usuario(numero):
    numero = normalizar_numero(numero)

    if numero in usuarios:
        return

    empresa_db = buscar_empresa_por_telegram(numero)

    if empresa_db:
        servicos = buscar_servicos_empresa(empresa_db["id"])

        usuarios[numero] = {
            "etapa": "pronto",
            "empresa_id": empresa_db["id"],
            "responsavel": empresa_db.get("responsavel"),
            "empresa": empresa_db.get("empresa"),
            "cnpj": empresa_db.get("cnpj"),
            "telefone": empresa_db.get("telefone"),
            "email": empresa_db.get("email"),
            "endereco": empresa_db.get("endereco"),
            "logo_path": empresa_db.get("logo_path"),
            "servicos": servicos or {},
            "cadastro": {
                "lgpd_aceito": True,
                "nome_usuario": empresa_db.get("responsavel"),
                "nome_empresa": empresa_db.get("empresa"),
                "cnpj": empresa_db.get("cnpj"),
                "telefone": empresa_db.get("telefone"),
                "email": empresa_db.get("email"),
                "endereco": empresa_db.get("endereco"),
                "logo_path": empresa_db.get("logo_path"),
                "primeiro_pdf_gerado": False,
                "perguntou_complemento": False,
            }
        }
    else:
        usuarios[numero] = {
            "etapa": "lgpd",
            "cadastro": cadastro_basico(numero),
            "servicos": {}
        }


def salvar_cadastro_minimo(numero):
    cadastro = usuarios[numero]["cadastro"]

    responsavel = cadastro.get("nome_usuario") or "Não informado"
    empresa = cadastro.get("nome_empresa") or responsavel
    cnpj = cadastro.get("cnpj") or ""
    telefone = cadastro.get("telefone") or numero
    email = cadastro.get("email") or ""
    endereco = cadastro.get("endereco") or ""
    logo_path = cadastro.get("logo_path") or usuarios[numero].get("logo_path")

    empresa_id = salvar_empresa(
        numero,
        responsavel,
        empresa,
        cnpj,
        telefone,
        email,
        endereco,
        logo_path
    )

    usuarios[numero]["empresa_id"] = empresa_id
    usuarios[numero]["responsavel"] = responsavel
    usuarios[numero]["empresa"] = empresa
    usuarios[numero]["cnpj"] = cnpj
    usuarios[numero]["telefone"] = telefone
    usuarios[numero]["email"] = email
    usuarios[numero]["endereco"] = endereco
    usuarios[numero]["logo_path"] = logo_path

    return empresa_id


def atualizar_dados_usuario(numero):
    cadastro = usuarios[numero]["cadastro"]

    usuarios[numero]["responsavel"] = cadastro.get("nome_usuario") or usuarios[numero].get("responsavel", "")
    usuarios[numero]["empresa"] = cadastro.get("nome_empresa") or usuarios[numero].get("empresa", usuarios[numero]["responsavel"])
    usuarios[numero]["cnpj"] = cadastro.get("cnpj") or ""
    usuarios[numero]["telefone"] = cadastro.get("telefone") or numero
    usuarios[numero]["email"] = cadastro.get("email") or ""
    usuarios[numero]["endereco"] = cadastro.get("endereco") or ""
    usuarios[numero]["logo_path"] = cadastro.get("logo_path") or usuarios[numero].get("logo_path")


# =========================
# ORÇAMENTO
# =========================

def resumo_confirmacao(dados):
    linhas = [
        "Confirme os dados:\n",
        f"Cliente: {dados.get('cliente') or 'Não informado'}",
        f"Telefone: {dados.get('telefone_cliente') or 'Não informado'}",
        f"Documento: {dados.get('cpf_cnpj_cliente') or 'Não informado'}",
        f"Endereço: {dados.get('endereco_servico') or 'Não informado'}",
        "",
        "Itens:"
    ]

    itens = dados.get("itens", [])

    if not itens:
        linhas.append("• Nenhum item identificado")

    total = 0

    for item in itens:
        servico = item.get("servico") or "Serviço não informado"
        quantidade = item.get("quantidade", 1) or 1
        valor = item.get("valor_unitario")

        if valor is not None:
            try:
                valor_float = float(valor)
                subtotal = valor_float * float(quantidade)
                total += subtotal
                linhas.append(f"• {servico} x{quantidade} - {formatar_moeda(valor_float)} cada")
            except Exception:
                linhas.append(f"• {servico} x{quantidade}")
        else:
            linhas.append(f"• {servico} x{quantidade}")

    if dados.get("materiais_adicionais"):
        try:
            total += float(dados.get("materiais_adicionais"))
        except Exception:
            pass

        linhas.append("")
        linhas.append(f"Materiais adicionais: {formatar_moeda(dados.get('materiais_adicionais'))}")

    if total > 0:
        linhas.append("")
        linhas.append(f"Total estimado: {formatar_moeda(total)}")

    if dados.get("observacao"):
        linhas.append("")
        linhas.append(f"Observação: {dados.get('observacao')}")

    linhas.extend([
        "",
        "Está correto?",
        "",
        "Responda SIM para gerar o PDF.",
        "Responda NÃO para corrigir."
    ])

    return "\n".join(linhas)


def buscar_servico_salvo_por_nome(numero, nome):
    if numero not in usuarios:
        return None

    nome_norm = normalizar_texto(nome)

    for chave, servico in usuarios[numero].get("servicos", {}).items():
        chave_norm = normalizar_texto(chave)
        servico_norm = normalizar_texto(servico.get("nome"))

        if nome_norm == chave_norm or nome_norm == servico_norm:
            return servico

        if nome_norm in chave_norm or chave_norm in nome_norm:
            return servico

        if nome_norm in servico_norm or servico_norm in nome_norm:
            return servico

    return None


def preencher_valores_servicos_cadastrados(numero, dados):
    for item in dados.get("itens", []):
        if item.get("valor_unitario") is not None:
            item["valor_unitario"] = valor_para_float(item.get("valor_unitario"))
            continue

        servico = buscar_servico_salvo_por_nome(numero, item.get("servico", ""))

        if servico:
            item["servico"] = servico["nome"]
            item["valor_unitario"] = float(servico["valor"])

    return dados


def itens_sem_valor(dados):
    return [
        item for item in dados.get("itens", [])
        if item.get("valor_unitario") is None
    ]


def mensagem_pedir_valores(itens):
    linhas = ["Só preciso dos valores para finalizar 😊\n"]

    for item in itens:
        servico = item.get("servico") or "Serviço não informado"
        qtd = item.get("quantidade", 1)
        linhas.append(f"• {servico} x{qtd}: R$ ?")

    linhas.append("\nPode responder assim:")

    for item in itens[:2]:
        nome = item.get("servico") or "Serviço"
        linhas.append(f"{nome} 150")

    return "\n".join(linhas)


def aplicar_valores_pendentes(numero, texto):
    dados = usuarios[numero]["orcamento_pendente"]
    itens = dados.get("itens", [])

    resultado = interpretar_valores_itens_com_ia(texto, itens)
    valores = resultado.get("itens", [])

    for item in itens:
        nome_item = normalizar_texto(item.get("servico"))

        for valor_info in valores:
            nome_valor = normalizar_texto(valor_info.get("servico"))

            if nome_item and nome_valor and (nome_item in nome_valor or nome_valor in nome_item):
                valor = valor_para_float(valor_info.get("valor_unitario"))

                if valor is not None:
                    item["valor_unitario"] = valor

    usuarios[numero]["orcamento_pendente"] = dados
    return dados


def criar_tabela_servicos_temporaria(dados):
    tabela = {}

    for item in dados.get("itens", []):
        servico = item.get("servico") or "Serviço"
        valor = item.get("valor_unitario") or 0

        tabela[normalizar_texto(servico)] = {
            "nome": servico,
            "valor": float(valor)
        }

    return tabela


def gerar_pdf_orcamento(numero, dados_orc):
    atualizar_dados_usuario(numero)

    dados_empresa = {
        "responsavel": usuarios[numero].get("responsavel", ""),
        "empresa": usuarios[numero].get("empresa", ""),
        "cnpj": usuarios[numero].get("cnpj", ""),
        "telefone": usuarios[numero].get("telefone", ""),
        "email": usuarios[numero].get("email", ""),
        "endereco": usuarios[numero].get("endereco", ""),
        "logo": usuarios[numero].get("logo_path", ""),
        "logo_path": usuarios[numero].get("logo_path", ""),
    }

    tabela_servicos = criar_tabela_servicos_temporaria(dados_orc)

    nome_pdf = f"orcamento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    caminho_pdf = os.path.join(PASTA_ARQUIVOS, nome_pdf)

    gerar_orcamento(
        dados_orcamento=dados_orc,
        dados_empresa=dados_empresa,
        tabela_servicos=tabela_servicos,
        nome_arquivo=caminho_pdf,
    )

    empresa_db = buscar_empresa_por_telegram(numero)

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


def processar_pedido_orcamento(numero, texto_limpo):
    if parece_comando_orcamento_generico(texto_limpo):
        enviar_mensagem(numero, mensagem_pedir_orcamento(numero))
        return

    dados_emitente = {
        "responsavel": usuarios[numero].get("responsavel", ""),
        "empresa": usuarios[numero].get("empresa", ""),
        "cnpj": usuarios[numero].get("cnpj", ""),
        "telefone": usuarios[numero].get("telefone", ""),
        "email": usuarios[numero].get("email", ""),
        "endereco": usuarios[numero].get("endereco", ""),
    }

    try:
        dados = interpretar_orcamento_com_ia(
            texto_limpo,
            usuarios[numero].get("servicos", {}),
            dados_emitente
        )

        print("\n====== DADOS IA ORÇAMENTO ======")
        print(dados)
        print("================================\n")

        dados = normalizar_dados_orcamento_ia(dados)
        dados = preencher_valores_servicos_cadastrados(numero, dados)

    except Exception as erro:
        print("ERRO IA ORÇAMENTO:", erro)
        enviar_mensagem(numero, mensagem_pedir_orcamento(numero))
        return

    if not mensagem_tem_dados_minimos_orcamento(dados):
        enviar_mensagem(numero, mensagem_pedir_orcamento(numero))
        return

    usuarios[numero]["orcamento_pendente"] = dados

    faltando = itens_sem_valor(dados)

    if faltando:
        usuarios[numero]["etapa"] = "aguardando_valores"
        enviar_mensagem(numero, mensagem_pedir_valores(faltando))
        return

    usuarios[numero]["etapa"] = "confirmando_orcamento"
    enviar_mensagem(numero, resumo_confirmacao(dados))


# =========================
# SERVIÇOS
# =========================

def parse_servicos(texto):
    servicos = {}

    partes = re.split(r"\n|(?<!\d),(?!\d)", str(texto or ""))

    for parte in partes:
        parte = parte.strip()

        if not parte:
            continue

        match = re.search(
            r"(.+?)(?:-|:|=)?\s*R?\$?\s*((?:\d{1,3}(?:\.\d{3})+|\d+)(?:[,.]\d{1,2})?)$",
            parte
        )

        if not match:
            continue

        nome = match.group(1).strip(" -:=.")
        valor = valor_para_float(match.group(2))

        if nome and valor is not None:
            servicos[normalizar_texto(nome)] = {
                "nome": nome,
                "valor": valor
            }

    return servicos


def resumo_servicos(servicos):
    linhas = ["Confirme os serviços cadastrados:\n"]

    for servico in servicos.values():
        linhas.append(f"• {servico['nome']} - {formatar_moeda(servico['valor'])}")

    linhas.append("\nEstá correto?")
    linhas.append("")
    linhas.append("Responda SIM para salvar.")
    linhas.append("Responda NÃO para corrigir.")

    return "\n".join(linhas)


# =========================
# COMANDOS
# =========================

def detectar_comando_local(texto):
    t = normalizar_texto(texto)

    if t in ["ajuda", "menu", "opcoes"]:
        return "ajuda"

    if parece_comando_orcamento_generico(t):
        return "novo_orcamento"

    if parece_pedido_orcamento_com_dados(texto):
        return None

    if any(p in t for p in [
        "adicionar servico", "novo servico", "adicionar produto", "novo produto",
        "cadastrar servico", "cadastrar produto", "meus servicos",
        "servicos cadastrados", "produtos cadastrados", "atualizar servicos",
        "atualizar produtos"
    ]):
        return "cadastrar_servicos"

    if any(p in t for p in ["logo", "logotipo", "marca", "imagem da empresa"]):
        return "editar_logo"

    verbos_edicao = [
        "editar", "alterar", "atualizar", "adicionar",
        "colocar", "trocar", "como faco", "como faço"
    ]

    if "endereco" in t and any(p in t for p in verbos_edicao):
        return "editar_endereco"

    if "cnpj" in t and any(p in t for p in verbos_edicao):
        return "editar_cnpj"

    if ("email" in t or "e-mail" in t) and any(p in t for p in verbos_edicao):
        return "editar_email"

    if "telefone" in t and any(p in t for p in verbos_edicao):
        return "editar_telefone"

    if "empresa" in t and any(p in t for p in verbos_edicao):
        return "editar_empresa"

    if "nome" in t and any(p in t for p in verbos_edicao):
        return "editar_nome"

    if "cor" in t or "layout" in t or "modelo" in t:
        return "recurso_indisponivel"

    return None


def processar_comando(numero, texto_limpo):
    acao = detectar_comando_local(texto_limpo)

    if not acao and not parece_pedido_orcamento_com_dados(texto_limpo):
        try:
            resultado = interpretar_comando_usuario(texto_limpo)
            acao = resultado.get("acao")
        except Exception:
            acao = None

    if acao == "ajuda":
        enviar_mensagem(numero, mensagem_ajuda())
        return True

    if acao == "novo_orcamento":
        enviar_mensagem(numero, mensagem_pedir_orcamento(numero))
        return True

    if acao == "cadastrar_servicos":
        usuarios[numero]["etapa"] = "cadastrar_servicos"
        enviar_mensagem(numero, mensagem_cadastrar_servicos())
        return True

    if acao == "editar_logo":
        usuarios[numero]["etapa"] = "aguardando_logo"
        enviar_mensagem(numero, "Perfeito 😊\n\nMe envie a logo da sua empresa em imagem PNG ou JPG.")
        return True

    mapa = {
        "editar_cnpj": ("editar_cnpj", "Me informe o novo CNPJ com 14 números."),
        "editar_email": ("editar_email", "Me informe o novo e-mail."),
        "editar_endereco": ("editar_endereco", "Me informe o novo endereço."),
        "editar_telefone": ("editar_telefone", "Me informe o novo telefone com DDD."),
        "editar_empresa": ("editar_empresa", "Me informe o novo nome da empresa."),
        "editar_nome": ("editar_nome", "Me informe seu nome."),
    }

    if acao in mapa:
        usuarios[numero]["etapa"] = mapa[acao][0]
        enviar_mensagem(numero, mapa[acao][1])
        return True

    if acao == "recurso_indisponivel":
        enviar_mensagem(
            numero,
            "Ainda não é possível alterar esse detalhe por aqui.\n\n"
            "Mas essa melhoria já está no radar do Orçaí ✅"
        )
        return True

    if "editar" in normalizar_texto(texto_limpo) or "alterar" in normalizar_texto(texto_limpo):
        enviar_mensagem(
            numero,
            "O que deseja editar?\n\n"
            "1 - Nome\n"
            "2 - Empresa\n"
            "3 - CNPJ\n"
            "4 - Telefone\n"
            "5 - E-mail\n"
            "6 - Endereço\n"
            "7 - Logo\n"
            "8 - Serviços"
        )
        usuarios[numero]["etapa"] = "menu_edicao"
        return True

    return False


# =========================
# MÍDIA
# =========================

def extensao_por_mime(mime_type):
    mime_type = str(mime_type or "").lower()

    if "png" in mime_type:
        return ".png"
    if "jpeg" in mime_type or "jpg" in mime_type:
        return ".jpg"
    if "webp" in mime_type:
        return ".webp"
    if "ogg" in mime_type or "opus" in mime_type:
        return ".ogg"
    if "mpeg" in mime_type or "mp3" in mime_type:
        return ".mp3"

    return ".bin"


def obter_info_midia(media_id):
    url = f"https://graph.facebook.com/v23.0/{media_id}"

    resposta = requests.get(
        url,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        timeout=60
    )

    print("\n====== INFO MÍDIA META ======")
    print(resposta.status_code)
    print(resposta.text)
    print("=============================\n")

    resposta.raise_for_status()
    return resposta.json()


def baixar_midia_meta(media_id, sufixo=None):
    info = obter_info_midia(media_id)

    url_midia = info.get("url")
    mime_type = info.get("mime_type", "")

    if not url_midia:
        raise Exception("Meta não retornou URL da mídia.")

    resposta = requests.get(
        url_midia,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        timeout=90
    )

    print("\n====== DOWNLOAD MÍDIA META ======")
    print(resposta.status_code)
    print(resposta.headers.get("Content-Type"))
    print("===============================\n")

    resposta.raise_for_status()

    if not sufixo:
        sufixo = extensao_por_mime(mime_type or resposta.headers.get("Content-Type"))

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=sufixo)
    temp.write(resposta.content)
    temp.close()

    return temp.name


def salvar_logo_meta(numero, media_id, tipo="image"):
    caminho_temp = baixar_midia_meta(media_id)

    ext = os.path.splitext(caminho_temp)[1].lower()

    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise Exception(f"Formato de logo não suportado: {ext}")

    nome_logo = (
        f"logo_{normalizar_numero(numero)}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    )

    caminho_logo = os.path.join(PASTA_LOGOS, nome_logo)

    with open(caminho_temp, "rb") as origem:
        conteudo = origem.read()

    with open(caminho_logo, "wb") as destino:
        destino.write(conteudo)

    if os.path.exists(caminho_temp):
        os.remove(caminho_temp)

    usuarios[numero]["cadastro"]["logo_path"] = caminho_logo
    usuarios[numero]["logo_path"] = caminho_logo

    salvar_cadastro_minimo(numero)
    atualizar_logo_empresa(numero, caminho_logo)

    return caminho_logo


# =========================
# PROCESSAMENTO PRINCIPAL
# =========================

def processar_texto(numero, texto):
    numero = normalizar_numero(numero)
    texto_limpo = str(texto or "").strip()

    carregar_usuario(numero)

    if not texto_limpo:
        enviar_mensagem(numero, "Não consegui entender. Pode repetir por texto ou mandar outro áudio?")
        return

    if normalizar_texto(texto_limpo) == "resetar":
        usuarios.pop(numero, None)
        enviar_mensagem(numero, "Cadastro resetado ✅\n\nMande Oi para começar de novo.")
        return

    etapa = usuarios[numero]["etapa"]

    if etapa == "lgpd":
        enviar_mensagem(numero, mensagem_lgpd())
        usuarios[numero]["etapa"] = "aguardando_lgpd"
        return

    if etapa == "aguardando_lgpd":
        if resposta_sim(texto_limpo):
            usuarios[numero]["cadastro"]["lgpd_aceito"] = True
            usuarios[numero]["etapa"] = "aguardando_nome"
            enviar_mensagem(numero, "Perfeito 😊\n\nQual é o seu nome?")
            return

        if resposta_nao(texto_limpo):
            usuarios[numero]["etapa"] = "encerrado"
            enviar_mensagem(numero, "Tudo bem. Sem sua autorização, não consigo gerar orçamentos por aqui.")
            return

        enviar_mensagem(numero, "Responda SIM para continuar ou NÃO para encerrar.")
        return

    if etapa == "aguardando_nome":
        usuarios[numero]["cadastro"]["nome_usuario"] = texto_limpo
        usuarios[numero]["cadastro"]["telefone"] = numero
        salvar_cadastro_minimo(numero)

        usuarios[numero]["etapa"] = "pronto"
        enviar_mensagem(numero, mensagem_primeiro_orcamento(texto_limpo))
        return

    if etapa == "aguardando_valores":
        dados = aplicar_valores_pendentes(numero, texto_limpo)
        dados = preencher_valores_servicos_cadastrados(numero, dados)
        faltando = itens_sem_valor(dados)

        if faltando:
            enviar_mensagem(numero, mensagem_pedir_valores(faltando))
            return

        usuarios[numero]["etapa"] = "confirmando_orcamento"
        enviar_mensagem(numero, resumo_confirmacao(dados))
        return

    if etapa == "confirmando_orcamento":
        if resposta_sim(texto_limpo):
            dados = usuarios[numero].get("orcamento_pendente")

            if not dados:
                usuarios[numero]["etapa"] = "pronto"
                enviar_mensagem(numero, "Nenhum orçamento pendente.")
                return

            primeiro_pdf = not usuarios[numero]["cadastro"].get("primeiro_pdf_gerado")

            enviar_mensagem(numero, "Gerando PDF...")

            caminho_pdf = gerar_pdf_orcamento(numero, dados)
            resposta_pdf = enviar_pdf(numero, caminho_pdf)

            time.sleep(2)

            if resposta_pdf is not None and resposta_pdf.status_code in [200, 201]:
                enviar_mensagem(numero, mensagem_pdf_gerado())
            else:
                enviar_mensagem(numero, "PDF gerado, mas tive problema ao enviar pelo WhatsApp.")

            if primeiro_pdf and not usuarios[numero]["cadastro"].get("perguntou_complemento"):
                usuarios[numero]["cadastro"]["perguntou_complemento"] = True
                usuarios[numero]["etapa"] = "pos_primeiro_pdf"
                time.sleep(1)
                enviar_mensagem(numero, mensagem_pos_primeiro_pdf())
            else:
                usuarios[numero]["etapa"] = "pronto"

            return

        if resposta_nao(texto_limpo):
            usuarios[numero]["etapa"] = "pronto"
            usuarios[numero].pop("orcamento_pendente", None)
            enviar_mensagem(numero, "Sem problema 😊\n\nMe envie novamente os dados do orçamento com as correções.")
            return

        enviar_mensagem(numero, "Responda SIM para gerar o PDF ou NÃO para corrigir.")
        return

    if etapa == "pos_primeiro_pdf":
        if resposta_sim(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_empresa"
            enviar_mensagem(
                numero,
                "Ótimo 😊\n\n"
                "Qual nome da empresa você quer exibir nos orçamentos?\n\n"
                "Se não quiser colocar agora, responda PULAR."
            )
            return

        if resposta_nao(texto_limpo) or resposta_pular(texto_limpo):
            usuarios[numero]["etapa"] = "perguntar_servicos"
            enviar_mensagem(numero, mensagem_perguntar_servicos())
            return

        enviar_mensagem(numero, "Responda SIM para continuar ou NÃO para deixar para depois.")
        return

    if etapa == "complementar_empresa":
        if not resposta_pular(texto_limpo):
            usuarios[numero]["cadastro"]["nome_empresa"] = texto_limpo
            usuarios[numero]["empresa"] = texto_limpo

        usuarios[numero]["etapa"] = "complementar_logo_pergunta"
        enviar_mensagem(
            numero,
            "Deseja adicionar a logo da sua empresa nos orçamentos?\n\n"
            "Responda SIM ou NÃO."
        )
        return

    if etapa == "complementar_logo_pergunta":
        if resposta_sim(texto_limpo):
            usuarios[numero]["etapa"] = "aguardando_logo"
            usuarios[numero]["voltar_para"] = "complementar_cnpj_pergunta"
            enviar_mensagem(numero, "Perfeito 😊\n\nMe envie a logo da sua empresa em imagem PNG ou JPG.")
            return

        if resposta_nao(texto_limpo) or resposta_pular(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_cnpj_pergunta"
            enviar_mensagem(
                numero,
                "Deseja exibir CNPJ nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        enviar_mensagem(numero, "Responda SIM para adicionar logo ou NÃO para pular.")
        return

    if etapa == "aguardando_logo":
        enviar_mensagem(numero, "Me envie a imagem da logo em PNG ou JPG.")
        return

    if etapa == "complementar_cnpj_pergunta":
        if resposta_sim(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_cnpj"
            enviar_mensagem(numero, "Perfeito. Me envie o CNPJ com 14 números.")
            return

        if resposta_nao(texto_limpo) or resposta_pular(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_email_pergunta"
            enviar_mensagem(
                numero,
                "Deseja exibir e-mail nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        if validar_cnpj(texto_limpo):
            usuarios[numero]["cadastro"]["cnpj"] = apenas_numeros(texto_limpo)
            usuarios[numero]["cnpj"] = apenas_numeros(texto_limpo)
            usuarios[numero]["etapa"] = "complementar_email_pergunta"
            enviar_mensagem(
                numero,
                "CNPJ salvo ✅\n\n"
                "Deseja exibir e-mail nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        enviar_mensagem(numero, "Responda SIM para informar o CNPJ ou NÃO para pular.")
        return

    if etapa == "complementar_cnpj":
        if validar_cnpj(texto_limpo):
            usuarios[numero]["cadastro"]["cnpj"] = apenas_numeros(texto_limpo)
            usuarios[numero]["cnpj"] = apenas_numeros(texto_limpo)
            usuarios[numero]["etapa"] = "complementar_email_pergunta"
            enviar_mensagem(
                numero,
                "CNPJ salvo ✅\n\n"
                "Deseja exibir e-mail nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        if resposta_pular(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_email_pergunta"
            enviar_mensagem(
                numero,
                "Tudo bem.\n\n"
                "Deseja exibir e-mail nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        enviar_mensagem(numero, "Esse CNPJ parece incompleto. Envie com 14 números ou responda PULAR.")
        return

    if etapa == "complementar_email_pergunta":
        if resposta_sim(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_email"
            enviar_mensagem(numero, "Perfeito. Me envie o e-mail.")
            return

        if resposta_nao(texto_limpo) or resposta_pular(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_endereco_pergunta"
            enviar_mensagem(
                numero,
                "Deseja exibir endereço nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        if validar_email(texto_limpo):
            usuarios[numero]["cadastro"]["email"] = texto_limpo
            usuarios[numero]["email"] = texto_limpo
            usuarios[numero]["etapa"] = "complementar_endereco_pergunta"
            enviar_mensagem(
                numero,
                "E-mail salvo ✅\n\n"
                "Deseja exibir endereço nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        enviar_mensagem(numero, "Responda SIM para informar o e-mail ou NÃO para pular.")
        return

    if etapa == "complementar_email":
        if validar_email(texto_limpo):
            usuarios[numero]["cadastro"]["email"] = texto_limpo
            usuarios[numero]["email"] = texto_limpo
            usuarios[numero]["etapa"] = "complementar_endereco_pergunta"
            enviar_mensagem(
                numero,
                "E-mail salvo ✅\n\n"
                "Deseja exibir endereço nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        if resposta_pular(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_endereco_pergunta"
            enviar_mensagem(
                numero,
                "Tudo bem.\n\n"
                "Deseja exibir endereço nos orçamentos?\n\n"
                "Responda SIM ou NÃO."
            )
            return

        enviar_mensagem(numero, "Esse e-mail parece inválido. Envie novamente ou responda PULAR.")
        return

    if etapa == "complementar_endereco_pergunta":
        if resposta_sim(texto_limpo):
            usuarios[numero]["etapa"] = "complementar_endereco"
            enviar_mensagem(numero, "Perfeito. Me envie o endereço que deve aparecer nos orçamentos.")
            return

        if resposta_nao(texto_limpo) or resposta_pular(texto_limpo):
            salvar_cadastro_minimo(numero)
            usuarios[numero]["etapa"] = "perguntar_servicos"
            enviar_mensagem(numero, "Dados atualizados ✅\n\n" + mensagem_perguntar_servicos())
            return

        usuarios[numero]["cadastro"]["endereco"] = texto_limpo
        usuarios[numero]["endereco"] = texto_limpo
        salvar_cadastro_minimo(numero)
        usuarios[numero]["etapa"] = "perguntar_servicos"
        enviar_mensagem(numero, "Endereço salvo ✅\n\n" + mensagem_perguntar_servicos())
        return

    if etapa == "complementar_endereco":
        if not resposta_pular(texto_limpo):
            usuarios[numero]["cadastro"]["endereco"] = texto_limpo
            usuarios[numero]["endereco"] = texto_limpo

        salvar_cadastro_minimo(numero)
        usuarios[numero]["etapa"] = "perguntar_servicos"
        enviar_mensagem(numero, "Dados atualizados ✅\n\n" + mensagem_perguntar_servicos())
        return

    if etapa == "perguntar_servicos":
        if resposta_sim(texto_limpo):
            usuarios[numero]["etapa"] = "cadastrar_servicos"
            enviar_mensagem(numero, mensagem_cadastrar_servicos())
            return

        if resposta_nao(texto_limpo) or resposta_pular(texto_limpo):
            usuarios[numero]["etapa"] = "pronto"
            enviar_mensagem(
                numero,
                "Fechado ✅\n\n"
                "Quando quiser gerar um orçamento, me envie por texto ou áudio.\n\n"
                f"Exemplo:\n{exemplo_orcamento_com_servicos(numero)}"
            )
            return

        enviar_mensagem(numero, "Responda SIM para cadastrar serviços ou NÃO para deixar para depois.")
        return

    if etapa == "cadastrar_servicos":
        servicos = parse_servicos(texto_limpo)

        if not servicos:
            servicos = interpretar_servicos_com_ia(texto_limpo)

        if not servicos:
            enviar_mensagem(
                numero,
                "Não consegui identificar os serviços.\n\n"
                "Envie assim:\n"
                "Nome do serviço/produto - valor\n"
                "Nome do serviço/produto - valor"
            )
            return

        usuarios[numero]["servicos_pendentes"] = servicos
        usuarios[numero]["etapa"] = "confirmar_servicos"
        enviar_mensagem(numero, resumo_servicos(servicos))
        return

    if etapa == "confirmar_servicos":
        if resposta_sim(texto_limpo):
            servicos = usuarios[numero].pop("servicos_pendentes", {})

            if not usuarios[numero].get("empresa_id"):
                salvar_cadastro_minimo(numero)

            salvar_servicos(usuarios[numero]["empresa_id"], servicos)

            usuarios[numero]["servicos"] = buscar_servicos_empresa(
                usuarios[numero]["empresa_id"]
)

            usuarios[numero]["etapa"] = "pronto"
            enviar_mensagem(numero, mensagem_final_servicos(numero))
            return

        if resposta_nao(texto_limpo):
            usuarios[numero].pop("servicos_pendentes", None)
            usuarios[numero]["etapa"] = "cadastrar_servicos"
            enviar_mensagem(numero, "Sem problema. Me envie novamente os serviços com os valores.")
            return

        enviar_mensagem(numero, "Responda SIM para salvar ou NÃO para corrigir.")
        return

    if etapa == "menu_edicao":
        opcoes = {
            "1": "editar_nome",
            "2": "editar_empresa",
            "3": "editar_cnpj",
            "4": "editar_telefone",
            "5": "editar_email",
            "6": "editar_endereco",
            "7": "aguardando_logo",
            "8": "cadastrar_servicos",
        }

        nova_etapa = opcoes.get(normalizar_texto(texto_limpo))

        if not nova_etapa:
            enviar_mensagem(numero, "Escolha uma opção de 1 a 8.")
            return

        usuarios[numero]["etapa"] = nova_etapa

        if nova_etapa == "aguardando_logo":
            enviar_mensagem(numero, "Me envie a imagem da logo em PNG ou JPG.")
        elif nova_etapa == "cadastrar_servicos":
            enviar_mensagem(numero, mensagem_cadastrar_servicos())
        else:
            enviar_mensagem(numero, "Me envie a nova informação.")

        return

    if etapa.startswith("editar_"):
        campo = etapa.replace("editar_", "")

        if campo == "cnpj" and not validar_cnpj(texto_limpo):
            enviar_mensagem(numero, "Esse CNPJ parece inválido. Envie com 14 números.")
            return

        if campo == "email" and not validar_email(texto_limpo):
            enviar_mensagem(numero, "Esse e-mail parece inválido. Envie novamente.")
            return

        if campo == "telefone" and not validar_telefone(texto_limpo):
            enviar_mensagem(numero, "Esse telefone parece inválido. Envie com DDD.")
            return

        if campo == "nome":
            usuarios[numero]["cadastro"]["nome_usuario"] = texto_limpo
            usuarios[numero]["responsavel"] = texto_limpo
        elif campo == "empresa":
            usuarios[numero]["cadastro"]["nome_empresa"] = texto_limpo
            usuarios[numero]["empresa"] = texto_limpo
        elif campo == "cnpj":
            usuarios[numero]["cadastro"]["cnpj"] = apenas_numeros(texto_limpo)
            usuarios[numero]["cnpj"] = apenas_numeros(texto_limpo)
        elif campo == "telefone":
            usuarios[numero]["cadastro"]["telefone"] = texto_limpo
            usuarios[numero]["telefone"] = texto_limpo
        elif campo == "email":
            usuarios[numero]["cadastro"]["email"] = texto_limpo
            usuarios[numero]["email"] = texto_limpo
        elif campo == "endereco":
            usuarios[numero]["cadastro"]["endereco"] = texto_limpo
            usuarios[numero]["endereco"] = texto_limpo

        salvar_cadastro_minimo(numero)
        usuarios[numero]["etapa"] = "pronto"
        enviar_mensagem(numero, "Informação atualizada ✅")
        return

    if etapa == "pronto":
        if eh_saudacao(texto_limpo):
            enviar_mensagem(numero, mensagem_pedir_orcamento(numero))
            return

        if parece_pedido_orcamento_com_dados(texto_limpo):
            processar_pedido_orcamento(numero, texto_limpo)
            return

        if processar_comando(numero, texto_limpo):
            return

        processar_pedido_orcamento(numero, texto_limpo)
        return

    if etapa == "encerrado":
        enviar_mensagem(
            numero,
            "Para usar o Orçaí, preciso da autorização de uso dos dados. Se quiser continuar, responda SIM."
        )
        usuarios[numero]["etapa"] = "aguardando_lgpd"
        return


# =========================
# WEBHOOK
# =========================

def extrair_texto_mensagem(payload):
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return None, None, None, None

        mensagem = value["messages"][0]

        numero = mensagem.get("from", "")
        texto = ""
        media_id = None
        tipo = mensagem.get("type")

        if tipo == "text":
            texto = mensagem["text"]["body"]
        elif tipo == "audio":
            media_id = mensagem["audio"]["id"]
        elif tipo == "image":
            media_id = mensagem["image"]["id"]
        elif tipo == "document":
            media_id = mensagem["document"]["id"]

        return normalizar_numero(numero), texto, media_id, tipo

    except Exception as erro:
        print("ERRO AO LER PAYLOAD META:", erro)
        return None, None, None, None


@app.get("/")
def home():
    return {"status": "Orçaí rodando com Meta Cloud API"}


@app.get("/webhook")
async def verificar_webhook(request: Request):
    params = dict(request.query_params)

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)

    return PlainTextResponse("Token inválido", status_code=403)


@app.get("/arquivos/{nome_arquivo}")
def servir_arquivo(nome_arquivo: str):
    caminho = os.path.join(PASTA_ARQUIVOS, nome_arquivo)

    if os.path.exists(caminho):
        return FileResponse(caminho, media_type="application/pdf", filename=nome_arquivo)

    return {"erro": "arquivo não encontrado"}


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()

    print("\n====== WEBHOOK META ======")
    print(payload)
    print("==========================\n")

    numero, texto, media_id, tipo = extrair_texto_mensagem(payload)

    if not numero:
        return {"status": "ignorado"}

    carregar_usuario(numero)

    if tipo == "audio" and media_id:
        try:
            enviar_mensagem(numero, "Transcrevendo áudio...")

            caminho_audio = baixar_midia_meta(media_id, ".ogg")
            texto = transcrever_audio(caminho_audio)

            print("\n====== TEXTO TRANSCRITO DO ÁUDIO ======")
            print(texto)
            print("=======================================\n")

            if os.path.exists(caminho_audio):
                os.remove(caminho_audio)

            if texto_transcricao_invalido(texto):
                enviar_mensagem(
                    numero,
                    "Não consegui entender esse áudio. Pode mandar novamente ou escrever a mensagem?"
                )
                return {"status": "audio_vazio"}

        except Exception as erro:
            print("ERRO ÁUDIO:", erro)
            enviar_mensagem(numero, "Erro ao transcrever áudio.")
            return {"status": "erro_audio"}

    elif tipo in ["image", "document"] and media_id:
        try:
            if usuarios[numero]["etapa"] == "aguardando_logo":
                salvar_logo_meta(numero, media_id, tipo)

                proxima = usuarios[numero].pop("voltar_para", None)

                if proxima:
                    usuarios[numero]["etapa"] = proxima
                    enviar_mensagem(
                        numero,
                        "Logo salva ✅\n\n"
                        "Deseja exibir CNPJ nos orçamentos?\n\n"
                        "Responda SIM ou NÃO."
                    )
                else:
                    usuarios[numero]["etapa"] = "pronto"
                    enviar_mensagem(numero, "Logo salva ✅\n\nEla será usada nos próximos orçamentos.")
            else:
                enviar_mensagem(
                    numero,
                    "Recebi o arquivo 😊\n\n"
                    "Se quiser adicionar isso como logo, me mande: quero adicionar minha logo."
                )

            return {"status": "ok"}

        except Exception as erro:
            print("ERRO LOGO:", erro)
            enviar_mensagem(numero, "Não consegui salvar essa imagem. Tente enviar em PNG ou JPG.")
            return {"status": "erro_logo"}

    if texto:
        try:
            processar_texto(numero, texto)
        except Exception as erro:
            print("\n====== ERRO AO PROCESSAR TEXTO ======")
            print(erro)
            traceback.print_exc()
            print("=====================================\n")

            enviar_mensagem(
                numero,
                "Tive um erro ao processar sua mensagem. Pode tentar mandar de novo?"
            )

    return {"status": "ok"}