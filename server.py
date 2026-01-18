from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from functools import wraps
from flask_cors import CORS
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "chave_padrao_insegura")
CORS(app)

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

# =============================
# AUTH ADMIN
# =============================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logado"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

# =============================
# INTENÇÕES
# =============================
def detectar_intencao(msg):
    msg = msg.lower()

    if any(p in msg for p in ["reiniciar", "recomeçar"]):
        return "REINICIAR"
    if any(p in msg for p in ["quanto custa", "valor", "preço", "preco"]):
        return "PRECO"
    if any(p in msg for p in [
        "onde atende",
        "onde a dra atende",
        "local de atendimento",
        "local",
        "endereço",
        "endereco",
        "consultório",
        "consultorio"
    ]):
        return "LOCAL"
    if any(p in msg for p in ["horário", "horarios", "disponível", "disponiveis", "vaga"]):
        return "HORARIOS"
    if any(p in msg for p in ["marcar", "agendar"]):
        return "AGENDAR"
    if any(p in msg for p in ["não quero marcar", "nao quero marcar"]):
        return "DESISTIR"

    if any(p in msg for p in ["plano", "convênio", "convenio", "atende plano"]):
        return "PLANO"

    return "DESCONHECIDO"


def parece_nome(texto):
    proibidas = ["valor", "horario", "consulta", "onde", "preço", "preco"]
    texto = texto.lower()
    return len(texto.split()) >= 1 and not any(p in texto for p in proibidas)


def eh_pergunta_administrativa(msg):
    palavras = [
        "quanto custa", "valor", "preço", "preco",
        "onde atende", "endereço", "endereco",
        "local", "consultório", "consultorio",
        "duração", "duracao", "tempo",
        "pagamento", "forma de pagamento"
    ]
    return any(p in msg for p in palavras)

