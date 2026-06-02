from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters
)

from interpretador_ia import (
    interpretar_cadastro,
    normalizar_dados_orcamento_ia,
    corrigir_itens_orcamento
)

from ai_client import interpretar_orcamento_com_ia

from transcricao_audio import (
    baixar_audio_telegram,
    transcrever_audio
)

from orcamento import (
    gerar_orcamento
)

from banco import (
    criar_tabelas,
    salvar_empresa,
    buscar_empresa_por_telegram,
    salvar_servicos,
    buscar_servicos_empresa,
    salvar_orcamento
)

from difflib import get_close_matches

import os
import re


TOKEN = "SEU_TOKEN_AQUI"

usuarios = {}


# =====================================================
# UTILITÁRIOS
# =====================================================

def apenas_numeros(texto):
    return re.sub(r"\D", "", texto or "")


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

    return cnpj


def formatar_telefone(telefone):

    numeros = apenas_numeros(telefone)

    if len(numeros) == 11:

        return (
            f"({numeros[:2]}) "
            f"{numeros[2:7]}-"
            f"{numeros[7:]}"
        )

    return telefone


def formatar_endereco(endereco):

    endereco = endereco.strip()

    endereco = re.sub(
        r"\bav\b",
        "Av.",
        endereco,
        flags=re.IGNORECASE
    )

    endereco = re.sub(
        r"\brua\b",
        "Rua",
        endereco,
        flags=re.IGNORECASE
    )

    return endereco.title()


def validar_cnpj(cnpj):

    numeros = apenas_numeros(cnpj)

    return len(numeros) == 14


def normalizar_texto(texto):

    return (
        texto.lower()
        .strip()
        .replace("-", " ")
    )


# =====================================================
# SERVIÇOS
# =====================================================

def parse_servicos(texto):

    servicos = {}

    linhas = texto.splitlines()

    for linha in linhas:

        if "-" not in linha:
            continue

        try:

            nome, valor = linha.split("-", 1)

            nome_original = nome.strip()

            chave = normalizar_texto(
                nome_original
            )

            valor = (
                valor.strip()
                .replace(",", ".")
            )

            servicos[chave] = {
                "nome": nome_original,
                "valor": float(valor)
            }

        except:
            pass

    return servicos


def eh_lista_de_servicos_valida(texto):
    return "-" in texto


def gerar_exemplo_orcamento(
    tabela_servicos
):

    lista = list(
        tabela_servicos.values()
    )

    if len(lista) >= 2:

        s1 = lista[0]["nome"]
        s2 = lista[1]["nome"]

        return (
            "Cadastro concluído com sucesso ✅\n\n"

            "Agora envie o orçamento de forma livre.\n\n"

            "Exemplo:\n\n"

            "Preciso de um orçamento para João da Silva\n"
            "65999998888\n"
            f"{s1} 2\n"
            f"{s2} 1\n"
            "material 50\n"
            "observação orçamento solicitado via WhatsApp"
        )

    return (
        "Cadastro concluído com sucesso ✅"
    )


# =====================================================
# CONFIRMAÇÃO
# =====================================================

def formatar_resumo_confirmacao(
    dados_orc
):

    texto = (
        "Entendi o seguinte orçamento:\n\n"
    )

    texto += (
        f"👤 Cliente: "
        f"{dados_orc.get('cliente', '')}\n"
    )

    texto += (
        f"📞 Telefone: "
        f"{dados_orc.get('telefone_cliente', '')}\n\n"
    )

    texto += "🛠 Serviços:\n"

    for item in dados_orc.get(
        "itens",
        []
    ):

        texto += (
            f"- {item['servico']} "
            f"(Qtd: {item['quantidade']})\n"
        )

    texto += (
        f"\n💰 Materiais adicionais: "
        f"R$ {dados_orc.get('materiais_adicionais', 0)}"
    )

    observacao = dados_orc.get(
        "observacao",
        ""
    )

    if observacao:

        texto += (
            f"\n📝 Observação: "
            f"{observacao}"
        )

    texto += (
        "\n\nEstá correto?\n"
        "✅ sim\n"
        "❌ não"
    )

    return texto


# =====================================================
# GERAR ORÇAMENTO
# =====================================================

