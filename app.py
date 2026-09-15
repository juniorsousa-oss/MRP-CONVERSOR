import base64
import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from conversores.estoque import processar_estoque
from conversores.relatorio_geral import processar_relatorio_geral
from conversores.compras import processar_compras
from conversores.tc_tp import processar_tc_tp

FAVICON = Path(__file__).parent / "favicon.png.png"
CONFIG_ENDERECOS = Path(__file__).parent / "config" / "enderecos_nao_disponiveis.json"
CONFIG_LOGO = Path(__file__).parent / "config" / "logo_setta.svg"

st.set_page_config(
    page_title="CONVERSOR MRP | SETTA",
    page_icon=str(FAVICON),
    layout="wide",
    initial_sidebar_state="collapsed",
)


def carregar_enderecos_nao_disponiveis():
    try:
        with CONFIG_ENDERECOS.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return [str(x).strip() for x in dados.get("enderecos_nao_disponiveis", []) if str(x).strip()]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def carregar_logo_padrao():
    try:
        return CONFIG_LOGO.read_bytes(), "image/svg+xml"
    except OSError:
        return None, None


def ler_excel_seguro(arquivo, **kwargs):
    """Lê Excel normalmente e usa Calamine quando o openpyxl encontra
    formatação/condicional inválida no arquivo de origem.
    """
    try:
        return pd.read_excel(arquivo, **kwargs)
    except TypeError as exc:
        if "MultiCellRange" not in str(exc):
            raise
        try:
            arquivo.seek(0)
        except (AttributeError, OSError):
            pass
        return pd.read_excel(arquivo, engine="calamine", **kwargs)


def ler_estoque_como_cabecalho(arquivo):
    return ler_excel_seguro(arquivo, header=1)


def ler_compras_como_cabecalho(arquivo, sheet_name=0):
    return ler_excel_seguro(arquivo, sheet_name=sheet_name, header=1)


def ler_for001(arquivo):
    return ler_excel_seguro(arquivo, sheet_name="PAINEL", header=4)


def ler_for022(arquivo):
    return ler_excel_seguro(arquivo, sheet_name="Datas esperadas", header=0)