# =============================
# ROTAS
# =============================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    mensagem_original = data.get("message", "").strip()
    mensagem = mensagem_original.lower()

    if not mensagem:
        return jsonify({"error": "Mensagem vazia"}), 400

    user_id = "usuario_unico"

    if user_id not in estado_usuario:
        estado_usuario[user_id] = {
            "etapa": "inicio",
            "nome": None,
            "data": None,
            "horario": None,
            "boas_vindas_enviadas": False
        }

    estado = estado_usuario[user_id]
    intencao = detectar_intencao(mensagem)

    # =============================
    # COMANDOS GLOBAIS
    # =============================
    if intencao == "REINICIAR":
        estado_usuario.pop(user_id, None)
        return jsonify({"reply": "🔄 Atendimento reiniciado. Como posso ajudar?"})

    if intencao == "DESISTIR":
        estado_usuario.pop(user_id, None)
        return jsonify({"reply": "Tudo bem 😊 Se precisar, estarei por aqui."})

    # =============================
    # ETAPA INICIAL
    # =============================
    if estado["etapa"] == "inicio":

        if not estado["boas_vindas_enviadas"]:
            estado["boas_vindas_enviadas"] = True
            return jsonify({
                "reply": (
                    "Sou o assistente virtual inteligente da Dra. Gabrielle. "
                    "Espero que esteja bem 😊. Como posso ajudar?\n"
                    "Você pode reiniciar esse atendimento a qualquer momento digitando *Reiniciar*."
                )
            })

        if mensagem in ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"]:
            return jsonify({"reply": "😊 Posso informar valores, local ou te ajudar a agendar uma consulta."})

        if intencao == "PRECO":
            return jsonify({"reply": "💰 O valor da consulta é R$ 450,00 (particular)."})

        if intencao == "LOCAL":
            return jsonify({"reply": "📍 A Dra Gabrielle atende presencialmente no Shopping Aldeota – Sala 1605"})

        if intencao == "HORARIOS":
            horarios = buscar_disponibilidade_sqlite()
            if not horarios:
                return jsonify({"reply": "No momento não há horários disponíveis."})

            texto = "📅 Horários disponíveis:\n"
            for d, h in horarios:
                texto += f"- {d.strftime('%d/%m/%Y')} às {h}\n"
            texto += "\nSe quiser, posso agendar para você 😊"
            return jsonify({"reply": texto})

        if intencao == "AGENDAR":
            estado["etapa"] = "pedir_nome"
            return jsonify({"reply": "Perfeito 😊 Qual é o seu nome completo?"})

        if intencao == "PLANO":
            return jsonify({
                "reply": (
                    "💳 A Dra. Gabrielle atende apenas consultas particulares.\n\n"
                    "Se quiser, posso te informar valores ou ajudar no agendamento 😊"
                )
            })

        return jsonify({"reply": "😊 Posso te ajudar com valores, local ou agendamento."})

    # =============================
    # PEDIR NOME
    # =============================
    if estado["etapa"] == "pedir_nome":

        if eh_pergunta_administrativa(mensagem):
            if "valor" in mensagem or "preço" in mensagem or "preco" in mensagem:
                return jsonify({"reply": "💰 O valor da consulta é R$ 450,00.\n\nQuando quiser continuar, me informe seu nome completo 😊"})
            if "onde atende" in mensagem or "endereco" in mensagem or "endereço" in mensagem:
                return jsonify({"reply": "📍 Shopping Aldeota – Sala 1605\n\nQuando quiser continuar, me informe seu nome completo 😊"})
            if "duracao" in mensagem or "duração" in mensagem:
                return jsonify({"reply": "⏱️ A consulta dura cerca de 1 hora.\n\nQuando quiser continuar, me informe seu nome completo 😊"})

        if not parece_nome(mensagem_original):
            return jsonify({"reply": "😊 Para continuar o agendamento, me informe seu *nome completo*."})

        estado["nome"] = mensagem_original
        estado["etapa"] = "mostrar_horarios"

        horarios = buscar_disponibilidade_sqlite()
        if not horarios:
            estado_usuario.pop(user_id)
            return jsonify({"reply": "No momento não há horários disponíveis."})

        texto = "Temos os seguintes horários disponíveis:\n"
        for d, h in horarios:
            texto += f"- {d.strftime('%d/%m/%Y')} às {h}\n"
        texto += "\nInforme a data e o horário desejados (ex: 18/12 14:00)."
        return jsonify({"reply": texto})

    # =============================
    # ESCOLHER HORÁRIO
    # =============================
    if estado["etapa"] == "mostrar_horarios":
        try:
            partes = mensagem.replace("às", "").replace("as", "").split()
            data_str, hora_str = partes[0], partes[1]
            if ":" not in hora_str:
                hora_str += ":00"

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
                "reply": (
                    f"Confirmando:\n📅 {data.strftime('%d/%m/%Y')}\n"
                    f"⏰ {hora_str}\n👤 {estado['nome']}\n\n"
                    "Está correto? (sim ou não)"
                )
            })
        except:
            return jsonify({"reply": "Use o formato: 18/12 14:00"})

    # =============================
    # CONFIRMAÇÃO
    # =============================
    if estado["etapa"] == "confirmacao":

        if "sim" in mensagem:
            sucesso = marcar_horario_sqlite(
                estado["data"], estado["horario"], estado["nome"]
            )
            estado_usuario.pop(user_id)

            if sucesso:
                return jsonify({
                    "reply": (
                        "✅ Consulta confirmada!\n"
                        "📍 Shopping Aldeota – Sala 1605\n"
                        "💰 Valor: R$ 450,00\n\n"
                        "Qualquer dúvida, estou à disposição 😊"
                    )
                })

            return jsonify({"reply": "❌ Esse horário não está mais disponível."})

        estado_usuario.pop(user_id)
        return jsonify({"reply": "Tudo bem 😊 Se quiser, posso ajudar a agendar outro horário."})


# =============================
# ADMIN
# =============================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (
            request.form.get("usuario") == os.getenv("ADMIN_USER")
            and request.form.get("senha") == os.getenv("ADMIN_PASSWORD")
            #request.form.get("usuario") == "admin"
            #and request.form.get("senha") == "admin"
        ):
            session["admin_logado"] = True
            return redirect(url_for("admin_panel"))
        return render_template("admin_login.html", erro="Usuário ou senha inválidos")
    return render_template("admin_login.html")


@app.route("/admin")
@login_required
def admin_panel():
    conn = get_db_connection()
    consultas = conn.execute(
        "SELECT * FROM agendamentos WHERE disponivel='nao' ORDER BY data, horario"
    ).fetchall()
    horarios_livres = conn.execute(
        "SELECT * FROM agendamentos WHERE disponivel='sim' ORDER BY data, horario"
    ).fetchall()
    conn.close()

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
    conn = get_db_connection()
    conn.execute("""
        UPDATE agendamentos
        SET disponivel='sim', nome_paciente=NULL
        WHERE id=?
    """, (consulta_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))


@app.route("/admin/adicionar-horario", methods=["POST"])
@login_required
def adicionar_horario():
    data = request.form.get("data")
    horario = request.form.get("horario")

    if data and horario:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO agendamentos (data, horario, disponivel) VALUES (?, ?, 'sim')",
            (data, horario)
        )
        conn.commit()
        conn.close()

    return redirect(url_for("admin_panel"))


@app.route("/admin/excluir-horario/<int:horario_id>")
@login_required
def excluir_horario_livre(horario_id):
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM agendamentos WHERE id=? AND disponivel='sim'",
        (horario_id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

#if __name__ == '__main__': app.run(host='127.0.0.1', port=5000, debug=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
