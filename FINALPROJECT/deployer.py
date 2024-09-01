import boto3
import git
import yaml
import os
import zipfile
import paramiko
import sys

def clone_repo(repo_url, ec2Name):
    clone_dir = os.mkdir(f"/{ec2Name}_Clone") 
    if not os.path.exists(clone_dir):
        os.makedirs(clone_dir)
    git.Repo.clone_from(repo_url, clone_dir)
    print(f"Repository cloned to {clone_dir}")
    return f"{ec2Name}_Clone"

def zip_directory(directory, zip_name):
    with zipfile.ZipFile(zip_name, 'w') as zipf:
        for root, _, files in os.walk(directory):
            for file in files:
                zipf.write(os.path.join(root, file),
                           os.path.relpath(os.path.join(root, file),
                                           os.path.join(directory, '..')))
    print(f"Directory {directory} zipped as {zip_name}")

def load_config(file_path):
    with open(file_path, 'r') as file:
        config = yaml.safe_load(file)
    return config

def launch_ec2_instance(config, configs_name, ec2DeployName):
    try:
        session = boto3.Session(profile_name='deployerProfile')
        ec2 = session.client('ec2')
    except Exception as e:
        print(f"Error creating boto3 session: {e}")

    ami_id = config[configs_name].get('ami_id')
    instance_type = config[configs_name].get('instance_type')
    key_name = config[configs_name].get('key_name')
    security_group_id = config[configs_name].get('security_group_id')

    if(ami_id == "" or instance_type == "" or key_name == "" or security_group_id == ""):
        exit("Please provide ami_id, instance_type, key_name, and security_group_id in the config file")
    
    try:
        response = ec2.run_instances(
            ImageId=ami_id,
            InstanceType=instance_type,
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': f'{ec2DeployName}_ec2Instance'
                        }
                    ]
                }
            ]
        )
    
        instance_id = response['Instances'][0]['InstanceId']
        print(f"EC2 Instance launched with ID: {instance_id}")

        return response['Instances'][0]['PrivateIpAddress']
    except Exception as e:
        print(f"Error launching EC2 instance: {e}")
        return None

def upload_directory(local_dir, remote_dir, ssh_client, sftp_client):
    # Create remote directory if it does not exist
    try:
        sftp_client.chdir(remote_dir)
    except FileNotFoundError:
        sftp_client.mkdir(remote_dir)
        sftp_client.chdir(remote_dir)
    
    # Upload files
    for root, dirs, files in os.walk(local_dir):
        # Create directories
        for dir in dirs:
            remote_path = os.path.join(remote_dir, os.path.relpath(os.path.join(root, dir), local_dir))
            try:
                sftp_client.mkdir(remote_path)
            except OSError:
                # Directory already exists
                pass
        
        # Upload files
        for file in files:
            local_path = os.path.join(root, file)
            remote_path = os.path.join(remote_dir, os.path.relpath(local_path, local_dir))
            sftp_client.put(local_path, remote_path)
            print(f"Uploaded {local_path} to {remote_path}")

def connect_and_upload(instance_ip, key_path, local_dir, remote_dir):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(instance_ip, username='ec2-user', key_filename=key_path)
    
    sftp = ssh.open_sftp()
    upload_directory(local_dir, remote_dir, ssh, sftp)
    
    sftp.close()
    ssh.close()

def main(repo_url, name):
    repo_url = sys.argv[1]
    name = sys.argv[2]
    configs_name = sys.argv[3]

    if(repo_url == "" or name == ""):
        exit("Please provide a repo url and a name for the ec2 instance")
    if(configs_name == ""):
        configs_name = 'default'
        
    try:
        _clone_repo = clone_repo(repo_url, name)
        zip_directory(f"/{_clone_repo}", f"{name}_files_zipped.zip")
        configs = load_config('/Configs/Config.yaml')
        instanceIP = launch_ec2_instance(configs, configs_name, name)
        connect_and_upload(instanceIP, configs['ec2'].get('key_name'), f"{name}_Clone", '/home/ec2-user')
        os.rmdir(f"/{_clone_repo}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
