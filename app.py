import io

import pandas as pd
import streamlit as st

from conversores.estoque import processar_estoque
from conversores.relatorio_geral import processar_relatorio_geral

st.set_page_config(page_title="MRP-CONVERSOR", page_icon="📊", layout="wide")

st.title("MRP-CONVERSOR")
st.caption("Conversão e validação de relatórios brutos do ERP para Excel tratado.")

with st.sidebar:
    st.header("Configuração")
    tipo_relatorio = st.selectbox("Tipo de relatório", ["Relatório Geral", "Saldo em Estoque"])
    st.info(
        "O conversor não calcula MRP. Ele apenas transforma, agrupa, valida e exporta os dados para uso posterior."
    )


def ler_primeira_linha_como_cabecalho(arquivo) -> pd.DataFrame:
    """Mantido para compatibilidade com outros relatórios."""
    return pd.read_excel(arquivo, header=0)


def ler_estoque_como_cabecalho(arquivo) -> pd.DataFrame:
    """Lê relatórios de estoque em que a primeira linha é um título e a segunda é o cabeçalho."""
    return pd.read_excel(arquivo, header=1)


if tipo_relatorio == "Relatório Geral":
    st.subheader("1. Enviar relatório bruto")
    arquivo = st.file_uploader("Selecione o arquivo Excel", type=["xlsx", "xls", "xltx"], key="geral")

    if arquivo is not None:
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

        if st.button("Processar relatório", type="primary", use_container_width=True, key="processar_geral"):
            with st.spinner("Processando e validando..."):
                resultado = processar_relatorio_geral(bruto)
            st.session_state["resultado_geral"] = resultado

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
            st.download_button(
                "Baixar Excel tratado",
                data=buffer,
                file_name="RelatorioGeral_Tratado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_geral",
            )


else:
    st.subheader("1. Enviar os dois relatórios brutos")
    st.write("O Analítico é a base do saldo. O relatório de Endereço é usado apenas como complemento para descontar os endereços classificados como não disponíveis.")

    analitico_arquivo = st.file_uploader(
        "Analítico — Cód. Produto, Descrição e Saldo em Estoque",
        type=["xlsx", "xls", "xltx"],
        key="analitico",
    )
    endereco_arquivo = st.file_uploader(
        "Endereço — Cód. Produto, Endereço e Quantidade",
        type=["xlsx", "xls", "xltx"],
        key="endereco",
    )

    if analitico_arquivo is not None and endereco_arquivo is not None:
        try:
            # Ambos os relatórios de estoque possuem uma linha inicial de título.
            # A segunda linha contém o cabeçalho real; por isso header=1.
            analitico_bruto = ler_estoque_como_cabecalho(analitico_arquivo)
            endereco_bruto = ler_estoque_como_cabecalho(endereco_arquivo)
        except Exception as exc:
            st.error(f"Não foi possível ler os relatórios: {exc}")
            st.stop()

        # Mostra os endereços disponíveis para classificação.
        enderecos = (
            endereco_bruto.iloc[:, 3]
            .dropna()
            .astype(str)
            .str.strip()
        )
        enderecos = sorted([x for x in enderecos.unique().tolist() if x])

        st.subheader("2. Classificar endereços não disponíveis")
        st.caption("Marque os endereços cuja quantidade deve ser abatida do Saldo em Estoque do Analítico.")
        selecionados = st.multiselect(
            "Endereços considerados NÃO DISPONÍVEIS",
            options=enderecos,
            key="enderecos_nao_disponiveis",
        )

        c1, c2 = st.columns(2)
        c1.metric("Linhas do Analítico", f"{len(analitico_bruto):,}".replace(",", "."))
        c2.metric("Linhas do Endereço", f"{len(endereco_bruto):,}".replace(",", "."))

        if st.button("Processar saldo em estoque", type="primary", use_container_width=True, key="processar_estoque"):
            with st.spinner("Consolidando estoque e validando..."):
                resultado = processar_estoque(
                    analitico_bruto,
                    endereco_bruto,
                    selecionados,
                )
            st.session_state["resultado_estoque"] = resultado

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
            st.error("Foram encontradas falhas estruturais. O arquivo não deve ser exportado até que sejam corrigidas.")
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
            st.download_button(
                "Baixar Estoque tratado",
                data=buffer,
                file_name="Estoque_Tratado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_estoque",
            )
