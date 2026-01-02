import socket
import threading
import customtkinter as ctk
from tkinter import *
from tkinter import filedialog, simpledialog, messagebox, simpledialog, END
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
from queue import Queue
import os
import struct
import ipaddress

# AES configuration (must match server)
KEY = b'mysecretpasswordmysecretpassword'  # 32 bytes for AES-256
IV = b'initialvector123'  # 16 bytes for AES
CHUNK_SIZE = 4096


# ---------- Encryption helpers ----------
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


# ---------- Chunk transfer helpers ----------
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


# ---------- GUI and networking ----------
def connection():
    ipaddr = ipaddr_entry.get()
    nickname = username_entry.get()
    if not ipaddr.strip():
        messagebox.showerror("Error", "IP Address cannot be empty.")
        return
    try:
        ipaddress.ip_address(ipaddr)
    except ValueError:
        messagebox.showerror("Invalid IP", "Please enter a valid IP address.")
        return
    if not nickname.strip():
        messagebox.showerror("Error", "Nickname cannot be empty.")
        return
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((ipaddr, 8080))
    except socket.error as e:
        messagebox.showerror("Connection error", f"Could not connect to server: {e}")
        client.close()
        return
    login.destroy()

    window = ctk.CTk()
    window.title(f"Chat room, username: {nickname}")

    # Configure grid weights for resizing
    window.columnconfigure(0, weight=1)
    window.columnconfigure(1, weight=0)
    window.columnconfigure(2, weight=0)
    window.columnconfigure(3, weight=0)
    window.rowconfigure(0, weight=1)
    window.rowconfigure(1, weight=0)
    window.rowconfigure(2, weight=0)

    text_messages = Text(window, bg="green")
    text_messages.grid(row=0, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")
    scrollbar = Scrollbar(window, command=text_messages.yview)
    scrollbar.grid(row=0, column=3, sticky="ns", padx=10, pady=10)
    text_messages.config(yscrollcommand=scrollbar.set)
    
    def on_file_link_click(event):
        index = text_messages.index("@%d,%d" % (event.x, event.y))
        line = text_messages.get(f"{index} linestart", f"{index} lineend")
        if "uploaded file: " in line:
            filename = line.split("uploaded file: ", 1)[1].strip()
            request_file(filename)

    text_messages.tag_configure("file_link", foreground="blue", underline=True)
    text_messages.tag_bind("file_link", "<Button-1>", on_file_link_click)

    your_messages = ctk.CTkEntry(window)
    your_messages.grid(row=1, column=0, padx=10, pady=10, sticky="ew")

    messagebutton = ctk.CTkButton(window, text="Send Message")
    messagebutton.grid(row=1, column=1, padx=5, pady=10)

    # --- New GUI elements for file sending ---
    file_path_entry = ctk.CTkEntry(window)
    file_path_entry.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
    send_file_button = ctk.CTkButton(window, text="Send File")
    send_file_button.grid(row=2, column=1, padx=5, pady=5)

    browse_button = ctk.CTkButton(window, text="Browse")
    browse_button.grid(row=2, column=2, padx=5, pady=5)

    def on_file_link_click(event):
        index = text_messages.index("@%d,%d" % (event.x, event.y))
        line = text_messages.get(f"{index} linestart", f"{index} lineend")
        if "uploaded file: " in line:
            filename = line.split("uploaded file: ", 1)[1].strip()
            request_file(filename)

    def upload_file(filepath=None):
        if filepath is None:
            filepath = filedialog.askopenfilename()
            if not filepath:
                return
        try:
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            client.send(encrypt_message(f'FILE_UPLOAD:{filename}:{filesize}'))

            with open(filepath, 'rb') as f:
                sent = 0
                while sent < filesize:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    send_encrypted_chunk(client, chunk)
                    sent += len(chunk)
            messagebox.showinfo("Upload", f"Uploaded {filename} ({filesize} bytes)")
            message1 = f"<{time.asctime(time.localtime())}>{nickname} uploaded file: {filename}"
            encrypted_msg = encrypt_message(message1)
            client.sendall(encrypted_msg)

        except Exception as e:
            messagebox.showerror("Upload error", str(e))

    def request_file(filename=None):
        if filename is None:
            filename = simpledialog.askstring("Download", "Enter filename to download from server:")
            if not filename:
                return
        client.send(encrypt_message(f'FILE_DOWNLOAD_REQ:{filename}'))

    def write(event=None):
        txt = your_messages.get()
        if not txt:
            return
        if txt.startswith("/put"):
            parts = txt.split(maxsplit=1)
            if len(parts) == 2:
                upload_file(parts[1])
            else:
                upload_file(None)
            your_messages.delete(0, "end")
            return
        if txt.startswith("/get"):
            parts = txt.split(maxsplit=1)
            if len(parts) == 2:
                request_file(parts[1])
            else:
                request_file(None)
            your_messages.delete(0, "end")
            return

        message1 = f"<{time.asctime(time.localtime())}>{nickname}: {txt}"
        encrypted_msg = encrypt_message(message1)
        client.sendall(encrypted_msg)
        your_messages.delete(0, "end")

    def send_file_from_entry():
        path = file_path_entry.get()
        if not path:
            messagebox.showwarning("Warning", "Please enter a file path.")
            return
        if not os.path.isfile(path):
            messagebox.showerror("Error", "Invalid file path.")
            return
        upload_file(path)

    def browse_file():
        filepath = filedialog.askopenfilename()
        if filepath:
            file_path_entry.delete(0, END)
            file_path_entry.insert(0, filepath)

    messagebutton.configure(command=write)
    window.bind("<Return>", write)
    send_file_button.configure(command=send_file_from_entry)
    browse_button.configure(command=browse_file)

    def handle_incoming_file(initial_info: str):
        try:
            _, filename, size_s = initial_info.split(":", 2)
            size = int(size_s)
        except Exception as e:
            text_messages.insert(END, f"\nInvalid file header: {initial_info}")
            return

        save_path = filedialog.asksaveasfilename(initialfile=filename, title="Save file as")
        if not save_path:
            remaining = size
            while remaining > 0:
                chunk = recv_encrypted_chunk(client)
                remaining -= len(chunk)
            text_messages.insert(END, f"\nDownload cancelled by user.")
            return

        try:
            with open(save_path, 'wb') as f:
                received = 0
                while received < size:
                    chunk = recv_encrypted_chunk(client)
                    f.write(chunk)
                    received += len(chunk)
            text_messages.insert(END, f"\nFile downloaded and saved to {save_path}")
        except Exception as e:
            text_messages.insert(END, f"\nError saving file: {e}")

    def receive():
        while True:
            try:
                encrypted_message = client.recv(4096)
                if not encrypted_message:
                    continue

                if encrypted_message == encrypt_message("NICK"):
                    client.send(encrypt_message(nickname))
                    continue

                try:
                    message = decrypt_message(encrypted_message)
                except Exception as e:
                    continue

                if message.startswith("FILE_DOWNLOAD:"):
                    handle_incoming_file(message)
                else:
                    text_messages.insert(END, "\n" + message)
                    if "uploaded file: " in message:
                        line_start = text_messages.index("end-1l")
                        line_end = text_messages.index("end-1c")
                        content = text_messages.get(line_start, line_end)
                        pos = content.find("uploaded file: ")
                        if pos != -1:
                            start_tag = f"{line_start}+{pos + len('uploaded file: ')}c"
                            end_tag = line_end
                            text_messages.tag_add("file_link", start_tag, end_tag)
                            
            except Exception as e:
                print(f"An error occurred: {e}")
                client.close()
                break

    def update_messages():
        while not message_queue.empty():
            message = message_queue.get()
            text_messages.insert(END, f"\n{message}")
        window.after(100, update_messages)

    message_queue = Queue()
    threading.Thread(target=receive, daemon=True).start()
    window.after(100, update_messages)
    window.mainloop()


# ---------- Login window ----------
login = ctk.CTk()
login.title("Server connection")

# Configure grid weights
login.columnconfigure(0, weight=0)
login.columnconfigure(1, weight=1)

ipaddr_label = ctk.CTkLabel(login, text="IP Address:")
ipaddr_label.grid(row=0, column=0, padx=10, pady=10)
ipaddr_entry = ctk.CTkEntry(login)
ipaddr_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

username_label = ctk.CTkLabel(login, text="Nickname:")
username_label.grid(row=1, column=0, padx=10, pady=10)
username_entry = ctk.CTkEntry(login)
username_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

login_button = ctk.CTkButton(login, text="Join", command=connection)
login_button.grid(row=2, column=0, columnspan=2, padx=10, pady=10)

login.mainloop()
