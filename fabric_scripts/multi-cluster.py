import fabric
from fabric import Connection
import subprocess
import yaml
import os
import boto3
import time
import re
import math
import statistics

num_masters = 2

def create_instances(ip_map):
    print("Scaling Host")
    new_instance = ec2.create_instances(
        ImageId='ami-0453c8a132a1f92d3',
        MinCount=1,
        MaxCount=1,
        InstanceType='m5.2xlarge',
        KeyName="test_keynovts",
        SecurityGroupIds=[config['sg_group']]
    )
    time.sleep(10)
    for i in new_instance:
        i.reload()
        ip_map[str(i.private_ip_address)] = i.id
        ip = i.public_ip_address.replace(".","-")
        c = Connection(host=f'ubuntu@ec2-{ip}.compute-1.amazonaws.com', connect_kwargs={'key_filename': config['ssh_path']})
        time.sleep(20)
        token_file = open("fabric_scripts/token.sh", "r")
        command = token_file.readlines()[0].rstrip()
        c.run(f'sudo {command}')
    # os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} fabric_scripts/token.sh ubuntu@ec2-{ip}.compute-1.amazonaws.com:~/")
    # c.run("sudo chmod 400 token.sh")
    # c.run("sudo ./token.sh")
    return ip_map

def scale_and_terminate(master_ip):
    name_spaces = open("status/podstatus.txt", "r")
    name_spaces_lines = name_spaces.readlines()

    name_regex = list(re.finditer(r'NAME', name_spaces_lines[0]))
    i1 = name_regex[0].start()
    i2 = name_regex[1].start()
    i3 = name_spaces_lines[0].index("READY")
    i4 = name_spaces_lines[0].index("STATUS")
    i5 = name_spaces_lines[0].index("RESTARTS")
    pending = 0

    pod_namespace = {}

    for line in name_spaces_lines[1:]:
        namespace = line[i1:i2].strip()
        name = line[i2:i3].strip()
        status = line[i4:i5].strip()
        if(status == "Pending"):
            pending += 1
        pod_namespace[name] = namespace
    
    status = open("status/cpumetrics.txt", "r") #metrics of nodes
    lines = status.readlines()

    #indexes into table
    index1 = lines[0].index("NAME")
    index2 = lines[0].index("CPU(cores)")
    index3 = lines[0].index("CPU%")
    index4 = lines[0].index("MEMORY(bytes)")
    index5 = lines[0].index("MEMORY%")

    def insert(nodes, value):
        if(len(nodes)==0):
            return [value]
        for i in range(len(nodes)):
            if(value[0] <= nodes[i][0]):
                nodes.insert(i, value)
                return nodes
            if(i == len(nodes) -1):
                nodes.append(value)
        return nodes


    down_nodes = [] #nodes that are down due to unexpected reasons
    terminate_metrics = [] #sorted list of node metrics eligible for termination
    cpu_usage = []
    
    for line in lines[1:]:
        ip = line[index1:index2].strip() #ip address of node
        cores = line[index2:index3].strip() #cpu core work
        if(cores == '<unknown>'): #check if node is down
            down_nodes.append(ip)
            continue
        else:
            cpu = line[index3:index4].strip()[:-1] #cpu work score
            if(int(cpu) < 30): #check if node should be deleted
                terminate_metrics = insert(terminate_metrics, (int(cpu), ip)) #add to sorted array
            cpu_usage.append(int(cpu))
    
    avg_cpu = statistics.mean(cpu_usage)
    
    if(len(terminate_metrics)>= 2): 
        scale_down_node = terminate_metrics[0][1] 
        print("scale down node ", scale_down_node)

    print("down nodes ", down_nodes)

    pods = open("status/podloc.txt", "r") #location of pods on nodes
    podline = pods.readlines()

    #indexes into table
    index1 = podline[0].index("NAME")
    index2 = podline[0].index("STATUS")
    index3 = podline[0].index("NODE")

    pods_on_down = [] # pods on down nodes

    pods_on_term_nodes = {}

    for val in terminate_metrics:
        if(val[1] not in master_ip): #make sure not the master IP
            pods_on_term_nodes[val[1]] = [] #dictionary of all pods in ndes eligible for termination

    counter = 0
    for line in podline[1:]:
        name = line[index1:index2].strip()
        podstat = line[index2:index3].strip()
        node = line[index3:].strip()
        if(node != "<none>"): #!<none> ensures skip pending nodes
            counter += 1
            if(node in pods_on_term_nodes.keys()):
                print(name)
                pods_on_term_nodes[node].append(name) ##make sure redis pod is not evicted 
            elif(node in down_nodes):
                pods_on_down.append((name,pod_namespace[name])) ##if there exists a pod on a down node it is guaranteed to be a fail node and not a new node

    print(counter)
    print("pods on term nodes", pods_on_term_nodes)
    print("pods on down nodes", pods_on_down)

    terminate = False
    pods_to_term = None
    ip = None

    if(len(pods_on_term_nodes.keys()) >= 2): #check if there are any nodes to terminate
        index = 0 #firsr node with lowest cpu score
        term_nodes = list(pods_on_term_nodes.keys()) #all nodes eligible for termination
        while(not terminate and index < len(pods_on_term_nodes.keys())): 
            terminate = True #assume can be terminated
            term_node = term_nodes[index] #current node under question
            for pods in pods_on_term_nodes[term_node]: #go through all the pods that are on that node
                if re.search(r'redis', pods) or  re.search(r'producer', pods): #check if any are the redis store or the metrics server
                    terminate = False #dont terminate the node
            index += 1 #check the next node
        if(index < len(term_nodes)+1): #if found a node eligible for termination
            pods_to_term = zip(pods_on_term_nodes[term_nodes[index-1]], [pod_namespace[pod] for pod in pods_on_term_nodes[term_nodes[index-1]]]) #set the node for termination else it will be None
            ip = term_nodes[index-1]

                
    return pending,avg_cpu,[terminate,ip,pods_to_term], pods_on_down




