import pickle
import boto3
import datetime
import sys

s3 = boto3.client('s3')


name = sys.argv[1]

print(datetime.datetime.utcnow())
obj = s3.get_object(Bucket=name, Key='pwd')
pwd = obj['Body'].read()
pwd = pickle.loads(pwd)
print(pwd)