async def gerar_orcamento_completo(
    update,
    dados_orc,
    user_id
):

    dados_empresa = {

        "responsavel":
            usuarios[user_id]["responsavel"],

        "empresa":
            usuarios[user_id]["empresa"],

        "cnpj":
            usuarios[user_id]["cnpj"],

        "telefone":
            usuarios[user_id]["telefone"],

        "email":
            usuarios[user_id]["email"],

        "endereco":
            usuarios[user_id]["endereco"],
    }

    tabela_servicos = usuarios[user_id].get(
        "servicos",
        {}
    )

    caminho_pdf = gerar_orcamento(

        dados_orcamento=dados_orc,

        dados_empresa=dados_empresa,

        tabela_servicos=tabela_servicos

    )

    # =====================================
    # SALVAR NO MYSQL
    # =====================================

    empresa_db = buscar_empresa_por_telegram(
        user_id
    )

    if empresa_db:

        salvar_orcamento(

            empresa_db["id"],

            dados_orc,

            tabela_servicos,

            caminho_pdf

        )

    # =====================================

    await update.message.reply_text(
        "Orçamento gerado com sucesso ✅"
    )

    with open(caminho_pdf, "rb") as pdf:

        await update.message.reply_document(
            document=pdf
        )

    # se quiser manter histórico físico
    # comenta essa linha
    # os.remove(caminho_pdf)


# =====================================================
# TEXTO
# =====================================================

