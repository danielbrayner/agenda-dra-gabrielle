import sqlite3
import pandas as pd
from datetime import datetime

# Lê o Excel
df = pd.read_excel("agenda.xlsx")

# Normaliza nomes das colunas
df.columns = [c.lower().strip() for c in df.columns]

# Conecta ao banco
conn = sqlite3.connect("agenda.db")
cursor = conn.cursor()

for _, row in df.iterrows():
    cursor.execute("""
        INSERT INTO agendamentos (
            data,
            horario,
            disponivel,
            nome_paciente,
            primeira_vez,
            criado_em
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        str(pd.to_datetime(row["data"]).date()),
        str(row["horario"]),
        str(row["disponivel"]).lower(),
        row.get("nome do paciente"),
        None,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

conn.commit()
conn.close()

print("Dados migrados com sucesso do Excel para o SQLite!")
