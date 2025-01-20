from flask import Flask, request, jsonify
import psycopg2
import logging

app = Flask(__name__)

# PostgreSQL 연결 정보
DB_CONFIG = {
    'host': 'postgresql://email_tracking_user:mNAMNdLFG4o3GuAsVYAryPPK6ImjO1ey@dpg-cu714md6l47c73c52cdg-a/email_tracking',        # PostgreSQL 호스트 주소
    'port': '5432',             # 일반적으로 5432
    'database': 'email_tracking', # 데이터베이스 이름
    'user': 'email_tracking_user',    # 사용자 이름
    'password': 'mNAMNdLFG4o3GuAsVYAryPPK6ImjO1ey' # 비밀번호
}

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)

# 데이터베이스 연결 함수
def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logging.info("Database connection established successfully.")
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        raise

# /logs 엔드포인트
@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # SQL 쿼리 실행
        query = "SELECT id, email, opened_at FROM email_logs LIMIT 100;"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # 결과를 JSON 형태로 변환
        columns = [desc[0] for desc in cursor.description]
        data = [dict(zip(columns, row)) for row in rows]
        
        return jsonify(data)
    
    except psycopg2.Error as e:
        logging.error(f"SQL Error: {e}")
        return jsonify({'error': 'Database query failed', 'details': str(e)}), 500
    
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# /pixel 엔드포인트
@app.route('/pixel', methods=['GET'])
def pixel():
    try:
        email = request.args.get('email')
        if not email:
            return jsonify({'error': 'Email parameter is missing'}), 400
        
        # 추가 로직 (예: DB에 기록)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # DB에 email 기록 (예제)
        query = "INSERT INTO email_logs (email, opened_at) VALUES (%s, NOW());"
        cursor.execute(query, (email,))
        conn.commit()
        
        return "Pixel logged successfully", 200
    
    except psycopg2.Error as e:
        logging.error(f"Database error during pixel logging: {e}")
        return jsonify({'error': 'Database operation failed', 'details': str(e)}), 500
    
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# 기본 라우트 (테스트용)
@app.route('/')
def index():
    return "Server is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
