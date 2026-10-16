"""Chave cronológica de semanas operacionais (domingo a sábado)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd


FUSO_SETTA = ZoneInfo("America/Sao_Paulo")


def hoje_setta() -> date:
    """Data atual da SETTA, independente do fuso do servidor."""
    return datetime.now(FUSO_SETTA).date()


def inicio_semana_operacional(hoje: date | None = None) -> date:
    """Domingo inicial da semana operacional (domingo a sábado)."""
    referencia = hoje if hoje is not None else hoje_setta()
    return referencia - timedelta(days=(referencia.weekday() + 1) % 7)


def versao_semana_operacional(hoje: date | None = None) -> int:
    """Marcador inteiro YYYYMMDD do domingo, para controle de reprocessamento."""
    return int(inicio_semana_operacional(hoje).strftime("%Y%m%d"))


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
