
import sqlite3
import random
from datetime import datetime, timedelta, date

DB_PATH = "clinic.db"

#Schema definition with realistic fields and relationships

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS patients (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name     TEXT NOT NULL,
    last_name      TEXT NOT NULL,
    email          TEXT,
    phone          TEXT,
    date_of_birth  DATE,
    gender         TEXT,
    city           TEXT,
    registered_date DATE
);

CREATE TABLE IF NOT EXISTS doctors (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    specialization   TEXT,
    department       TEXT,
    phone            TEXT
);

CREATE TABLE IF NOT EXISTS appointments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id       INTEGER REFERENCES patients(id),
    doctor_id        INTEGER REFERENCES doctors(id),
    appointment_date DATETIME,
    status           TEXT,
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS treatments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id   INTEGER REFERENCES appointments(id),
    treatment_name   TEXT,
    cost             REAL,
    duration_minutes INTEGER
);

CREATE TABLE IF NOT EXISTS invoices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id   INTEGER REFERENCES patients(id),
    invoice_date DATE,
    total_amount REAL,
    paid_amount  REAL,
    status       TEXT
);
"""

# Dummy data

FIRST_NAMES_M = ["James","John","Robert","Michael","William","David","Joseph","Charles",
                  "Thomas","Christopher","Daniel","Matthew","Anthony","Mark","Donald",
                  "Paul","Steven","Andrew","Kenneth","Joshua","Kevin","Brian","George","Edward","Ronald"]
FIRST_NAMES_F = ["Mary","Patricia","Jennifer","Linda","Barbara","Elizabeth","Susan","Jessica",
                  "Sarah","Karen","Lisa","Nancy","Betty","Margaret","Sandra","Ashley","Dorothy",
                  "Kimberly","Emily","Donna","Michelle","Carol","Amanda","Melissa","Deborah"]
LAST_NAMES    = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
                  "Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson",
                  "Thomas","Taylor","Moore","Jackson","Martin","Lee","Thompson","White","Harris","Sanchez"]
CITIES        = ["New York","Los Angeles","Chicago","Houston","Phoenix",
                  "Philadelphia","San Antonio","Dallas","San Diego","Austin"]
SPECIALIZATIONS = {
    "Dermatology": "Skin Care",
    "Cardiology":  "Heart & Vascular",
    "Orthopedics": "Bone & Joint",
    "General":     "General Medicine",
    "Pediatrics":  "Child Health",
}
DOCTOR_NAMES  = [
    ("Dr. Emily Carter",   "Dermatology"),
    ("Dr. Raj Patel",      "Dermatology"),
    ("Dr. Susan Lee",      "Dermatology"),
    ("Dr. Michael Torres", "Cardiology"),
    ("Dr. David Kim",      "Cardiology"),
    ("Dr. Angela Davis",   "Cardiology"),
    ("Dr. Robert Singh",   "Orthopedics"),
    ("Dr. Maria Gonzalez", "Orthopedics"),
    ("Dr. James Wilson",   "Orthopedics"),
    ("Dr. Linda Chen",     "General"),
    ("Dr. Kevin Brown",    "General"),
    ("Dr. Sarah Johnson",  "General"),
    ("Dr. William Park",   "Pediatrics"),
    ("Dr. Nancy White",    "Pediatrics"),
    ("Dr. Thomas Adams",   "Pediatrics"),
]
TREATMENT_MAP = {
    "Dermatology": [("Skin Biopsy",350,30),("Acne Treatment",150,20),("Mole Removal",500,45),
                     ("Chemical Peel",250,40),("Laser Therapy",800,60)],
    "Cardiology":  [("ECG",200,15),("Echocardiogram",600,45),("Stress Test",400,60),
                     ("Holter Monitor",350,30),("Angioplasty",4500,120)],
    "Orthopedics": [("X-Ray",150,20),("MRI Scan",900,60),("Joint Injection",300,30),
                     ("Physical Therapy",200,45),("Arthroscopy",3500,90)],
    "General":     [("Blood Test",80,15),("General Checkup",120,30),("Vaccination",60,10),
                     ("Urinalysis",70,15),("Blood Pressure Check",50,10)],
    "Pediatrics":  [("Well-Child Visit",150,30),("Developmental Assessment",200,45),
                     ("Ear Exam",100,15),("Allergy Test",300,40),("Growth Monitoring",90,20)],
}
STATUSES_APT  = ["Scheduled","Completed","Cancelled","No-Show"]
STATUSES_INV  = ["Paid","Pending","Overdue"]
NOTES_POOL    = [
    "Patient reports improvement.",
    "Follow-up required in 2 weeks.",
    "Prescribed medication adjusted.",
    "Patient anxious; reassured.",
    "Lab results pending.",
    None, None, None,  # nulls for realism
]


def rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def rand_datetime(start: date, end: date) -> datetime:
    d = rand_date(start, end)
    hour = random.randint(8, 17)
    minute = random.choice([0, 15, 30, 45])
    return datetime(d.year, d.month, d.day, hour, minute)


def insert_doctors(cur):
    rows = []
    for name, spec in DOCTOR_NAMES:
        dept = SPECIALIZATIONS[spec]
        phone = f"555-{random.randint(1000,9999)}"
        rows.append((name, spec, dept, phone))
    cur.executemany(
        "INSERT INTO doctors (name,specialization,department,phone) VALUES (?,?,?,?)",
        rows
    )
    return cur.lastrowid 


def insert_patients(cur, n=200):
    today = date.today()
    start_reg = today - timedelta(days=365)
    rows = []
    for _ in range(n):
        gender = random.choice(["M","F"])
        fname = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
        lname = random.choice(LAST_NAMES)
        email = f"{fname.lower()}.{lname.lower()}{random.randint(1,99)}@email.com" if random.random() > 0.1 else None
        phone = f"555-{random.randint(1000,9999)}" if random.random() > 0.1 else None
        dob   = rand_date(date(1950,1,1), date(2010,12,31))
        city  = random.choice(CITIES)
        reg   = rand_date(start_reg, today)
        rows.append((fname, lname, email, phone, str(dob), gender, city, str(reg)))
    cur.executemany(
        "INSERT INTO patients (first_name,last_name,email,phone,date_of_birth,gender,city,registered_date) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows
    )


def insert_appointments(cur, n=500):
    today = date.today()
    start = today - timedelta(days=365)
    # Weights: some patients get many appts, some doctors get more
    patient_weights = [random.choices([1,2,3,4,5], weights=[40,30,15,10,5])[0] for _ in range(200)]
    patient_pool = []
    for pid, w in enumerate(patient_weights, start=1):
        patient_pool.extend([pid]*w)

    doctor_weights = [random.choices([1,2,3,4,5], weights=[20,20,20,20,20])[0] for _ in range(15)]
    doctor_pool = []
    for did, w in enumerate(doctor_weights, start=1):
        doctor_pool.extend([did]*w)

    rows = []
    for _ in range(n):
        pid    = random.choice(patient_pool)
        did    = random.choice(doctor_pool)
        dt     = rand_datetime(start, today)
        status = random.choices(STATUSES_APT, weights=[20,50,20,10])[0]
        note   = random.choice(NOTES_POOL)
        rows.append((pid, did, dt.strftime("%Y-%m-%d %H:%M:%S"), status, note))
    cur.executemany(
        "INSERT INTO appointments (patient_id,doctor_id,appointment_date,status,notes) VALUES (?,?,?,?,?)",
        rows
    )


def insert_treatments(cur, n_target=350):
    # Get completed appointment IDs + their doctor specialization
    rows = cur.execute(
        "SELECT a.id, d.specialization FROM appointments a "
        "JOIN doctors d ON d.id = a.doctor_id WHERE a.status='Completed'"
    ).fetchall()
    random.shuffle(rows)
    rows = rows[:n_target]
    inserts = []
    for apt_id, spec in rows:
        treatments = TREATMENT_MAP.get(spec, TREATMENT_MAP["General"])
        tname, base_cost, dur = random.choice(treatments)
        cost = round(base_cost * random.uniform(0.85, 1.25), 2)
        inserts.append((apt_id, tname, cost, dur))
    cur.executemany(
        "INSERT INTO treatments (appointment_id,treatment_name,cost,duration_minutes) VALUES (?,?,?,?)",
        inserts
    )


def insert_invoices(cur, n=300):
    patient_ids = [r[0] for r in cur.execute("SELECT id FROM patients").fetchall()]
    random.shuffle(patient_ids)
    used = patient_ids[:n] + random.choices(patient_ids, k=max(0,n-len(patient_ids)))
    today = date.today()
    start = today - timedelta(days=365)
    inserts = []
    for pid in used[:n]:
        inv_date = rand_date(start, today)
        total    = round(random.uniform(50, 5000), 2)
        status   = random.choices(STATUSES_INV, weights=[50,30,20])[0]
        paid     = total if status=="Paid" else round(total * random.uniform(0, 0.5), 2) if status=="Pending" else 0.0
        inserts.append((pid, str(inv_date), total, paid, status))
    cur.executemany(
        "INSERT INTO invoices (patient_id,invoice_date,total_amount,paid_amount,status) VALUES (?,?,?,?,?)",
        inserts
    )


def main():
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(SCHEMA_SQL)

    insert_doctors(cur)
    insert_patients(cur, 200)
    con.commit()
    insert_appointments(cur, 500)
    con.commit()
    insert_treatments(cur)
    con.commit()
    insert_invoices(cur, 300)
    con.commit()

    counts = {
        "patients":     cur.execute("SELECT COUNT(*) FROM patients").fetchone()[0],
        "doctors":      cur.execute("SELECT COUNT(*) FROM doctors").fetchone()[0],
        "appointments": cur.execute("SELECT COUNT(*) FROM appointments").fetchone()[0],
        "treatments":   cur.execute("SELECT COUNT(*) FROM treatments").fetchone()[0],
        "invoices":     cur.execute("SELECT COUNT(*) FROM invoices").fetchone()[0],
    }
    con.close()
    print(f" Database '{DB_PATH}' created successfully.")
    print(f"   Created {counts['patients']} patients, {counts['doctors']} doctors, "
          f"{counts['appointments']} appointments, {counts['treatments']} treatments, "
          f"{counts['invoices']} invoices.")


if __name__ == "__main__":
    main()
