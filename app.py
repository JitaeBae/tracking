import psycopg2
from flask import Flask, request, send_file
from datetime import datetime

app = Flask(__name__)

# Render PostgreSQL 연결
DATABASE_URL = "postgresql://email_tracking_user:mNAMNdLFG4o3GuAsVYAryPPK6ImjO1ey@dpg-cu714md6l47c73c52cdg-a/email_tracking"
conn = psycopg2.connect(DATABASE_URL, sslmode='require')

# 데이터베이스 테이블 생성
with conn.cursor() as cursor:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_logs (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

@app.route('/pixel', methods=['GET'])
def pixel():
    email = request.args.get('email')
    if not email:
        return "이메일 주소가 없습니다!", 400

    # 로그 저장
    with conn.cursor() as cursor:
        cursor.execute("INSERT INTO email_logs (email) VALUES (%s)", (email,))
        conn.commit()

    print(f"{datetime.now()} - {email} - 이메일 열림 확인")
    return send_file('transparent.png', mimetype='image/png')

@app.route('/logs', methods=['GET'])
def get_logs():
    # 로그 조회
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM email_logs")
        logs = cursor.fetchall()
        return {"logs": [{"id": log[0], "email": log[1], "timestamp": log[2].strftime("%Y-%m-%d %H:%M:%S")} for log in logs]}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
