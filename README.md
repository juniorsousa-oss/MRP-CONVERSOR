# MRP-CONVERSOR

Aplicação independente para transformar relatórios brutos exportados do ERP em relatórios padronizados e validados para uso posterior no MRP.

## Fluxo

`Relatório bruto → Conversão → Agrupamento → Validação → Excel tratado`

## Primeira versão

O primeiro módulo trata o **Relatório Geral**, usando a aba `Geral`.

Regras principais:

- Projeto: exatamente 11 dígitos, completando zeros à esquerda quando necessário.
- Código do material: exatamente 8 dígitos, completando zeros à esquerda quando necessário.
- `COD_MRP = Projeto + "_" + Código`.
- Uma linha final por Projeto + Material.
- Última solicitação: maior data.
- Quantidade necessária: soma.
- Quantidade atendida: soma.
- Pendência: recalculada como necessária - atendida.
- Responsável pela separação: nomes distintos consolidados.
- Data de separação: maior data.
- Responsável pela conferência: nomes distintos consolidados.
- Data de conferência: maior data.
- Lote não participa do agrupamento nesta primeira versão.

## Execução local

```bash
pip install -r requirements.txt
streamlit run app.py
```

O aplicativo é propositalmente separado do futuro sistema MRP. O MRP deverá consumir somente os arquivos tratados e validados por este conversor.
