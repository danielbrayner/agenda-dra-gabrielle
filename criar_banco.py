import sqlite3

conn = sqlite3.connect("agenda.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS agendamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    horario TEXT NOT NULL,
    disponivel TEXT NOT NULL,
    nome_paciente TEXT,
    primeira_vez INTEGER,
    criado_em TEXT
)
""")

conn.commit()
conn.close()

print("Banco de dados criado com sucesso!")
