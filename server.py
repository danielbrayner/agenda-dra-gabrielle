from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from functools import wraps
from flask_cors import CORS
import os
from dotenv import load_dotenv
from openai import OpenAI
import sqlite3
from datetime import datetime, timedelta


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "chave_padrao_insegura")
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =============================
# CONTROLE DE ESTADO
# =============================
estado_usuario = {}

# =============================
# BANCO DE DADOS
# =============================
def get_db_connection():
    conn = sqlite3.connect("agenda.db")
    conn.row_factory = sqlite3.Row
    return conn


def buscar_disponibilidade_sqlite():
    conn = get_db_connection()
    cursor = conn.cursor()

    hoje = datetime.now().date()
    limite = hoje + timedelta(days=14)

    cursor.execute("""
        SELECT data, horario
        FROM agendamentos
        WHERE disponivel = 'sim'
          AND date(data) BETWEEN ? AND ?
        ORDER BY data, horario
    """, (str(hoje), str(limite)))

    rows = cursor.fetchall()
    conn.close()

    return [(datetime.strptime(r["data"], "%Y-%m-%d").date(), r["horario"]) for r in rows]


def marcar_horario_sqlite(data, horario, nome_paciente):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM agendamentos
        WHERE data = ? AND horario = ? AND disponivel = 'sim'
    """, (str(data), horario))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return False

    cursor.execute("""
        UPDATE agendamentos
        SET disponivel = 'nao',
            nome_paciente = ?,
            criado_em = ?
        WHERE id = ?
    """, (
        nome_paciente,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        row["id"]
    ))

    conn.commit()
    conn.close()
    return True


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logado"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


def buscar_consultas_agendadas():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, data, horario, nome_paciente, criado_em
        FROM agendamentos
        WHERE disponivel = 'nao'
        ORDER BY data, horario
    """)

    consultas = cursor.fetchall()
    conn.close()
    return consultas

