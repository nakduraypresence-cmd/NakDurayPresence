from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import re
import itsdangerous
import resend
from flask_bcrypt import Bcrypt
from flask_admin import Admin, BaseView, expose

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sua_chave_secreta_super_segura') 
bcrypt = Bcrypt(app)

s = itsdangerous.URLSafeTimedSerializer(app.secret_key)

# Configuração da API Key do Resend via Variável de Ambiente
resend.api_key = os.environ.get("RESEND_API_KEY")

# Constantes de Segurança e Acesso
CODIGO_CONVITE_MESTRE = os.environ.get("CODIGO_CONVITE", "NAK2026")
EMAIL_ADMIN_MESTRE = os.environ.get("EMAIL_ADMIN", "mvvinicius231017vk@gmail.com")

# Caminho Absoluto do Banco de Dados SQLite (Evita perder dados nos deploys do Render)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row 
    conn.execute('PRAGMA foreign_keys = ON') # Garante a integridade das chaves estrangeiras
    return conn

def init_db():
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS treinadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                nome TEXT NOT NULL, 
                email TEXT UNIQUE NOT NULL, 
                senha TEXT NOT NULL,
                ativo INTEGER DEFAULT 0
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS alunos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                nome_completo TEXT NOT NULL, 
                presencas INTEGER DEFAULT 0
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS turmas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                nome TEXT NOT NULL, 
                horario TEXT NOT NULL, 
                professor TEXT NOT NULL, 
                vagas_totais INTEGER NOT NULL,
                treinador_id INTEGER,
                FOREIGN KEY (treinador_id) REFERENCES treinadores (id) ON DELETE CASCADE
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS alunos_turma (
                aluno_id INTEGER, 
                turma_id INTEGER, 
                FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE, 
                FOREIGN KEY (turma_id) REFERENCES turmas (id) ON DELETE CASCADE
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS punicoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                aluno_id INTEGER, 
                quantidade INTEGER, 
                motivo TEXT, 
                FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE
            )
        ''')
        conn.commit()
    finally:
        conn.close()

init_db()

def validar_email(email):
    padrao = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    if not re.match(padrao, email):
        return False
    dominios_proibidos = ['teste.com', 'email.com', 'abc.com', 'fake.com', 'x.com']
    dominio = email.split('@')[-1].lower()
    if dominio in dominios_proibidos:
        return False
    return True

# Configuração do Painel Administrativo Protegido
class GerenciarTreinadoresView(BaseView):
    def is_accessible(self):
        return session.get('treinador_email') == EMAIL_ADMIN_MESTRE

    def inaccessible_callback(self, name, **kwargs):
        flash('Acesso restrito ao administrador do sistema.', 'erro')
        return redirect(url_for('login'))

    @expose('/')
    def index(self):
        conn = get_db_connection()
        try:
            treinadores = conn.execute('SELECT id, nome, email, ativo FROM treinadores').fetchall()
        finally:
            conn.close()
        return self.render('admin/treinadores.html', treinadores=treinadores)

    @expose('/excluir/<int:id>', methods=['POST'])
    def excluir(self, id):
        if session.get('treinador_id') == id:
            flash('Você não pode excluir sua própria conta enquanto estiver logado!', 'erro')
            return redirect(url_for('gerenciartreinadoresview.index'))

        conn = get_db_connection()
        try:
            conn.execute('DELETE FROM treinadores WHERE id = ?', (id,))
            conn.commit()
            flash('Treinador excluído com sucesso!', 'sucesso')
        except Exception as e:
            flash(f'Erro ao excluir: {e}', 'erro')
        finally:
            conn.close()
            
        return redirect(url_for('gerenciartreinadoresview.index'))

admin = Admin(app, name='Nakduray Admin')
admin.add_view(GerenciarTreinadoresView(name='Gerenciar Treinadores', endpoint='gerenciartreinadoresview'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    sucesso = request.args.get('sucesso')
    erro = None

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        senha = request.form['senha'].strip()

        conn = get_db_connection()
        try:
            treinador = conn.execute('SELECT * FROM treinadores WHERE email = ?', (email,)).fetchone()

            if treinador and bcrypt.check_password_hash(treinador['senha'], senha):
                if treinador['ativo'] == 1:
                    session['treinador_id'] = treinador['id']
                    session['treinador_nome'] = treinador['nome']
                    session['treinador_email'] = treinador['email']
                    return redirect(url_for('dashboard'))
                else:
                    erro = 'Sua conta ainda não está ativa.'
            else:
                erro = 'E-mail ou senha incorretos.'
        except Exception as e:
            erro = f"Erro no sistema: {e}"
        finally:
            conn.close()

    return render_template('login.html', erro=erro, sucesso=sucesso)

@app.route('/cadastro_treinador', methods=['GET', 'POST'])
def cadastro_treinador():
    erro = None
    if request.method == 'POST':
        nome = request.form['nome'].strip()
        email = request.form['email'].strip().lower()
        senha = request.form['senha'].strip()
        codigo = request.form.get('codigo_convite', '').strip()
        
        if codigo != CODIGO_CONVITE_MESTRE:
            erro = 'Código de convite inválido! Solicite a chave de acesso ao administrador.'
        elif not validar_email(email):
            erro = 'Por favor, insira um endereço de e-mail real e válido.'
        else:
            conn = get_db_connection()
            try:
                treinador_existente = conn.execute('SELECT id FROM treinadores WHERE email = ?', (email,)).fetchone()
                if treinador_existente:
                    erro = 'Este e-mail já está cadastrado.'
                else:
                    hashed_password = bcrypt.generate_password_hash(senha).decode('utf-8')
                    conn.execute('INSERT INTO treinadores (nome, email, senha, ativo) VALUES (?, ?, ?, 1)', (nome, email, hashed_password))
                    conn.commit()
                    return redirect(url_for('login', sucesso='Conta criada com sucesso! Faça login para acessar.'))
            except Exception as e:
                erro = f"Erro ao criar conta: {e}"
            finally:
                conn.close()
                
    return render_template('cadastro_treinador.html', erro=erro)

@app.route('/verificar_email_aviso')
def verificar_email_aviso():
    return render_template('verificar_email.html')

@app.route('/ativar/<token>')
def ativar_conta(token):
    try:
        email = s.loads(token, salt='email-confirmacao', max_age=3600)
    except:
        return 'O link de ativação é inválido ou já expirou.', 400
    
    conn = get_db_connection()
    try:
        conn.execute('UPDATE treinadores SET ativo = 1 WHERE email = ?', (email,))
        conn.commit()
    finally:
        conn.close()
    
    return render_template('conta_ativada.html')

@app.route('/esqueci_senha', methods=['GET', 'POST'])
def esqueci_senha():
    erro = None
    sucesso = None
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        conn = get_db_connection()
        try:
            treinador = conn.execute('SELECT * FROM treinadores WHERE email = ?', (email,)).fetchone()
        finally:
            conn.close()
        
        if treinador:
            try:
                token = s.dumps(email, salt='recuperar-senha')
                link = url_for('redefinir_senha', token=token, _external=True)
                
                resend.Emails.send({
                    "from": "Nakduray Presence <onboarding@resend.dev>",
                    "to": email,
                    "subject": "Redefinição de Senha - Nakduray Presence",
                    "html": f"""
                        <h2>Olá, {treinador['nome']}!</h2>
                        <p>Para redefinir sua senha no Nakduray Presence, clique no link abaixo:</p>
                        <p><a href="{link}" style="background-color: #E50914; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Redefinir Senha</a></p>
                        <br>
                        <p><small>Este link expira em 15 minutos.</small></p>
                    """
                })
                sucesso = 'Um link de recuperação foi enviado para o seu e-mail!'
            except Exception as e:
                print(f"Erro ao enviar e-mail: {e}")
                erro = 'Ocorreu um erro ao enviar o e-mail de recuperação.'
        else:
            erro = 'E-mail não encontrado em nossa base de dados.'
            
    return render_template('esqueci_senha.html', erro=erro, sucesso=sucesso)

@app.route('/redefinir_senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    try:
        email = s.loads(token, salt='recuperar-senha', max_age=900)
    except:
        return 'O link de recuperação é inválido ou expirou.', 400
        
    if request.method == 'POST':
        nova_senha = request.form['senha'].strip()
        hashed_password = bcrypt.generate_password_hash(nova_senha).decode('utf-8')
        
        conn = get_db_connection()
        try:
            conn.execute('UPDATE treinadores SET senha = ? WHERE email = ?', (hashed_password, email))
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for('login', sucesso='Senha alterada com sucesso! Faça login.'))
        
    return render_template('nova_senha.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/apagar_conta', methods=['POST'])
def apagar_conta():
    if 'treinador_id' not in session:
        return redirect(url_for('login'))
    
    treinador_id = session['treinador_id']
    conn = get_db_connection()
    try:
        turmas_treinador = conn.execute('SELECT id FROM turmas WHERE treinador_id = ?', (treinador_id,)).fetchall()
        
        for turma in turmas_treinador:
            conn.execute('DELETE FROM alunos_turma WHERE turma_id = ?', (turma['id'],))
            
        conn.execute('DELETE FROM turmas WHERE treinador_id = ?', (treinador_id,))
        conn.execute('DELETE FROM treinadores WHERE id = ?', (treinador_id,))
        conn.commit()
    finally:
        conn.close()
    
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def dashboard():
    if 'treinador_id' not in session: 
        return redirect(url_for('login'))
    
    treinador_id = session['treinador_id']
    
    conn = get_db_connection()
    try:
        turmas_db = conn.execute('SELECT * FROM turmas WHERE treinador_id = ?', (treinador_id,)).fetchall()
        aulas_hoje = []
        
        total_confirmados_geral = 0
        for turma in turmas_db:
            confirmados = conn.execute('SELECT COUNT(*) FROM alunos_turma WHERE turma_id = ?', (turma['id'],)).fetchone()[0]
            total_confirmados_geral += confirmados
            vagas_restantes = turma['vagas_totais'] - confirmados
            ocupacao_pct = (confirmados / turma['vagas_totais']) * 100 if turma['vagas_totais'] > 0 else 0
            aulas_hoje.append({
                "id": turma['id'], "nome_turma": turma['nome'], "horario": turma['horario'],
                "confirmados": confirmados, "vagas": vagas_restantes, "ocupacao_pct": int(ocupacao_pct), "professor": turma['professor']
            })
        
        total_alunos = conn.execute('SELECT COUNT(*) FROM alunos').fetchone()[0]
        presencas_hoje = total_confirmados_geral
        alunos_com_presenca = conn.execute('SELECT COUNT(DISTINCT aluno_id) FROM alunos_turma').fetchone()[0]
        ausentes_hoje = max(0, total_alunos - alunos_com_presenca)
        
        punicoes = conn.execute('SELECT p.id, a.nome_completo, p.quantidade_flexoes, p.motivo FROM punicoes p JOIN alunos a ON p.aluno_id = a.id').fetchall()
    finally:
        conn.close()
        
    return render_template(
        'index.html', 
        nome_mestre=session.get('treinador_nome'), 
        total_alunos=total_alunos, 
        presencas_hoje=presencas_hoje, 
        ausentes_hoje=ausentes_hoje, 
        aulas=aulas_hoje, 
        punicoes=punicoes
    )

@app.route('/criar_aula', methods=['GET', 'POST'])
def criar_aula():
    if 'treinador_id' not in session: 
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        conn = get_db_connection()
        try:
            treinador_id = session['treinador_id']
            treinador_atual = conn.execute('SELECT nome FROM treinadores WHERE id = ?', (treinador_id,)).fetchone()
            professor_responsavel = treinador_atual['nome'] if treinador_atual else session.get('treinador_nome')
            
            conn.execute('INSERT INTO turmas (nome, horario, professor, vagas_totais, treinador_id) VALUES (?, ?, ?, ?, ?)', 
                         (request.form['nome'], request.form['horario'], professor_responsavel, request.form['vagas'], treinador_id))
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for('dashboard'))
    
    return render_template('criar_aula.html')

@app.route('/excluir_aula/<int:id>')
def excluir_aula(id):
    if 'treinador_id' not in session: 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    try:
        # CORREÇÃO AQUI: Remove primeiro as dependências da chave estrangeira antes de deletar a turma
        conn.execute('DELETE FROM alunos_turma WHERE turma_id = ?', (id,))
        conn.execute('DELETE FROM turmas WHERE id = ?', (id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/registrar_punicao', methods=['GET', 'POST'])
def registrar_punicao():
    if request.method == 'POST':
        aluno_id = request.form['aluno_id']
        tipo_punicao = request.form['tipo_punicao']  # Vem do formulário HTML
        motivo = request.form['motivo']
        
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        
        # Inserindo com o nome correto da coluna do banco: 'quantidade_flexoes'
        conn.execute(
            "INSERT INTO punicoes (aluno_id, motivo, quantidade_flexoes) VALUES (?, ?, ?)", 
            (aluno_id, motivo, tipo_punicao)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('dashboard'))
    
    # Busca os alunos para preencher o select no HTML
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    alunos = conn.execute("SELECT * FROM alunos").fetchall()
    conn.close()
    
    return render_template('registrar_punicao.html', alunos=alunos)

@app.route('/remover_punicao/<int:id>')
def remover_punicao(id):
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM punicoes WHERE id = ?', (id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/alunos', methods=['GET', 'POST'])
def gerenciar_alunos():
    if 'treinador_id' not in session: return redirect(url_for('login'))
    erro = None
    
    if request.method == 'POST':
        nome_aluno = request.form['nome'].strip()
        conn = get_db_connection()
        try:
            aluno_existente = conn.execute('SELECT * FROM alunos WHERE nome_completo = ?', (nome_aluno,)).fetchone()
            
            if aluno_existente:
                erro = f'Já existe um atleta cadastrado com o nome "{nome_aluno}".'
            else:
                conn.execute('INSERT INTO alunos (nome_completo, presencas) VALUES (?, 0)', (nome_aluno,))
                conn.commit()
                return redirect(url_for('gerenciar_alunos'))
        finally:
            conn.close()
            
    conn = get_db_connection()
    try:
        alunos = conn.execute('SELECT * FROM alunos ORDER BY nome_completo ASC').fetchall()
    finally:
        conn.close()
        
    return render_template('alunos.html', alunos=alunos, erro=erro)

@app.route('/excluir_aluno/<int:id>')
def excluir_aluno(id):
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM alunos WHERE id = ?', (id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('gerenciar_alunos'))

@app.route('/ranking')
def ranking():
    if 'treinador_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        ranking_db = conn.execute('SELECT * FROM alunos ORDER BY presencas DESC').fetchall()
    finally:
        conn.close()
    return render_template('ranking.html', ranking=ranking_db)

@app.route('/perfil')
def perfil():
    if 'treinador_id' not in session: return redirect(url_for('login'))
    treinador_id = session['treinador_id']
    
    conn = get_db_connection()
    try:
        total_alunos = conn.execute('SELECT COUNT(*) FROM alunos').fetchone()[0]
        total_turmas = conn.execute('SELECT COUNT(*) FROM turmas WHERE treinador_id = ?', (treinador_id,)).fetchone()[0]
        total_punicoes = conn.execute('SELECT COUNT(*) FROM punicoes').fetchone()[0]
    finally:
        conn.close()
        
    return render_template(
        'perfil.html', 
        nome_mestre=session.get('treinador_nome'), 
        total_alunos=total_alunos, 
        total_turmas=total_turmas, 
        total_punicoes=total_punicoes
    )

@app.route('/gerenciar/<int:id>')
def gerenciar(id):
    if 'treinador_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        turma = conn.execute('SELECT * FROM turmas WHERE id = ?', (id,)).fetchone()
        if not turma:
            return redirect(url_for('dashboard'))
        alunos = conn.execute('SELECT a.id, a.nome_completo FROM alunos a JOIN alunos_turma at ON a.id = at.aluno_id WHERE at.turma_id = ?', (id,)).fetchall()
    finally:
        conn.close()
        
    return render_template('gerenciar.html', turma=turma, alunos=alunos)

@app.route('/aluno/turma/<int:id>', methods=['GET', 'POST'])
def aluno_turma(id):
    conn = get_db_connection()
    try:
        turma = conn.execute('SELECT * FROM turmas WHERE id = ?', (id,)).fetchone()
        
        if not turma:
            return render_template('turma_invalida.html'), 404
            
        if request.method == 'POST':
            aluno_id = request.form.get('aluno_id')
            if aluno_id:
                ja_confirmado = conn.execute('SELECT * FROM alunos_turma WHERE aluno_id = ? AND turma_id = ?', (aluno_id, id)).fetchone()
                if not ja_confirmado:
                    conn.execute('INSERT INTO alunos_turma (aluno_id, turma_id) VALUES (?, ?)', (aluno_id, id))
                    conn.execute('UPDATE alunos SET presencas = presencas + 1 WHERE id = ?', (aluno_id,))
                    conn.commit()
            return redirect(url_for('aluno_turma', id=id))
            
        todos_alunos = conn.execute('SELECT * FROM alunos ORDER BY nome_completo ASC').fetchall()
        alunos_confirmados = conn.execute('SELECT a.id, a.nome_completo FROM alunos a JOIN alunos_turma at ON a.id = at.aluno_id WHERE at.turma_id = ?', (id,)).fetchall()
    finally:
        conn.close()
        
    return render_template('aluno_turma.html', turma=turma, todos_alunos=todos_alunos, alunos_confirmados=alunos_confirmados)

@app.route('/remover_checkin/<int:aula_id>/<int:aluno_id>')
def remover_checkin(aula_id, aluno_id):
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM alunos_turma WHERE turma_id = ? AND aluno_id = ?', (aula_id, aluno_id))
        conn.execute('UPDATE alunos SET presencas = MAX(0, presencas - 1) WHERE id = ?', (aluno_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('aluno_turma', id=aula_id))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    is_production = os.environ.get("PORT") is not None
    app.run(host='0.0.0.0', port=port, debug=not is_production)