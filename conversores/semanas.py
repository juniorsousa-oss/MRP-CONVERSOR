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


def interpretar_data_setta(valor):
    """Interpreta datas brasileiras e ISO sem inverter dia/mês.

    Excel/datetime permanecem como datas; ISO AAAA-MM-DD nunca passa por
    dayfirst=True. Data BR DD/MM/AAAA é reconhecida pelo formato explícito.
    Não tenta adivinhar formatos desconhecidos.
    """
    import re
    if valor is None:
        return pd.NaT
    try:
        if pd.isna(valor):
            return pd.NaT
    except (TypeError, ValueError):
        return pd.NaT
    if isinstance(valor, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(valor)
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        # Datas numéricas do Excel (somente a faixa de seriais de data).
        numero = float(valor)
        if numero.is_integer() and 20000 <= numero <= 80000:
            return pd.to_datetime(numero, unit="D", origin="1899-12-30", errors="coerce")
        return pd.NaT
    texto = str(valor).strip()
    if not texto or texto.upper() in {"NAN", "NAT", "NONE", "NI", "NA", "N/A"}:
        return pd.NaT
    if re.match(r"^\\d{4}-\\d{2}-\\d{2}(?:$|[T\\s])", texto):
        return pd.to_datetime(texto[:10], format="%Y-%m-%d", errors="coerce")
    if re.match(r"^\\d{2}/\\d{2}/\\d{4}(?:$|\\s)", texto):
        return pd.to_datetime(texto[:10], format="%d/%m/%Y", errors="coerce")
    if re.match(r"^\\d{4}/\\d{2}/\\d{2}(?:$|\\s)", texto):
        return pd.to_datetime(texto[:10], format="%Y/%m/%d", errors="coerce")
    return pd.NaT


def semana_operacional(valor, hoje=None, sem_data_usa_hoje=False):
    """Devolve ('AAAA-SS', 'dd/mm/aaaa a dd/mm/aaaa').

    A data de origem não é modificada; datas vencidas e, quando solicitado,
    datas ausentes são alocadas na semana atual. A semana que atravessa o
    réveillon pertence ao ano do domingo em que começou.
    """
    hoje = hoje if hoje is not None else hoje_setta()
    data = interpretar_data_setta(valor)

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
