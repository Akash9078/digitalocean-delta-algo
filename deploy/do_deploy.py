"""
do_deploy.py – SSH into DigitalOcean droplet, pull latest code, rebuild and start containers.
Reads from .env file (DO_HOST, DO_USER, DO_PASSWORD, APP_DIR)
"""
import sys
import os
import io

# Fix for Windows Unicode output
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from dotenv import load_dotenv
import time
import paramiko

# Load from .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

HOST     = os.getenv("DO_HOST", "")
USER     = os.getenv("DO_USER", "root")
PASSWORD = os.getenv("DO_PASSWORD", "")
APP_DIR  = os.getenv("APP_DIR", "digitalocean-delta-algo")

if not HOST or not PASSWORD:
    print("Error: DO_HOST and DO_PASSWORD required in .env")
    sys.exit(1)

COMMANDS = [
    # Clone if not present, otherwise hard-reset to latest main
    f"[ -d ~/{APP_DIR} ] && echo 'dir exists' || git clone https://github.com/Akash9078/digitalocean-delta-algo.git ~/{APP_DIR}",
    f"cd ~/{APP_DIR} && git fetch --all && git reset --hard origin/main && git clean -fd",
    # Copy .env template if .env doesn't exist
    f"cd ~/{APP_DIR} && ([ -f .env ] && echo '.env already exists' || cp .env.example .env)",
    # Stop old containers cleanly
    f"cd ~/{APP_DIR} && docker compose down --remove-orphans 2>&1; true",
    # Build fresh
    f"cd ~/{APP_DIR} && docker compose build --no-cache bot 2>&1",
    # Start all services
    f"cd ~/{APP_DIR} && docker compose up -d 2>&1",
    # Show running containers
    f"sleep 5 && cd ~/{APP_DIR} && docker compose ps 2>&1",
    # Tail recent logs
    f"cd ~/{APP_DIR} && docker compose logs --tail=80 bot 2>&1",
]


def run_cmd(client, cmd, timeout=300):
    print(f"\n{'='*65}")
    print(f"$ {cmd}")
    print('='*65)
    _, stdout, _ = client.exec_command(cmd, timeout=timeout, get_pty=True)
    stdout.channel.set_combine_stderr(True)
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            chunk = stdout.channel.recv(4096).decode('utf-8', errors='replace')
            sys.stdout.write(chunk)
            sys.stdout.flush()
        time.sleep(0.15)
    remaining = stdout.read().decode('utf-8', errors='replace')
    if remaining:
        sys.stdout.write(remaining)
        sys.stdout.flush()
    rc = stdout.channel.recv_exit_status()
    print(f"\n[exit {rc}]")
    return rc


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"Connecting to {HOST} ...")
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
        print("Connected!\n")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    try:
        for cmd in COMMANDS:
            run_cmd(client, cmd)

        print("\n" + "="*65)
        print("  DEPLOYMENT COMPLETE")
        print("="*65)
        print(f"  API:       http://{HOST}:8501")
        print(f"  API Docs:  http://{HOST}:8501/docs")
        print(f"  Health:    http://{HOST}:8501/health")
        print()
        print("  NOTE: Add your Delta API credentials if not already set:")
        print(f"    ssh root@{HOST}")
        print(f"    nano ~/{APP_DIR}/.env")
        print(f"    docker compose -f ~/{APP_DIR}/docker-compose.yml restart bot")
        print("="*65)
    finally:
        client.close()


if __name__ == "__main__":
    main()
