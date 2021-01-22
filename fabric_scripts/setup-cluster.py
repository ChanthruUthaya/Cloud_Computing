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

# loading the config file
with open('fabric_scripts/config.yaml') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

def create_instances(ip_map):
    print("Scaling Host")
    new_instance = ec2.create_instances(
        ImageId='ami-0453c8a132a1f92d3',
        MinCount=1,
        MaxCount=1,
        InstanceType='m5.large',
        KeyName=config["ssh_key_name"],
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
    return ip_map

def scale_up():
    pending = 0
    running = 0
    status = open("status/podstatus.txt", "r")
    lines = status.readlines()
    for line in lines:
        line_strip = line[9:].strip()
        if line_strip == "Pending":
            pending += 1
        if line_strip == "Running":
            running += 1
    return pending


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

    with open("status/avg_cpu_t.txt", "a") as fs:
        for line in lines:
            fs.write(line)


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
    count = 0

    for line in lines[1:]:
        ip = line[index1:index2].strip() #ip address of node
        cores = line[index2:index3].strip() #cpu core work
        if(cores == '<unknown>'): #check if node is down
            down_nodes.append(ip)
            continue
        else:
            count += 1
            cpu = line[index3:index4].strip()[:-1] #cpu work score
            if(int(cpu) < 50 and ip != master_ip): #check if node should be deleted
                terminate_metrics = insert(terminate_metrics, (int(cpu), ip)) #add to sorted array
            if(ip != master_ip):
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
        if(val[1] != master_ip): #make sure not the master IP
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
                if re.search(r'redis', pods) or  re.search(r'metrics', pods): #check if any are the redis store or the metrics server
                    terminate = False #dont terminate the node
            index += 1 #check the next node
        if(index < len(term_nodes)+1): #if found a node eligible for termination
            pods_to_term = zip(pods_on_term_nodes[term_nodes[index-1]], [pod_namespace[pod] for pod in pods_on_term_nodes[term_nodes[index-1]]]) #set the node for termination else it will be None
            ip = term_nodes[index-1]


    return count, pending,avg_cpu,[terminate,ip,pods_to_term], pods_on_down


run = True

ec2 = boto3.resource('ec2')

# create instances
instances = ec2.create_instances(
    ImageId='ami-0453c8a132a1f92d3',
    MinCount=4,
    MaxCount=4,
    InstanceType='m5.large',
    KeyName=config["ssh_key_name"],
    SecurityGroupIds=[config['sg_group']]
)

print("Created instances")
print(instances)


# wait for ip addresses to initialise
time.sleep(10)

for i in instances:
    i.reload()

ip_addresses = {str(i.public_ip_address) : str(i.private_ip_address) for i in instances}
ip_address_map = {}
for i in instances:
    ip_address_map[str(i.private_ip_address)] = i.id

print(ip_addresses)
print(ip_address_map)

config['hosts'] = ip_addresses

with open('fabric_scripts/config.yaml', 'w') as f:
    data = yaml.dump(config, f, default_flow_style=False)

print("Added IP addresses to config.yaml")


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
    c = Connection(host=f'ubuntu@ec2-{public_ip}.compute-1.amazonaws.com', connect_kwargs={'key_filename': config['ssh_path']})
    
    time.sleep(20)
    print("Successfully connected...")

    # ec2.instances.terminate()
    if current == master:
        print(f'master ip {public_ip}')
        c.run("sudo kubeadm init")
        c.run("mkdir -p $HOME/.kube")
        c.run("sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config")
        c.run("sudo chown $(id -u):$(id -g) $HOME/.kube/config")
        c.run("sudo kubectl --kubeconfig=/etc/kubernetes/admin.conf create -f https://docs.projectcalico.org/v3.14/manifests/calico.yaml")
        c.run("kubeadm token create --print-join-command 2> /dev/null > token.sh")
        os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} ubuntu@ec2-{public_ip}.compute-1.amazonaws.com:~/token.sh ./fabric_scripts")
        c.run("kubectl taint nodes --all node-role.kubernetes.io/master-")
        for k,v in config['folder'].items():
            os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} -r {v} ubuntu@ec2-{public_ip}.compute-1.amazonaws.com:~/")

    if current != master:
        print(f'worker ip {public_ip}')
        token_file = open("fabric_scripts/token.sh", "r")
        command = token_file.readlines()[0].rstrip()
        c.run(f'sudo {command}')

masterip = master[0].replace('.','-')

master_c = Connection(host=f'ubuntu@ec2-{masterip}.compute-1.amazonaws.com', connect_kwargs={'key_filename': config['ssh_path']})

time.sleep(20)

master_c.run("kubectl apply -f yaml/metrics")
time.sleep(30)
master_c.run(f"kubectl taint nodes ip-{master[1].replace('.','-')} node-role.kubernetes.io/master=:NoSchedule")

master_c.run("kubectl apply -f yaml/pods")
master_c.run("kubectl autoscale deployment worker-deployment --cpu-percent=80 --min=20 --max=100")

print(f"\n===================================\nFRONT END AVAILABLE AT {master[0]}:31745\n===================================\n")

print("Monitoring setting up, available in 2 minutes")

time.sleep(120)

master_c.run("mkdir status")


counter = 0
prev = None
scale_up = False
scale_down = False
while(run):
    print(f"\n===================================\nFRONT END AVAILABLE AT {master[0]}:31745\n===================================\n")
    print("Checking....")
    master_c.run("kubectl get pods --all-namespaces > status/podstatus.txt") #list of pods on node #list of nodes and status, list of CPU usage
    master_c.run("kubectl get pod --all-namespaces -o=custom-columns=NAME:.metadata.name,STATUS:.status.phase,NODE:.spec.nodeName > status/podloc.txt")
    master_c.run("kubectl top nodes > status/cpumetrics.txt")
    os.system(f"scp -o StrictHostKeyChecking=no -i {config['ssh_path']} -r ubuntu@ec2-{masterip}.compute-1.amazonaws.com:~/status/ .")
    count, pending, avg_cpu ,scale_down_data, evict_pods = scale_and_terminate(f'ip-{master[1].replace(".","-")}')
    if(len(evict_pods) > 0 and counter > 1): #evict pods on down nodes
        for pod, namespace in evict_pods:
            master_c.run(f"kubectl delete pod {pod} --namespace={namespace} --grace-period=0 --force")
        ip_address_map = create_instances(ip_address_map)
    elif(avg_cpu > 80 and pending and counter > 1 and count < 10): #scale up
        ip_address_map = create_instances(ip_address_map)
    elif(scale_down_data[0] and counter > 1 and count > 4):
        for pod, namespace in scale_down_data[2]:
            master_c.run(f"kubectl delete pod {pod} --namespace={namespace} --grace-period=0 --force")
        ec2.instances.filter(InstanceIds = [ip_address_map[scale_down_data[1][3:].replace("-",".")]]).terminate()
    time.sleep(60)

    counter += 1
    print("finished check, sleeping.... ")

print("Set up finished, exiting.")
