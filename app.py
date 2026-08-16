from flask import Flask, flash, jsonify, make_response, redirect, render_template, request, session, url_for
import sqlite3

app = Flask(__name__)
app.secret_key = "nakduray_secret_key" 

def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    """)
    if not conn.execute("SELECT * FROM config WHERE chave = 'senha_mestre'").fetchone():
        conn.execute("INSERT INTO config (chave, valor) VALUES ('senha_mestre', 'nakduray2026')")
    
    # Certifique-se de que suas tabelas de treinos e presencas também são criadas aqui se já não forem
    conn.commit()
    conn.close()

def get_senha_mestre():
    conn = get_db_connection()
    senha = conn.execute("SELECT valor FROM config WHERE chave = 'senha_mestre'").fetchone()
    conn.close()
    return senha['valor']

def admin_required(f):
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route("/alterar_senha", methods=["GET", "POST"])
def alterar_senha():
    if request.method == "POST":
        senha_antiga = request.form.get("senha_antiga")
        nova_senha = request.form.get("nova_senha")
        
        if senha_antiga == get_senha_mestre():
            conn = get_db_connection()
            conn.execute("UPDATE config SET valor = ? WHERE chave = 'senha_mestre'", (nova_senha,))
            conn.commit()
            conn.close()
            flash("Senha alterada com sucesso!")
        else:
            flash("Senha antiga incorreta!")
    return render_template("alterar_senha.html")

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("senha") == get_senha_mestre():
            session["admin"] = True
            return redirect(url_for("index"))
        else:
            flash("Senha incorreta!")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

# 1. Painel Principal com anti-cache rigoroso para atualizar a lista na hora
@app.route("/", methods=["GET", "POST"])
@admin_required
def index():
    conn = get_db_connection()
    if request.method == "POST":
        periodo = request.form["periodo"]
        dia = request.form["dia"]
        horario = request.form["horario"]
        vagas = request.form["vagas"]
        titulo = f"Muay Thai - {periodo}"
        data_horario = f"{dia}, {horario}"
        conn.execute("INSERT INTO treinos (titulo, data_horario, vagas) VALUES (?, ?, ?)", (titulo, data_horario, vagas))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
        
    treinos = conn.execute("SELECT * FROM treinos ORDER BY id DESC").fetchall()
    conn.close()
    
    # Força o navegador a nunca guardar cache do painel do Mestre
    response = make_response(render_template("index.html", treinos=treinos))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    return response

# 2. Remover Treino (Agora joga o Mestre de volta para o painel limpo)
@app.route("/remover_treino/<int:id>")
@admin_required
def remover_treino(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM presencas WHERE treino_id = ?", (id,))
    conn.execute("DELETE FROM treinos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    
    # O Mestre volta para o painel e o treino some instantaneamente!
    return redirect(url_for("index"))


@app.route("/remover_presenca/<int:id>/<int:treino_id>")
@admin_required
def remover_presenca(id, treino_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM presencas WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("treino_detalhe", id=treino_id))

@app.route("/api/treino/<int:id>/status")
def api_treino_status(id):
    conn = get_db_connection()
    treino = conn.execute("SELECT * FROM treinos WHERE id = ?", (id,)).fetchone()
    
    if not treino:
        conn.close()
        return jsonify({"erro": "Treino não encontrado"}), 404
        
    presencas = conn.execute("SELECT * FROM presencas WHERE treino_id = ?", (id,)).fetchall()
    conn.close()
    
    lista_presencas = [{"id": p["id"], "nome_aluno": p["nome_aluno"]} for p in presencas]
    
    return jsonify({
        "vagas_ocupadas": len(presencas),
        "limite_vagas": treino["vagas"],
        "presencas": lista_presencas,
        "is_admin": bool(session.get("admin"))  # Informa ao JS se é admin ou não
    })

@app.route("/treino/<int:id>", methods=["GET", "POST"])
def treino_detalhe(id):
    conn = get_db_connection()
    treino = conn.execute("SELECT * FROM treinos WHERE id = ?", (id,)).fetchone()
    
    if not treino:
        conn.close()
        return render_template("treino_removido.html")

    session_key = f"confirmado_{id}"

    if request.method == "POST":
        nome_aluno = request.form.get("nome_aluno", "").strip()
        
        if not nome_aluno:
            flash("Por favor, digite seu nome completo.", "error")
        elif session.get(session_key):
            flash("Você já confirmou presença neste treino usando este aparelho!", "error")
        else:
            total_presencas = conn.execute("SELECT COUNT(*) as total FROM presencas WHERE treino_id = ?", (id,)).fetchone()["total"]
            
            if total_presencas >= treino['vagas']:
                flash("As vagas para este treino estão esgotadas!", "error")
            else:
                conn.execute("INSERT INTO presencas (treino_id, nome_aluno) VALUES (?, ?)", (id, nome_aluno))
                conn.commit()
                session[session_key] = True
                flash("Presença confirmada!", "success")
            
        conn.close()
        return redirect(url_for('treino_detalhe', id=id))
        
    presencas = conn.execute("SELECT * FROM presencas WHERE treino_id = ?", (id,)).fetchall()
    conn.close()
    
    response = make_response(render_template("treino.html", treino=treino, presencas=presencas, total=len(presencas)))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    return response

if __name__ == "__main__":
    init_db()
    app.run(debug=True)

    import os

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)