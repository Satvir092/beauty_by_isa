from flask import Flask, render_template, request, url_for
from flask_mail import Mail, Message
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime, date
import logging
import os
import sqlite3

logging.basicConfig(
level=logging.INFO,
format='%(asctime)s [%(levelname)s] %(message)s',
handlers=[
    logging.FileHandler("app.log"),
    logging.StreamHandler()  
]
)

app = Flask(__name__)

load_dotenv()

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['OWNER_EMAIL'] = os.getenv('OWNER_EMAIL')

mail = Mail(app)

s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

def generate_token(data):

    return s.dumps(data, salt='email-confirm-salt')

def confirm_token(token, expiration=3600):
    try:
        data = s.loads(token, salt='email-confirm-salt', max_age=expiration)
    except Exception:
        return False
    return data

# Setup database
def init_db():
    with sqlite3.connect("appointments.db", timeout = 5) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT
            )
        ''')

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/appointments')
def appointments():
    today = date.today().isoformat()
    return render_template("appointments.html", today = today)

@app.route('/aboutus')
def aboutus():
    return render_template("aboutus.html")

@app.errorhandler(404)
def not_found(e):
    app.logger.error(f"Internal Server Error: {e}") 
    return render_template("error.html", message="Page not found."), 404

@app.errorhandler(500)
def internal_error(e):
    app.logger.error(f"Internal Server Error: {e}") 
    return render_template("error.html", message="Something went wrong. Try again."), 500

@app.route('/verify/<token>')
def verify_email(token):
    
    data = confirm_token(token)

    if not data:
        return render_template("error.html", message="Verification link is invalid or expired.")

    name = data['name']
    date = data['date']
    time = data['time']
    email = data['email']
    phone = data.get('phone')

    app.logger.info(f"Booking requested: {name} | {date} at {time} | Email: {email}")

    with sqlite3.connect("appointments.db", timeout = 5) as conn:
        
        cursor = conn.cursor()

        cursor.execute("INSERT INTO appointments (name, date, time, email, phone) VALUES (?, ?, ?, ?, ?)",
                       (name, date, time, email, phone))
        conn.commit()

        owner_msg = Message("New Appointment Booked",
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[app.config['OWNER_EMAIL']])  
        
        formatted_time = datetime.strptime(time, "%H:%M").strftime("%I:%M %p")

        owner_msg.html = f"""
        <html>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #fff8f0; color: #222;">
            <div style="max-width: 600px; margin: 30px auto; padding: 20px; background-color: #ffffff; border-radius: 8px; border: 1px solid #f3c0cb;">
            <h2 style="color: #b85778;">New Appointment Confirmed</h2>
            <hr style="border: none; height: 1px; background-color: #f3c0cb;" />
            <p style="font-size: 16px; margin: 12px 0;"><strong>Name:</strong> {name}</p>
            <p style="font-size: 16px; margin: 12px 0;"><strong>Email:</strong> {email}</p>
            <p style="font-size: 16px; margin: 12px 0;"><strong>Phone #:</strong> {phone or 'N/A'}</p>
            <p style="font-size: 16px; margin: 12px 0;"><strong>Date:</strong> {date}</p>
            <p style="font-size: 16px; margin: 12px 0;"><strong>Time:</strong> {formatted_time}</p>
            <hr style="border: none; height: 1px; background-color: #f3c0cb;" />
            </div>
        </body>
        </html>
        """
        mail.send(owner_msg)

    return render_template("confirmation.html", name=name, date=date, time=formatted_time)

@app.route('/book', methods=["POST"])
def book():
    
    name = request.form['name']
    date = request.form['date']
    time = request.form['time']
    email = request.form['email']
    phone = request.form.get('phone')

    app.logger.info(f"Booking requested: {name} | {date} at {time} | Email: {email}")

    with sqlite3.connect("appointments.db", timeout = 5) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM appointments WHERE date=? AND time=?", (date, time))
        existing = cursor.fetchone()

        if existing:
            return render_template("error.html", message= "Sorry, that time slot was already booked by someone else. Please select another time.")
        
        cursor.execute("SELECT * FROM appointments WHERE email=? AND date=?", (email, date))
        already_booked = cursor.fetchone()
        
        if already_booked:
            return render_template(
                "error.html",
                message="You already have an appointment booked for that day. Only one appointment is allowed per day."
            )

    data = {'name': name, 'date': date, 'time': time, 'email': email, 'phone': phone}

    token = generate_token(data)

    verify_url = url_for('verify_email', token=token, _external=True)

    msg = Message("Verify Your Appointment Email",
                  sender=app.config['MAIL_USERNAME'],
                  recipients=[email])
    
    formatted_time = datetime.strptime(time, "%H:%M").strftime("%I:%M %p")

    msg.html = f"""
    <html>
    <body style="margin:0; padding:20px; font-family: Arial, sans-serif; background-color: #fff8f0; color: #222;">
        <div style="max-width: 600px; margin: auto; background-color: #ffffff; border: 1px solid #f3c0cb; border-radius: 8px; padding: 20px;">
        <h2 style="color: #b85778; margin-top: 0;">Verify Your Appointment</h2>
        <hr style="border: none; height: 1px; background-color: #f3c0cb;" />
        <p style="font-size: 16px;">Please verify your appointment details:</p>
        <p style="font-size: 16px;"><strong>Date:</strong> {date}</p>
        <p style="font-size: 16px;"><strong>Time:</strong> {formatted_time}</p>
        <p style="font-size: 16px;">Click the link below to confirm your appointment:</p>
        <p><a href="{verify_url}" style="color: #b85778; word-break: break-word;">{verify_url}</a></p>
        <hr style="border: none; height: 1px; background-color: #f3c0cb;" />
        <p style="font-size: 14px; color: #666;">Thank you!</p>
        </div>
    </body>
    </html>
    """

    mail.send(msg)

    return render_template("check_email.html", email=email)

#if __name__ == "__main__":
    #app.run(debug=False)