st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background: #f4f7fb;
    }

    [data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0.96);
    }

    .block-container {
        max-width: 1780px;
        padding-top: 3.2rem;
        padding-left: 2.7rem;
        padding-right: 2.7rem;
        padding-bottom: 3rem;
    }

    .setta-logo-card {
        width: 100%;
        min-height: 128px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #ffffff;
        border: 1px solid #e5e8ee;
        border-radius: 16px;
        box-shadow: 0 4px 14px rgba(24, 39, 75, 0.08);
        box-sizing: border-box;
        margin: 0 0 2.55rem 0;
        padding: 1.1rem 2rem;
    }

    .setta-logo-card img {
        display: block;
        width: auto;
        height: auto;
        max-width: 205px;
        max-height: 86px;
        object-fit: contain;
    }

    .app-title {
        margin: 0;
        padding: 0;
        font-size: 2.55rem;
        line-height: 1.08;
        font-weight: 800;
        letter-spacing: -0.04em;
        color: #050505;
    }

    .app-subtitle {
        margin-top: 0.72rem;
        margin-bottom: 0;
        font-size: 0.94rem;
        color: #4f5661;
    }

    .app-info {
        margin: 1.05rem 0 1.65rem 0;
        padding: 1rem 1.05rem;
        background: #dce8f9;
        color: #1457b6;
        border-radius: 9px;
        font-size: 0.98rem;
        line-height: 1.35;
    }

    section[data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e8ebf0;
    }

    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.6rem;
    }

    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #111111;
    }

    div[data-testid="stFileUploader"] section {
        border-radius: 10px;
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e7eaf0;
        border-radius: 12px;
        padding: 0.8rem 1rem;
    }

    div.stButton > button[kind="primary"],
    div.stDownloadButton > button {
        border-radius: 9px;
        font-weight: 600;
    }

    @media (max-width: 900px) {
        .block-container {
            padding-top: 2rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .setta-logo-card {
            min-height: 105px;
            margin-bottom: 1.8rem;
        }
        .setta-logo-card img {
            max-width: 170px;
            max-height: 72px;
        }
        .app-title {
            font-size: 2rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


logo_bytes, logo_mime = carregar_logo_padrao()

with st.sidebar:
    st.header("Configuração")
    tipo_relatorio = st.selectbox(
        "Tipo de relatório",
        [
            "Relatório Geral",
            "Saldo em Estoque",
            "Compras — S.C + P.C + Pré-nota",
            "MRP — TC/TP",
        ],
    )

    st.divider()
    st.caption("Identidade visual")
    logo_empresa = st.file_uploader(
        "Alterar logo da empresa",
        type=["png", "jpg", "jpeg", "svg"],
        key="logo_empresa",
        help="A imagem selecionada substitui a logo padrão apenas durante a sessão atual.",
    )
    if logo_empresa is not None:
        logo_bytes = logo_empresa.getvalue()
        logo_mime = logo_empresa.type or "image/png"

    st.info(
        "O conversor não calcula MRP. Ele transforma, agrupa, valida e exporta os dados para uso posterior."
    )


if logo_bytes:
    logo_base64 = base64.b64encode(logo_bytes).decode("ascii")
    mime = logo_mime or "image/png"
    logo_html = f'<img src="data:{mime};base64,{logo_base64}" alt="Setta">'
else:
    logo_html = '<div style="font-size:2rem;font-weight:800;color:#202124;">SETTA</div>'

st.markdown(
    f'<div class="setta-logo-card">{logo_html}</div>',
    unsafe_allow_html=True,
)
st.markdown('<h1 class="app-title">CONVERSOR MRP | SETTA</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="app-subtitle">Conversão e validação de relatórios brutos do ERP para Excel tratado.</p>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="app-info">Selecione o tipo de relatório no menu lateral, envie os arquivos brutos e gere a base tratada para utilização no MRP.</div>',
    unsafe_allow_html=True,
)


if tipo_relatorio == "Relatório Geral":
    st.subheader("1. Enviar os três relatórios brutos")
    st.caption("O Relatório Geral recebe a DATA MRP e a condição do FOR-001 pela OP, e a DATA CM do FOR-022 pela OP.")
    arquivo = st.file_uploader("Relatório Geral — aba 'Geral'", type=["xlsx", "xls", "xltx"], key="geral")
    for001_arquivo = st.file_uploader("FOR-001 — Plano Mestre de Produção", type=["xlsx", "xls", "xltx"], key="for001")
    for022_arquivo = st.file_uploader("FOR-022 — Planejamento Macro Produção", type=["xlsx", "xls", "xltx"], key="for022")

    if arquivo is not None and for001_arquivo is not None and for022_arquivo is not None:
        try:
            bruto = ler_excel_seguro(arquivo, sheet_name="Geral")
            for001_bruto = ler_for001(for001_arquivo)
            for022_bruto = ler_for022(for022_arquivo)
        except ValueError as exc:
            st.error(f"Não foi possível localizar a aba necessária nos arquivos: {exc}")
            st.stop()
        except Exception as exc:
            st.error(f"Não foi possível ler os arquivos: {exc}")
            st.stop()

        c1, c2, c3 = st.columns(3)
        c1.metric("Linhas Relatório Geral", f"{len(bruto):,}".replace(",", "."))
        c2.metric("OPs FOR-001", f"{len(for001_bruto):,}".replace(",", "."))
        c3.metric("Linhas FOR-022", f"{len(for022_bruto):,}".replace(",", "."))

        st.subheader("2. Regras aplicadas")
        st.info("FOR-001: OP → DATA MRP + CONDIÇÃO. NORMAL usa a DATA MRP para calcular a semana e entra na NECESSIDADE DA SEMANA. Condições diferentes de NORMAL permanecem visíveis no campo da semana, mas não entram no total. FOR-022: OP → DATA CM (coluna Separação); OP não encontrada = NI.")

        if st.button("Processar relatório", type="primary", use_container_width=True, key="processar_geral"):
            with st.spinner("Processando, vinculando PCP e validando..."):
                st.session_state["resultado_geral"] = processar_relatorio_geral(bruto, for001_bruto, for022_bruto)

    if "resultado_geral" in st.session_state:
        resultado = st.session_state["resultado_geral"]
        st.subheader("3. Resultado da conversão")
        metricas = resultado["metricas"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Linhas brutas", f"{metricas['linhas_brutas']:,}".replace(",", "."))
        c2.metric("Chaves únicas", f"{metricas['chaves_unicas']:,}".replace(",", "."))
        c3.metric("Linhas agrupadas", f"{metricas['linhas_agrupadas']:,}".replace(",", "."))
        c4.metric("Erros", str(metricas["erros"]))
        if resultado["erros"]:
            st.error("Foram encontradas inconsistências que precisam ser corrigidas antes da exportação.")
            for erro in resultado["erros"]:
                st.write(f"- {erro}")
        else:
            st.success("Validação concluída sem erros críticos.")
        if resultado["avisos"]:
            with st.expander(f"Avisos ({len(resultado['avisos'])})"):
                for aviso in resultado["avisos"]:
                    st.write(f"- {aviso}")
        st.subheader("Prévia do relatório tratado")
        st.dataframe(resultado["tratado"].head(100), use_container_width=True, height=420)
        if not resultado["erros"]:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                resultado["tratado"].to_excel(writer, sheet_name="RelatorioTratado", index=False)
                resultado["validacao"].to_excel(writer, sheet_name="Validacao", index=False)
            buffer.seek(0)
            st.subheader("4. Exportar")
            st.download_button("Baixar Excel tratado", data=buffer, file_name="RelatorioGeral_Tratado.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key="download_geral")


elif tipo_relatorio == "Saldo em Estoque":
    st.subheader("1. Enviar os dois relatórios brutos")
    st.write("O Analítico é a base do saldo. O relatório de Endereço complementa o cálculo dos endereços não disponíveis.")
    analitico_arquivo = st.file_uploader("Analítico — Cód. Produto, Descrição e Saldo em Estoque", type=["xlsx", "xls", "xltx"], key="analitico")
    endereco_arquivo = st.file_uploader("Endereço — Cód. Produto, Endereço e Quantidade", type=["xlsx", "xls", "xltx"], key="endereco")
    if analitico_arquivo is not None and endereco_arquivo is not None:
        try:
            analitico_bruto = ler_estoque_como_cabecalho(analitico_arquivo)
            endereco_bruto = ler_estoque_como_cabecalho(endereco_arquivo)
        except Exception as exc:
            st.error(f"Não foi possível ler os relatórios: {exc}")
            st.stop()
        enderecos = sorted([x for x in endereco_bruto.iloc[:, 3].dropna().astype(str).str.strip().unique().tolist() if x])
        st.subheader("2. Classificar endereços não disponíveis")
        st.caption("Os endereços configurados permanentemente já vêm pré-selecionados.")
        configurados = carregar_enderecos_nao_disponiveis()
        selecionados = st.multiselect("Endereços considerados NÃO DISPONÍVEIS", options=enderecos, default=[x for x in configurados if x in enderecos], key="enderecos_nao_disponiveis")
        c1, c2 = st.columns(2)
        c1.metric("Linhas do Analítico", f"{len(analitico_bruto):,}".replace(",", "."))
        c2.metric("Linhas do Endereço", f"{len(endereco_bruto):,}".replace(",", "."))
        if st.button("Processar saldo em estoque", type="primary", use_container_width=True, key="processar_estoque"):
            with st.spinner("Consolidando estoque e validando..."):
                st.session_state["resultado_estoque"] = processar_estoque(analitico_bruto, endereco_bruto, selecionados)
    if "resultado_estoque" in st.session_state:
        resultado = st.session_state["resultado_estoque"]
        st.subheader("3. Resultado da conversão")
        metricas = resultado["metricas"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Produtos no Analítico", f"{metricas['produtos_analitico']:,}".replace(",", "."))
        c2.metric("Produtos no Endereço", f"{metricas['produtos_endereco']:,}".replace(",", "."))
        c3.metric("Inconsistências", str(metricas["inconsistencias"]))
        c4.metric("Erros estruturais", str(metricas["erros"]))
        if resultado["erros"]:
            st.error("Foram encontradas falhas estruturais. O arquivo não deve ser exportado.")
            for erro in resultado["erros"]:
                st.write(f"- {erro}")
        else:
            st.success("Conversão concluída. O Analítico foi mantido como base do saldo.")
        if resultado["avisos"]:
            with st.expander(f"Avisos e inconsistências ({len(resultado['avisos'])})"):
                for aviso in resultado["avisos"]:
                    st.write(f"- {aviso}")
        st.subheader("Prévia do saldo em estoque tratado")
        st.dataframe(resultado["tratado"].head(100), use_container_width=True, height=420)
        if not resultado["erros"]:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                resultado["tratado"].to_excel(writer, sheet_name="EstoqueTratado", index=False)
                resultado["validacao"].to_excel(writer, sheet_name="Validacao", index=False)
                resultado["enderecos"].to_excel(writer, sheet_name="EnderecosConsolidados", index=False)
            buffer.seek(0)
            st.subheader("4. Exportar")
            st.download_button("Baixar Estoque tratado", data=buffer, file_name="Estoque_Tratado.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key="download_estoque")


elif tipo_relatorio == "Compras — S.C + P.C + Pré-nota":
    st.subheader("1. Enviar os três relatórios brutos")
    st.caption("Todos usam a segunda linha como cabeçalho. No P.C, somente a planilha '2-Pedido de Compras   Autoriz' é utilizada.")
    sc_arquivo = st.file_uploader("S.C — Solicitação de Compra", type=["xlsx", "xls", "xltx"], key="sc")
    pc_arquivo = st.file_uploader("P.C — Pedido de Compra", type=["xlsx", "xls", "xltx"], key="pc")
    pn_arquivo = st.file_uploader("Pré-nota", type=["xlsx", "xls", "xltx"], key="pre_nota")

    if sc_arquivo is not None and pc_arquivo is not None and pn_arquivo is not None:
        try:
            sc_bruto = ler_compras_como_cabecalho(sc_arquivo)
            excel_pc = pd.ExcelFile(pc_arquivo)
            nome_aba_pc = "2-Pedido de Compras   Autoriz"
            if nome_aba_pc not in excel_pc.sheet_names:
                st.error(f"A planilha '{nome_aba_pc}' não foi encontrada no P.C.")
                st.stop()
            pc_bruto = ler_compras_como_cabecalho(pc_arquivo, sheet_name=nome_aba_pc)
            pn_bruto = ler_compras_como_cabecalho(pn_arquivo)
        except Exception as exc:
            st.error(f"Não foi possível ler os relatórios de compras: {exc}")
            st.stop()

        st.subheader("2. Regras aplicadas")
        st.info("S.C: Centro de Custo 600307 + Saldo SC. P.C: Centro de Custo 600307 + (Quantidade - Qtd.Entregue). S.C e P.C são agrupados por produto e data de entrega; Pré-nota é somada somente por produto. Quantidades de S.C e P.C nunca são somadas entre si.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Linhas S.C", f"{len(sc_bruto):,}".replace(",", "."))
        c2.metric("Linhas P.C", f"{len(pc_bruto):,}".replace(",", "."))
        c3.metric("Linhas Pré-nota", f"{len(pn_bruto):,}".replace(",", "."))
        if st.button("Processar fluxo de compras", type="primary", use_container_width=True, key="processar_compras"):
            with st.spinner("Consolidando S.C, P.C e Pré-nota..."):
                st.session_state["resultado_compras"] = processar_compras(sc_bruto, pc_bruto, pn_bruto)

    if "resultado_compras" in st.session_state:
        resultado = st.session_state["resultado_compras"]
        st.subheader("3. Resultado da conversão")
        metricas = resultado["metricas"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("S.C tratadas", f"{metricas['linhas_sc_tratadas']:,}".replace(",", "."))
        c2.metric("P.C tratadas", f"{metricas['linhas_pc_tratadas']:,}".replace(",", "."))
        c3.metric("Produtos Pré-nota", f"{metricas['produtos_pre_nota']:,}".replace(",", "."))
        c4.metric("Inconsistências", str(metricas["inconsistencias"]))
        if resultado["erros"]:
            st.error("Foram encontradas falhas estruturais. O arquivo não deve ser exportado.")
            for erro in resultado["erros"]:
                st.write(f"- {erro}")
        else:
            st.success("Fluxo de compras convertido e validado.")
        if resultado["avisos"]:
            with st.expander(f"Avisos e inconsistências ({len(resultado['avisos'])})"):
                for aviso in resultado["avisos"]:
                    st.write(f"- {aviso}")
        st.subheader("Prévia da base comum")
        st.dataframe(resultado["tratado"].head(150), use_container_width=True, height=480)
        if not resultado["erros"]:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                resultado["tratado"].to_excel(writer, sheet_name="ComprasTratado", index=False)
                resultado["validacao"].to_excel(writer, sheet_name="Validacao", index=False)
            buffer.seek(0)
            st.subheader("4. Exportar")
            st.download_button("Baixar Compras tratado", data=buffer, file_name="Compras_Tratado.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key="download_compras")


else:
    st.subheader("1. Enviar os dois relatórios brutos")
    st.caption("O PMP_ATUALIZADO define as OFs programadas e o H001 fornece a BOM fixa de cada produto intermediário.")

    pmp_arquivo = st.file_uploader(
        "PMP_ATUALIZADO — programação de OFs",
        type=["xlsx", "xls", "xltx"],
        key="pmp_tc_tp",
    )
    h001_arquivo = st.file_uploader(
        "H001 — lista de materiais (BOM)",
        type=["xlsx", "xls", "xltx"],
        key="h001_tc_tp",
    )

    if pmp_arquivo is not None and h001_arquivo is not None:
        try:
            pmp_bruto = ler_excel_seguro(pmp_arquivo)
            h001_bruto = ler_excel_seguro(h001_arquivo)
        except Exception as exc:
            st.error(f"Não foi possível ler os relatórios de TC/TP: {exc}")
            st.stop()

        c1, c2 = st.columns(2)
        c1.metric("Linhas PMP", f"{len(pmp_bruto):,}".replace(",", "."))
        c2.metric("Linhas H001", f"{len(h001_bruto):,}".replace(",", "."))

        st.subheader("2. Regras aplicadas")
        st.info(
            "PMP: somente STATUS = PROGRAMADO. Cada OF programada representa 1 unidade do produto. "
            "A coluna P (CÓDIGO UNIFICADO) faz a junção com H001 coluna F. "
            "A BOM vem de H001: H = MATERIAL, I = DESCRIÇÃO MATERIAL, L = QUANTIDADE. "
            "A DATA DE NECESSIDADE é DATA DE ENTREGA do PMP menos 30 dias. "
            "A semana é domingo a sábado e a NECESSIDADE DA SEMANA é a soma do material para a mesma semana."
        )

        if st.button("Processar MRP — TC/TP", type="primary", use_container_width=True, key="processar_tc_tp"):
            with st.spinner("Limpando PMP, expandindo BOM e calculando necessidades semanais..."):
                st.session_state["resultado_tc_tp"] = processar_tc_tp(pmp_bruto, h001_bruto)

    if "resultado_tc_tp" in st.session_state:
        resultado = st.session_state["resultado_tc_tp"]
        st.subheader("3. Resultado da conversão")
        metricas = resultado["metricas"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("OFs programadas", f"{metricas['ofs_programadas']:,}".replace(",", "."))
        c2.metric("OFs com BOM", f"{metricas['ofs_com_bom']:,}".replace(",", "."))
        c3.metric("Materiais únicos", f"{metricas['materiais_unicos']:,}".replace(",", "."))
        c4.metric("Avisos", str(metricas["avisos"]))

        if resultado["avisos"]:
            with st.expander(f"Avisos e inconsistências ({len(resultado['avisos'])})", expanded=True):
                for aviso in resultado["avisos"]:
                    st.write(f"- {aviso}")
        else:
            st.success("Conversão concluída sem avisos.")

        st.subheader("Prévia do MRP — TC/TP")
        st.dataframe(resultado["tratado"].head(150), use_container_width=True, height=480)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            resultado["tratado"].to_excel(writer, sheet_name="MRP_TC_TP", index=False)
            resultado["validacao"].to_excel(writer, sheet_name="Validacao", index=False)
        buffer.seek(0)
        st.subheader("4. Exportar")
        st.download_button(
            "Baixar MRP TC/TP tratado",
            data=buffer,
            file_name="MRP_TC_TP_Tratado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="download_tc_tp",
        )
