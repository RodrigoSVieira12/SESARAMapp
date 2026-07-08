"""Geração do resumo de orientação em PDF (server-side, reportlab).

Porque reportlab e não WeasyPrint: reportlab é Python puro, instala-se com
`pip install reportlab` em qualquer sistema (incluindo Windows) sem precisar
de bibliotecas do sistema (Cairo/Pango). Para um protótipo que corre na
máquina de um estagiário, é a escolha robusta.

O PDF é deliberadamente um documento de ORIENTAÇÃO, não um registo clínico:
- não capta identificação do utente (mantém a promessa de "não guardamos
  dados"); há um bloco opcional de preenchimento MANUAL para quem quiser
  levar o papel ao balcão;
- repete o mesmo aviso da app: não substitui avaliação clínica, e os dados
  de unidades e as regras de triagem são exemplos por validar.

Este mesmo documento é a peça central de qualquer integração futura: um PDF
é o formato que qualquer sistema (Portal do Utente, correio, ou um sistema
interno) consegue anexar. Ver INTEGRACAO.md.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Rótulos legíveis dos tipos de serviço (iguais aos do frontend).
_SERVICOS_PT = {
    "urgencia_polivalente": "Urgência (hospitalar)",
    "urgencia_basica": "Urgência básica",
    "atendimento_urgente": "Atendimento urgente",
    "consulta_aberta": "Consulta aberta / sem marcação",
}
_SERVICOS_EN = {
    "urgencia_polivalente": "Emergency department (hospital)",
    "urgencia_basica": "Basic emergency unit",
    "atendimento_urgente": "Urgent care",
    "consulta_aberta": "Walk-in appointment",
}

_TXT = {
    "pt": {
        "cabecalho": "SESARAM · Serviço de Saúde da Região Autónoma da Madeira",
        "cabecalho_nota": "(identificação institucional por confirmar)",
        "titulo": "Resumo de orientação — Triagem de sintomas",
        "gerado": "Documento gerado em",
        "prioridade": "Nível de prioridade sugerido",
        "queixa": "Queixa principal",
        "respostas": "Respostas dadas",
        "recomendacao": "Recomendação",
        "unidade": "Unidade sugerida",
        "alternativas": "Alternativas",
        "morada": "Morada",
        "telefone": "Telefone",
        "distancia": "Distância aproximada",
        "estado": "Estado agora",
        "aberta": "Aberta",
        "fechada": "Fechada",
        "espera": "Tempo de espera estimado",
        "horarios": "Horários",
        "autocuidado": "Enquanto aguarda / autocuidado",
        "fazer": "Pode fazer",
        "evitar": "Evitar",
        "contactos": "Contactos úteis",
        "emergencia": "Emergência médica",
        "sns": "SNS 24 (aconselhamento)",
        "identificacao": "Identificação (preenchimento manual, opcional)",
        "id_nome": "Nome",
        "id_nascimento": "Data de nascimento",
        "id_utente": "Nº de utente / Nº SNS",
        "sim": "Sim",
        "nao": "Não",
        "aviso": (
            "Este documento é uma orientação e NÃO substitui a avaliação "
            "clínica nem a triagem oficial feita nas urgências. As regras de "
            "triagem e os dados das unidades são exemplos por validar pela "
            "equipa clínica do SESARAM. Em caso de agravamento, ligue 112."
        ),
        "km": "km",
    },
    "en": {
        "cabecalho": "SESARAM · Madeira Regional Health Service",
        "cabecalho_nota": "(institutional identification to be confirmed)",
        "titulo": "Guidance summary — Symptom triage",
        "gerado": "Document generated on",
        "prioridade": "Suggested priority level",
        "queixa": "Main complaint",
        "respostas": "Answers given",
        "recomendacao": "Recommendation",
        "unidade": "Suggested unit",
        "alternativas": "Alternatives",
        "morada": "Address",
        "telefone": "Phone",
        "distancia": "Approximate distance",
        "estado": "Status now",
        "aberta": "Open",
        "fechada": "Closed",
        "espera": "Estimated waiting time",
        "horarios": "Opening hours",
        "autocuidado": "While you wait / self-care",
        "fazer": "You can",
        "evitar": "Avoid",
        "contactos": "Useful contacts",
        "emergencia": "Medical emergency",
        "sns": "SNS 24 (advice line)",
        "identificacao": "Identification (fill in by hand, optional)",
        "id_nome": "Name",
        "id_nascimento": "Date of birth",
        "id_utente": "Patient / SNS number",
        "sim": "Yes",
        "nao": "No",
        "aviso": (
            "This document is guidance and does NOT replace clinical "
            "assessment or the official triage carried out at emergency "
            "departments. The triage rules and unit data are examples pending "
            "validation by the SESARAM clinical team. If symptoms worsen, "
            "call 112."
        ),
        "km": "km",
    },
}


def _hora_legivel(iso: str | None, lingua: str) -> str:
    if not iso:
        iso = datetime.now().isoformat()
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return dt.strftime("%d/%m/%Y %H:%M") if lingua == "pt" else dt.strftime("%Y-%m-%d %H:%M")


def _cor_segura(valor: Any, omissao: str = "#0C447C") -> colors.Color:
    try:
        return colors.HexColor(valor)
    except Exception:
        return colors.HexColor(omissao)


def _texto_espera(tempo_espera: Any) -> str | None:
    """O campo tempo_espera pode vir como dict, número ou texto."""
    if tempo_espera in (None, "", {}):
        return None
    if isinstance(tempo_espera, dict):
        if tempo_espera.get("texto"):
            return str(tempo_espera["texto"])
        if tempo_espera.get("minutos") is not None:
            return f"~{tempo_espera['minutos']} min"
        return None
    if isinstance(tempo_espera, (int, float)):
        return f"~{int(tempo_espera)} min"
    return str(tempo_espera)


def gerar_pdf(dados: dict) -> bytes:
    """Recebe o resumo da avaliação (o que o frontend mostrou) e devolve PDF."""
    lingua = "en" if dados.get("lingua") == "en" else "pt"
    T = _TXT[lingua]
    serv_labels = _SERVICOS_EN if lingua == "en" else _SERVICOS_PT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=T["titulo"],
        author="Onde Ir (protótipo SESARAM)",
    )

    base = getSampleStyleSheet()
    normal = ParagraphStyle("corpo", parent=base["Normal"], fontSize=10, leading=14)
    suave = ParagraphStyle("suave", parent=normal, textColor=colors.HexColor("#5b6470"))
    h_sec = ParagraphStyle(
        "sec",
        parent=base["Heading2"],
        fontSize=11,
        leading=14,
        spaceBefore=10,
        spaceAfter=4,
        textColor=colors.HexColor("#0C447C"),
        alignment=TA_LEFT,
    )
    titulo = ParagraphStyle(
        "titulo", parent=base["Heading1"], fontSize=16, leading=19, spaceAfter=2
    )
    rotulo_pequeno = ParagraphStyle(
        "rotpeq", parent=normal, fontSize=8, textColor=colors.HexColor("#5b6470")
    )

    el: list = []

    # PDF enxuto e de uma página: só o que um utente leva consigo ou mostra.
    # Cabeçalho compacto (instituição + data + queixa).
    el.append(Paragraph(T["cabecalho"], ParagraphStyle(
        "cab", parent=normal, fontSize=9.5, textColor=colors.HexColor("#0C447C"),
        fontName="Helvetica-Bold")))
    el.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0C447C")))
    el.append(Spacer(1, 5))
    el.append(Paragraph(T["titulo"], titulo))
    linha_data = f"{T['gerado']} {_hora_legivel(dados.get('gerado_em'), lingua)}"
    if dados.get("queixa"):
        linha_data += f" &nbsp;·&nbsp; {T['queixa']}: {dados['queixa']}"
    el.append(Paragraph(linha_data, suave))
    el.append(Spacer(1, 8))

    # Faixa da cor de prioridade (o destaque).
    cor = dados.get("cor")
    if cor:
        cor_hex = _cor_segura(dados.get("cor_hex"))
        classif = dados.get("classificacao") or cor.capitalize()
        tempo = dados.get("tempo_alvo") or ""
        faixa = Table(
            [[Paragraph(
                f'<font color="white"><b>{T["prioridade"].upper()}</b><br/>'
                f'<font size="14">{classif}</font></font>',
                ParagraphStyle("faixa", parent=normal, textColor=colors.white)),
              Paragraph(
                f'<font color="white">{tempo}</font>',
                ParagraphStyle("faixaR", parent=normal, textColor=colors.white,
                               alignment=2))]],
            colWidths=[110 * mm, 64 * mm],
        )
        faixa.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), cor_hex),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        el.append(faixa)

    # Recomendação (o que fazer / para onde ir).
    if dados.get("mensagem"):
        el.append(Paragraph(T["recomendacao"], h_sec))
        el.append(Paragraph(str(dados["mensagem"]), normal))

    # Unidade sugerida: nome, morada, telefone, horários. Sem distância nem
    # tempo de espera (só fazem sentido em direto, ficam desatualizados no
    # papel).
    unidade = dados.get("unidade")
    if isinstance(unidade, dict) and unidade.get("nome"):
        el.append(Paragraph(T["unidade"], h_sec))
        el.append(Paragraph(f"<b>{unidade['nome']}</b>", normal))
        if unidade.get("morada"):
            el.append(Paragraph(f"{T['morada']}: {unidade['morada']}", normal))
        if unidade.get("telefone"):
            el.append(Paragraph(f"{T['telefone']}: {unidade['telefone']}", normal))
        horarios = unidade.get("horarios") or {}
        if horarios:
            partes = [f"{serv_labels.get(k, k)}: {v}" for k, v in horarios.items()]
            el.append(Paragraph(f"{T['horarios']}: " + "; ".join(partes), normal))

    # Sinais de alarme: quando procurar ajuda com urgência (o essencial de
    # segurança). Limitado a quatro para não crescer.
    ac = dados.get("autocuidado")
    if isinstance(ac, dict) and ac.get("alerta"):
        el.append(Paragraph((ac.get("alerta_titulo") or "").strip() or T["autocuidado"], h_sec))
        for item in ac["alerta"][:4]:
            el.append(Paragraph(
                f'&nbsp;&nbsp;<font color="#C62828">•</font> {item}', normal))

    # Contactos úteis (uma linha).
    contactos = dados.get("contactos") or {}
    n_112 = ((contactos.get("emergencia") or {}).get("numero")) or "112"
    n_sns = ((contactos.get("sns24") or {}).get("numero")) or "808 24 24 24"
    el.append(Paragraph(T["contactos"], h_sec))
    el.append(Paragraph(
        f"{T['emergencia']}: <b>{n_112}</b> &nbsp;·&nbsp; {T['sns']}: <b>{n_sns}</b>", normal))

    # Rodapé/aviso.
    el.append(Spacer(1, 10))
    el.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#c8ccd2")))
    el.append(Spacer(1, 4))
    el.append(Paragraph(T["aviso"], rotulo_pequeno))

    doc.build(el)
    return buf.getvalue()
