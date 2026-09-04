import io
import streamlit as st
import pandas as pd

from conversores.relatorio_geral import processar_relatorio_geral

st.set_page_config(page_title="MRP-CONVERSOR", page_icon="📊", layout="wide")

st.title("MRP-CONVERSOR")
st.caption("Conversão e validação de relatórios brutos do ERP para Excel tratado.")

with st.sidebar:
    st.header("Configuração")
    tipo_relatorio = st.selectbox("Tipo de relatório", ["Relatório Geral"])
    st.info(
        "O conversor não calcula MRP. Ele apenas transforma, agrupa, valida e exporta os dados para uso posterior."
    )

st.subheader("1. Enviar relatório bruto")
arquivo = st.file_uploader("Selecione o arquivo Excel", type=["xlsx", "xls"])

if arquivo is not None:
    if tipo_relatorio == "Relatório Geral":
        try:
            bruto = pd.read_excel(arquivo, sheet_name="Geral")
        except ValueError:
            st.error("A planilha 'Geral' não foi encontrada no arquivo.")
            st.stop()
        except Exception as exc:
            st.error(f"Não foi possível ler o arquivo: {exc}")
            st.stop()

        st.subheader("2. Processar")
        st.write(f"Linhas recebidas: **{len(bruto):,}**".replace(",", "."))

        if st.button("Processar relatório", type="primary", use_container_width=True):
            with st.spinner("Processando e validando..."):
                resultado = processar_relatorio_geral(bruto)
            st.session_state["resultado"] = resultado

if "resultado" in st.session_state:
    resultado = st.session_state["resultado"]

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
        st.download_button(
            "Baixar Excel tratado",
            data=buffer,
            file_name="RelatorioGeral_Tratado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
