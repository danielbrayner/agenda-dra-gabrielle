from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
import os
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

app.secret_key = os.getenv("SECRET_KEY")

ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

DB_PATH = "agenda.db"

# =============================
# FUNÇÕES DE BANCO
# =============================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def horarios_disponiveis():
    conn = get_db()
    cur = conn.cursor()

    hoje = datetime.now().date()
    limite = hoje + timedelta(days=14)

    cur.execute("""
        SELECT * FROM agendamentos
        WHERE disponivel = 'sim'
        AND date(data) BETWEEN ? AND ?
        ORDER BY data, horario
    """, (hoje.isoformat(), limite.isoformat()))

    rows = cur.fetchall()
    conn.close()
    return rows


def horarios_agendados():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM agendamentos
        WHERE disponivel = 'nao'
        ORDER BY data, horario
    """)

    rows = cur.fetchall()
    conn.close()
    return rows


def marcar_horario(data, horario, nome):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE agendamentos
        SET disponivel = 'nao', nome_paciente = ?
        WHERE data = ? AND horario = ? AND disponivel = 'sim'
    """, (nome, data, horario))

    sucesso = cur.rowcount > 0
    conn.commit()
    conn.close()
    return sucesso


# =============================
# LOGIN ADMIN
# =============================
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password")

        if user == ADMIN_USER and pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_painel"))

        return render_template("login.html", erro="Login inválido")

    return render_template("login.html")


@app.route("/admin/painel")
def admin_painel():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    return render_template(
        "painel.html",
        disponiveis=horarios_disponiveis(),
        agendados=horarios_agendados()
    )


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# =============================
# GERENCIAMENTO DE HORÁRIOS
# =============================
@app.route("/admin/adicionar", methods=["POST"])
def adicionar_horario():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    data = request.form["data"]
    horario = request.form["horario"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO agendamentos (data, horario, disponivel)
        VALUES (?, ?, 'sim')
    """, (data, horario))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_painel"))


@app.route("/admin/excluir/<int:id>")
def excluir_horario(id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM agendamentos WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_painel"))


# =============================
# CHAT (ROBÔ)
# =============================
estado_usuario = {}

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    msg = data.get("message", "").lower().strip()
    user_id = "usuario_unico"

    if user_id not in estado_usuario:
        estado_usuario[user_id] = {"etapa": "inicio"}

    estado = estado_usuario[user_id]

    if estado["etapa"] == "inicio":
        if any(x in msg for x in ["marcar", "consulta", "agendar"]):
            estado["etapa"] = "nome"
            return jsonify({"reply": "Claro! Por favor, informe seu nome completo."})

    elif estado["etapa"] == "nome":
        estado["nome"] = msg
        estado["etapa"] = "horarios"

        horarios = horarios_disponiveis()
        if not horarios:
            return jsonify({"reply": "No momento não há horários disponíveis."})

        texto = "Temos os seguintes horários disponíveis:\n"
        for h in horarios:
            texto += f"- {h['data']} às {h['horario']}\n"

        texto += "\nInforme a data e o horário desejados (ex: 18/01 14:00)."
        return jsonify({"reply": texto})

    elif estado["etapa"] == "horarios":
        try:
            partes = msg.replace("às", "").replace("as", "").replace("h", "").split()
            dia, mes = map(int, partes[0].split("/"))
            hora = partes[1]

            ano = datetime.now().year
            data = datetime(ano, mes, dia).date()

            estado["data"] = data.isoformat()
            estado["horario"] = hora if ":" in hora else f"{hora}:00"
            estado["etapa"] = "confirmar"

            return jsonify({
                "reply": f"Confirmando:\n📅 {data.strftime('%d/%m/%Y')}\n⏰ {estado['horario']}\n👤 {estado['nome']}\n\nEstá correto? (sim ou não)"
            })
        except:
            return jsonify({"reply": "Formato inválido. Ex: 18/01 14:00"})

    elif estado["etapa"] == "confirmar":
        if "sim" in msg:
            sucesso = marcar_horario(
                estado["data"],
                estado["horario"],
                estado["nome"]
            )
            estado_usuario.pop(user_id)

            if sucesso:
                return jsonify({"reply": "✅ Consulta confirmada com sucesso!"})
            else:
                return jsonify({"reply": "❌ Esse horário não está mais disponível."})

        estado_usuario.pop(user_id)
        return jsonify({"reply": "Tudo bem! Se quiser, posso ajudar novamente 😊"})

    return jsonify({"reply": "Posso ajudar com agendamento de consultas."})


if __name__ == "__main__":
    app.run(debug=True)



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
