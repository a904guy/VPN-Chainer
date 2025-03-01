import os
import random
import sys
import subprocess
import signal
import uuid

try:
    import speedtest
except ImportError:
    print("[INFO] speedtest module not found. Installing...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'speedtest-cli'], check=True)
    import speedtest

try:
    from setproctitle import setproctitle
except ImportError:
    print("[INFO] setproctitle module not found. Installing...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'setproctitle'], check=True)
    from setproctitle import setproctitle

from pathlib import Path
import time
try:
    from flask import Flask, jsonify, request, abort
except ImportError:
    print("[INFO] Flask module not found. Installing...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'Flask'], check=True)
    from flask import Flask, jsonify, request, abort

# Initialize Flask app
app = Flask(__name__)

# Directory for WireGuard configs
WG_CONFIG_DIR = '/etc/wireguard/'
HOOKS_DIR = "/etc/vpn-chainer/hooks"
SERVICE_FILE_PATH = "/etc/systemd/system/vpn-chainer.service"

# Global Variables
active_vpn_configs = []
previous_routes = []
vpn_count = 0  # Number of VPNs requested at startup
vpn_uuid = str(uuid.uuid4())  # Unique API key
use_fastest = False  # Flag for speed testing

SAMPLE_HOOKS = {
    "pre-spin-up.sh": "#!/bin/bash\n# Pre-Spin-Up Hook\n# Example: echo 'VPN is starting...'\necho '[HOOK] Pre-Spin-Up triggered!'\n",
    "post-spin-up.sh": "#!/bin/bash\n# Post-Spin-Up Hook\n# Example: systemctl restart tor\n\n",
    "pre-spin-down.sh": "#!/bin/bash\n# Pre-Spin-Down Hook\n# Example: echo 'VPN is stopping...'\necho '[HOOK] Pre-Spin-Down triggered!'\n",
    "post-spin-down.sh": "#!/bin/bash\n# Post-Spin-Down Hook\n# Example: echo 'VPN has shut down.'\n\n"
}


def check_and_install(pkg, apt_name=None):
    """Ensure necessary packages are installed."""
    if not subprocess.run(['which', pkg], capture_output=True).returncode == 0:
        print(f"[INFO] {pkg} is not installed. Installing...")
        subprocess.run(['apt', 'update'], check=True)
        if apt_name:
            subprocess.run(['apt', 'install', '-y', apt_name], check=True)
        else:
            subprocess.run(['apt', 'install', '-y', pkg], check=True)

def list_vpn_configs():
    """List all available VPN config files."""
    return list(Path(WG_CONFIG_DIR).glob('*.conf'))

def test_vpn_speed(config_file):
    """Bring up a VPN, run a speed test, and return the download speed."""
    try:
        subprocess.run(['wg-quick', 'up', str(config_file)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st = speedtest.Speedtest()
        st.get_best_server()
        download_speed = st.download() / 1_000_000  # Convert to Mbps
        print(f"[SPEEDTEST] {config_file.stem}: {download_speed:.2f} Mbps")
    except Exception as e:
        print(f"[ERROR] Speed test failed for {config_file.stem}: {e}")
        download_speed = 0
    finally:
        subprocess.run(['wg-quick', 'down', str(config_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return download_speed

def select_vpn_configs(count, fastest=False):
    """Select VPN configs either randomly or by top speed."""
    all_configs = list_vpn_configs()

    if count > len(all_configs):
        print(f"[ERROR] Only {len(all_configs)} available configurations, cannot select {count}.")
        sys.exit(1)

    if fastest:
        print("\n[SPEEDTEST] Measuring VPN speeds for all configurations...")
        vpn_speeds = [(config, test_vpn_speed(config)) for config in all_configs]

        # Sort VPNs by speed (fastest first) and take the top N
        vpn_speeds.sort(key=lambda x: x[1], reverse=True)
        selected_vpns = [config for config, speed in vpn_speeds[:count]]
        print(f"\n[INFO] Top {count} fastest VPNs selected.")
    else:
        selected_vpns = random.sample(all_configs, count)

    return selected_vpns

def setup_vpn():
    """Bring up VPN interfaces, set routing, and run hooks."""
    global active_vpn_configs, previous_routes

    run_hook("pre-spin-up")

    active_vpn_configs = select_vpn_configs(vpn_count, fastest=use_fastest)

    previous_routes = []
    print("\n[SETUP] Establishing VPN Chain...")

    vpn_names = []
    vpn_ips = []

    for i, config_file in enumerate(active_vpn_configs):
        with open(config_file, 'r') as file:
            config = file.read()

        vpn_name = config_file.stem
        vpn_names.append(vpn_name)

        address_line = next(line for line in config.splitlines() if line.startswith("Address"))
        address = address_line.split("=")[1].strip()
        vpn_ips.append(address)

        print(f"  - Activating VPN [{vpn_name}] at {address}...")
        subprocess.run(['wg-quick', 'up', str(config_file)], check=True)

        if i > 0:
            previous_address = previous_routes[i - 1]
            subprocess.run(['ip', 'route', 'add', f'{address}/24', 'via', previous_address, 'dev', f'wg{i}'], check=True)

        previous_routes.append(address)

        subprocess.run(['iptables', '-A', 'FORWARD', '-i', f'wg{i}', '-o', f'wg{i + 1}', '-j', 'ACCEPT'], check=True)

    run_hook("post-spin-up")

    print("\n[INFO] VPN Chain Established Successfully!")
    print(f"  [VPN Route]  {' -> '.join(vpn_names)}")
    print(f"  [IP Route]   {' -> '.join(vpn_ips)}\n")

def undo_vpn():
    """Shutdown VPN interfaces, remove routing, and run hooks."""
    global active_vpn_configs, previous_routes

    run_hook("pre-spin-down")

    print("\n[SHUTDOWN] Cleaning up VPNs...")

    for config_file in active_vpn_configs:
        vpn_name = config_file.stem
        print(f"  - Deactivating VPN [{vpn_name}]...")
        subprocess.run(['wg-quick', 'down', str(config_file)], check=True)

    for route in previous_routes:
        subprocess.run(['ip', 'route', 'del', route], check=True)

    subprocess.run(['iptables', '-F'], check=True)

    run_hook("post-spin-down")

    active_vpn_configs = []
    previous_routes = []

@app.route('/rotate_vpn', methods=['GET'])
def rotate_vpn():
    """Trigger VPN rotation via API."""
    if request.args.get('key') != vpn_uuid:
        abort(403, description="Forbidden: Invalid API Key.")
    print("\n[INFO] Rotating VPN Chain...")
    undo_vpn()
    setup_vpn()
    return jsonify({"message": "VPN rotation completed."}), 200

HOOKS_DIR = "/etc/vpn-chainer/hooks"

def ensure_hooks_directory():
    """Ensure that the hooks directory exists."""
    if not os.path.exists(HOOKS_DIR):
        print(f"[INFO] Creating hooks directory at {HOOKS_DIR}...")
        os.makedirs(HOOKS_DIR, exist_ok=True)

    for hook, content in SAMPLE_HOOKS.items():
        hook_path = os.path.join(HOOKS_DIR, hook)
        if not os.path.exists(hook_path):
            print(f"[INFO] Creating sample hook script: {hook_path}")
            with open(hook_path, "w") as hook_file:
                hook_file.write(content)
            os.chmod(hook_path, 0o644)  # Ensure script is NOT executable by default

def run_hook(hook_name):
    """Run a script if it exists in the hooks directory."""
    hook_script = os.path.join(HOOKS_DIR, f"{hook_name}.sh")

    if os.path.exists(hook_script) and os.access(hook_script, os.X_OK):
        print(f"[HOOK] Running {hook_name} script...")
        subprocess.run([hook_script], check=True)
    else:
        print(f"[HOOK] No {hook_name} script found. Skipping.")

def auto_install():
    service_content = f"""
[Unit]
Description=VPN Chainer Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/vpn-chainer {vpn_count}
Restart=always
User=root

[Install]
WantedBy=multi-user.target
"""

    print("[INSTALL] Setting up systemd service for VPN-Chainer...")

    # Write systemd service file
    with open(SERVICE_FILE_PATH, "w") as service_file:
        service_file.write(service_content)

    # Reload systemctl and enable service
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "vpn-chainer"], check=True)
    subprocess.run(["systemctl", "start", "vpn-chainer"], check=True)

    print("[INSTALL] VPN-Chainer service installed and started successfully.\n")

    print("[LOG] Displaying logs (press Ctrl+C to exit):\n")
    subprocess.run(["journalctl", "-u", "vpn-chainer", "-f"])


if __name__ == "__main__":
    
    setproctitle("VPN-Chainer")

    check_and_install('wg', 'wireguard')
    check_and_install('resolvconf')
    check_and_install('iptables')

    ensure_hooks_directory()

    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        print("Usage: vpn-chainer <number_of_vpns> [--fastest] [--auto-install]")
        sys.exit(1)

    vpn_count = int(sys.argv[1])
    use_fastest = "--fastest" in sys.argv  # Check if --fastest is supplied

    # Check if --auto-install flag is present
    if "--auto-install" in sys.argv:
        auto_install()
        sys.exit(0)

    signal.signal(signal.SIGINT, lambda s, f: (undo_vpn(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (undo_vpn(), sys.exit(0)))

    setup_vpn()

    server_ip = subprocess.run(['hostname', '-I'], capture_output=True, text=True).stdout.strip().split()[0]
    print(f"[INFO] VPN-Chainer API running at: http://{server_ip}:5000/rotate_vpn?key={vpn_uuid}\n")
    app.run(host='0.0.0.0', port=5000)
