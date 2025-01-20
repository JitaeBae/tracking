from flask import Flask, request, send_file, jsonify
from io import BytesIO
from PIL import Image
import os
import datetime

app = Flask(__name__)

# 트래킹된 이메일 기록을 저장할 디렉토리
LOG_DIR = "email_logs"
os.makedirs(LOG_DIR, exist_ok=True)

# 이메일 열기 트래킹 정보 기록 함수
def log_email(email):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_filename = os.path.join(LOG_DIR, "email_tracking_log.txt")
    
    with open(log_filename, "a") as log_file:
        log_file.write(f"{timestamp} - {email} opened\n")

# 이메일 열림을 트래킹하는 픽셀 이미지 반환
@app.route('/pixel')
def pixel():
    email = request.args.get('email')  # 이메일 주소를 URL 파라미터로 받음
    if email:
        log_email(email)
    
    # 1x1 픽셀 이미지를 생성
    img = Image.new('RGB', (1, 1), color=(255, 255, 255))  # 흰색 픽셀
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    # 이미지 반환
    return send_file(img_byte_arr, mimetype='image/png')

@app.route('/logs', methods=['GET'])
def get_logs():
    # 이메일 트래킹 로그를 반환
    log_filename = os.path.join(LOG_DIR, "email_tracking_log.txt")
    
    if os.path.exists(log_filename):
        with open(log_filename, 'r') as file:
            logs = file.readlines()
        return jsonify(logs), 200
    else:
        return jsonify({"message": "No logs found"}), 404

if __name__ == '__main__':
    app.run(debug=True)
