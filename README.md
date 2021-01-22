# CW20-04 - MD5 Password Cracking

### Coursework by
*   Chanthru Uthaya-Shankar (cu17780)
*   Ainesh Sevellaraja (as17284)
*   Karthik Sridhar (ks17226)

## Pre-requisites
*   From CW20-04 folder create a folder named Status, inside this folder create a file named ```avg_cpu_t.txt```     
*   Inside ```yaml/pods/worker-deployment.yaml```
    *   Download and update the AWS credentials ```env``` variables
    *   Create an S3 Bucket and update the bucket name.
*   Inside ```fabric_scripts/config.yaml```
    *   Create a Security Group on AWS EC2 with **All traffic** on inbound and outbound rules
    *   Replace the ```sg_group``` key with the ID in the config file.
    *   Replace the ```ssh_path``` key with the location of your AWS key-pair file
    *   Replace the ```ssh_key_name``` key with the name of your AWS key-pair
*   From the base directory ```CW20-04/```, Install the python modules by running ```pip install -r requirements.txt```.

## Running instructions
*   From the base directory ```CW20-04/```, run ```python fabric_scripts/setup-cluster.py```. This will spin up the Kubernetes cluster with 3 ec2 instances initially, where one of them is the master while the others are workers. The IP addresses of the master and worker nodes will be printed to the console.
*   Once the terminal is about to switch to monitor mode, it will periodically (every 1 minute) check for potential scale operations to perform, meaning the initial set up is complete.

## Using the controller
*   Open another terminal and ```ssh``` into the master node by running ```ssh -i "fabric_scripts/TestKey.pem" ubuntu@ec2-<master-ip>.compute-1.amazonaws.com```
*   Once the metrics server is fully set up (roughly 2 min wait time), you can check whether the nodes are up and running by executing ```kubectl top nodes```. This will return you the CPU and Memory usage of each of the nodes in the cluster.
*   Verify all the worker pods are running by executing ```kubectl get pods```.

## Running the Front end
*   The service will be running on port ```31745``` as it is of type ```NodePort```, specified in the ```yaml/pods/front-end-service.yaml``` file. The URL should look like ```master-ip:31745```. Paste this URL in your browser and it should redirect you to the front end.
*   Enter your password, click submit and wait for our service to crack it. Our service is able to handle 6 to 7 passwords.

## Verifying the crack
The password when decrypted is written into the S3 bucket created at the start. This can be verified by running the ```get_password_s3.py``` script. Simply run ```python get_password_s3.py <bucket name>``` and it should print the original password entered that was cracked.

The ```timer-service``` helps time the entire password cracking process and returns the result. This can be checked by viewing the logs of the timer service, by following the steps:
*   Identify the service by running ```kubectl get pods | grep timer``` and copy the pod ID.
*   View the logs of the service by running ```kubectl logs <timer id>```
