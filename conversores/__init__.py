"""Conversores do MRP-CONVERSOR.

Este pacote contém somente regras de transformação de dados.
Não deve alterar componentes do Streamlit, estado de sessão, navegação,
identidade visual ou qualquer outro comportamento de interface.

Padrão SETTA:
- UI e navegação pertencem a app.py;
- integração/estado pertencem a central_data.py e pipeline_sync.py;
- conversores recebem DataFrames e devolvem resultados de negócio.
"""
