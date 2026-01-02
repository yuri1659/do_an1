import socket
import threading
import subprocess
import re
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
import struct
import os
import customtkinter as ctk
from tkinter import messagebox, Listbox
import time

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

running = False

# AES configuration (must match client)
KEY = b'mysecretpasswordmysecretpassword'  # 32 bytes for AES-256
IV = b'initialvector123'  # 16 bytes for AES

clients = []
nicknames = []
connected_clients = []  # list of {'nickname': str, 'ip': str, 'port': int, 'status': str}

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
    global connected_clients, client_listbox
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
                    for c in connected_clients:
                        if c['nickname'] == nickname:
                            c['status'] = 'offline'
                            break
                    client_listbox.delete(0, 'end')
                    for c in connected_clients:
                        client_listbox.insert('end', f"{c['nickname']} - {c['ip']}:{c['port']} - {c['status']} - {c['connect_time']}")
                except:
                    pass
            break

def receive():
    global running, connected_clients, client_listbox
    print('Waiting for connection...')
    server.settimeout(1.0)  # timeout to check running flag
    while running:
        try:
            client, address = server.accept()
            print(f'connected with {str(address)}')

            client.send(encrypt_message('NICK'))
            encrypted_nickname = client.recv(1024)
            nickname = decrypt_message(encrypted_nickname)
            nicknames.append(nickname)
            clients.append(client)
            connected_clients.append({'nickname': nickname, 'ip': address[0], 'port': address[1], 'status': 'online', 'connect_time': time.asctime(time.localtime())})
            client_listbox.insert('end', f"{nickname} - {address[0]}:{address[1]} - online - {time.asctime(time.localtime())}")

            print(f'Nickname of the client is {nickname}!')
            broadcast(f'{nickname} has joined the chat')

            thread = threading.Thread(target=handle, args=(client,))
            thread.start()
        except socket.timeout:
            continue
        except Exception as e:
            if running:
                print(f"Server error: {e}")
            break

def start_server():
    global running, server, client_listbox
    if running:
        messagebox.showinfo("Info", "Server is already running")
        return
    running = True
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    threading.Thread(target=receive, daemon=True).start()
    messagebox.showinfo("Info", f"Server started on {host}:{port}")

def stop_server():
    global running, connected_clients, client_listbox
    if not running:
        messagebox.showinfo("Info", "Server is not running")
        return
    running = False
    server.close()
    # Close all clients
    for client in clients:
        try:
            client.close()
        except:
            pass
    clients.clear()
    nicknames.clear()
    for c in connected_clients:
        c['status'] = 'offline'
    client_listbox.delete(0, 'end')
    for c in connected_clients:
        client_listbox.insert('end', f"{c['nickname']} - {c['ip']}:{c['port']} - {c['status']} - {c['connect_time']}")
    messagebox.showinfo("Info", "Server stopped")

def clear_list():
    global client_listbox
    client_listbox.delete(0, 'end')

if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Chat Server Control")
    root.geometry("400x400")

    start_button = ctk.CTkButton(root, text="Start Server", command=start_server)
    start_button.pack(pady=10)

    stop_button = ctk.CTkButton(root, text="Stop Server", command=stop_server)
    stop_button.pack(pady=10)

    # Listbox for connected clients
    client_listbox = Listbox(root, height=10)
    client_listbox.pack(pady=10, fill="both", expand=True)

    clear_button = ctk.CTkButton(root, text="Clear List", command=clear_list)
    clear_button.pack(pady=10)

    root.mainloop()