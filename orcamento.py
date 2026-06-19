from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from datetime import datetime
import os
import re


AZUL = colors.HexColor("#003B8F")
AZUL_ESCURO = colors.HexColor("#00245C")
VERDE = colors.HexColor("#18C95A")
VERDE_ESCURO = colors.HexColor("#0E9F43")
CINZA_TEXTO = colors.HexColor("#1F2937")
CINZA_BORDA = colors.HexColor("#D9E2EF")

ORCAI_LINK = os.getenv("ORCAI_LINK", "https://wa.me/556599230983")


def normalizar_texto(texto):
    texto = (texto or "").strip().lower()
    return re.sub(r"\s+", " ", texto)


def safe_texto(valor, padrao="-"):
    valor = str(valor or "").strip()
    return valor if valor else padrao


def formatar_nome_visual(texto):
    if not texto:
        return ""

    minusculas = {"de", "da", "do", "das", "dos", "e"}
    palavras = str(texto).split()
    resultado = []

    for i, palavra in enumerate(palavras):
        if palavra.upper() == palavra and len(palavra) <= 4:
            resultado.append(palavra.upper())
        elif palavra.lower() in minusculas and i != 0:
            resultado.append(palavra.lower())
        else:
            resultado.append(palavra.capitalize())

    return " ".join(resultado)


def formatar_telefone(telefone):
    numeros = re.sub(r"\D", "", telefone or "")

    if len(numeros) == 13 and numeros.startswith("55"):
        numeros = numeros[2:]

    if len(numeros) == 11:
        return f"({numeros[:2]}) {numeros[2:7]}-{numeros[7:]}"

    if len(numeros) == 10:
        return f"({numeros[:2]}) {numeros[2:6]}-{numeros[6:]}"

    return telefone or ""


def formatar_cnpj(cnpj):
    numeros = re.sub(r"\D", "", cnpj or "")

    if len(numeros) == 14:
        return (
            f"{numeros[:2]}."
            f"{numeros[2:5]}."
            f"{numeros[5:8]}/"
            f"{numeros[8:12]}-"
            f"{numeros[12:]}"
        )

    return cnpj or ""


def formatar_moeda(valor):
    try:
        valor = float(valor or 0)
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _encontrar_servico_tabela(servico_digitado, tabela_servicos):
    chave = normalizar_texto(servico_digitado)

    if chave in tabela_servicos:
        return tabela_servicos[chave]

    for k, v in tabela_servicos.items():
        if chave and chave in normalizar_texto(k):
            return v

    for k, v in tabela_servicos.items():
        tokens = normalizar_texto(k).split()
        if chave and any(token.startswith(chave) for token in tokens):
            return v

    return None


def _criar_estilos():
    styles = getSampleStyleSheet()

    return {
        "titulo": ParagraphStyle(
            "Titulo",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=30,
            textColor=AZUL_ESCURO,
            alignment=1,
        ),
        "subtitulo": ParagraphStyle(
            "Subtitulo",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            textColor=CINZA_TEXTO,
            alignment=1,
        ),
        "secao_azul": ParagraphStyle(
            "SecaoAzul",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=AZUL,
            spaceAfter=10,
        ),
        "secao_verde": ParagraphStyle(
            "SecaoVerde",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=VERDE_ESCURO,
            spaceAfter=10,
        ),
        "normal": ParagraphStyle(
            "Normal",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=11.5,
            leading=16,
            textColor=CINZA_TEXTO,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=16,
            textColor=CINZA_TEXTO,
        ),
        "tabela_header": ParagraphStyle(
            "TabelaHeader",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.white,
        ),
        "tabela_item": ParagraphStyle(
            "TabelaItem",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=CINZA_TEXTO,
        ),
        "rodape": ParagraphStyle(
            "Rodape",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.white,
        ),
        "rodape_link": ParagraphStyle(
            "RodapeLink",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=AZUL_ESCURO,
        ),
    }


def _linha_dados(rotulo, valor):
    return [
        Paragraph(f"<b>{rotulo}</b>", _ESTILOS["label"]),
        Paragraph(safe_texto(valor), _ESTILOS["normal"]),
    ]


def _card_tabela(titulo, dados, cor_titulo=AZUL):
    titulo_style = _ESTILOS["secao_azul"] if cor_titulo == AZUL else _ESTILOS["secao_verde"]

    tabela = Table(
        [
            [Paragraph(titulo, titulo_style)],
            [dados],
        ],
        colWidths=[17.2 * cm]
    )

    tabela.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, CINZA_BORDA),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
        ("TOPPADDING", (0, 0), (-1, -1), 13),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
    ]))

    return tabela


