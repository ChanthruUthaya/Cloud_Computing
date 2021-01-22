from flask import Flask, render_template, request, jsonify
import redis
import time

app = Flask(__name__)

conn = redis.Redis(host="redis-service.default.svc", port=6379, db=0)

@app.route("/")
def main():
    print("Timer started", flush=True)
    return "Timer Started"

@app.route("/start", methods=["POST"])
def start_timer():
    start = time.time()
    conn.rpush("time", start)
    print("pushed here", flush = True)
    return "Timer started"

@app.route("/stop", methods=["POST"])
def stop_timer():
    print("timer stopped", flush = True)
    start = float(conn.rpop("time"))
    end = request.json["Time"]
    conn.flushdb()
    print(f'total is {end-start}', flush=True)
    return jsonify(resp="recieved")
    
if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, port=5000)
