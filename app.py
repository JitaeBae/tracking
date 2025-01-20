from flask import Flask, g, request, jsonify, send_file
from psycopg2 import pool
import os
from io import BytesIO
import logging

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL 환경 변수가 설정되지 않았습니다.")

try:
    connection_pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=f"{DATABASE_URL}?sslmode=require"
    )
    print("Connection pool created successfully!")
except Exception as e:
    print(f"Error creating connection pool: {e}")
    raise e

def get_db():
    if 'db_conn' not in g or g.db_conn.closed:
        g.db_conn = connection_pool.getconn()
    return g.db_conn

@app.teardown_appcontext
def close_db(exception):
    db_conn = g.pop('db_conn', None)
    if db_conn:
        connection_pool.putconn(db_conn)

def initialize_table():
    try:
        conn = connection_pool.getconn()
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_logs (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    opened_at TIMESTAMP
                );
            """)
            conn.commit()
        print("Table initialized successfully!")
    except Exception as e:
        print(f"Error initializing table: {e}")
        raise e
    finally:
        if conn:
            connection_pool.putconn(conn)

@app.route('/track_email', methods=['GET'])
def track_email():
    email_id = request.args.get('id')
    if not email_id or not email_id.isdigit():
        return "Invalid or missing ID", 400

    try:
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE email_logs SET opened_at = NOW() WHERE id = %s",
                (email_id,)
            )
            conn.commit()

        pixel = BytesIO()
        pixel.write(
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00'
            b'\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
        )
        pixel.seek(0)
        return send_file(pixel, mimetype='image/gif')
    except Exception as e:
        logging.error(f"Error tracking email: {e}")
        return "Internal Server Error", 500

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, email, opened_at FROM email_logs")
            logs = cursor.fetchall()
            return jsonify({
                "logs": [
                    {
                        "id": log[0],
                        "email": log[1],
                        "opened_at": log[2].strftime("%Y-%m-%d %H:%M:%S") if log[2] else None
                    }
                    for log in logs
                ]
            })
    except Exception as e:
        logging.error(f"Error fetching logs: {e}")
        return jsonify({"error": f"Unexpected error: {e}"}), 500

@app.route('/')
def home():
    return "Render 환경에서 실행 중입니다!"

if __name__ == "__main__":
    initialize_table()
    app.run(host='0.0.0.0', port=5000)