def _montar_logo_empresa(dados_empresa):
    logo_path = (
        dados_empresa.get("logo")
        or dados_empresa.get("logo_path")
        or dados_empresa.get("caminho_logo")
    )

    if logo_path and os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=3.6 * cm, height=1.8 * cm)
            img.hAlign = "LEFT"
            return img
        except Exception:
            pass

    empresa = safe_texto(dados_empresa.get("empresa"), "")
    if not empresa:
        empresa = "Orçamento"

    return Paragraph(
        f"<b>{empresa}</b>",
        ParagraphStyle(
            "EmpresaLogoTexto",
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=AZUL,
        )
    )


def _footer_final(dados_empresa):
    telefone = formatar_telefone(dados_empresa.get("telefone", ""))

    bloco_contato = (
        "<b>Atendimento via WhatsApp</b><br/>"
        "Fale conosco agora mesmo"
    )

    if telefone:
        bloco_contato += f"<br/><br/><b>{telefone}</b>"

    bloco_orcai = (
        f"<b><a href='{ORCAI_LINK}' color='#00245C'>Gerado pelo Orçaí</a></b><br/>"
        f"<a href='{ORCAI_LINK}' color='#00245C'>Clique aqui para criar orçamentos pelo WhatsApp</a>"
    )

    footer = Table(
        [[
            Paragraph(bloco_contato, _ESTILOS["rodape"]),
            Paragraph(bloco_orcai, _ESTILOS["rodape_link"]),
        ]],
        colWidths=[8.2 * cm, 8.2 * cm]
    )

    footer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), AZUL_ESCURO),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F0FFF6")),
        ("BOX", (1, 0), (1, 0), 0.8, VERDE),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 15),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    texto_final = Paragraph(
        "<font color='#64748B'>Documento gerado automaticamente pelo Orçaí</font>",
        ParagraphStyle(
            "TextoFinal",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            alignment=1,
        )
    )

    return [
        Spacer(1, 20),
        footer,
        Spacer(1, 7),
        texto_final,
    ]


