"""Chave cronológica de semanas operacionais (domingo a sábado)."""

from datetime import date, timedelta

import pandas as pd


def semana_operacional(valor, hoje=None, sem_data_usa_hoje=False):
    """Devolve ('AAAA-SS', 'dd/mm/aaaa a dd/mm/aaaa').

    A data de origem não é modificada; datas vencidas e, quando solicitado,
    datas ausentes são alocadas na semana atual. A semana que atravessa o
    réveillon pertence ao ano do domingo em que começou.
    """
    hoje = hoje or date.today()
    data = pd.to_datetime(valor, errors="coerce", dayfirst=True)

    if pd.isna(data):
        if not sem_data_usa_hoje:
            return "", ""
        data_calculo = hoje
    else:
        data_original = pd.Timestamp(data).date()
        data_calculo = max(data_original, hoje)

    domingo = data_calculo - timedelta(days=(data_calculo.weekday() + 1) % 7)
    ano_semana = domingo.year
    primeiro_domingo = date(ano_semana, 1, 1)
    primeiro_domingo += timedelta(days=(6 - primeiro_domingo.weekday()) % 7)
    numero = ((domingo - primeiro_domingo).days // 7) + 1
    sabado = domingo + timedelta(days=6)
    return f"{ano_semana}-{numero:02d}", f"{domingo:%d/%m/%Y} a {sabado:%d/%m/%Y}"
