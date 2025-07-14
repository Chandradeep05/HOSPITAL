# 🏥 Hospital Staff Management System

A simple web-based system built with **Flask** to manage hospital staff, patients, doctors, and workers. It allows you to **register**, **view**, **search**, and **delete** records for each category, with a user-friendly dashboard and interface.

---

## 🌐 Features

- ✅ User login and authentication  
- 👨‍⚕️ Register and view doctors  
- 🧑‍🦽 Register and view patients  
- 🧹 Register and view workers  
- 🔍 Search functionality across all records  
- ❌ Delete records with confirmation  
- 🎨 Responsive UI with clean CSS and background images  

---

## 🛠️ Tech Stack

- **Backend**: Python (Flask)  
- **Frontend**: HTML, CSS, JS  
- **Database**: SQLite3  
- **Templating**: Jinja2  

---

## 📂 Folder Structure

hospital-staff-management/
│
├── static/
│ ├── images/
│ ├── style.css
│ └── script.js
│
├── templates/
│ ├── dashboard.html
│ ├── login.html
│ ├── index.html
│ ├── delete_records.html
│ ├── delete_confirmation.html
│ ├── search.html
│ ├── doctors/
│ │ ├── register_doctor.html
│ │ └── view_doctors.html
│ ├── patients/
│ │ ├── register_patients.html
│ │ └── view_patients.html
│ └── workers/
│ ├── register_worker.html
│ └── view_workers.html
│
├── hospital.py
├── hospital.db
└── README.md

---

## 🚀 Getting Started

### 1. Clone the Repository
git clone https://github.com/Chandradeep05/HOSPITAL.git
cd HOSPITAL
### 2. (Optional) Set up Virtual Environment
python -m venv venv
venv\Scripts\activate      # On Windows
# OR
source venv/bin/activate   # On Linux/Mac
### 3. Install Required Packages
pip install flask
### 4. Run the Application
python hospital.py
Then open your browser and go to:
📎 http://127.0.0.1:5000

### 📸 Screenshots
![Login Page](static/images/login_bg.jpg)
![Dashboard](static/images/dashboard_bg.jpg)
### ✨ Future Improvements
* Add role-based authentication (Admin, Staff)

* Appointment scheduling module

* Export reports (CSV/PDF)

* Billing and payment integration

* Add unit tests and validations

### 🤝 Contribution
Feel free to fork this repo, make changes, and open a pull request.
Make sure your changes are tested and documented properly.

### 📄 License
This project is licensed under the MIT License.

### 🙌 Acknowledgements
Thanks to the open-source community and Flask documentation contributors.

