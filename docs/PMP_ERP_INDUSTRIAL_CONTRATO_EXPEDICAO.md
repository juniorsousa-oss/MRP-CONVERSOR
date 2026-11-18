# Integração ERP Industrial → PMP (regra de expedição O + status P)

**Data:** 18/11/2026  
**Destino:** Supabase Edge Function `pmp-ingest` (versão 13 ou posterior)  
**Origem:** ERP Industrial — transformadores  
**Situação:** receptor e Conversor adequados; **emissor ERP Industrial ainda precisa enviar `data_expedicao`**.

## Alteração obrigatória no ERP Industrial

No objeto JSON de **cada OP** já enviado para `pmp-ingest`, incluir:

```json
"data_expedicao": "2026-11-18"
```

Quando a OP não possuir uma data real de expedição, enviar **`"data_expedicao": ""`**, nunca omitir a chave. Datas com valor precisam estar no formato ISO `AAAA-MM-DD`.

O campo deve vir da **coluna O — DATA DE EXPEDIÇÃO** do PMP, **não** da coluna N (DATA DE FINALIZAÇÃO), M (DATA ENTREGA CLIENTE) ou do status P.

O restante do envio deve permanecer igual: autenticação `Authorization: Bearer <PMP_INGEST_TOKEN>`, envelope e chaves existentes. Não registrar o token em repositórios ou logs.

### Exemplo mínimo de envelope com dados fictícios

```json
{
  "schema_version": 1,
  "origem": "ERP_INDUSTRIAL",
  "unidade": "TRANSFORMADORES",
  "quantidade": 2,
  "registros": [
    {
      "ordem_producao": "TESTE-EXP-001",
      "codigo_produto": "70150003",
      "descricao": "TC TESTE",
      "data_entrega_cliente": "2026-11-20",
      "data_expedicao": "",
      "status": "EXEC. NO PRAZO",
      "codigo_unificado": ""
    },
    {
      "ordem_producao": "TESTE-EXP-002",
      "codigo_produto": "70150003",
      "descricao": "TC TESTE",
      "data_entrega_cliente": "2026-11-20",
      "data_expedicao": "2026-11-18",
      "status": "EXEC. ADIANTADO",
      "codigo_unificado": ""
    }
  ]
}
```

**Não publicar este exemplo:** são OPs fictícias. Testes devem utilizar ambiente isolado ou unit tests antes de enviar qualquer informação real.

## Mapeamento entre o PMP do Excel e o JSON da API

| PMP | Informação | Chave JSON |
|---|---|---|
| A | ORDEM DE PRODUÇÃO | `ordem_producao` |
| C | CÓDIGO | `codigo_produto` |
| D | DESCRIÇÃO | `descricao` |
| M | DATA ENTREGA CLIENTE | `data_entrega_cliente` |
| **O** | **DATA DE EXPEDIÇÃO** | **`data_expedicao`** |
| P | STATUS | `status` |
| Q | UNIFICADO | `codigo_unificado` |

O receptor gera a fonte normalizada com os cabeçalhos **ORDEM DE PRODUÇÃO, CÓDIGO, DESCRIÇÃO, DATA ENTREGA CLIENTE, DATA DE EXPEDIÇÃO, STATUS, UNIFICADO**. O Conversor localiza por cabeçalho, independentemente da posição física.

## Lógica de classificação final

1. Se `data_expedicao` contém uma data válida → `FINALIZADA_EXPEDIDA`; não compõe produção futura ou explosão H001.
2. Sem data de expedição + status de reprovação/negação de aprovação → `NAO_APROVADA`; não conta como fabricação válida; registrar exceção.
3. Sem data de expedição + status sem reprovação → `EM_FABRICACAO`; vincular H001 e computar previsão de produção.

**Data da finalização da fabricação não é data de expedição.** Um status `EXEC. NO PRAZO`, `EXEC. ADIANTADO` ou `EXEC. ATRASADO` permanece em fabricação até haver expedição.

O Conversor não deve inventar componentes se uma OP não tiver H001: manter a fabricação marcada com MATERIAL=00000000, QUANTIDADE=0, registrando inconsistência da BOM.

## Comportamento do receptor

- Chave `data_expedicao` ausente / não string: **HTTP 422 / MISSING_EXPEDITION_DATE_FIELD**.
- Data de expedição inválida: **HTTP 422 / INVALID_EXPEDITION_DATE**.
- Nenhuma OP elegível: **HTTP 422 / NO_ELIGIBLE_ORDERS_PMP_OP**.
- O receptor não substitui a fonte atual por um payload reprovado.
- Chave, valores e quantidades recebidos devem ser auditados no ERP antes de reenviar a fonte integral.

## Checklist de homologação

- [ ] Confirmar código emissor responsável por `PMP_ERP_INDUSTRIAL.json` e alterar a montagem das `registros`.
- [ ] Verificar que todos os itens transmitidos têm `data_expedicao`, mesmo vazia.
- [ ] Conferir formatos e ausência de horários/fusos no campo de data.
- [ ] Conferir amostra do PMP completo: 1.101 OPs no arquivo de 18/11; 993 com data, 94 sem data e sem reprovação, 14 reprovadas sem data (referência histórica, não meta fixa).
- [ ] Enviar nova publicação completa pelo ERP, preservando as mesmas OPs e dados fiscais.
- [ ] Confirmar aumento da versão `pmp` na Central e a coluna DATA DE EXPEDIÇÃO na origem normalizada.
- [ ] Conferir processamento `tctp_tratado` sem erro de coluna ausente, com revisão `revisao_elegibilidade_pmp_expedicao_o_status_p = 3`.
- [ ] Recalcular MRP e conferir fabricação/necessidades por OP, incluindo produto `70150003` e OP `26-1120-01`.
- [ ] Só homologar após comparar quantidade de OPs e registrar as diferenças de demanda e listas H001.

### Limite da atualização atual

A Edge Function foi atualizada, mas **o código do emissor ERP Industrial não está neste repositório nem nos repositórios acessíveis da Nexon/SETTA por esta conexão**. Não declarar integração ponta a ponta concluída antes do envio real com a coluna O.