run = True

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

# get security group
# security_group = ec2.describe_security_groups(GroupIds=config['sg_group'])

# create instances
instances = ec2.create_instances(
    ImageId='ami-0453c8a132a1f92d3',
    MinCount=1,
    MaxCount=3+num_masters,
    InstanceType='m5.large',
    KeyName="test_keynovts",
    SecurityGroupIds=[config['sg_group']]
)

load_balancers = ec2.create_instances(
    ImageId='ami-0e7c06fe8c6283d03',
    MinCount=1,
    MaxCount=1,
    InstanceType='m5.large',
    KeyName="test_keynovts",
    SecurityGroupIds=[config['sg_group']]
)


print("Created instances")
print(instances)

# ip_addresses = {}

# wait for ip addresses to initialise
time.sleep(10)

for i in instances+ load_balancers:
    # i.wait_until_running()
    i.reload()
#     while i.public_ip_address is None or i.private_ip_address is None:
#         i.reload()
#     print(i.public_ip_address)
#     print(i.private_ip_address)
#
#     ip_addresses[str(i.public_ip_address)] = str(i.private_ip_address)

ip_addresses = {str(i.public_ip_address) : str(i.private_ip_address) for i in load_balancers+ instances}
ip_address_map = {}
for i in load_balancers +instances:
    ip_address_map[str(i.private_ip_address)] = i.id

print(ip_addresses)
print(ip_address_map)

config['hosts'] = ip_addresses

with open('fabric_scripts/config.yaml', 'w') as f:
    data = yaml.dump(config, f, default_flow_style=False)

print("Added IP addresses to config.yaml")

# ec2.instances.terminate()

# Getting the host IPs
hosts = [(k, v) for k, v in config['hosts'].items()]

