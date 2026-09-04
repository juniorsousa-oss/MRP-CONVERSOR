import io
import json
import base64
from pathlib import Path

import pandas as pd
import streamlit as st

from conversores.estoque import processar_estoque
from conversores.relatorio_geral import processar_relatorio_geral
from conversores.compras import processar_compras

st.set_page_config(page_title="MRP-CONVERSOR", page_icon="📊", layout="wide")
st.title("MRP-CONVERSOR")
st.caption("Conversão e validação de relatórios brutos do ERP para Excel tratado.")

BASE_DIR = Path(__file__).parent
CONFIG_ENDERECOS = BASE_DIR / "config" / "enderecos_nao_disponiveis.json"
LOGO_PADRAO = BASE_DIR / "config" / "logo_setta.svg"


def carregar_enderecos_nao_disponiveis():
    try:
        with CONFIG_ENDERECOS.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return [str(x).strip() for x in dados.get("enderecos_nao_disponiveis", []) if str(x).strip()]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def ler_estoque_como_cabecalho(arquivo):
    return pd.read_excel(arquivo, header=1)


def ler_compras_como_cabecalho(arquivo, sheet_name=0):
    return pd.read_excel(arquivo, sheet_name=sheet_name, header=1)


def ler_for001(arquivo):
    return pd.read_excel(arquivo, sheet_name="PAINEL", header=4)


def ler_for022(arquivo):
    return pd.read_excel(arquivo, sheet_name="Datas esperadas", header=0)


def svg_data_uri(caminho):
    try:
        conteudo = caminho.read_text(encoding="utf-8")
        return "data:image/svg+xml;base64," + base64.b64encode(conteudo.encode("utf-8")).decode("ascii")
    except OSError:
        return ""


with st.sidebar:
    logo_largura = st.session_state.get("logo_largura", 280)
    logo_distancia_topo = st.session_state.get("logo_distancia_topo", -20)
    logo_upload = st.session_state.get("logo_upload_data")

    with st.popover("⚙️", help="Configurar logo da empresa"):
        st.markdown("**Identidade visual**")
        novo_logo = st.file_uploader(
            "Adicionar ou substituir logo",
            type=["png", "jpg", "jpeg", "svg"],
            key="logo_upload_widget",
        )
        if novo_logo is not None:
            st.session_state["logo_upload_data"] = {
                "bytes": novo_logo.getvalue(),
                "mime": "image/svg+xml" if novo_logo.name.lower().endswith(".svg") else novo_logo.type,
            }
            logo_upload = st.session_state["logo_upload_data"]

        st.markdown("**Tamanho da logo**")
        logo_largura = st.slider(
            "Largura (px)", min_value=80, max_value=340,
            value=int(logo_largura), step=10, key="logo_largura"
        )
        st.markdown("**Posição vertical**")
        logo_distancia_topo = st.slider(
            "Distância do topo (px)", min_value=-120, max_value=120,
            value=int(logo_distancia_topo), step=5,
            help="Valores negativos aproximam a logo do topo.", key="logo_distancia_topo"
        )

    if logo_upload:
        mime = logo_upload.get("mime", "image/png")
        encoded = base64.b64encode(logo_upload["bytes"]).decode("ascii")
        src = f"data:{mime};base64,{encoded}"
    else:
        src = svg_data_uri(LOGO_PADRAO)

    if src:
        st.markdown(
            f'''<div style="margin-top:{logo_distancia_topo}px;width:100%;display:flex;justify-content:center;">
            <img src="{src}" style="width:{logo_largura}px;max-width:100%;height:auto;object-fit:contain;display:block;">
            </div>''',
            unsafe_allow_html=True,
        )

    st.divider()
    st.header("Configuração")
    tipo_relatorio = st.selectbox(
        "Tipo de relatório",
        ["Relatório Geral", "Saldo em Estoque", "Compras — S.C + P.C + Pré-nota"],
    )
    st.info("O conversor não calcula MRP. Ele transforma, agrupa, valida e exporta os dados para uso posterior.")


if tipo_relatorio == "Relatório Geral":
    st.subheader("1. Enviar os três relatórios brutos")
    st.caption("O Relatório Geral recebe a DATA MRP e a condição do FOR-001 pela OP, e a DATA CM do FOR-022 pela OP.")
    arquivo = st.file_uploader("Relatório Geral — aba 'Geral'", type=["xlsx", "xls", "xltx"], key="geral")
    for001_arquivo = st.file_uploader("FOR-001 — Plano Mestre de Produção", type=["xlsx", "xls", "xltx"], key="for001")
    for022_arquivo = st.file_uploader("FOR-022 — Planejamento Macro Produção", type=["xlsx", "xls", "xltx"], key="for022")
    if arquivo is not None and for001_arquivo is not None and for022_arquivo is not None:
        try:
            bruto = pd.read_excel(arquivo, sheet_name="Geral")
            for001_bruto = ler_for001(for001_arquivo)
            for022_bruto = ler_for022(for022_arquivo)
        except Exception as exc:
            st.error(f"Não foi possível ler os arquivos: {exc}")
            st.stop()
        c1, c2, c3 = st.columns(3)
        c1.metric("Linhas Relatório Geral", f"{len(bruto):,}".replace(",", "."))
        c2.metric("OPs FOR-001", f"{len(for001_bruto):,}".replace(",", "."))
        c3.metric("Linhas FOR-022", f"{len(for022_bruto):,}".replace(",", "."))
        st.subheader("2. Regras aplicadas")
        st.info("FOR-001: OP → DATA MRP + CONDIÇÃO. NORMAL usa a DATA MRP para calcular a semana e entra na NECESSIDADE DA SEMANA. Condições diferentes de NORMAL permanecem visíveis no campo da semana, mas não entram no total. FOR-022: OP → DATA CM; OP não encontrada = NI.")
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
            for erro in resultado["erros"]: st.write(f"- {erro}")
        else: st.success("Validação concluída sem erros críticos.")
        if resultado["avisos"]:
            with st.expander(f"Avisos ({len(resultado['avisos'])})"):
                for aviso in resultado["avisos"]: st.write(f"- {aviso}")
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
            for erro in resultado["erros"]: st.write(f"- {erro}")
        else: st.success("Conversão concluída. O Analítico foi mantido como base do saldo.")
        if resultado["avisos"]:
            with st.expander(f"Avisos e inconsistências ({len(resultado['avisos'])})"):
                for aviso in resultado["avisos"]: st.write(f"- {aviso}")
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

else:
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
            for erro in resultado["erros"]: st.write(f"- {erro}")
        else: st.success("Fluxo de compras convertido e validado.")
        if resultado["avisos"]:
            with st.expander(f"Avisos e inconsistências ({len(resultado['avisos'])})"):
                for aviso in resultado["avisos"]: st.write(f"- {aviso}")
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
