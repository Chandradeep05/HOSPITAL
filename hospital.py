from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import date as date_type, datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
import re
import os
import csv
import io
import warnings
import logging

load_dotenv()  # Load .env file into environment before any os.getenv() calls

# ──────────────────────────────────────────────
# App & DB Configuration
# ──────────────────────────────────────────────
app = Flask(__name__)
_secret = os.getenv('SECRET_KEY')
if not _secret:
    if os.getenv('FLASK_DEBUG', '0') != '1':
        raise ValueError("SECRET_KEY must be set in production. Add it to your .env file or hosting environment.")
    _secret = 'dev-secret-key-unsafe'
    warnings.warn("SECRET_KEY not set — using insecure dev default. Set SECRET_KEY before deploying.", stacklevel=2)
app.secret_key = _secret

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
_db_url = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(BASE_DIR, 'hospital.db')}")
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# PostgreSQL / Supabase connection-pool tuning
if _db_url.startswith('postgresql://'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,       # detect stale connections before use
        'pool_recycle': 280,         # recycle connections before Supabase timeout (300s)
        'pool_size': 5,              # sensible default for free tier
        'max_overflow': 2,           # allow 2 extra connections under burst
        'connect_args': {
            'sslmode': 'require',    # Supabase requires SSL
            'options': '-c statement_timeout=30000',  # 30s query timeout
        },
    }
    print(f"[HSMS] Using PostgreSQL: {_db_url.split('@')[1] if '@' in _db_url else '(configured)'}")
