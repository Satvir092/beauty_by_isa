from flask import Flask, render_template, request, url_for
from flask_mail import Mail, Message
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from datetime import date
import logging
import os
import psycopg2

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
app.config['DATABASE_URL'] = os.getenv('DATABASE_URL')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

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

def get_db_connection():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    return conn

def init_db():
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    date DATE NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    instagram TEXT NOT NULL
                );
            ''')
    conn.close()

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/appointments')
def appointments():
    today = date.today().isoformat()
    return render_template("appointments.html", today=today)

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
    date_val = data['date']
    email = data['email']
    phone = data['phone']
    instagram = data['instagram']
    time_preference = data['time_preference']

    app.logger.info(f"Booking verified: {name} | {date_val} | Email: {email}")

    conn = get_db_connection()
    with conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO appointments (name, date, email, phone, instagram, time_preference) VALUES (%s, %s, %s, %s, %s, %s)",
                (name, date_val, email, phone, instagram, time_preference)
            )
    conn.close()

    owner_msg = Message("New Appointment Booked",
                        sender=app.config['MAIL_USERNAME'],
                        recipients=[app.config['OWNER_EMAIL']])

    owner_msg.html = f"""
    <html>
    <body style='margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #fff8f0; color: #222;'>
        <div style='max-width: 600px; margin: 30px auto; padding: 20px; background-color: #ffffff; border-radius: 8px; border: 1px solid #f3c0cb;'>
            <h2 style='color: #b85778;'>New Appointment Confirmed</h2>
            <hr style='border: none; height: 1px; background-color: #f3c0cb;' />
            <p><strong>Name:</strong> {name}</p>
            <p><strong>Email:</strong> {email}</p>
            <p><strong>Phone #:</strong> {phone or 'N/A'}</p>
            <p><strong>Date:</strong> {date_val}</p>
            <p><strong>Instagram:</strong> {instagram}</p>
            <p><strong>Time Preference:</strong> {time_preference}</p>
            <hr style='border: none; height: 1px; background-color: #f3c0cb;' />
        </div>
    </body>
    </html>
    """
    mail.send(owner_msg)

    return render_template("confirmation.html", name=name, date=date_val)

@app.route('/book', methods=["POST"])
def book():
    name = request.form['name']
    date_val = request.form['date']
    email = request.form['email']
    phone = request.form['phone']
    instagram = request.form["instagram"]
    time_preference = request.form['time_preference']

    app.logger.info(f"Booking requested: {name} | {date_val} | Email: {email}")

    conn = get_db_connection()
    with conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM appointments WHERE email=%s AND date=%s", (email, date_val))
            already_booked = cursor.fetchone()
            if already_booked:
                return render_template("error.html", message="You already have an appointment booked for that day. Only one appointment is allowed per day.")

            cursor.execute("SELECT COUNT(*) FROM appointments WHERE date=%s", (date_val,))
            count = cursor.fetchone()[0]
            if count >= 3:
                return render_template("error.html", message="Sorry, the maximum number of appointments for this day has been reached. Please choose another day.")

    conn.close()

    data = {'name': name, 'date': date_val, 'email': email, 'phone': phone, 'instagram': instagram, 'time_preference': time_preference}
    token = generate_token(data)
    verify_url = url_for('verify_email', token=token, _external=True)

    msg = Message("Verify Your Appointment Email",
                  sender=app.config['MAIL_USERNAME'],
                  recipients=[email])

    msg.html = f"""
    <html>
    <body style='margin:0; padding:20px; font-family: Arial, sans-serif; background-color: #fff8f0; color: #222;'>
        <div style='max-width: 600px; margin: auto; background-color: #ffffff; border: 1px solid #f3c0cb; border-radius: 8px; padding: 20px;'>
            <h2 style='color: #b85778;'>Verify Your Appointment</h2>
            <hr style='border: none; height: 1px; background-color: #f3c0cb;' />
            <p>Please verify your appointment details:</p>
            <p><strong>Date:</strong> {date_val}</p>
            <p>Click the link below to confirm your appointment:</p>
            <p><a href='{verify_url}' style='color: #b85778; word-break: break-word;'>{verify_url}</a></p>
            <hr style='border: none; height: 1px; background-color: #f3c0cb;' />
            <p style='font-size: 14px; color: #666;'>Thank you!</p>
        </div>
    </body>
    </html>
    """

    mail.send(msg)

    return render_template("check_email.html", email=email)

#if __name__ == "__main__":
    # Make sure DB is initialized when starting app
    #init_db()
    #app.run(debug=False)