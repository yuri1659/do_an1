import socket
import threading
import subprocess
import re
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64

def get_windows_wireless_ip():
    try:
        output = subprocess.check_output(['ipconfig'], text=True, encoding='iso8859-2')
        # Regex to find IPv4 address under "Wireless LAN adapter Wi-Fi"
        match = re.search(r"Wireless LAN adapter Wi-Fi:.*?IPv4 Address[.\s]*: (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", output, re.DOTALL)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Error executing ipconfig: {e}")
    return None

ip = get_windows_wireless_ip()
host = ip
port = 8080
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((host, port))
server.listen()

# AES configuration (must match client)
KEY = b'mysecretpasswordmysecretpassword'  # 32 bytes for AES-256
IV = b'initialvector123'  # 16 bytes for AES

clients = []
nicknames = []


def encrypt_message(message):
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    padded_message = pad(message.encode('utf-8'), AES.block_size)
    encrypted_message = cipher.encrypt(padded_message)
    return base64.b64encode(encrypted_message)


def decrypt_message(encrypted_message):
    encrypted_message = base64.b64decode(encrypted_message)
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    decrypted_message = cipher.decrypt(encrypted_message)
    return unpad(decrypted_message, AES.block_size).decode('utf-8')


def broadcast(message):
    encrypted_msg = encrypt_message(message)
    for client in clients:
        client.send(encrypted_msg)


def handle(client):
    while True:
        try:
            encrypted_message = client.recv(1024)
            if not encrypted_message:
                continue
            message = decrypt_message(encrypted_message)
            broadcast(message)
        except Exception as e:
            print(f"Error: {e}")
            index = clients.index(client)
            clients.remove(client)
            client.close()
            nickname = nicknames[index]
            broadcast(f'{nickname} disconnected')
            nicknames.remove(nickname)
            break


def receive():
    while True:
        client, address = server.accept()
        print(f'connected with {str(address)}')

        client.send(encrypt_message('NICK'))
        encrypted_nickname = client.recv(1024)
        nickname = decrypt_message(encrypted_nickname)
        nicknames.append(nickname)
        clients.append(client)

        print(f'Nickname of the client is {nickname}!')
        broadcast(f'{nickname} has joined the chat')

        thread = threading.Thread(target=handle, args=(client,))
        thread.start()


print('Waiting for connection...')
receive()
