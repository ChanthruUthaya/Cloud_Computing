from flask import Flask, render_template, request, jsonify
import redis

app = Flask(__name__)

host = "redis-service.default.svc"

name = "work_q"

q = redis.Redis(host="redis-service.default.svc", port=6379, db=0)

@app.route("/")
def main():
    return "Producer"

@app.route("/produce", methods=["POST"])
def produce():
    batch_size = request.json["batch_size"]
    pwd = request.json["pwd"]
    length = request.json["length"]
    batches = request.json["batches"]

    print(batch_size, length, batches, pwd, flush=True)

    for i in range(batches):
        pushstr = f"{i}:{batch_size}:{length}:{pwd}"
        q.lpush("work_q",pushstr)
    
    return jsonify({"message":"done"})




if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, port=5000)
