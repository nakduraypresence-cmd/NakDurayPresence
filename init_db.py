import sqlite3

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS punicoes')
    cursor.execute('DROP TABLE IF EXISTS alunos_turma')
    cursor.execute('DROP TABLE IF EXISTS alunos')
    cursor.execute('DROP TABLE IF EXISTS turmas')

    cursor.execute('''
        CREATE TABLE turmas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            horario TEXT NOT NULL,
            professor TEXT NOT NULL,
            vagas_totais INTEGER NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_completo TEXT NOT NULL,
            presencas INTEGER DEFAULT 0
        )
    ''')

    # Tabela intermediária para guardar quais alunos fizeram check-in em qual turma
    cursor.execute('''
        CREATE TABLE alunos_turma (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER,
            turma_id INTEGER,
            FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE,
            FOREIGN KEY (turma_id) REFERENCES turmas (id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE punicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER,
            motivo TEXT NOT NULL,
            quantidade_flexoes INTEGER NOT NULL,
            status TEXT DEFAULT 'pendente',
            FOREIGN KEY (aluno_id) REFERENCES alunos (id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()
    print("Banco de dados configurado com Cadastro, Ranking e Check-in! 🥊")

if __name__ == '__main__':
    init_db()