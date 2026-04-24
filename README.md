# 🏥 Hospital Staff Management System

# 🏥 HSMS — Hospital Staff Management System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Flask-3.x-black?style=for-the-badge&logo=flask" />
  <img src="https://img.shields.io/badge/PostgreSQL-Production-336791?style=for-the-badge&logo=postgresql" />
  <img src="https://img.shields.io/badge/Deployed-Render-46E3B7?style=for-the-badge&logo=render" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

<p align="center">
  A production-ready, full-stack Hospital Administration Portal built with Flask & SQLAlchemy — handling patients, doctors, staff, and appointments end-to-end.
</p>

<p align="center">
  <a href="https://hospital-1-8ttx.onrender.com" target="_blank"><strong>🔗 Live Demo →</strong></a>
</p>

---

## 📸 Screenshots

| Dashboard | Book Appointment |
|-----------|-----------------|
| ![Dashboard]<img width="1366" height="637" alt="image" src="https://github.com/user-attachments/assets/73c5870d-4a2d-4de4-a935-1700004c6c09" />
 | ![Book Appointment]<img width="1366" height="638" alt="image" src="https://github.com/user-attachments/assets/61eb8de4-0f21-4227-b60e-03405cbf04cd" />

 |

| Register Patient | View Workers | View Appointments |
|-----------------|--------------|-------------------|
| ![Register Patient]<img width="1365" height="768" alt="image" src="https://github.com/user-attachments/assets/ad211383-8f3f-426c-992f-e2967731baf3" />
 | ![Workers]<img width="1362" height="634" alt="image" src="https://github.com/user-attachments/assets/e72400c0-f914-4c7f-85f9-92dc86a38ba0" />
 | ![Appointments]<img width="1357" height="639" alt="image" src="https://github.com/user-attachments/assets/ef5e9829-7331-4dd0-99b3-f1d06a5763fe" />
 |

---

## ✨ Features

### 🗂️ Entity Management
- **Full CRUD** for Patients, Doctors, and Workers
- **Soft Deletion** — records use an `is_active` flag instead of being physically deleted, preserving complete historical audit trails
- **Server-side validation** on all form inputs before hitting the database

### 📅 Intelligent Appointment Scheduling
- **Slot-based booking** — dynamically generates 30-minute slots from each doctor's working hours
- **Conflict prevention** — already-booked and past slots are filtered out in real-time
- **Soft cancellation** — appointments are marked `Cancelled` (never deleted), keeping patient history intact
- **Department-aware** — appointments are linked to doctor specialisations (Cardiology, Neurology, Orthopaedics, General Medicine, etc.)

### 🔐 Security & Access Control
- **Role-Based Access Control (RBAC)** — custom `@role_required` decorators restrict admin-only actions (bulk exports, deletions)
- **bcrypt password hashing** — plaintext passwords are never stored
- **Environment-based secrets** — `SECRET_KEY` and `DATABASE_URL` loaded via `.env`, never in source code
- **Production flags** — `debug=False` enforced in production

### 📊 Analytics & Search
- **Live dashboard** with system-wide stats (total patients, doctors, workers, appointments)
- **7-day trailing appointment trend** chart powered by Chart.js
- **Global search** across all entity types with secondary filters (e.g. filter doctors by department)
- **CSV data export** (admin-restricted) for auditing and reporting

### ☁️ Production Readiness
- **Dual database support** — SQLite for local development, PostgreSQL for production (auto-detected via `DATABASE_URL`)
- **Idempotent migrations** — `init_db()` runs `ALTER TABLE` safely on startup, hardened for PostgreSQL's strict transaction rules
- **Self-healing startup** — wrapped in `try/except` to prevent Gunicorn worker crashes on database hiccups
- **Gunicorn WSGI server** configured via `Procfile` for Render deployment

---

## 🏗️ Architecture

```
HSMS/
├── hospital.py          # Main app — routes, models, auth logic
├── templates/           # Jinja2 HTML templates
│   ├── dashboard.html
│   ├── patients/
│   ├── doctors/
│   ├── workers/
│   └── appointments/
├── static/              # CSS, JS, Chart.js assets
├── .env                 # Secrets (never committed)
├── requirements.txt
├── Procfile             # Gunicorn config for Render
└── .gitignore
```

**Pattern:** Monolithic MVC — Models (SQLAlchemy ORM), Views (Jinja2 templates), Controllers (Flask route handlers)

### Data Models

| Model | Key Fields |
|-------|-----------|
| `User` | id, username, password_hash, role |
| `Patient` | id, name, patient_id, age, gender, phone, diagnosis, is_active |
| `Doctor` | id, name, doctor_id, specialisation, department, phone, is_active |
| `Worker` | id, name, worker_id, role, age, phone, is_active |
| `Appointment` | id, patient_id (FK), doctor_id (FK), appt_date, appt_time, reason, status |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- pip
- Git

### Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/hsms.git
cd hsms

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add:
#   SECRET_KEY=your-secret-key-here
#   DATABASE_URL=            # leave blank to use SQLite locally

# 5. Run the app
python hospital.py
```

Visit `http://localhost:5000` — the database and tables are created automatically on first run.

### Default Admin Credentials

```
Username: admin
Password: admin123
```

> ⚠️ Change these immediately after first login in any production deployment.

---

## 🌐 Deployment (Render)

This project is pre-configured for [Render](https://render.com).

1. Push your code to GitHub
2. Create a new **Web Service** on Render, connect your repo
3. Set the following environment variables in Render's dashboard:
   ```
   SECRET_KEY=<strong-random-key>
   DATABASE_URL=<your-postgres-url>
   ```
4. Render auto-detects the `Procfile` and runs Gunicorn

The `Procfile`:
```
web: gunicorn hospital:app
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask |
| ORM | SQLAlchemy |
| Auth | Flask-Bcrypt |
| Server | Gunicorn |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL |
| Frontend | HTML5, CSS3, Jinja2 |
| Charts | Chart.js |
| Deployment | Render |

---

## 🗺️ Roadmap

- [ ] Flask Blueprints refactor (modular routing)
- [ ] Pytest test suite (slot generator, RBAC decorators)
- [ ] Database-level `UniqueConstraint` on `(doctor_id, appt_date, appt_time)` to close race condition
- [ ] REST API layer (JSON endpoints)
- [ ] React or Vue frontend (decoupled architecture)
- [ ] Billing & invoice module
- [ ] Email/SMS appointment reminders
- [ ] Patient medical history timeline

---

## 🤝 Contributing

Contributions are welcome! Please open an issue first to discuss any changes.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 👤 Author

**Chandradeep**  
[GitHub](https://github.com/YOUR_USERNAME) · [Live Project](https://hospital-1-8ttx.onrender.com)

---

<p align="center">Built with ❤️ using Flask & SQLAlchemy</p>