def buscar_horarios_livres():
    conn = sqlite3.connect("agenda.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, data, horario
        FROM agendamentos
        WHERE disponivel = 'sim'
        ORDER BY data, horario
    """)

    horarios = cursor.fetchall()
    conn.close()
    return horarios



# =============================
# ROTAS
# =============================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    user_message_original = data.get("message", "").strip()
    user_message = user_message_original.lower()

    if not user_message:
        return jsonify({"error": "Mensagem vazia"}), 400

    user_id = "usuario_unico"

    if user_id not in estado_usuario:
        estado_usuario[user_id] = {
            "etapa": "inicio",
            "nome": None,
            "data": None,
            "horario": None
        }

    estado = estado_usuario[user_id]

    # =============================
    # INÍCIO
    # =============================
    if estado["etapa"] == "inicio":

        if any(p in user_message for p in ["bom dia", "boa tarde", "boa noite"]):
            hora = datetime.now().hour
            saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
            return jsonify({
                "reply": f"{saudacao}! 😊 Sou o assistente virtual inteligente da Dra. Gabrielle. "
                         "Espero que esteja bem. Como posso ajudar?"
            })

        if any(p in user_message for p in ["receita", "remédio", "medicamento"]):
            return jsonify({
                "reply": "Entendi. Vou encaminhar sua mensagem para a Dra. Gabrielle e, assim que possível, "
                         "ela assumirá a conversa por aqui."
            })

        if any(p in user_message for p in ["marcar", "agendar", "consulta", "atendimento"]):
            estado["etapa"] = "pedir_nome"
            return jsonify({
                "reply": "Claro! Para agendar, preciso apenas do seu nome completo 😊"
            })

        if "quanto custa" in user_message or "valor" in user_message:
            return jsonify({"reply": "O valor da consulta é R$ 450,00 (particular)."})

    # =============================
    # NOME DO PACIENTE
    # =============================
    elif estado["etapa"] == "pedir_nome":
        estado["nome"] = user_message_original
        estado["etapa"] = "mostrar_horarios"

        horarios = buscar_disponibilidade_sqlite()
        if not horarios:
            estado_usuario.pop(user_id)
            return jsonify({"reply": "No momento não há horários disponíveis nas próximas duas semanas."})

        texto = "Temos os seguintes horários disponíveis:\n"
        for d, h in horarios:
            texto += f"- {d.strftime('%d/%m/%Y')} às {h}\n"

        texto += "\nInforme a data e o horário desejados (ex: 18/12 14:00)."
        return jsonify({"reply": texto})

    # =============================
    # ESCOLHA DE DATA / HORÁRIO
    # =============================
    elif estado["etapa"] == "mostrar_horarios":
        try:
            partes = user_message.replace("às", "").replace("as", "").split()
            data_str = partes[0]
            hora_str = partes[1].replace("h", "").strip()

            if ":" not in hora_str:
                hora_str = f"{hora_str}:00"

            dia, mes = map(int, data_str.split("/"))
            hoje = datetime.now().date()
            ano = hoje.year
            data = datetime(ano, mes, dia).date()

            if data < hoje:
                data = datetime(ano + 1, mes, dia).date()

            estado["data"] = data
            estado["horario"] = hora_str
            estado["etapa"] = "confirmacao"

            return jsonify({
                "reply": f"Perfeito! 😊 Confirmando:\n"
                         f"📅 Data: {data.strftime('%d/%m/%Y')}\n"
                         f"⏰ Horário: {hora_str}\n"
                         f"👤 Nome: {estado['nome']}\n\n"
                         f"Está correto? (sim ou não)"
            })
        except:
            return jsonify({"reply": "Não consegui entender. Use o formato: 18/12 14:00"})

    # =============================
    # CONFIRMAÇÃO
    # =============================
    elif estado["etapa"] == "confirmacao":
        if "sim" in user_message:
            sucesso = marcar_horario_sqlite(
                estado["data"],
                estado["horario"],
                estado["nome"]
            )

            estado_usuario.pop(user_id)

            if sucesso:
                return jsonify({
                    "reply": "✅ Consulta confirmada com sucesso!\n"
                             "📍 Shopping Aldeota, sala 1605\n"
                             "⏰ Duração: 1 hora\n"
                             "💳 Valor: R$ 450,00 (particular)\n\n"
                             "Qualquer dúvida, fico à disposição 😊"
                })
            else:
                return jsonify({"reply": "❌ Esse horário não está mais disponível. Escolha outro, por favor."})

        else:
            estado_usuario.pop(user_id)
            return jsonify({"reply": "Tudo bem! Se quiser, posso ajudar a agendar outro horário 😊"})

    # =============================
    # FALLBACK
    # =============================
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um assistente exclusivo da Dra. Gabrielle, médica psiquiatra. "
                    "Responda apenas informações administrativas da consulta."
                )
            },
            {"role": "user", "content": user_message_original}
        ]
    )

    return jsonify({"reply": completion.choices[0].message.content})

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        if (
            usuario == os.getenv("ADMIN_USER")
            and senha == os.getenv("ADMIN_PASSWORD")
                #usuario == "admin"
                #and senha == "admin"
        ):
            session["admin_logado"] = True
            return redirect(url_for("admin_panel"))
        else:
            return render_template(
                "admin_login.html",
                erro="Usuário ou senha inválidos"
            )

    return render_template("admin_login.html")


@app.route("/admin")
@login_required
def admin_panel():
    consultas = buscar_consultas_agendadas()
    horarios_livres = buscar_horarios_livres()
    return render_template(
        "admin_panel.html",
        consultas=consultas,
        horarios_livres=horarios_livres
    )




@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/excluir/<int:consulta_id>")
@login_required
def excluir_consulta(consulta_id):
    conn = sqlite3.connect("agenda.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE agendamentos
        SET disponivel = 'sim', nome_paciente = NULL
        WHERE id = ?
    """, (consulta_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_panel"))

@app.route("/admin/adicionar-horario", methods=["POST"])
@login_required
def adicionar_horario():
    data = request.form.get("data")
    horario = request.form.get("horario")

    if not data or not horario:
        return redirect(url_for("admin_panel"))

    conn = sqlite3.connect("agenda.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO agendamentos (data, horario, disponivel)
        VALUES (?, ?, 'sim')
    """, (data, horario))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_panel"))


#if __name__ == '__main__': app.run(host='127.0.0.1', port=5000, debug=True)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
