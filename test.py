import subprocess
import re

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

if __name__ == "__main__":
    ip = get_windows_wireless_ip()
    if ip:
        print(f"Wireless LAN Adapter IP (Windows): {ip}")
    else:
        print("Could not find wireless IP on Windows.")