load_balancer = hosts[0]
master = hosts[1:1+num_masters]
workers = hosts[1+num_masters:]
initial_master = master[0]
private_master = [m[1] for m in master]

# Connecting to hosts
for i in range(len(hosts)):
    current = hosts[i]
    public_ip = current[0]

    # Replacing dots with dashes
    public_ip = public_ip.replace(".", "-")

    # Establishing connection
    c = Connection(host=f'ubuntu@ec2-{public_ip}.compute-1.amazonaws.com', connect_kwargs={'key_filename': config['ssh_path']})
    print(c.is_connected)
    time.sleep(20)
    print("Successfully connected...")

    if current == load_balancer:
        str1 = f"bind {current[1]}:6443"
        str2 = "mode tcp "
        str3 = "option tcplog "
        str4 = "default_backend kubernetes-backend "
        str5 = "option tcp-check "
        str6 = "balance roundrobin "
        c.sudo("su - root -c'echo '' >> ../etc/haproxy/haproxy.cfg'")
        c.sudo("su - root -c'echo frontend kubernetes-frontend >> ../etc/haproxy/haproxy.cfg'")
        c.sudo(f"su - root -c'echo {str1} >> ../etc/haproxy/haproxy.cfg'")
        c.sudo(f"su - root -c'echo {str2} >> ../etc/haproxy/haproxy.cfg'")
        c.sudo(f"su - root -c'echo {str3} >> ../etc/haproxy/haproxy.cfg'")
        c.sudo(f"su - root -c'echo {str4} >> ../etc/haproxy/haproxy.cfg'")
        c.sudo("su - root -c'echo '' >> ../etc/haproxy/haproxy.cfg'")
        c.sudo("su - root -c'echo backend kubernetes-backend >> ../etc/haproxy/haproxy.cfg'")
        c.sudo(f"su - root -c'echo {str2} >> ../etc/haproxy/haproxy.cfg'")
        c.sudo(f"su - root -c'echo {str5} >> ../etc/haproxy/haproxy.cfg'")
        c.sudo(f"su - root -c'echo {str6} >> ../etc/haproxy/haproxy.cfg'")
        counter = 1
        for host in master:
            dns = "ip-"+str(host[1]).replace(".","-")+".ec2.internal"
            mas_str = f" server {dns} {host[1]}:6443 check fall 3 rise 2"
            counter += 1 
            c.sudo(f"su - root -c'echo {mas_str} >> ../etc/haproxy/haproxy.cfg'")
        c.sudo("systemctl restart haproxy")

    # ec2.instances.terminate()
    elif current == initial_master:
        print(f'master ip {public_ip}')
        c.sudo(f"kubeadm init --control-plane-endpoint='{load_balancer[1]}:6443' --upload-certs --apiserver-advertise-address={current[1]} --pod-network-cidr=192.168.0.0/16 > ctr.txt")
        c.run("mkdir -p $HOME/.kube")
        c.run("sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config")
        c.run("sudo chown $(id -u):$(id -g) $HOME/.kube/config")
        c.run("sudo kubectl --kubeconfig=/etc/kubernetes/admin.conf create -f https://docs.projectcalico.org/v3.14/manifests/calico.yaml")
        c.run("kubeadm token create --print-join-command 2> /dev/null > token.sh")
        os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} ubuntu@ec2-{public_ip}.compute-1.amazonaws.com:~/token.sh ./fabric_scripts")
        os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} ubuntu@ec2-{public_ip}.compute-1.amazonaws.com:~/ctr.txt ./fabric_scripts")
        tokenfile = open('fabric_scripts/ctr.txt', 'r')
        lines = tokenfile.readlines()
        master_token = lines[67:70]
        for i in range(len(master_token)):
            if(i==0 or i==1):
                master_token[i] = master_token[i][:-3]
            else:
                master_token[i] = master_token[i][:-1].rstrip()

        command = ''.join(master_token)
        f = open("fabric_scripts/mastertoken.sh", "w")
        f.write(command)
        f.close() 
        # files = [v for k, v in config['file'].items()]
        # os.system(f"scp -i {config['ssh_path']} {' '.join(files)} ubuntu@ec2-{public_ip}.compute-1.amazonaws.com:~/")

        for k,v in config['folder'].items():
            os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} -r {v} ubuntu@ec2-{public_ip}.compute-1.amazonaws.com:~/")
        
        # with c.cd("local_version"):
        #     c.run("sudo docker build -t worker .")
    
    elif current in master:
        c.run("mkdir -p $HOME/.kube")
        c.run("sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config")
        c.run("sudo chown $(id -u):$(id -g) $HOME/.kube/config")
        tokenfile = open('fabric_scripts/mastertoken.sh', 'r')
        command = tokenfile.readlines()[0]
        c.sudo(command)


    elif current in workers:
        print(f'worker ip {public_ip}')
        token_file = open("fabric_scripts/token.sh", "r")
        command = token_file.readlines()[0].rstrip()
        c.run(f'sudo {command}')
        # for k,v in config['folder'].items():
        #     os.system(f"scp -i {config['ssh_path']} -r {v} ubuntu@ec2-{public_ip}.compute-1.amazonaws.com:~/")
        # with c.cd("local_version"):
        #     c.run("sudo docker build -t worker .")#
    