else:
    print(f"[HSMS] Using SQLite: {_db_url}")

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class User(db.Model):
    """Admin/staff user for authentication."""
    __tablename__ = 'users'
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)   # bcrypt hash
    role     = db.Column(db.String(20), nullable=False, default='admin')  # 'admin' | 'staff'

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Patient(db.Model):
    """Hospital patient record."""
    __tablename__ = 'patient_details'
    id         = db.Column(db.String(20), primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    age        = db.Column(db.Integer, nullable=False)
    gender     = db.Column(db.String(10))
    problem    = db.Column(db.String(200))
    phone      = db.Column(db.String(20))
    # Phase 9: soft-delete + audit
    is_active  = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Patient {self.name}>'


class Doctor(db.Model):
    """Hospital doctor record."""
    __tablename__ = 'doctor_details'
    id         = db.Column(db.String(20), primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    age        = db.Column(db.Integer, nullable=False)
    department = db.Column(db.String(100))
    phone      = db.Column(db.String(20))
    # Phase 7: working-hours window (NULL-safe; code defaults to 09:00-17:00)
    start_time = db.Column(db.String(5))
    end_time   = db.Column(db.String(5))
    # Phase 9: soft-delete + audit
    is_active  = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Doctor {self.name}>'


class Worker(db.Model):
    """Hospital worker / staff record."""
    __tablename__ = 'worker_details'
    id        = db.Column(db.String(20), primary_key=True)
    name      = db.Column(db.String(100), nullable=False)
    age       = db.Column(db.Integer, nullable=False)
    work_type = db.Column(db.String(100))
    phone     = db.Column(db.String(20))
    # Phase 9: soft-delete + audit
    is_active  = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Worker {self.name}>'


class Appointment(db.Model):
    """Appointment linking a patient to a doctor."""
    __tablename__ = 'appointments'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.String(20), db.ForeignKey('patient_details.id'), nullable=False)
    doctor_id  = db.Column(db.String(20), db.ForeignKey('doctor_details.id'), nullable=False)
    appt_date  = db.Column(db.String(20), nullable=False)   # stored as 'YYYY-MM-DD'
    appt_time  = db.Column(db.String(10), nullable=False)   # stored as 'HH:MM'
    reason     = db.Column(db.String(200))
    status     = db.Column(db.String(20), default='Scheduled')  # Scheduled | Cancelled

    # Relationships for easy access in templates
    patient = db.relationship('Patient', backref='appointments')
    doctor  = db.relationship('Doctor',  backref='appointments')

    def __repr__(self):
        return f'<Appointment {self.id}: {self.patient_id} -> {self.doctor_id}>'


# ──────────────────────────────────────────────
# DB Initialisation — create tables + seed admin
# ──────────────────────────────────────────────
def init_db():
    """Create all tables and ensure the default admin user exists with a hashed password."""
    db.create_all()

    # Phase 6 migration: add 'role' column to existing users table if missing
    # (SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS, so we check first)
    try:
        db.session.execute(db.text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'admin'"))
        db.session.commit()
        print("[HSMS] 'role' column added to users table.")
    except Exception:
        db.session.rollback()  # Column already exists — rollback to clean transaction for Postgres

    # Phase 7 migration: add working-hour columns to doctor_details if missing
    for _col in ('start_time', 'end_time'):
        try:
            db.session.execute(db.text(f"ALTER TABLE doctor_details ADD COLUMN {_col} VARCHAR(5)"))
            db.session.commit()
        except Exception:
            db.session.rollback()  # Column already exists — rollback to clean transaction for Postgres

    # Phase 9 migration: soft-delete + audit columns
    _migrations = [
        ("patient_details",  "is_active  INTEGER NOT NULL DEFAULT 1"),
        ("patient_details",  "created_at DATETIME"),
        ("patient_details",  "updated_at DATETIME"),
        ("doctor_details",   "is_active  INTEGER NOT NULL DEFAULT 1"),
        ("doctor_details",   "created_at DATETIME"),
        ("doctor_details",   "updated_at DATETIME"),
        ("worker_details",   "is_active  INTEGER NOT NULL DEFAULT 1"),
        ("worker_details",   "created_at DATETIME"),
        ("worker_details",   "updated_at DATETIME"),
    ]
    for _table, _col_def in _migrations:
        _col_name = _col_def.split()[0]
        try:
            db.session.execute(db.text(f"ALTER TABLE {_table} ADD COLUMN {_col_def}"))
            db.session.commit()
            print(f"[HSMS] '{_col_name}' added to {_table}.")
        except Exception:
            db.session.rollback()  # Already exists — rollback to clean transaction for Postgres

    # Read credentials from environment variables (production) or fall back to defaults (dev)
    default_username = os.environ.get('HSMS_ADMIN_USER', 'Chandradeep05')
    default_password = os.environ.get('HSMS_ADMIN_PASS', '987654321')

    admin = User.query.filter_by(username=default_username).first()

    if not admin:
        # Fresh install — create admin with hashed password
        hashed = bcrypt.generate_password_hash(default_password).decode('utf-8')
        admin = User(username=default_username, password=hashed)
        db.session.add(admin)
        db.session.commit()
        print("[HSMS] Admin user created with bcrypt-hashed password.")
    elif not admin.password.startswith('$2b$'):
        # Existing user has a plaintext password from Phase 1 — migrate it now
        admin.password = bcrypt.generate_password_hash(admin.password).decode('utf-8')
        db.session.commit()
        print("[HSMS] Existing admin password migrated to bcrypt hash.")

    # Ensure role column exists on existing rows (SQLite has no ALTER COLUMN,
    # so we patch via the ORM if the field came back as None)
    if admin and admin.role is None:
        admin.role = 'admin'
        db.session.commit()
        print("[HSMS] Existing admin role set to 'admin'.")


# ──────────────────────────────────────────────
# Sample Data Seeding
# ──────────────────────────────────────────────
def seed_data():
    """
    Insert realistic sample data only when the DB is completely empty.
    Safe to call on every startup — guards against re-seeding.
    """
    if Patient.query.count() > 0:
        return  # Data already exists — skip seeding

    print("[HSMS] Seeding sample data...")

    # ── Patients ──────────────────────────────
    patients = [
        Patient(id='P001', name='Arjun Sharma',   age=34, gender='Male',   problem='Fever & cough',        phone='9876543210'),
        Patient(id='P002', name='Priya Mehta',    age=28, gender='Female', problem='Migraine',              phone='9823456701'),
        Patient(id='P003', name='Ravi Kumar',     age=52, gender='Male',   problem='Hypertension',         phone='9845001234'),
        Patient(id='P004', name='Sunita Patel',   age=45, gender='Female', problem='Diabetes Type II',      phone='9712345678'),
        Patient(id='P005', name='Anil Verma',     age=61, gender='Male',   problem='Knee osteoarthritis',  phone='9900112233'),
        Patient(id='P006', name='Meera Iyer',     age=31, gender='Female', problem='Anxiety & insomnia',   phone='9988776655'),
    ]
    db.session.add_all(patients)

    # ── Doctors ───────────────────────────────
    doctors = [
        Doctor(id='D001', name='Dr. Ananya Rao',      age=42, department='General Medicine', phone='9811000001', start_time='09:00', end_time='17:00'),
        Doctor(id='D002', name='Dr. Rajesh Nair',     age=50, department='Cardiology',       phone='9811000002', start_time='10:00', end_time='16:00'),
        Doctor(id='D003', name='Dr. Kavita Singh',    age=38, department='Neurology',        phone='9811000003', start_time='09:00', end_time='15:00'),
        Doctor(id='D004', name='Dr. Suresh Menon',    age=55, department='Orthopaedics',     phone='9811000004', start_time='08:00', end_time='14:00'),
    ]
    db.session.add_all(doctors)

    # ── Workers ───────────────────────────────
    workers = [
        Worker(id='W001', name='Ramesh Pillai',  age=35, work_type='Nurse',         phone='9700100001'),
        Worker(id='W002', name='Shalini Das',    age=29, work_type='Lab Technician', phone='9700100002'),
        Worker(id='W003', name='Deepak Joshi',   age=40, work_type='Ward Boy',      phone='9700100003'),
    ]
    db.session.add_all(workers)
    db.session.commit()  # Commit before appointments (FK dependency)

    # ── Appointments (spread across past + future dates) ──
    today = date_type.today()
    # FIX: timedelta is already imported at top level — removed redundant inline import
    appointments = [
        # Today
        Appointment(patient_id='P001', doctor_id='D001', appt_date=today.strftime('%Y-%m-%d'),               appt_time='09:00', reason='Follow-up checkup',       status='Scheduled'),
        Appointment(patient_id='P002', doctor_id='D003', appt_date=today.strftime('%Y-%m-%d'),               appt_time='10:30', reason='Migraine review',          status='Scheduled'),
        Appointment(patient_id='P004', doctor_id='D002', appt_date=today.strftime('%Y-%m-%d'),               appt_time='11:00', reason='Cardiac screening',        status='Scheduled'),
        # Tomorrow
        Appointment(patient_id='P003', doctor_id='D001', appt_date=(today + timedelta(days=1)).strftime('%Y-%m-%d'), appt_time='09:30', reason='BP monitoring',    status='Scheduled'),
        Appointment(patient_id='P005', doctor_id='D004', appt_date=(today + timedelta(days=1)).strftime('%Y-%m-%d'), appt_time='08:00', reason='Knee X-ray review', status='Scheduled'),
        # Day after tomorrow
        Appointment(patient_id='P006', doctor_id='D003', appt_date=(today + timedelta(days=2)).strftime('%Y-%m-%d'), appt_time='10:00', reason='Anxiety consult',   status='Scheduled'),
        Appointment(patient_id='P001', doctor_id='D002', appt_date=(today + timedelta(days=2)).strftime('%Y-%m-%d'), appt_time='10:30', reason='ECG test',           status='Scheduled'),
        # Past (for chart history)
        Appointment(patient_id='P002', doctor_id='D001', appt_date=(today - timedelta(days=1)).strftime('%Y-%m-%d'), appt_time='09:00', reason='Routine checkup',   status='Scheduled'),
        Appointment(patient_id='P003', doctor_id='D002', appt_date=(today - timedelta(days=2)).strftime('%Y-%m-%d'), appt_time='11:00', reason='Cholesterol test',   status='Cancelled'),
        Appointment(patient_id='P004', doctor_id='D004', appt_date=(today - timedelta(days=3)).strftime('%Y-%m-%d'), appt_time='08:30', reason='Post-op review',    status='Scheduled'),
    ]
    db.session.add_all(appointments)
    db.session.commit()
    print(f"[HSMS] Seeded: {len(patients)} patients, {len(doctors)} doctors, {len(workers)} workers, {len(appointments)} appointments.")




# ──────────────────────────────────────────────
# Helpers — auth guard + role guard
# ──────────────────────────────────────────────
def login_required(f):
    """Decorator: redirect unauthenticated requests to login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Decorator factory: allow access only to users whose role is in `roles`."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                return render_template('dashboard.html',
                                       stats=_dashboard_stats(),
                                       access_error='You do not have permission to perform this action.'), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def _dashboard_stats():
    """Helper: returns stats dict used by dashboard and role_required fallback."""
    return {
        'total_patients':         Patient.query.filter_by(is_active=True).count(),
        'total_doctors':          Doctor.query.filter_by(is_active=True).count(),
        'total_workers':          Worker.query.filter_by(is_active=True).count(),
        'total_appointments':     Appointment.query.count(),
        'active_appointments':    Appointment.query.filter_by(status='Scheduled').count(),
        'cancelled_appointments': Appointment.query.filter_by(status='Cancelled').count(),
    }


# ──────────────────────────────────────────────
# Phase 7 — slot generation helpers
# ──────────────────────────────────────────────

def generate_slots(start: str, end: str) -> list:
    """Return HH:MM slot strings every 30 min from start (inclusive) to end (exclusive)."""
    slots, cur = [], datetime.strptime(start, '%H:%M')
    stop = datetime.strptime(end, '%H:%M')
    while cur < stop:
        slots.append(cur.strftime('%H:%M'))
        total = cur.hour * 60 + cur.minute + 30
        cur = cur.replace(hour=total // 60, minute=total % 60)
    return slots


def get_available_slots(doctor_id: str, appt_date: str) -> list:
    """Return available 30-min slots for doctor on date (booked + past slots removed)."""
    doctor = Doctor.query.filter_by(id=doctor_id, is_active=True).first()
    if not doctor:
        return []
    all_slots = generate_slots(doctor.start_time or '09:00', doctor.end_time or '17:00')
    booked = {a.appt_time for a in Appointment.query.filter_by(
        doctor_id=doctor_id, appt_date=appt_date, status='Scheduled').all()}
    available = [s for s in all_slots if s not in booked]
    if appt_date == date_type.today().strftime('%Y-%m-%d'):
        now_hm = datetime.now().strftime('%H:%M')
        available = [s for s in available if s > now_hm]
    return available


# ──────────────────────────────────────────────
# Helper — server-side validation
# ──────────────────────────────────────────────
def validate_record(name, age_str, phone):
    """Returns a list of error strings. Empty list means valid."""
    errors = []
    if not name:
        errors.append('Name is required.')
    elif len(name) < 2:
        errors.append('Name must be at least 2 characters.')

    if not age_str:
        errors.append('Age is required.')
    else:
        try:
            age = int(age_str)
            if age < 1 or age > 120:
                errors.append('Age must be between 1 and 120.')
        except ValueError:
            errors.append('Age must be a valid number.')

    if phone and not phone.replace('+', '').replace('-', '').replace(' ', '').isdigit():
        errors.append('Phone must contain only digits (+ - spaces allowed).')
    elif phone and len(phone.replace('+', '').replace('-', '').replace(' ', '')) < 7:
        errors.append('Phone number is too short (min 7 digits).')

    return errors


# ──────────────────────────────────────────────
# Authentication Routes
# ──────────────────────────────────────────────

@app.route('/')
def login():
    return render_template('login.html')


@app.route('/auth', methods=['POST'])
def auth():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    # FIX: wrap DB query so a database error shows a safe message instead of a 500
    try:
        user = User.query.filter_by(username=username).first()
    except Exception as e:
        logging.error(f'[HSMS] DB error during login for "{username}": {e}')
        return render_template('login.html', error='System is starting up. Please try again in a moment.')

    if user and bcrypt.check_password_hash(user.password, password):
        session['user'] = user.username
        session['role'] = user.role or 'admin'   # store role for RBAC checks
        return redirect(url_for('dashboard'))
    return render_template('login.html', error='Invalid credentials. Please try again.')


@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('role', None)   # clear role on logout
    return redirect(url_for('login'))


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    stats = _dashboard_stats()

    # Today's appointments (up to 5, sorted by time)
    today_str = date_type.today().strftime('%Y-%m-%d')
    today_appointments = (
        Appointment.query
        .filter_by(appt_date=today_str)
        .order_by(Appointment.appt_time.asc())
        .limit(5)
        .all()
    )

    # 7-day appointment trend (real data)
    from datetime import timedelta
    chart_labels = []
    chart_data   = []
    for i in range(6, -1, -1):
        day = date_type.today() - timedelta(days=i)
        day_str = day.strftime('%Y-%m-%d')
        count   = Appointment.query.filter_by(appt_date=day_str).count()
        chart_labels.append(day.strftime('%a %d'))
        chart_data.append(count)

    return render_template('dashboard.html',
                           stats=stats,
                           today_appointments=today_appointments,
                           chart_labels=chart_labels,
                           chart_data=chart_data)


@app.route('/index')
@login_required
def index():
    return render_template('index.html')


# ──────────────────────────────────────────────
# Patient Routes
# ──────────────────────────────────────────────

@app.route('/patients', methods=['GET', 'POST'])
@login_required
def patients():
    if request.method == 'POST':
        pid     = request.form.get('id', '').strip()
        name    = request.form.get('name', '').strip()
        age     = request.form.get('age', '').strip()
        problem = request.form.get('problem', '').strip()
        phone   = request.form.get('phone', '').strip()

        if Patient.query.get(pid):
            return render_template('patients/register_patients.html', error=f'Patient ID {pid} already exists.')

        patient = Patient(id=pid, name=name, age=int(age), problem=problem, phone=phone)
        db.session.add(patient)
        db.session.commit()
        return redirect(url_for('view_patients'))
    return render_template('patients/register_patients.html')


@app.route('/register_patient', methods=['GET', 'POST'])
@login_required
def register_patient():
    if request.method == 'POST':
        pid       = request.form.get('id', '').strip()
        name      = request.form.get('name', '').strip()
        age       = request.form.get('age', '').strip()
        gender    = request.form.get('gender', '').strip()
        phone     = request.form.get('phone', '').strip()
        diagnosis = request.form.get('diagnosis', '').strip()

        # Server-side validation
        errors = validate_record(name, age, phone)
        if not pid:
            errors.append('Patient ID is required.')
        elif Patient.query.get(pid):
            errors.append(f'Patient ID "{pid}" already exists.')
        if not gender:
            errors.append('Gender is required.')

        if errors:
            return render_template('patients/register_patients.html',
                                   errors=errors,
                                   form=request.form)

        patient = Patient(id=pid, name=name, age=int(age),
                          gender=gender, problem=diagnosis, phone=phone)
        db.session.add(patient)
        db.session.commit()
        return redirect(url_for('view_patients'))
    return render_template('patients/register_patients.html')


@app.route('/view_patients')
@login_required
def view_patients():
    page = request.args.get('page', 1, type=int)
    pagination = Patient.query.filter_by(is_active=True).order_by(Patient.id.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template('patients/view_patients.html',
                           patients=pagination.items,
                           pagination=pagination)


@app.route('/edit_patient/<pid>', methods=['GET', 'POST'])
@login_required
def edit_patient(pid):
    patient = Patient.query.get_or_404(pid)
    if request.method == 'POST':
        name      = request.form.get('name', '').strip()
        age       = request.form.get('age', '').strip()
        gender    = request.form.get('gender', '').strip()
        phone     = request.form.get('phone', '').strip()
        diagnosis = request.form.get('diagnosis', '').strip()

        errors = validate_record(name, age, phone)
        if not gender:
            errors.append('Gender is required.')

        if errors:
            return render_template('patients/edit_patient.html',
                                   patient=patient, errors=errors)

        patient.name    = name
        patient.age     = int(age)
        patient.gender  = gender
        patient.phone   = phone
        patient.problem = diagnosis
        db.session.commit()
        return redirect(url_for('view_patients'))
    return render_template('patients/edit_patient.html', patient=patient)


# ──────────────────────────────────────────────
# Doctor Routes
# ──────────────────────────────────────────────

@app.route('/register_doctor', methods=['GET', 'POST'])
@login_required
def register_doctor():
    if request.method == 'POST':
        did        = request.form.get('id', '').strip()
        name       = request.form.get('name', '').strip()
        age        = request.form.get('age', '').strip()
        department = request.form.get('department', '').strip()
        phone      = request.form.get('phone', '').strip()

        errors = validate_record(name, age, phone)
        if not did:
            errors.append('Doctor ID is required.')
        elif Doctor.query.get(did):
            errors.append(f'Doctor ID "{did}" already exists.')
        if not department:
            errors.append('Department is required.')

        if errors:
            return render_template('doctors/register_doctor.html',
                                   errors=errors, form=request.form)

        doctor = Doctor(id=did, name=name, age=int(age),
                        department=department, phone=phone)
        db.session.add(doctor)
        db.session.commit()
        return redirect(url_for('view_doctors'))
    return render_template('doctors/register_doctor.html')


@app.route('/view_doctors')
@login_required
def view_doctors():
    page = request.args.get('page', 1, type=int)
    pagination = Doctor.query.filter_by(is_active=True).order_by(Doctor.id.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template('doctors/view_doctors.html',
                           doctors=pagination.items,
                           pagination=pagination)


@app.route('/edit_doctor/<did>', methods=['GET', 'POST'])
@login_required
def edit_doctor(did):
    doctor = Doctor.query.get_or_404(did)
    if request.method == 'POST':
        name       = request.form.get('name', '').strip()
        age        = request.form.get('age', '').strip()
        department = request.form.get('department', '').strip()
        phone      = request.form.get('phone', '').strip()

        errors = validate_record(name, age, phone)
        if not department:
            errors.append('Department is required.')

        if errors:
            return render_template('doctors/edit_doctor.html',
                                   doctor=doctor, errors=errors)

        doctor.name       = name
        doctor.age        = int(age)
        doctor.department = department
        doctor.phone      = phone
        db.session.commit()
        return redirect(url_for('view_doctors'))
    return render_template('doctors/edit_doctor.html', doctor=doctor)


# ──────────────────────────────────────────────
# Worker Routes
# ──────────────────────────────────────────────

@app.route('/register_worker', methods=['GET', 'POST'])
@login_required
def register_worker():
    if request.method == 'POST':
        wid       = request.form.get('id', '').strip()
        name      = request.form.get('name', '').strip()
        age       = request.form.get('age', '').strip()
        work_type = request.form.get('work_type', '').strip()
        phone     = request.form.get('phone', '').strip()

        errors = validate_record(name, age, phone)
        if not wid:
            errors.append('Worker ID is required.')
        elif Worker.query.get(wid):
            errors.append(f'Worker ID "{wid}" already exists.')
        if not work_type:
            errors.append('Work type is required.')

        if errors:
            return render_template('workers/register_worker.html',
                                   errors=errors, form=request.form)

        worker = Worker(id=wid, name=name, age=int(age),
                        work_type=work_type, phone=phone)
        db.session.add(worker)
        db.session.commit()
        return redirect(url_for('view_workers'))
    return render_template('workers/register_worker.html')


@app.route('/view_workers')
@login_required
def view_workers():
    page = request.args.get('page', 1, type=int)
    pagination = Worker.query.filter_by(is_active=True).order_by(Worker.id.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template('workers/view_workers.html',
                           workers=pagination.items,
                           pagination=pagination)


@app.route('/edit_worker/<wid>', methods=['GET', 'POST'])
@login_required
def edit_worker(wid):
    worker = Worker.query.get_or_404(wid)
    if request.method == 'POST':
        name      = request.form.get('name', '').strip()
        age       = request.form.get('age', '').strip()
        work_type = request.form.get('work_type', '').strip()
        phone     = request.form.get('phone', '').strip()

        errors = validate_record(name, age, phone)
        if not work_type:
            errors.append('Work type is required.')

        if errors:
            return render_template('workers/edit_worker.html',
                                   worker=worker, errors=errors)

        worker.name      = name
        worker.age       = int(age)
        worker.work_type = work_type
        worker.phone     = phone
        db.session.commit()
        return redirect(url_for('view_workers'))
    return render_template('workers/edit_worker.html', worker=worker)


# ──────────────────────────────────────────────
# JSON API
# ──────────────────────────────────────────────

MODEL_MAP = {
    'patient': Patient,
    'doctor':  Doctor,
    'worker':  Worker,
}


@app.route('/get_all/<entity>')
@login_required
@role_required('admin')
def get_all(entity):
    model = MODEL_MAP.get(entity)
    if not model:
        return jsonify({'error': 'Invalid entity'}), 400

    records = model.query.all()
    result = [row.__dict__.copy() for row in records]
    for r in result:
        r.pop('_sa_instance_state', None)
    return jsonify(result)


@app.route('/delete/<entity>/<record_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_entity(entity, record_id):
    model = MODEL_MAP.get(entity)
    if not model:
        return jsonify({'error': 'Invalid entity'}), 400

    record = model.query.get(record_id)
    if not record:
        return jsonify({'error': 'Record not found'}), 404

    db.session.delete(record)
    db.session.commit()
    return jsonify({'message': f'{entity.capitalize()} deleted successfully'})


# ──────────────────────────────────────────────
# Search Route
# ──────────────────────────────────────────────

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    results          = []
    search_performed = False
    record_type      = request.values.get('record_type', '')
    query            = request.values.get('query', '').strip()
    department_f     = request.values.get('department', '').strip()
    date_f           = request.values.get('date', '').strip()

    if request.method == 'POST' or (request.method == 'GET' and query):
        if not record_type:
            # GET from topbar with no type selected — don't execute a blank search
            return render_template('search.html',
                                   results=[], search_performed=False,
                                   record_type='', query=query,
                                   department_f='', date_f='',
                                   departments=[
                                       r[0] for r in db.session.query(Doctor.department)
                                       .filter(Doctor.is_active == True, Doctor.department.isnot(None))
                                       .distinct().order_by(Doctor.department).all()
                                   ],
                                   search_hint='Please select a record type to search.')
        search_performed = True
        like = f'%{query}%'

        if record_type == 'patient':
            q = Patient.query.filter_by(is_active=True)
            if query:
                q = q.filter(db.or_(Patient.name.ilike(like), Patient.id.ilike(like)))
            results = q.order_by(Patient.name).all()

        elif record_type == 'doctor':
            q = Doctor.query.filter_by(is_active=True)
            if query:
                q = q.filter(db.or_(Doctor.name.ilike(like), Doctor.id.ilike(like)))
            if department_f:
                q = q.filter(Doctor.department.ilike(f'%{department_f}%'))
            results = q.order_by(Doctor.name).all()

        elif record_type == 'worker':
            q = Worker.query.filter_by(is_active=True)
            if query:
                q = q.filter(db.or_(Worker.name.ilike(like), Worker.id.ilike(like)))
            results = q.order_by(Worker.name).all()

        elif record_type == 'appointment':
            q = Appointment.query
            if query:
                q = q.filter(db.or_(
                    Appointment.patient_id.ilike(like),
                    Appointment.doctor_id.ilike(like),
                    Appointment.reason.ilike(like)
                ))
            if date_f:
                q = q.filter(Appointment.appt_date == date_f)
            results = q.order_by(Appointment.appt_date.desc(), Appointment.appt_time).all()

    # Pass distinct departments for filter dropdown
    departments = [r[0] for r in db.session.query(Doctor.department)
                   .filter(Doctor.is_active == True, Doctor.department.isnot(None))
                   .distinct().order_by(Doctor.department).all()]

    return render_template('search.html',
                           results=results,
                           search_performed=search_performed,
                           record_type=record_type,
                           query=query,
                           department_f=department_f,
                           date_f=date_f,
                           departments=departments)


# ──────────────────────────────────────────────
# Delete Records (admin only)
# ──────────────────────────────────────────────

@app.route('/delete_records', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def delete_record():
    if request.method == 'POST':
        record_type = request.form.get('record_type', '')
        record_id   = request.form.get('record_id', '').strip()

        model = MODEL_MAP.get(record_type)
        if not model:
            return "Invalid record type.", 400

        record = model.query.get(record_id)
        if record:
            if hasattr(record, 'is_active'):
                # Soft delete — preserve the record, just mark inactive
                record.is_active = False
                db.session.commit()
            else:
                db.session.delete(record)
                db.session.commit()

        return render_template('delete_confirmation.html',
                               record_type=record_type.capitalize(),
                               record_id=record_id)

    return render_template('delete_records.html')


# ──────────────────────────────────────────────
# Appointment Routes
# ──────────────────────────────────────────────

@app.route('/get_slots')
@login_required
def get_slots():
    """AJAX: return available slots JSON for a doctor on a given date."""
    doctor_id = request.args.get('doctor_id', '').strip()
    appt_date = request.args.get('date', '').strip()
    if not doctor_id or not appt_date:
        return jsonify({'slots': []}), 400
    try:
        datetime.strptime(appt_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'slots': []}), 400
    return jsonify({'slots': get_available_slots(doctor_id, appt_date)})


@app.route('/appointments', methods=['GET', 'POST'])
@login_required
def appointments():
    """Book a new appointment with full validation and double-booking prevention."""
    patients_list = Patient.query.filter_by(is_active=True).order_by(Patient.name).all()
    doctors_list  = Doctor.query.filter_by(is_active=True).order_by(Doctor.name).all()
    errors = []

    if request.method == 'POST':
        patient_id = request.form.get('patient_id', '').strip()
        doctor_id  = request.form.get('doctor_id',  '').strip()
        appt_date  = request.form.get('appt_date',  '').strip()
        appt_time  = request.form.get('appt_time',  '').strip()
        reason     = request.form.get('reason',     '').strip()

        # --- Field presence checks ---
        if not patient_id:
            errors.append('Please select a patient.')
        if not doctor_id:
            errors.append('Please select a doctor.')
        if not appt_date:
            errors.append('Appointment date is required.')
        if not appt_time:
            errors.append('Appointment time is required.')

        # --- Validate patient exists and is active ---
        if patient_id:
            _pat = Patient.query.filter_by(id=patient_id, is_active=True).first()
            if not _pat:
                errors.append(f'Patient ID "{patient_id}" does not exist or is inactive.')

        # --- Validate doctor exists and is active ---
        if doctor_id:
            _doc = Doctor.query.filter_by(id=doctor_id, is_active=True).first()
            if not _doc:
                errors.append(f'Doctor ID "{doctor_id}" does not exist or is inactive.')

        # --- Validate date is not in the past ---
        if appt_date:
            try:
                parsed_date = datetime.strptime(appt_date, '%Y-%m-%d').date()
                if parsed_date < date_type.today():
                    errors.append('Appointment date cannot be in the past.')
            except ValueError:
                errors.append('Invalid date format. Use YYYY-MM-DD.')

        # --- Slot availability re-check (race-condition guard) ---
        if not errors and doctor_id and appt_date and appt_time:
            if appt_time not in get_available_slots(doctor_id, appt_date):
                errors.append('Slot just got booked. Please choose another.')

        if not errors:
            appt = Appointment(
                patient_id=patient_id,
                doctor_id=doctor_id,
                appt_date=appt_date,
                appt_time=appt_time,
                reason=reason,
                status='Scheduled'
            )
            db.session.add(appt)
            db.session.commit()
            return redirect(url_for('view_appointments'))

    return render_template('appointments/book_appointment.html',
                           patients=patients_list,
                           doctors=doctors_list,
                           errors=errors,
                           today=date_type.today().strftime('%Y-%m-%d'))


@app.route('/view_appointments')
@login_required
def view_appointments():
    """View all appointments with pagination, newest first."""
    page = request.args.get('page', 1, type=int)
    pagination = Appointment.query.order_by(
        Appointment.appt_date.desc(),
        Appointment.appt_time.desc()
    ).paginate(page=page, per_page=10, error_out=False)
    active_count = Appointment.query.filter_by(status='Scheduled').count()
    return render_template('appointments/view_appointments.html',
                           appointments=pagination.items,
                           pagination=pagination,
                           active_count=active_count)


@app.route('/cancel_appointment/<int:appt_id>', methods=['POST'])
@login_required
def cancel_appointment(appt_id):
    """Soft-cancel: sets status to Cancelled. Never deletes the record."""
    appt = Appointment.query.get_or_404(appt_id)
    if appt.status == 'Scheduled':
        appt.status = 'Cancelled'
        db.session.commit()
    # Already Cancelled — idempotent, no action needed
    return redirect(url_for('view_appointments'))


# ──────────────────────────────────────────────
# CSV Export
# ──────────────────────────────────────────────

EXPORT_CONFIG = {
    'patients': {
        'model':   Patient,
        'headers': ['ID', 'Name', 'Age', 'Gender', 'Phone', 'Diagnosis'],
        'row':     lambda r: [r.id, r.name, r.age, r.gender or '', r.phone or '', r.problem or ''],
    },
    'doctors': {
        'model':   Doctor,
        'headers': ['ID', 'Name', 'Age', 'Department', 'Phone'],
        'row':     lambda r: [r.id, r.name, r.age, r.department or '', r.phone or ''],
    },
    'appointments': {
        'model':   Appointment,
        'headers': ['ID', 'Patient ID', 'Patient Name', 'Doctor ID', 'Doctor Name',
                    'Date', 'Time', 'Reason', 'Status'],
        'row':     lambda r: [r.id, r.patient_id, r.patient.name,
                              r.doctor_id, r.doctor.name,
                              r.appt_date, r.appt_time,
                              r.reason or '', r.status],
    },
}


@app.route('/export/<entity>')
@login_required
@role_required('admin')
def export_csv(entity):
    """
    Export all records for the given entity as a UTF-8 CSV download.
    Supported entities: patients, doctors, appointments.
    Future-ready admin check: add role verification here when roles are implemented.
    """
    # Access control stub — extend when role system is added
    # if session.get('role') != 'admin':
    #     return 'Access denied.', 403

    config = EXPORT_CONFIG.get(entity)
    if not config:
        return 'Invalid export type. Choose: patients, doctors, appointments.', 400

    # Fetch all records and write to in-memory CSV with UTF-8 BOM (for Excel compatibility)
    records = config['model'].query.all()
    output  = io.StringIO()
    output.write('\ufeff')          # UTF-8 BOM — ensures Excel opens with correct encoding
    writer  = csv.writer(output)
    writer.writerow(config['headers'])
    for record in records:
        writer.writerow(config['row'](record))

    output.seek(0)
    filename = f"{entity}_{date_type.today().strftime('%Y%m%d')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# ──────────────────────────────────────────────
# DB Init — runs on every startup (gunicorn + python hospital.py)
# ──────────────────────────────────────────────

# FIX: module-level so Gunicorn triggers it on import (not just __main__).
_db_initialized = False

def _ensure_db():
    """Ensure DB tables exist. Safe to call multiple times."""
    global _db_initialized
    if _db_initialized:
        return
    try:
        init_db()
        seed_data()
        _db_initialized = True
        print("[HSMS] Database initialized successfully.")
    except Exception as e:
        logging.error(f"[HSMS] DB init failed: {e}")
        raise

# Attempt init at import time (works for most deployments)
with app.app_context():
    try:
        _ensure_db()
    except Exception as e:
        logging.warning(f"[HSMS] DB init deferred — will retry on first request: {e}")

@app.before_request
def _before_request_db_check():
    """Retry DB init if it failed at startup (e.g. Supabase cold start)."""
    if not _db_initialized:
        _ensure_db()


# ──────────────────────────────────────────────
# Entry Point (local dev only)
# ──────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', '0') == '1')
