from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_segura'  # Necessário para gerenciar sessões
bcrypt = Bcrypt(app)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    conn = get_db_connection()
    
    # Tabela de Treinadores (Login real)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS treinadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')
    
    # Tabela de Alunos
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_completo TEXT NOT NULL,
            presencas INTEGER DEFAULT 0
        )
    ''')
    
    # Tabela de Turmas/Aulas
    conn.execute('''
        CREATE TABLE IF NOT EXISTS turmas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            horario TEXT NOT NULL,
            professor TEXT NOT NULL,
            vagas_totais INTEGER NOT NULL
        )
    ''')
    
    # Tabela de Presença dos Alunos nas Turmas
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alunos_turma (
            aluno_id INTEGER,
            turma_id INTEGER,
            FOREIGN KEY (aluno_id) REFERENCES alunos (id),
            FOREIGN KEY (turma_id) REFERENCES turmas (id)
        )
    ''')

    # Tabela de Punições (Flexões)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS punicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER,
            quantidade INTEGER,
            motivo TEXT,
            FOREIGN KEY (aluno_id) REFERENCES alunos (id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        
        conn = get_db_connection()
        treinador = conn.execute('SELECT * FROM treinadores WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if treinador and bcrypt.check_password_hash(treinador['senha'], senha):
            session['treinador_id'] = treinador['id']
            session['nome_mestre'] = treinador['nome']
            return redirect(url_for('dashboard'))
        else:
            erro = 'E-mail ou senha incorretos.'
            
    return render_template('login.html', erro=erro)

@app.route('/cadastro_treinador', methods=['GET', 'POST'])
def cadastro_treinador():
    erro = None
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        
        hashed_password = bcrypt.generate_password_hash(senha).decode('utf-8')
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO treinadores (nome, email, senha) VALUES (?, ?, ?)', (nome, email, hashed_password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            erro = 'Este e-mail já está cadastrado.'
            conn.close()
            
    return render_template('cadastro_treinador.html', erro=erro)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ROTAS PROTEGIDAS ---

@app.route('/')
def dashboard():
    if 'treinador_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    turmas_db = conn.execute('SELECT * FROM turmas').fetchall()
    
    aulas_hoje = []
    for turma in turmas_db:
        confirmados = conn.execute('SELECT COUNT(*) FROM alunos_turma WHERE turma_id = ?', (turma['id'],)).fetchone()[0]
        vagas_restantes = turma['vagas_totais'] - confirmados
        ocupacao_pct = (confirmados / turma['vagas_totais']) * 100 if turma['vagas_totais'] > 0 else 0
        
        aulas_hoje.append({
            "id": turma['id'],
            "nome_turma": turma['nome'],
            "horario": turma['horario'],
            "confirmados": confirmados,
            "vagas": vagas_restantes,
            "ocupacao_pct": int(ocupacao_pct),
            "professor": turma['professor']
        })
    
    total_alunos = conn.execute('SELECT COUNT(*) FROM alunos').fetchone()[0]
    
    punicoes = conn.execute('''
        SELECT p.id, a.nome_completo, p.quantidade, p.motivo 
        FROM punicoes p 
        JOIN alunos a ON p.aluno_id = a.id
    ''').fetchall()
    
    conn.close()

    return render_template('index.html', 
                           nome_mestre=session.get('nome_mestre'),
                           total_alunos=total_alunos,
                           presencas_hoje=0, 
                           ausentes_hoje=0,
                           aulas=aulas_hoje,
                           punicoes=punicoes)

@app.route('/criar_aula', methods=['GET', 'POST'])
def criar_aula():
    if 'treinador_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        nome = request.form['nome']
        horario = request.form['horario']
        professor = request.form['professor']
        vagas = request.form['vagas']
        
        conn = get_db_connection()
        conn.execute('INSERT INTO turmas (nome, horario, professor, vagas_totais) VALUES (?, ?, ?, ?)', 
                     (nome, horario, professor, vagas))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    return render_template('criar_aula.html')

@app.route('/excluir_aula/<int:id>')
def excluir_aula(id):
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM turmas WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/registrar_punicao', methods=['GET', 'POST'])
def registrar_punicao():
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        aluno_id = request.form['aluno_id']
        quantidade = request.form['quantidade']
        motivo = request.form['motivo']
        
        conn.execute('INSERT INTO punicoes (aluno_id, quantidade, motivo) VALUES (?, ?, ?)', 
                     (aluno_id, quantidade, motivo))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
        
    alunos = conn.execute('SELECT * FROM alunos ORDER BY nome_completo ASC').fetchall()
    conn.close()
    return render_template('registrar_punicao.html', alunos=alunos)

@app.route('/remover_punicao/<int:id>')
def remover_punicao(id):
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM punicoes WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/alunos', methods=['GET', 'POST'])
def gerenciar_alunos():
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form['nome']
        conn.execute('INSERT INTO alunos (nome_completo, presencas) VALUES (?, 0)', (nome,))
        conn.commit()
    alunos = conn.execute('SELECT * FROM alunos ORDER BY nome_completo ASC').fetchall()
    conn.close()
    return render_template('alunos.html', alunos=alunos)

@app.route('/excluir_aluno/<int:id>')
def excluir_aluno(id):
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM alunos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('gerenciar_alunos'))

@app.route('/ranking')
def ranking():
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    ranking = conn.execute('SELECT * FROM alunos ORDER BY presencas DESC').fetchall()
    conn.close()
    return render_template('ranking.html', ranking=ranking)

@app.route('/perfil')
def perfil():
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    total_alunos = conn.execute('SELECT COUNT(*) FROM alunos').fetchone()[0]
    total_turmas = conn.execute('SELECT COUNT(*) FROM turmas').fetchone()[0]
    total_punicoes = conn.execute('SELECT COUNT(*) FROM punicoes').fetchone()[0]
    conn.close()
    
    return render_template('perfil.html', 
                           nome_mestre=session.get('nome_mestre'), 
                           total_alunos=total_alunos, 
                           total_turmas=total_turmas,
                           total_punicoes=total_punicoes)

@app.route('/gerenciar/<int:id>')
def gerenciar(id):
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    turma = conn.execute('SELECT * FROM turmas WHERE id = ?', (id,)).fetchone()
    if not turma:
        conn.close()
        return redirect(url_for('dashboard'))
        
    alunos = conn.execute('''
        SELECT a.id, a.nome_completo 
        FROM alunos a 
        JOIN alunos_turma at ON a.id = at.aluno_id 
        WHERE at.turma_id = ?
    ''', (id,)).fetchall()
    conn.close()
    
    return render_template('gerenciar.html', turma=turma, alunos=alunos)

# --- ROTA PÚBLICA PARA O ALUNO ---
@app.route('/aluno/turma/<int:id>')
def aluno_turma(id):
    conn = get_db_connection()
    turma = conn.execute('SELECT * FROM turmas WHERE id = ?', (id,)).fetchone()
    if not turma:
        conn.close()
        return "Turma não encontrada", 404
        
    # Busca os alunos confirmados nesta turma
    alunos = conn.execute('''
        SELECT a.id, a.nome_completo 
        FROM alunos a 
        JOIN alunos_turma at ON a.id = at.aluno_id 
        WHERE at.turma_id = ?
    ''', (id,)).fetchall()
    conn.close()
    
    return render_template('aluno_turma.html', turma=turma, alunos=alunos)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    is_production = os.environ.get("PORT") is not None
    app.run(host='0.0.0.0', port=port, debug=not is_production)