from flask import Flask, g, jsonify
from psycopg2 import pool, DatabaseError, InterfaceError
import psycopg2

app = Flask(__name__)

# Connection Pool 설정
try:
    connection_pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        user="email_tracking_user",
        password="mNAMNdLFG4o3GuAsVYAryPPK6ImjO1ey",
        host="dpg-cu714md6l47c73c52cdg-a",
        port="5432",
        database="email_tracking"
    )
    if connection_pool:
        print("Connection pool created successfully")
except Exception as e:
    print(f"Error creating connection pool: {e}")

# Database 연결 가져오기
def get_db():
    if 'db_conn' not in g:
        try:
            g.db_conn = connection_pool.getconn()
            if g.db_conn.closed:
                raise InterfaceError("Database connection is closed.")
        except Exception as e:
            print(f"Error getting database connection: {e}")
            raise e
    return g.db_conn

# 연결 반환 및 정리
@app.teardown_appcontext
def close_db(exception):
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        try:
            connection_pool.putconn(db_conn)
        except Exception as e:
            print(f"Error returning connection to pool: {e}")

# 로그 데이터 가져오기
@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM logs")  # 실제 테이블 이름으로 변경 필요
            logs = cursor.fetchall()
            return jsonify({"logs": logs})
    except DatabaseError as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    except InterfaceError as e:
        return jsonify({"error": f"Interface error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500
        
@app.route('/logs', methods=['GET'])
def get_logs():
    # 로그 조회
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM email_logs")
        logs = cursor.fetchall()
        return {"logs": [{"id": log[0], "email": log[1], "timestamp": log[2].strftime("%Y-%m-%d %H:%M:%S")} for log in logs]}
        
# 디버깅용 기본 경로
@app.route('/')
def home():
    return "Flask 앱이 정상적으로 실행 중입니다!"
    
# Flask 실행
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
