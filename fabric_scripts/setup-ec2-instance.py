import fabric
from fabric import Connection
import subprocess
import yaml
import os
import boto3
import time

running = True

ec2 = boto3.resource('ec2')

# loading the config file
with open('fabric_scripts/config.yaml') as f:
    config = yaml.load(f)

# create a file to store the key locally
if config['ssh_path'] == None:
    outfile = open("fabric_scripts/TestKey.pem",'w')

    # call the boto ec2 function to create a key pair
    key_pair = ec2.create_key_pair(KeyName='TestKey')

    # capture the key and store it in a file
    KeyPairOut = str(key_pair.key_material)
    outfile.write(KeyPairOut)
    os.system("chmod 400 fabric_scripts/TestKey.pem")
    config['ssh_path'] = "fabric_scripts/TestKey.pem"

    print("Created TestKey")

# create instances
instances = ec2.create_instances(
     ImageId='ami-04d29b6f966df1537',
     MinCount=1,
     MaxCount=1,
     InstanceType='m5.large',
     KeyName="test_keynovts",
     SecurityGroupIds=[config['sg_group']]
)

print("Created instances")
print(instances)

# wait for ip addresses to initialise
time.sleep(10)

for i in instances:
    i.reload()

ip_addresses = {str(i.public_ip_address) : str(i.private_ip_address) for i in instances}

print(ip_addresses)

config['hosts'] = ip_addresses

with open('fabric_scripts/config.yaml', 'w') as f:
    data = yaml.dump(config, f, default_flow_style=False)

print("Added IP addresses to config.yaml")

# ec2.instances.terminate()

# Getting the host IPs
hosts = [(k, v) for k, v in config['hosts'].items()]

master = hosts[0]

# Connecting to hosts
for i in range(len(hosts)):
    current = hosts[i]
    public_ip = current[0]

    # Replacing dots with dashes
    public_ip = public_ip.replace(".", "-")

    # Establishing connection
    c = Connection(host=f'ec2-user@ec2-{public_ip}.compute-1.amazonaws.com', connect_kwargs={'key_filename': config['ssh_path']})
    print(c.is_connected)
    time.sleep(20)
    print("Successfully connected...")

    # ec2.instances.terminate()

    # Docker and Kubernetes set up
    c.run("sudo yum update")
    c.run("sudo yum install -y docker")
    c.run("sudo systemctl start docker")
    c.run("sudo systemctl enable docker")
    c.run("sudo usermod -aG docker ec2-user")
    c.run("sudo yum install -y conntrack")
    c.run("sudo curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https:/storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl")
    c.run("sudo chmod +x ./kubectl")
    c.run("sudo mv ./kubectl /usr/bin/kubectl")
    c.run("sudo curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64")
    c.run("sudo install minikube-linux-amd64 /usr/bin/minikube")
    c.run("sudo minikube start --driver=none")
    c.run("mkdir -p $HOME/.kube")
    c.run("sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config")
    c.run("sudo chown $(id -u):$(id -g) $HOME/.kube/config")

    if (hosts[i] == master):
        files = [v for k, v in config['file'].items()]
        for k,v in config['folder'].items():
            os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} -r {v} ec2-user@ec2-{public_ip}.compute-1.amazonaws.com:~/")

    print("Set up finished, exiting.")
