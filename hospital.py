from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mysql.connector

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# ----------------------- GLOBAL DB CONNECTION -----------------------
conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='123456',
    database='hospital'
)
cursor = conn.cursor()

# ----------------------- RECONNECT HELPER -----------------------
def reconnect_db():
    global conn, cursor
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='123456',
        database='hospital'
    )
    cursor = conn.cursor()

# ----------------------- AUTH -----------------------
@app.route('/')
def login():
    return render_template('Login.html')

@app.route('/auth', methods=['POST'])
def auth():
    username = request.form['username']
    password = request.form['password']
    if username == 'Chandradeep05' and password == '987654321':
        session['user'] = username
        return redirect(url_for('dashboard'))
    else:
        return "Invalid credentials", 401

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# ----------------------- VIEWS -----------------------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('Dashboard.html')

@app.route('/index')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('Index.html')

@app.route('/patients', methods=['GET', 'POST'])
def patients():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        problem = request.form['problem']
        phone = request.form['phone']
        pid = request.form['id']
        cursor.execute("INSERT INTO patient_details (name, age, problem, phone, id) VALUES (%s, %s, %s, %s, %s)",
                       (name, age, problem, phone, pid))
        conn.commit()
        return redirect(url_for('view_patients'))
    return render_template('Patients.html')

@app.route('/register_patient', methods=['GET', 'POST'])
def register_patient():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        gender = request.form['gender']
        phone = request.form['phone']
        diagnosis = request.form['diagnosis']
        pid = request.form['id']
        cursor.execute("INSERT INTO patient_details (name, age, gender, problem, phone, id) VALUES (%s, %s, %s, %s, %s,%s)",
                       (name, age, gender, diagnosis,phone, pid))
        conn.commit()
        return redirect(url_for('view_patients'))
    return render_template('patients/register_patients.html')

@app.route('/view_patients')
def view_patients():
    if 'user' not in session:
        return redirect(url_for('login'))
    cursor.execute("SELECT * FROM patient_details")
    patients = cursor.fetchall()
    return render_template("patients/view_patients.html", patients=patients)

@app.route('/view_doctors')
def view_doctors():
    if 'user' not in session:
        return redirect(url_for('login'))
    cursor.execute("SELECT * FROM doctor_details")
    doctors = cursor.fetchall()
    return render_template("doctors/view_doctors.html", doctors=doctors)

@app.route('/view_workers')
def view_workers():
    if 'user' not in session:
        return redirect(url_for('login'))
    cursor.execute("SELECT * FROM worker_details")
    workers = cursor.fetchall()
    return render_template("workers/view_workers.html", workers=workers)

@app.route('/register_doctor', methods=['GET', 'POST'])
def register_doctor():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        department = request.form['department']
        phone = request.form['phone']
        did = request.form['id']
        cursor.execute("INSERT INTO doctor_details (name, age, department, phone, id) VALUES (%s, %s, %s, %s, %s)",
                       (name, age, department, phone, did))
        conn.commit()
        return redirect(url_for('view_doctors'))
    return render_template("doctors/register_doctor.html")

@app.route('/register_worker', methods=['GET', 'POST'])
def register_worker():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        work_type = request.form['work_type']
        phone = request.form['phone']
        wid = request.form['id']
        cursor.execute("INSERT INTO worker_details (name, age, work_type, phone, id) VALUES (%s, %s, %s, %s, %s)",
                       (name, age, work_type, phone, wid))
        conn.commit()
        return redirect(url_for('view_workers'))
    return render_template("workers/register_worker.html")

# ----------------------- JSON API -----------------------
@app.route('/get_all/<entity>')
def get_all(entity):
    table_map = {
        'patient': 'patient_details',
        'doctor': 'doctor_details',
        'worker': 'worker_details'
    }
    table = table_map.get(entity)
    if table:
        cursor.execute(f"SELECT * FROM {table}")
        data = cursor.fetchall()
        return jsonify(data)
    else:
        return jsonify({'error': 'Invalid entity'}), 400

@app.route('/delete/<entity>/<id>', methods=['POST'])
def delete_entity(entity, id):
    table_map = {
        'patient': 'patient_details',
        'doctor': 'doctor_details',
        'worker': 'worker_details'
    }
    table = table_map.get(entity)
    if table:
        cursor.execute(f"DELETE FROM {table} WHERE id=%s", (id,))
        conn.commit()
        return jsonify({'message': f'{entity.capitalize()} deleted successfully'})
    return jsonify({'error': 'Invalid entity'}), 400

# ----------------------- SEARCH + DELETE ROUTES -----------------------
@app.route('/search', methods=['GET', 'POST'])
def search():
    results = []
    search_performed = False
    record_type = None

    if request.method == 'POST':
        search_performed = True
        record_type = request.form['record_type']
        query = request.form['query']

        table_map = {
            'patient': ('patient_details', ['name', 'id']),
            'doctor': ('doctor_details', ['name', 'id']),
            'worker': ('worker_details', ['name', 'id'])
        }

        table, fields = table_map.get(record_type, (None, None))
        if not table:
            return "Invalid record type."

        sql = f"SELECT * FROM {table} WHERE {fields[0]} LIKE %s OR {fields[1]} LIKE %s"
        like_query = f"%{query}%"

        try:
            cursor.execute(sql, (like_query, like_query))
            results = cursor.fetchall()
        except mysql.connector.Error as e:
            return f"Database error: {e}"

    return render_template('search.html', results=results, search_performed=search_performed, record_type=record_type if search_performed else None)


@app.route('/delete_records', methods=['GET', 'POST'])
def delete_record():
    if request.method == 'POST':
        record_type = request.form['record_type']
        record_id = request.form['record_id']

        table_map = {
            'patient': 'patient_details',
            'doctor': 'doctor_details',
            'worker': 'worker_details'
        }

        table = table_map.get(record_type)
        if not table:
            return "Invalid record type."

        cursor.execute(f"DELETE FROM {table} WHERE id = %s", (record_id,))
        conn.commit()

        # Render a styled confirmation page with background
        return render_template(
            'delete_confirmation.html',
            record_type=record_type.capitalize(),
            record_id=record_id
        )

    return render_template('delete_records.html')

# ----------------------- MAIN -----------------------
if __name__ == '__main__':
    app.run(debug=True)
