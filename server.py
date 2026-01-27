from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from functools import wraps
from flask_cors import CORS
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime, timedelta, date
import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse, urlencode



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
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada.")

    url = urlparse(database_url)

    return psycopg2.connect(
        host=url.hostname,
        database=url.path[1:],
        user=url.username,
        password=url.password,
        port=url.port
    )




def fetchall_dict(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]



def buscar_disponibilidade():
    conn = get_db_connection()
    cursor = conn.cursor()

    hoje = datetime.now().date()
    limite = hoje + timedelta(days=14)

    cursor.execute("""
        SELECT data, horario
        FROM agendamentos
        WHERE disponivel = 'sim'
          AND data BETWEEN %s AND %s
        ORDER BY data, horario
    """, (hoje, limite))

    rows = fetchall_dict(cursor)
    conn.close()

    return [(r["data"], r["horario"]) for r in rows]



def marcar_horario(data, horario, nome_paciente, telefone, modalidade):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM agendamentos
        WHERE data = %s AND horario = %s AND disponivel = 'sim'
    """, (data, horario))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    agendamento_id = row[0]

    cursor.execute("""
        UPDATE agendamentos
        SET disponivel = 'nao',
            nome_paciente = %s,
            telefone = %s,
            modalidade = %s,
            criado_em = NOW()
        WHERE id = %s
    """, (
        nome_paciente,
        telefone,
        modalidade,
        agendamento_id
    ))

    conn.commit()
    conn.close()
    return True



def deletar_por_id(id_valor):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM agendamentos WHERE id = %s", (id_valor,))

    conn.commit()
    conn.close()



def deletar_varios(ids):
    if not ids:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM agendamentos WHERE id = ANY(%s)",
        (ids,)
    )

    conn.commit()
    conn.close()



def garantir_date(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None




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


def parece_telefone(texto):
    numeros = "".join(c for c in texto if c.isdigit())
    return 10 <= len(numeros) <= 11


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
        "onde ela atende",
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
            "telefone": None,
            "modalidade": None,
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
                    "Olá, sou o assistente virtual inteligente da Dra. Gabrielle. "
                    "Espero que esteja bem 😊. Como posso ajudar?\n"
                    "Você pode reiniciar esse atendimento a qualquer momento digitando Reiniciar."
                )
            })

        if mensagem in ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"]:
            return jsonify({"reply": "😊 Posso informar valores, local ou te ajudar a agendar uma consulta."})

        if intencao == "PRECO":
            return jsonify({"reply": "💰 O valor da consulta é R$ 450,00 (particular)."})

        if intencao == "LOCAL":
            return jsonify({"reply": "📍 A Dra Gabrielle atende presencialmente no Shopping Aldeota – Sala 1605"})

        if intencao == "HORARIOS":
            horarios = buscar_disponibilidade()
            if not horarios:
                return jsonify({"reply": "No momento não há horários disponíveis."})

            texto = "📅 Horários disponíveis:\n"
            for d, h in horarios:
                d = garantir_date(d)
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
            return jsonify({"reply": "Posso te passar essas informações 😊\nMas antes, me informe seu nome completo para continuar o agendamento."})

        if not parece_nome(mensagem_original):
            return jsonify({"reply": "😊 Para continuar o agendamento, me informe seu *nome completo*."})

        estado["nome"] = mensagem_original
        estado["etapa"] = "pedir_telefone"

    # =============================
    # PEDIR TELEFONE
    # =============================
    if estado["etapa"] == "pedir_telefone":

        if not parece_telefone(mensagem_original):
            return jsonify({"reply": "📞 Por favor, informe um telefone válido com DDD (ex: 85999999999)."})

        estado["telefone"] = mensagem_original
        estado["etapa"] = "mostrar_horarios"

        horarios = buscar_disponibilidade()
        if not horarios:
            estado_usuario.pop(user_id)
            return jsonify({"reply": "No momento não há horários disponíveis."})

        opcoes = []
        for d, h in horarios:
            data_str = d.strftime("%d/%m/%Y")
            hora_str = h.strftime("%H:%M")
            opcoes.append(f"{data_str} {hora_str}")

        return jsonify({
            "reply": "📅 Escolha um dos horários disponíveis:",
            "options": opcoes
        })

    # =============================
    # ESCOLHER HORÁRIO
    # =============================
    if estado["etapa"] == "mostrar_horarios":
        try:
            partes = mensagem.replace("às", "").replace("as", "").split()
            data_str, hora_str = partes[0], partes[1]

            if len(hora_str) == 5:
                hora_str += ":00"

            dia, mes, ano = map(int, data_str.split("/"))
            data_escolhida = date(ano, mes, dia)

            estado["data"] = data_escolhida
            estado["horario"] = hora_str

        except:
            return jsonify({"reply": "Clique em um dos horários da lista 😊"})

        estado["etapa"] = "perguntar_modalidade"
        return jsonify({
            "reply": (
                "A consulta será:\n"
                "🏥 Presencial\n"
                "💻 Online\n\n"
                "Por favor, responda Presencial ou Online."
            )
        })

    # =============================
    # MODALIDADE
    # =============================
    if estado["etapa"] == "perguntar_modalidade":

        if "presencial" in mensagem:
            estado["modalidade"] = "Presencial"
        elif "online" in mensagem:
            estado["modalidade"] = "Online"
        else:
            return jsonify({"reply": "Por favor, responda apenas Presencial ou Online 😊"})

        estado["etapa"] = "confirmacao"

        return jsonify({
            "reply": (
                f"Confirmando:\n"
                f"📅 {estado['data'].strftime('%d/%m/%Y')}\n"
                f"⏰ {estado['horario']}\n"
                f"📍 {estado['modalidade']}\n"
                f"👤 {estado['nome']}\n"
                f"📞 {estado['telefone']}\n\n"
                "Está correto? (sim ou não)"
            )
        })

    # =============================
    # CONFIRMAÇÃO
    # =============================
    if estado["etapa"] == "confirmacao":

        if "sim" in mensagem:
            sucesso = marcar_horario(
                estado["data"],
                estado["horario"],
                estado["nome"],
                estado["telefone"],
                estado["modalidade"]
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
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")


        if (
            usuario == os.getenv("ADMIN_USER")
            and senha == os.getenv("ADMIN_PASSWORD")
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
    cursor = conn.cursor()

    # CONSULTAS AGENDADAS
    cursor.execute("""
        SELECT 
            id,
            TO_CHAR(data, 'DD/MM/YYYY') AS data_formatada,
            horario,
            modalidade,
            nome_paciente,
            telefone
        FROM agendamentos
        WHERE disponivel = 'nao'
        ORDER BY data, horario
    """)
    consultas = fetchall_dict(cursor)

    # HORÁRIOS LIVRES
    cursor.execute("""
        SELECT 
            id,
            TO_CHAR(data, 'DD/MM/YYYY') AS data_formatada,
            horario
        FROM agendamentos
        WHERE disponivel = 'sim'
        ORDER BY data, horario
    """)
    horarios_livres = fetchall_dict(cursor)

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
    deletar_por_id(consulta_id)
    return redirect(url_for("admin_panel") + "#consultas")



@app.route("/admin/adicionar-horario", methods=["POST"])
@login_required
def adicionar_horario():
    data = request.form["data"]
    horario = request.form["horario"]

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO agendamentos (data, horario, disponivel)
            VALUES (%s, %s, 'sim')
            """,
            (data, horario)
        )
        conn.commit()

    except errors.UniqueViolation:
        conn.rollback()
        conn.close()
        query_string = urlencode({
            "data": data,
            "erro": "horario_existe"
        })
        return redirect(f"/admin?{query_string}#novo")

    conn.close()
    query_string = urlencode({"data": data})
    return redirect(f"/admin?{query_string}#novo")






@app.route("/admin/excluir-horario/<int:horario_id>")
@login_required
def excluir_horario_livre(horario_id):
    deletar_por_id(horario_id)
    return redirect(url_for("admin_panel") + "#horarios")



@app.route("/admin/excluir-consultas-lote", methods=["POST"])
@login_required
def excluir_consultas_lote():
    ids = [int(i) for i in request.form.getlist("consulta_ids")]
    deletar_varios(ids)
    return redirect(url_for("admin_panel") + "#consultas")



@app.route("/admin/excluir-horarios-lote", methods=["POST"])
@login_required
def excluir_horarios_lote():
    ids = [int(i) for i in request.form.getlist("horario_ids")]
    deletar_varios(ids)
    return redirect(url_for("admin_panel") + "#horarios")



#if __name__ == '__main__': app.run(host='127.0.0.1', port=5000, debug=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

