import redis
import redisWQ
import time
import datetime
import boto3
import pickle
from md5 import worker_function
import requests
import itertools
import string
import os

host = "redis-service.default.svc"
name = "work_q"


ACCESS_KEY = os.environ['aws_access_key_id']
SECRET_KEY = os.environ['aws_secret_access']
SESSION_TOKEN = os.environ['aws_session_token']
S3_BUCK = os.environ['s3_Buck_Name']

s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, aws_session_token=SESSION_TOKEN )

running = True

q = redisWQ.RedisWQ(name=name,role="worker",host=host)
conn = redis.Redis(host="redis-service.default.svc", port=6379, db=0)

print("Worker with sessionID: " +  q.sessionID())
print("Initial queue state: empty=" + str(q.empty()))
while(running):
  while not q.empty():
    item =  q.lease(lease_secs=10, block=False)
    print(f'item is {item} {type(item)}',flush=True)
    if item is not None:
      itemstr = item.decode("utf-8")
      print("Working on " + itemstr, flush=True)
      items = itemstr.split(":")
      index, workload, length = int(items[0]), int(items[1]), int(items[2])
      pwd = items[3]
      alpha = list(string.ascii_lowercase)
      outcomes = itertools.islice(itertools.product(alpha, repeat=length),
                                                    index*workload,
                                                    (index+1)*workload, 1)

      for comb in outcomes:
        comb = ''.join(comb)
        result = worker_function(comb.encode('utf-8'), pwd)
        if(result):
            end = time.time()
            resp = requests.post("http://timer-service.default.svc:81/stop", json={"Time":end})
            pwd = pickle.dumps([comb])
            s3.put_object(Bucket=S3_BUCK, Key='pwd',Body=pwd)
            print(f'Worker is returning: {comb}', flush=True)
        #stop queue work
      print("completed work", flush = True)
      q.complete(item)
    else:
      print("Waiting for work", flush=True)
print("Queue empty, exiting")
