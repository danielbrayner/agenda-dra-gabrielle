import sqlite3

conn = sqlite3.connect("agenda.db")
cursor = conn.cursor()

for row in cursor.execute("SELECT data, horario, disponivel, nome_paciente FROM agendamentos"):
    print(row)

conn.close()
