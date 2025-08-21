import paramiko  

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(hostname='172.23.21.12', port=22, username='s.hozyn', password='19Sie2011>>>', timeout=3)
    transport = client.get_transport()
    if transport is not None and transport.is_active():
        print("SSH connection established.")
    else:
        print("SSH connection failed or is inactive.")

    sftp = client.open_sftp()
    remote_path = "C:\\"
    sftp.chdir(remote_path)
    for filename in sftp.listdir():
        print(filename)

except Exception as e:
    print(e)

    
