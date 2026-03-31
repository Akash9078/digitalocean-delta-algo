"""
view_logs.py – Connect to DigitalOcean droplet and stream the trading bot logs.
Requires 'paramiko' (pip install paramiko).
Reads from .env file (DO_HOST, DO_USER, DO_PASSWORD, APP_DIR)
Press Ctrl+C to stop streaming.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import paramiko
import time
import socket

# Load from .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

HOST     = os.getenv("DO_HOST", "")
USER     = os.getenv("DO_USER", "root")
PASSWORD = os.getenv("DO_PASSWORD", "")
APP_DIR  = os.getenv("APP_DIR", "digitalocean-delta-algo")

def main():
    if not HOST or not PASSWORD:
        print("Error: DO_HOST and DO_PASSWORD required in .env")
        sys.exit(1)
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
        print("[+] Connected successfully!\n")
    except paramiko.AuthenticationException:
        print("[-] Authentication failed. Check your password.")
        sys.exit(1)
    except Exception as e:
        print(f"[-] Connection failed: {e}")
        sys.exit(1)

    print(f"[+] Requesting live runtime logs from Docker...")
    print("="*70)
    print("      (Press Ctrl+C to stop viewing logs)      ")
    print("="*70)
    print()

    # Get a pseudo-tty and execute docker compose logs -f
    try:
        # cd to the app directory and stream docker compose logs
        cmd = f"cd {APP_DIR} && docker compose logs -f --tail=100 bot"
        _, stdout, _ = client.exec_command(cmd, get_pty=True)
        
        # Continuously read from stdout until interrupted
        while not stdout.channel.exit_status_ready():
            # Use blocking recv (with short timeout) to grab bytes eagerly.
            # recv_ready() often misses endless stream triggers in paramiko.
            try:
                data = stdout.channel.recv(1024).decode('utf-8', errors='replace')
                if data:
                    sys.stdout.write(data)
                    sys.stdout.flush()
                else:
                    time.sleep(0.1)
            except socket.timeout:
                pass

    except KeyboardInterrupt:
        print("\n\n[-] Log streaming stopped by user (Ctrl+C). Disconnecting...")
    except Exception as e:
        print(f"\n[-] Disconnected or error occurred: {e}")
    finally:
        client.close()
        print("[+] Connection closed.")

if __name__ == "__main__":
    main()
