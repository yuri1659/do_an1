import socket
import threading
from tkinter import *
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
from queue import Queue
# AES configuration (must match server)
KEY = b'mysecretpasswordmysecretpassword'  # 32 bytes for AES-256
IV = b'initialvector123'  # 16 bytes for AES


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


def connection():
    ipaddr = ipaddr_entry.get()
    nickname = username_entry.get()
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((ipaddr, 8080))

    login.destroy()

    window = Tk()
    window.title(f"Chat room, username: {nickname}")
    text_messages = Text(window, width=100, bg="green")
    text_messages.grid(row=0, column=0, padx=10, pady=10)
    scrollbar = Scrollbar(window, command=text_messages.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    text_messages.config(yscrollcommand=scrollbar.set)



    your_messages = Entry(window, width=50)
    your_messages.grid(row=1, column=0, padx=10, pady=10)

    def write(event=None):
        message1 = f"<{time.asctime(time.localtime())}>{nickname}: {your_messages.get()}"
        encrypted_msg = encrypt_message(message1)
        client.send(encrypted_msg)
        your_messages.delete(0, "end")

    messagebutton = Button(window, text="Send", width=20, command=write)
    window.bind("<Return>", write)
    messagebutton.grid(row=2, column=0, padx=5, pady=10)

    def receive():
        while True:
            try:
                encrypted_message = client.recv(1024)
                if not encrypted_message:
                    continue

                if encrypted_message == encrypt_message("NICK"):
                    client.send(encrypt_message(nickname))
                else:
                    message = decrypt_message(encrypted_message)
                    print(message)
                    text_messages.insert(END, "\n" + message)
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
    receive_thread = threading.Thread(target=receive)
    receive_thread.daemon = True
    receive_thread.start()

    window.after(100, update_messages)
    window.mainloop()


login = Tk()
login.title("Server connection")
global ipaddr_entry
global username_entry
ipaddr_label = Label(login, text="ip address:", width=10)
ipaddr_label.grid(row=0, column=0, padx=10, pady=10)
ipaddr_entry = Entry(login, width=25)
ipaddr_entry.grid(row=0, column=1, padx=10, pady=10)

username_label = Label(login, text="nickname:", width=10)
username_label.grid(row=1, column=0, padx=10, pady=10)
username_entry = Entry(login, width=25)
username_entry.grid(row=1, column=1, padx=10, pady=10)

login_button = Button(login, text="join", width=15, command=connection)
login_button.grid(row=2, column=0, padx=10, pady=10)

login.mainloop()