masterip = initial_master[0].replace('.','-')

master_c = Connection(host=f'ubuntu@ec2-{masterip}.compute-1.amazonaws.com', connect_kwargs={'key_filename': config['ssh_path']})

time.sleep(20)

for node in master:
    node_str ="ip-"+str(node[1]).replace(".","-")
    master_c.run(f"kubectl taint node {node_str} node-role.kubernetes.io/master-")

master_c.run("kubectl apply -f yaml")
master_c.run("kubectl autoscale deployment worker-deployment --cpu-percent=80 --min=25 --max=80")

print(f"Master available at {master[0]}")

print("Monitoring setting up, availabe in 2 minutes")

time.sleep(120)

master_c.run("mkdir status")


print("Stepping into Monitoring mode")
        # 
counter = 0
prev = None
scale_up = False
scale_down = False
while(run):
    print("Checking....")
    master_c.run("kubectl get pods --all-namespaces > status/podstatus.txt") #list of pods on node #list of nodes and status, list of CPU usage
    master_c.run("kubectl get pod --all-namespaces -o=custom-columns=NAME:.metadata.name,STATUS:.status.phase,NODE:.spec.nodeName > status/podloc.txt")
    master_c.run("kubectl top nodes > status/cpumetrics.txt")
    os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} -r ubuntu@ec2-{masterip}.compute-1.amazonaws.com:~/status/ .") 
    pending, avg_cpu ,scale_down_data, evict_pods = scale_and_terminate(str(master[1]))
    print("scale down data",scale_down_data)
    if(len(evict_pods) > 0 and counter > 1): #evict pods on down nodes
        for pod, namespace in evict_pods:
            print(f'pod is {pod} part of {namespace}')
            master_c.run(f"kubectl delete pod {pod} --namespace={namespace} --grace-period=0 --force")
            ip_address_map = create_instances(ip_address_map)
    # elif(avg_cpu > 80 and pending and counter > 1): #scale up
    #     ip_address_map = create_instances(ip_address_map)
    # elif(scale_down_data[0] and counter > 1): 
    #     for pod, namespace in scale_down_data[2]:
    #         master_c.run(f"kubectl delete pod {pod} --namespace={namespace} --grace-period=0 --force")
    #         ec2.instances.filter(InstanceIds = [ip_address_map[scale_down_data[1][3:].replace("-",".")]]).terminate()
        

    else:
        print("Adequate amount of hosts")
    time.sleep(60)
    counter += 1
    print("finished check, sleeping.... ")

print("Set up finished, exiting.")