async def receber_mensagem(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.message.chat_id
    texto = update.message.text.strip()

    # =====================================
    # PRIMEIRO ACESSO
    # =====================================

    if user_id not in usuarios:

        empresa_db = buscar_empresa_por_telegram(
            user_id
        )

        if empresa_db:

            usuarios[user_id] = {

                "etapa": "concluido",

                "empresa_id":
                    empresa_db["id"],

                "responsavel":
                    empresa_db["responsavel"],

                "empresa":
                    empresa_db["empresa"],

                "cnpj":
                    empresa_db["cnpj"],

                "telefone":
                    empresa_db["telefone"],

                "email":
                    empresa_db["email"],

                "endereco":
                    empresa_db["endereco"],

                "servicos":
                    buscar_servicos_empresa(
                        empresa_db["id"]
                    )
            }

            await update.message.reply_text(
                "Bem-vindo de volta 😄"
            )

            return

        usuarios[user_id] = {
            "etapa": "responsavel"
        }

        await update.message.reply_text(
            "Olá! Eu sou o Orçai 🤖"
        )

        await update.message.reply_text(
            "Qual é o seu nome?"
        )

        return

    etapa = usuarios[user_id]["etapa"]

    # =====================================
    # CONFIRMAÇÃO
    # =====================================

    if etapa == "confirmando_orcamento":

        resposta = texto.lower().strip()

        if resposta in [
            "sim",
            "s",
            "ok",
            "confirmar"
        ]:

            dados_orc = usuarios[user_id].get(
                "orcamento_pendente"
            )

            usuarios[user_id]["etapa"] = (
                "concluido"
            )

            await gerar_orcamento_completo(
                update,
                dados_orc,
                user_id
            )

            return

        elif resposta in [
            "nao",
            "não"
        ]:

            usuarios[user_id]["etapa"] = (
                "concluido"
            )

            await update.message.reply_text(
                "Pode enviar novamente 😊"
            )

            return

    # =====================================
    # CADASTRO
    # =====================================

    if etapa == "responsavel":

        usuarios[user_id]["responsavel"] = (
            interpretar_cadastro(
                texto,
                "nome"
            )
        )

        usuarios[user_id]["etapa"] = "empresa"

        await update.message.reply_text(
            "Qual é o nome da sua empresa?"
        )

        return

    if etapa == "empresa":

        usuarios[user_id]["empresa"] = (
            interpretar_cadastro(
                texto,
                "empresa"
            )
        )

        usuarios[user_id]["etapa"] = "cnpj"

        await update.message.reply_text(
            "Qual é o CNPJ da sua empresa?"
        )

        return

    if etapa == "cnpj":

        valor = interpretar_cadastro(
            texto,
            "cnpj"
        )

        valor = formatar_cnpj(valor)

        if not validar_cnpj(valor):

            await update.message.reply_text(
                "CNPJ inválido."
            )

            return

        usuarios[user_id]["cnpj"] = valor

        usuarios[user_id]["etapa"] = "telefone"

        await update.message.reply_text(
            "Qual é o telefone da sua empresa?"
        )

        return

    if etapa == "telefone":

        valor = interpretar_cadastro(
            texto,
            "telefone"
        )

        usuarios[user_id]["telefone"] = (
            formatar_telefone(valor)
        )

        usuarios[user_id]["etapa"] = "email"

        await update.message.reply_text(
            "Qual é o e-mail da sua empresa?"
        )

        return

    if etapa == "email":

        usuarios[user_id]["email"] = (
            interpretar_cadastro(
                texto,
                "email"
            )
        )

        usuarios[user_id]["etapa"] = "endereco"

        await update.message.reply_text(
            "Qual é o endereço da sua empresa?"
        )

        return

    if etapa == "endereco":

        valor = interpretar_cadastro(
            texto,
            "endereco"
        )

        usuarios[user_id]["endereco"] = (
            formatar_endereco(valor)
        )

        usuarios[user_id]["etapa"] = "servicos"

        await update.message.reply_text(
            "Agora envie TODOS os serviços "
            "com seus valores.\n\n"

            "Exemplo:\n"
            "Criação de chatbot - 500\n"
            "Automação WhatsApp - 300"
        )

        return

    if etapa == "servicos":

        if not eh_lista_de_servicos_valida(
            texto
        ):

            await update.message.reply_text(
                "Formato inválido."
            )

            return

        servicos = parse_servicos(texto)

        if not servicos:

            await update.message.reply_text(
                "Não consegui ler."
            )

            return

        usuarios[user_id]["servicos"] = (
            servicos
        )

        # =====================================
        # SALVAR MYSQL
        # =====================================

        empresa_id = salvar_empresa(

            user_id,

            usuarios[user_id]["responsavel"],

            usuarios[user_id]["empresa"],

            usuarios[user_id]["cnpj"],

            usuarios[user_id]["telefone"],

            usuarios[user_id]["email"],

            usuarios[user_id]["endereco"]

        )

        salvar_servicos(
            empresa_id,
            servicos
        )

        usuarios[user_id]["empresa_id"] = (
            empresa_id
        )

        # =====================================

        usuarios[user_id]["etapa"] = (
            "concluido"
        )

        await update.message.reply_text(
            gerar_exemplo_orcamento(
                servicos
            )
        )

        return

    # =====================================
    # IA
    # =====================================

    if etapa == "concluido":

        tabela_servicos = usuarios[user_id].get(
            "servicos",
            {}
        )

        dados_orc = (
            interpretar_orcamento_com_ia(
                texto,
                tabela_servicos
            )
        )

        dados_orc = (
            normalizar_dados_orcamento_ia(
                dados_orc
            )
        )

        dados_orc = (
            corrigir_itens_orcamento(
                dados_orc,
                tabela_servicos
            )
        )

        usuarios[user_id][
            "orcamento_pendente"
        ] = dados_orc

        usuarios[user_id]["etapa"] = (
            "confirmando_orcamento"
        )

        await update.message.reply_text(
            formatar_resumo_confirmacao(
                dados_orc
            )
        )


# =====================================================
# ÁUDIO
# =====================================================

async def receber_audio(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.message.chat_id

    if user_id not in usuarios:

        await update.message.reply_text(
            "Faça seu cadastro primeiro."
        )

        return

    await update.message.reply_text(
        "Recebi seu áudio 🎙️"
    )

    try:

        file_id = (
            update.message.voice.file_id
        )

        caminho_audio = (
            await baixar_audio_telegram(
                context.bot,
                file_id
            )
        )

        texto_transcrito = (
            transcrever_audio(
                caminho_audio
            )
        )

        if not texto_transcrito:

            await update.message.reply_text(
                "Não consegui entender."
            )

            return

        await update.message.reply_text(
            "Áudio transcrito 🎙️\n\n"
            f"{texto_transcrito}"
        )

        tabela_servicos = usuarios[user_id].get(
            "servicos",
            {}
        )

        dados_orc = (
            interpretar_orcamento_com_ia(
                texto_transcrito,
                tabela_servicos
            )
        )

        dados_orc = (
            normalizar_dados_orcamento_ia(
                dados_orc
            )
        )

        dados_orc = (
            corrigir_itens_orcamento(
                dados_orc,
                tabela_servicos
            )
        )

        usuarios[user_id][
            "orcamento_pendente"
        ] = dados_orc

        usuarios[user_id]["etapa"] = (
            "confirmando_orcamento"
        )

        await update.message.reply_text(
            formatar_resumo_confirmacao(
                dados_orc
            )
        )

    except Exception as erro:

        print(erro)

        await update.message.reply_text(
            "Erro ao processar áudio 😢"
        )


# =====================================================
# INICIAR
# =====================================================

criar_tabelas()

app = (
    ApplicationBuilder()
    .token(TOKEN)
    .build()
)

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        receber_mensagem
    )
)

app.add_handler(
    MessageHandler(
        filters.VOICE,
        receber_audio
    )
)

print("Bot Orçai rodando...")

app.run_polling()