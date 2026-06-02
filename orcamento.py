from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from datetime import datetime
import re


def normalizar_texto(texto):
    texto = (texto or "").strip().lower()
    texto = re.sub(r"\s+", " ", texto)
    return texto


def formatar_nome_visual(texto):
    if not texto:
        return ""

    minusculas = {"de", "da", "do", "das", "dos", "e"}
    palavras = texto.split()
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
    if len(numeros) == 11:
        return f"({numeros[:2]}) {numeros[2:7]}-{numeros[7:]}"
    if len(numeros) == 10:
        return f"({numeros[:2]}) {numeros[2:6]}-{numeros[6:]}"
    return telefone or ""


def validar_dados_orcamento(dados):
    faltando = []

    if not dados.get("cliente"):
        faltando.append("cliente")

    if not dados.get("telefone_cliente"):
        faltando.append("telefone")

    if not dados.get("itens"):
        faltando.append("itens")

    return faltando


def _encontrar_servico_tabela(servico_digitado, tabela_servicos):
    chave = normalizar_texto(servico_digitado)

    if chave in tabela_servicos:
        return tabela_servicos[chave]

    for k, v in tabela_servicos.items():
        if chave in k:
            return v

    for k, v in tabela_servicos.items():
        if any(token.startswith(chave) for token in k.split()):
            return v

    return None


def gerar_orcamento(dados_orcamento, dados_empresa, tabela_servicos, nome_arquivo="orcamento.pdf"):
    itens_processados = []
    subtotal_servicos = 0.0

    for item in dados_orcamento.get("itens", []):
        info_servico = _encontrar_servico_tabela(item["servico"], tabela_servicos)

        if not info_servico:
            valor_unitario = 0.0
            nome_servico = item["servico"]
        else:
            valor_unitario = float(info_servico["valor"])
            nome_servico = info_servico["nome"]

        quantidade = int(item.get("quantidade", 1))
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

    doc = SimpleDocTemplate(
        nome_arquivo,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm
    )

    styles = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle(
        "TituloCustom",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#1F3C88"),
        spaceAfter=8
    )

    estilo_subtitulo = ParagraphStyle(
        "SubtituloCustom",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#1F3C88"),
        spaceAfter=6
    )

    estilo_normal = ParagraphStyle(
        "NormalCustom",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.black,
        spaceAfter=4
    )

    estilo_destaque = ParagraphStyle(
        "Destaque",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#111111"),
        spaceAfter=4
    )

    estilo_assinatura = ParagraphStyle(
        "AssinaturaVisual",
        parent=styles["BodyText"],
        fontName="Helvetica-Oblique",
        fontSize=18,
        leading=20,
        textColor=colors.HexColor("#23395B"),
        spaceAfter=2
    )

    elementos = []

    responsavel = formatar_nome_visual(dados_empresa["responsavel"])
    cliente = formatar_nome_visual(dados_orcamento["cliente"])
    telefone_cliente = formatar_telefone(dados_orcamento["telefone_cliente"])

    elementos.append(Paragraph("ORÇAMENTO", estilo_titulo))
    elementos.append(Paragraph("Documento gerado automaticamente pelo Orçai", estilo_normal))
    elementos.append(Spacer(1, 8))

    elementos.append(Paragraph("Dados da empresa", estilo_subtitulo))
    tabela_empresa = Table(
        [
            ["Responsável", responsavel],
            ["Empresa", dados_empresa["empresa"]],
            ["CNPJ", dados_empresa["cnpj"]],
            ["Telefone", formatar_telefone(dados_empresa["telefone"])],
            ["E-mail", (dados_empresa["email"] or "").lower()],
            ["Endereço", dados_empresa["endereco"]],
        ],
        colWidths=[4 * cm, 11.5 * cm]
    )
    tabela_empresa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF0FB")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabela_empresa)
    elementos.append(Spacer(1, 12))

    elementos.append(Paragraph("Dados do cliente", estilo_subtitulo))
    tabela_cliente = Table(
        [
            ["Cliente", cliente],
            ["Telefone", telefone_cliente],
        ],
        colWidths=[4 * cm, 11.5 * cm]
    )
    tabela_cliente.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabela_cliente)
    elementos.append(Spacer(1, 12))

    elementos.append(Paragraph("Detalhamento do orçamento", estilo_subtitulo))

    linhas_tabela = [["Serviço", "Qtd.", "Valor unit.", "Subtotal"]]
    for item in itens_processados:
        linhas_tabela.append([
            item["servico"],
            str(item["quantidade"]),
            f"R$ {item['valor_unitario']:.2f}",
            f"R$ {item['subtotal']:.2f}",
        ])

    tabela_orcamento = Table(
        linhas_tabela,
        colWidths=[9.5 * cm, 1.8 * cm, 2.8 * cm, 2.8 * cm]
    )
    tabela_orcamento.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3C88")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(tabela_orcamento)
    elementos.append(Spacer(1, 14))

    observacao = dados_orcamento.get("observacao") or "Sem observações"

    elementos.append(Paragraph("Informações adicionais", estilo_subtitulo))
    elementos.append(Paragraph(f"<b>Materiais adicionais:</b> R$ {materiais:.2f}", estilo_normal))
    elementos.append(Paragraph(f"<b>Observação:</b> {observacao}", estilo_normal))
    elementos.append(Paragraph(
        f"<b>Data de emissão:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        estilo_normal
    ))
    elementos.append(Paragraph("<b>Validade do orçamento:</b> 7 dias", estilo_normal))
    elementos.append(Paragraph("<b>Forma de pagamento:</b> a combinar", estilo_normal))
    elementos.append(Spacer(1, 12))

    tabela_total = Table(
        [
            ["Subtotal dos serviços", f"R$ {subtotal_servicos:.2f}"],
            ["Materiais adicionais", f"R$ {materiais:.2f}"],
            ["VALOR TOTAL", f"R$ {valor_total:.2f}"],
        ],
        colWidths=[10 * cm, 5.5 * cm]
    )
    tabela_total.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#EEF2FF")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#DCE8FF")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1F3C88")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#1F3C88")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    elementos.append(tabela_total)
    elementos.append(Spacer(1, 22))

    elementos.append(Paragraph(responsavel, estilo_assinatura))
    elementos.append(Paragraph("____________________________________", estilo_normal))
    elementos.append(Paragraph(responsavel, estilo_destaque))
    elementos.append(Paragraph("Responsável pelo orçamento", estilo_normal))
    elementos.append(Paragraph("Assinado digitalmente pelo Orçai", estilo_normal))

    doc.build(elementos)
    return nome_arquivo