def gerar_orcamento(dados_orcamento, dados_empresa, tabela_servicos, nome_arquivo="orcamento.pdf"):
    global _ESTILOS
    _ESTILOS = _criar_estilos()

    itens_processados = []
    subtotal_servicos = 0.0

    for item in dados_orcamento.get("itens", []):
        servico_digitado = item.get("servico", "Serviço")
        info_servico = _encontrar_servico_tabela(servico_digitado, tabela_servicos)

        if info_servico:
            valor_unitario = float(info_servico.get("valor", 0))
            nome_servico = info_servico.get("nome", servico_digitado)
        else:
            valor_unitario = float(item.get("valor_unitario") or 0)
            nome_servico = servico_digitado

        try:
            quantidade = int(item.get("quantidade", 1) or 1)
        except Exception:
            quantidade = 1

        subtotal = valor_unitario * quantidade
        subtotal_servicos += subtotal

        itens_processados.append({
            "servico": nome_servico,
            "quantidade": quantidade,
            "valor_unitario": valor_unitario,
            "subtotal": subtotal,
        })

    try:
        materiais = float(str(dados_orcamento.get("materiais_adicionais", 0)).replace(",", "."))
    except Exception:
        materiais = 0.0

    valor_total = subtotal_servicos + materiais
    data_emissao = datetime.now().strftime("%d/%m/%Y %H:%M")

    doc = SimpleDocTemplate(
        nome_arquivo,
        pagesize=A4,
        rightMargin=1.3 * cm,
        leftMargin=1.3 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.4 * cm,
    )

    elementos = []

    responsavel = formatar_nome_visual(dados_empresa.get("responsavel", ""))
    empresa = formatar_nome_visual(dados_empresa.get("empresa", ""))
    cliente = formatar_nome_visual(dados_orcamento.get("cliente", ""))
    telefone_cliente = formatar_telefone(dados_orcamento.get("telefone_cliente", ""))

    logo_ou_nome = _montar_logo_empresa(dados_empresa)

    header_info = Table(
        [[
            logo_ou_nome,
            Paragraph(
                "<b>ORÇAMENTO</b><br/><font size='12'>Documento gerado automaticamente</font>",
                _ESTILOS["titulo"],
            ),
        ]],
        colWidths=[7.7 * cm, 7.7 * cm]
    )

    header_info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBEFORE", (1, 0), (1, 0), 0.6, CINZA_BORDA),
        ("LEFTPADDING", (1, 0), (1, 0), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))

    elementos.append(header_info)
    elementos.append(Spacer(1, 14))

    dados_empresa_table = Table(
        [
            _linha_dados("Responsável", responsavel),
            _linha_dados("Empresa", empresa),
            _linha_dados("CNPJ", formatar_cnpj(dados_empresa.get("cnpj", ""))),
            _linha_dados("Telefone", formatar_telefone(dados_empresa.get("telefone", ""))),
            _linha_dados("E-mail", str(dados_empresa.get("email", "") or "").lower()),
            _linha_dados("Endereço", dados_empresa.get("endereco", "")),
        ],
        colWidths=[5.2 * cm, 10.8 * cm]
    )

    dados_empresa_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.45, CINZA_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elementos.append(_card_tabela("DADOS DA EMPRESA", dados_empresa_table, AZUL))
    elementos.append(Spacer(1, 13))

    dados_cliente_table = Table(
        [
            _linha_dados("Cliente", cliente),
            _linha_dados("Telefone", telefone_cliente),
        ],
        colWidths=[5.2 * cm, 10.8 * cm]
    )

    dados_cliente_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.45, CINZA_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elementos.append(_card_tabela("DADOS DO CLIENTE", dados_cliente_table, VERDE))
    elementos.append(Spacer(1, 13))

    linhas_tabela = [[
        Paragraph("<b>SERVIÇO</b>", _ESTILOS["tabela_header"]),
        Paragraph("<b>QTD.</b>", _ESTILOS["tabela_header"]),
        Paragraph("<b>VALOR UNIT.</b>", _ESTILOS["tabela_header"]),
        Paragraph("<b>SUBTOTAL</b>", _ESTILOS["tabela_header"]),
    ]]

    for item in itens_processados:
        linhas_tabela.append([
            Paragraph(item["servico"], _ESTILOS["tabela_item"]),
            Paragraph(str(item["quantidade"]), _ESTILOS["tabela_item"]),
            Paragraph(formatar_moeda(item["valor_unitario"]), _ESTILOS["tabela_item"]),
            Paragraph(formatar_moeda(item["subtotal"]), _ESTILOS["tabela_item"]),
        ])

    tabela_orcamento = Table(
        linhas_tabela,
        colWidths=[7.4 * cm, 2.1 * cm, 3.5 * cm, 3.5 * cm]
    )

    tabela_orcamento.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.45, CINZA_BORDA),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))

    subtotal_table = Table(
        [
            ["Subtotal dos serviços", formatar_moeda(subtotal_servicos)],
            ["Materiais adicionais", formatar_moeda(materiais)],
            ["VALOR TOTAL", formatar_moeda(valor_total)],
        ],
        colWidths=[11.8 * cm, 4.7 * cm]
    )

    subtotal_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#F2F7FF")),
        ("BACKGROUND", (0, 2), (0, 2), colors.HexColor("#EAF2FF")),
        ("BACKGROUND", (1, 2), (1, 2), AZUL),
        ("TEXTCOLOR", (1, 2), (1, 2), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11.5),
        ("FONTSIZE", (1, 2), (1, 2), 16),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.8, AZUL),
        ("LINEBELOW", (0, 0), (-1, 1), 0.4, CINZA_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))

    detalhes_card = Table(
        [
            [Paragraph("DETALHAMENTO DO ORÇAMENTO", _ESTILOS["secao_azul"])],
            [tabela_orcamento],
            [Spacer(1, 11)],
            [subtotal_table],
        ],
        colWidths=[17.2 * cm]
    )

    detalhes_card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, CINZA_BORDA),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
        ("TOPPADDING", (0, 0), (-1, -1), 13),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
    ]))

    elementos.append(detalhes_card)
    elementos.append(Spacer(1, 13))

    observacao = dados_orcamento.get("observacao") or "Sem observações"

    info_table = Table(
        [
            [Paragraph("<b>Materiais adicionais:</b>", _ESTILOS["label"]), Paragraph(formatar_moeda(materiais), _ESTILOS["normal"])],
            [Paragraph("<b>Observação:</b>", _ESTILOS["label"]), Paragraph(observacao, _ESTILOS["normal"])],
            [Paragraph("<b>Data de emissão:</b>", _ESTILOS["label"]), Paragraph(data_emissao, _ESTILOS["normal"])],
            [Paragraph("<b>Validade:</b>", _ESTILOS["label"]), Paragraph("7 dias", _ESTILOS["normal"])],
            [Paragraph("<b>Pagamento:</b>", _ESTILOS["label"]), Paragraph("a combinar", _ESTILOS["normal"])],
        ],
        colWidths=[5.2 * cm, 10.8 * cm]
    )

    info_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    elementos.append(_card_tabela("INFORMAÇÕES ADICIONAIS", info_table, VERDE))
    elementos.extend(_footer_final(dados_empresa))

    doc.build(elementos)

    return nome_arquivo