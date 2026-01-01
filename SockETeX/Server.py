import socket
import threading
import subprocess
import re
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
import struct
import os

def get_windows_wireless_ip():
    try:
        output = subprocess.check_output(['ifconfig'] or ['ipconfig'], text=True, encoding='iso8859-2')
        match = re.search(r"Wireless LAN adapter Wi-Fi:.*?IPv4 Address[.\s]*: (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", output, re.DOTALL)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Error executing ipconfig: {e}")
    return "0.0.0.0"

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

CHUNK_SIZE = 4096

# --- Encryption helpers ---
def encrypt_bytes(data: bytes) -> bytes:
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    padded = pad(data, AES.block_size)
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted)

def decrypt_bytes(enc_b64: bytes) -> bytes:
    enc = base64.b64decode(enc_b64)
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    decrypted = cipher.decrypt(enc)
    return unpad(decrypted, AES.block_size)

def encrypt_message(message: str) -> bytes:
    return encrypt_bytes(message.encode('utf-8'))

def decrypt_message(encrypted_message: bytes) -> str:
    return decrypt_bytes(encrypted_message).decode('utf-8')

# --- length-prefixed chunk helpers ---
def send_encrypted_chunk(sock: socket.socket, data_bytes: bytes):
    enc = encrypt_bytes(data_bytes)
    length = struct.pack('>Q', len(enc))
    sock.sendall(length + enc)

def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b''
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            raise ConnectionError("Connection closed while receiving exact bytes")
        buf += part
    return buf

def recv_encrypted_chunk(sock: socket.socket) -> bytes:
    header = recv_exact(sock, 8)
    length = struct.unpack('>Q', header)[0]
    enc = recv_exact(sock, length)
    return decrypt_bytes(enc)

# --- broadcast ---
def broadcast(message):
    encrypted_msg = encrypt_message(message)
    for client in clients:
        try:
            client.sendall(encrypted_msg)
        except:
            pass

# --- file recv/send handling ---
def receive_file_from_client(client, filename, filesize):
    # save to server current directory or 'uploads' folder
    os.makedirs('uploads', exist_ok=True)
    path = os.path.join('uploads', filename)
    try:
        with open(path, 'wb') as f:
            received = 0
            while received < filesize:
                chunk = recv_encrypted_chunk(client)
                f.write(chunk)
                received += len(chunk)
        broadcast(f"Server: Received file {filename} ({filesize} bytes) and saved to {path}")
    except Exception as e:
        broadcast(f"Server: Error receiving file {filename}: {e}")

def send_file_to_client(client, filename):
    # server expects the file to be in ./uploads/filename
    path = os.path.join('uploads', filename)
    if not os.path.exists(path):
        client.sendall(encrypt_message(f"ERROR: File not found:{filename}"))
        return
    filesize = os.path.getsize(path)
    # notify client to prepare
    client.sendall(encrypt_message(f"FILE_DOWNLOAD:{filename}:{filesize}"))
    with open(path, 'rb') as f:
        sent = 0
        while sent < filesize:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            send_encrypted_chunk(client, chunk)
            sent += len(chunk)
    # Optionally announce completion
    broadcast(f"Server: Sent file {filename} ({filesize} bytes) to a client")

# --- connection handling ---
def handle(client):
    while True:
        try:
            encrypted_message = client.recv(4096)
            if not encrypted_message:
                continue
            # decrypt to text
            try:
                message = decrypt_message(encrypted_message)
            except Exception as e:
                print("Failed to decrypt a message:", e)
                continue

            # file upload header: FILE_UPLOAD:<filename>:<size>
            if message.startswith("FILE_UPLOAD:"):
                try:
                    _, filename, size_s = message.split(":", 2)
                    size = int(size_s)
                except:
                    client.sendall(encrypt_message("ERROR: Invalid file upload header"))
                    continue
                # receive file data (length-prefixed encrypted chunks)
                receive_file_from_client(client, filename, size)
                continue

            # file download request from client: FILE_DOWNLOAD_REQ:<filename>
            if message.startswith("FILE_DOWNLOAD_REQ:"):
                try:
                    _, filename = message.split(":", 1)
                except:
                    client.sendall(encrypt_message("ERROR: Invalid download request"))
                    continue
                send_file_to_client(client, filename)
                continue

            # ordinary chat message: broadcast
            broadcast(message)
        except Exception as e:
            print(f"Error: {e}")
            if client in clients:
                index = clients.index(client)
                clients.remove(client)
                client.close()
                try:
                    nickname = nicknames[index]
                    broadcast(f'{nickname} disconnected')
                    nicknames.remove(nickname)
                except:
                    pass
            break

def receive():
    print('Waiting for connection...')
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

if __name__ == "__main__":
    receive()
