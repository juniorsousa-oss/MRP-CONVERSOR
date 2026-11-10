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

## Ingestão da API MES com exceções (preparação de código)

O adaptador `conversores/mes_generalreport.py` disponibiliza
`adaptar_json_mes_com_quarentena(payload, linhas_referencia=...)`,
que separa materiais válidos e linhas com erros, sem interromper a
conversão inteira pela falta de `Code` em uma única solicitação.

O retorno contém `tratado`, `inconsistencias`, `metricas`,
`pode_processar`, `status` e `motivos_protecao`. Registros com falha
são mantidos no diagnóstico operacional com motivo, linha e quantidade
informada; não se inventa código nem se subestima a demanda sem alerta.

Os limites iniciais são **0,5% de registros inconsistentes** e
**80% do volume da última fonte conhecida**; se extrapolados, preservar
a versão anterior para prevenir sobrescrita por payload parcialmente
corrompido. A conversão estrita anterior permanece compatível.

A publicação de bases deve sempre tratar a lista de `inconsistencias`
separadamente e só seguir quando `pode_processar=True`. O pipeline
atual de Relatório Geral já separa materiais sem chave e publica base
`relatorio_geral_inconsistencias`; a ingestão automática da API ainda
precisa ser vinculada à Central de Dados e executar essa publicação
antes de substituir o arquivo manual.

## MES API · exceções isoladas durante o reprocessamento

Quando a fonte `relatorio_geral` for publicada pela API MES, a aba
`Geral` conterá **somente materiais válidos** e a aba
`Inconsistencias MES` registrará todos os itens rejeitados (inclusive
BASCULANTE com código ausente). O pipeline de Relatório Geral agora
importa a aba adicional para a base derivada
`relatorio_geral_inconsistencias`, **sem permitir a recuperação
automática de códigos desses registros por coincidência de descrição**.

Assim o fluxo segue:

1. MES valida 100% das linhas; isola exceções com motivo.
2. O Monitor publica apenas após pré-validar o Excel gerado.
3. O worker existente percebe nova versão e processa `Geral` com
   FOR001, FOR022 e CADASTROS.
4. O Conversor agrega `Inconsistencias MES` à quarentena derivada,
   preservando a quantidade informada e deixando `Pendência` sem valor
   quando a quantidade é inválida.
5. Dados válidos são publicados mesmo existindo erros individuais.
   Falhas de esquema generalizadas interrompem a publicação.

A automação da coleta fica no repositório MONITOR-APIs às 07h20
(Brasília) e exige credencial MES no GitHub Actions. O reprocessamento
do Conversor continua pelo worker já agendado de cinco em cinco minutos
(sujeito a atraso de execução no GitHub).
