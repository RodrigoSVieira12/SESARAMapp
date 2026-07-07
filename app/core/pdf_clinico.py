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

    # ---- Cabeçalho institucional ----
    el.append(Paragraph(T["cabecalho"], ParagraphStyle(
        "cab", parent=normal, fontSize=10, textColor=colors.HexColor("#0C447C"),
        fontName="Helvetica-Bold")))
    el.append(Paragraph(T["cabecalho_nota"], rotulo_pequeno))
    el.append(Spacer(1, 4))
    el.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0C447C")))
    el.append(Spacer(1, 8))
    el.append(Paragraph(T["titulo"], titulo))
    el.append(Paragraph(
        f"{T['gerado']} {_hora_legivel(dados.get('gerado_em'), lingua)}", suave))
    el.append(Spacer(1, 8))

    # ---- Faixa da cor de prioridade ----
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
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        el.append(faixa)
        if dados.get("descricao_cor"):
            el.append(Spacer(1, 4))
            el.append(Paragraph(dados["descricao_cor"], normal))

    # ---- Queixa ----
    if dados.get("queixa"):
        el.append(Paragraph(T["queixa"], h_sec))
        el.append(Paragraph(str(dados["queixa"]), normal))
        if dados.get("motivo"):
            el.append(Paragraph(str(dados["motivo"]), suave))

    # ---- Respostas ----
    respostas = dados.get("respostas") or []
    if respostas:
        el.append(Paragraph(T["respostas"], h_sec))
        for r in respostas:
            if not isinstance(r, dict):
                continue
            resp = r.get("resposta")
            marca = T["sim"] if resp == "sim" else T["nao"] if resp == "nao" else str(resp or "")
            el.append(Paragraph(
                f"• {r.get('texto', '')} <b>{marca}</b>", normal))

    # ---- Recomendação ----
    if dados.get("mensagem"):
        el.append(Paragraph(T["recomendacao"], h_sec))
        el.append(Paragraph(str(dados["mensagem"]), normal))

    # ---- Unidade sugerida ----
    unidade = dados.get("unidade")
    if isinstance(unidade, dict) and unidade.get("nome"):
        el.append(Paragraph(T["unidade"], h_sec))
        el.append(Paragraph(f"<b>{unidade['nome']}</b>", normal))
        linhas = []
        if unidade.get("morada"):
            linhas.append(f"{T['morada']}: {unidade['morada']}")
        if unidade.get("telefone"):
            linhas.append(f"{T['telefone']}: {unidade['telefone']}")
        if unidade.get("distancia_km") is not None:
            linhas.append(f"{T['distancia']}: {unidade['distancia_km']} {T['km']}")
        if "aberta_agora" in unidade:
            estado_txt = T["aberta"] if unidade.get("aberta_agora") else T["fechada"]
            if not unidade.get("aberta_agora") and unidade.get("proxima_abertura_texto"):
                estado_txt += f" ({unidade['proxima_abertura_texto']})"
            linhas.append(f"{T['estado']}: {estado_txt}")
        espera_txt = _texto_espera(unidade.get("tempo_espera"))
        if espera_txt:
            linhas.append(f"{T['espera']}: {espera_txt}")
        for ln in linhas:
            el.append(Paragraph(ln, normal))
        horarios = unidade.get("horarios") or {}
        if horarios:
            el.append(Paragraph(T["horarios"] + ":", suave))
            for serv, texto in horarios.items():
                el.append(Paragraph(
                    f"&nbsp;&nbsp;— {serv_labels.get(serv, serv)}: {texto}", normal))

    # ---- Alternativas ----
    alternativas = dados.get("alternativas") or []
    alt_validas = [a for a in alternativas if isinstance(a, dict) and a.get("nome")]
    if alt_validas:
        el.append(Paragraph(T["alternativas"], h_sec))
        for a in alt_validas:
            partes = [a["nome"]]
            if a.get("concelho"):
                partes.append(a["concelho"])
            if a.get("distancia_km") is not None:
                partes.append(f"{a['distancia_km']} {T['km']}")
            estado_txt = ""
            if "aberta_agora" in a:
                estado_txt = f" — {T['aberta'] if a.get('aberta_agora') else T['fechada']}"
            el.append(Paragraph(f"• {', '.join(partes)}{estado_txt}", normal))

    # ---- Autocuidado ----
    ac = dados.get("autocuidado")
    if isinstance(ac, dict):
        el.append(Paragraph(ac.get("titulo") or T["autocuidado"], h_sec))
        if ac.get("intro"):
            el.append(Paragraph(str(ac["intro"]), normal))
        if ac.get("fazer"):
            el.append(Paragraph(T["fazer"] + ":", suave))
            for item in ac["fazer"]:
                el.append(Paragraph(
                    f'&nbsp;&nbsp;<font color="#2E7D32">•</font> {item}', normal))
        if ac.get("evitar"):
            el.append(Paragraph(T["evitar"] + ":", suave))
            for item in ac["evitar"]:
                el.append(Paragraph(
                    f'&nbsp;&nbsp;<font color="#C62828">•</font> {item}', normal))
        if ac.get("alerta"):
            el.append(Paragraph(
                (ac.get("alerta_titulo") or "").strip() or "—", suave))
            for item in ac["alerta"]:
                el.append(Paragraph(
                    f'&nbsp;&nbsp;<font color="#EF6C00">•</font> {item}', normal))

    # ---- Contactos ----
    el.append(Paragraph(T["contactos"], h_sec))
    contactos = dados.get("contactos") or {}
    n_112 = ((contactos.get("emergencia") or {}).get("numero")) or "112"
    n_sns = ((contactos.get("sns24") or {}).get("numero")) or "808 24 24 24"
    el.append(Paragraph(f"{T['emergencia']}: <b>{n_112}</b>", normal))
    el.append(Paragraph(f"{T['sns']}: <b>{n_sns}</b>", normal))

    # ---- Identificação manual opcional ----
    el.append(Paragraph(T["identificacao"], h_sec))
    linha = '<font color="#9aa1ab">_____________________________________________</font>'
    for rot in (T["id_nome"], T["id_nascimento"], T["id_utente"]):
        el.append(Paragraph(f"{rot}: {linha}", normal))
        el.append(Spacer(1, 2))

    # ---- Rodapé/aviso ----
    el.append(Spacer(1, 10))
    el.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#c8ccd2")))
    el.append(Spacer(1, 4))
    el.append(Paragraph(T["aviso"], rotulo_pequeno))

    doc.build(el)
    return buf.getvalue()
