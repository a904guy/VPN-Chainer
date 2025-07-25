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
previous_routes = []  # Store interface addresses for reference
added_routes = []  # Store actual network routes added for cleanup
vpn_name_list = []  # List of VPN interface names for cross-referencing
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
    global active_vpn_configs, previous_routes, added_routes, vpn_name_list

    run_hook("pre-spin-up")

    active_vpn_configs = select_vpn_configs(vpn_count, fastest=use_fastest)

    # Build list of vpn interface names at start of chaining routine
    vpn_name_list = [config_file.stem for config_file in active_vpn_configs]
    
    previous_routes = []
    added_routes = []
    print("\n[SETUP] Establishing VPN Chain...")

    vpn_names = []
    vpn_ips = []
    original_default_route = None
    
    # Save original default route before we modify anything
    try:
        result = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True, check=True)
        if result.stdout.strip():
            original_default_route = result.stdout.strip()
            print(f"  [INFO] Saved original default route: {original_default_route}")
    except subprocess.CalledProcessError:
        print("  [WARNING] Could not detect original default route")

    for i, config_file in enumerate(active_vpn_configs):
        # Parse WireGuard config manually
        config_data = {}
        with open(config_file, 'r') as file:
            current_section = None
            for line in file:
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1]
                    config_data[current_section] = {}
                elif '=' in line and current_section:
                    key, value = line.split('=', 1)
                    config_data[current_section][key.strip()] = value.strip()

        vpn_name = vpn_name_list[i]
        vpn_names.append(vpn_name)
        
        interface_config = config_data.get('Interface', {})
        peer_config = config_data.get('Peer', {})
        
        address = interface_config.get('Address')
        private_key = interface_config.get('PrivateKey')
        listen_port = interface_config.get('ListenPort', '51820')
        dns = interface_config.get('DNS', '1.1.1.1')
        
        public_key = peer_config.get('PublicKey')
        endpoint = peer_config.get('Endpoint')
        allowed_ips = peer_config.get('AllowedIPs', '0.0.0.0/0')
        persistent_keepalive = peer_config.get('PersistentKeepalive', '25')
        
        vpn_ips.append(address)
        print(f"  - Setting up VPN [{vpn_name}] at {address}...")
        
        # Create WireGuard interface manually (without wg-quick routing)
        subprocess.run(['ip', 'link', 'add', vpn_name, 'type', 'wireguard'], check=True)
        subprocess.run(['ip', 'address', 'add', address, 'dev', vpn_name], check=True)
        
        # Configure WireGuard (only core settings, not wg-quick settings like MTU, DNS, Address)
        wg_config = f"""[Interface]
PrivateKey = {private_key}
ListenPort = {listen_port}

[Peer]
PublicKey = {public_key}
Endpoint = {endpoint}
AllowedIPs = {allowed_ips}
PersistentKeepalive = {persistent_keepalive}
"""
        
        # Apply WireGuard configuration
        proc = subprocess.Popen(['wg', 'setconf', vpn_name, '/dev/stdin'], stdin=subprocess.PIPE, text=True)
        proc.communicate(input=wg_config)
        
        # Bring up the interface
        subprocess.run(['ip', 'link', 'set', vpn_name, 'up'], check=True)
        
        # Enable IP forwarding for this interface
        subprocess.run(['sysctl', '-w', f'net.ipv4.conf.{vpn_name}.forwarding=1'], check=True)
        
        # Wait for WireGuard handshake to establish
        print(f"    [INFO] Waiting for WireGuard handshake...")
        import time
        time.sleep(3)  # Give WireGuard time to establish connection
        
        # Set up DNS for this interface
        try:
            subprocess.run(['resolvconf', '-a', vpn_name, '-m', '0', '-x'], input=f'nameserver {dns}\n', text=True, check=False)
        except:
            pass

        if i > 0:
            # For chained VPNs: route traffic from this VPN through the previous one
            previous_vpn_name = vpn_name_list[i-1]
            
            print(f"    [ROUTE] Setting up chaining: {vpn_name} -> {previous_vpn_name} -> Internet")
            
            # Route all internet traffic from this VPN through the previous VPN
            try:
                subprocess.run(['ip', 'route', 'add', '0.0.0.0/1', 'dev', previous_vpn_name], check=True)
                subprocess.run(['ip', 'route', 'add', '128.0.0.0/1', 'dev', previous_vpn_name], check=True)
                added_routes.extend([f'0.0.0.0/1 dev {previous_vpn_name}', f'128.0.0.0/1 dev {previous_vpn_name}'])
            except subprocess.CalledProcessError as e:
                if e.returncode == 2:
                    print(f"    [INFO] Internet routes already exist, replacing...")
                    subprocess.run(['ip', 'route', 'replace', '0.0.0.0/1', 'dev', previous_vpn_name], check=True)
                    subprocess.run(['ip', 'route', 'replace', '128.0.0.0/1', 'dev', previous_vpn_name], check=True)
                    added_routes.extend([f'0.0.0.0/1 dev {previous_vpn_name}', f'128.0.0.0/1 dev {previous_vpn_name}'])
                else:
                    raise
            
            # Set up iptables rules for forwarding between VPN interfaces
            subprocess.run(['iptables', '-A', 'FORWARD', '-i', vpn_name, '-o', previous_vpn_name, '-j', 'ACCEPT'], check=True)
            subprocess.run(['iptables', '-A', 'FORWARD', '-i', previous_vpn_name, '-o', vpn_name, '-j', 'ACCEPT'], check=True)
            # NAT traffic going from this VPN to the previous one
            subprocess.run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', previous_vpn_name, '-j', 'MASQUERADE'], check=True)
        
        elif i == 0:
            # First VPN: route all internet traffic through it
            current_address = address.split('/')[0]
            print(f"    [ROUTE] Setting up default route through first VPN {vpn_name}")
            
            # First, add a specific route for the WireGuard endpoint to avoid routing loops
            endpoint_ip = endpoint.split(':')[0]  # Extract IP from endpoint
            print(f"    [ROUTE] Adding endpoint route for {endpoint_ip} via original gateway")
            try:
                # Route WireGuard endpoint traffic through original default route
                subprocess.run(['ip', 'route', 'add', endpoint_ip, 'via', '10.1.10.1', 'dev', 'eno2'], check=True)
                added_routes.append(f'{endpoint_ip} via 10.1.10.1 dev eno2')
            except subprocess.CalledProcessError as e:
                if e.returncode == 2:
                    print(f"    [INFO] Endpoint route already exists")
                else:
                    print(f"    [WARNING] Could not add endpoint route: {e}")
            
            try:
                # Use split default routes to override existing default
                subprocess.run(['ip', 'route', 'add', '0.0.0.0/1', 'dev', vpn_name], check=True)
                subprocess.run(['ip', 'route', 'add', '128.0.0.0/1', 'dev', vpn_name], check=True)
                added_routes.extend([f'0.0.0.0/1 dev {vpn_name}', f'128.0.0.0/1 dev {vpn_name}'])
            except subprocess.CalledProcessError as e:
                if e.returncode == 2:
                    print(f"    [INFO] Default routes already exist, replacing...")
                    subprocess.run(['ip', 'route', 'replace', '0.0.0.0/1', 'dev', vpn_name], check=True)
                    subprocess.run(['ip', 'route', 'replace', '128.0.0.0/1', 'dev', vpn_name], check=True)
                    added_routes.extend([f'0.0.0.0/1 dev {vpn_name}', f'128.0.0.0/1 dev {vpn_name}'])
                else:
                    raise
            
            # Set up NAT for the first VPN
            subprocess.run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', vpn_name, '-j', 'MASQUERADE'], check=True)

        previous_routes.append(address)

    # Enable global IP forwarding
    subprocess.run(['sysctl', '-w', 'net.ipv4.ip_forward=1'], check=True)
    
    # Flush DNS cache to force re-resolution through VPN
    try:
        subprocess.run(['systemctl', 'restart', 'systemd-resolved'], check=False)
    except:
        pass

    run_hook("post-spin-up")

    print("\n[INFO] VPN Chain Established Successfully!")
    print(f"  [VPN Route]  {' -> '.join(vpn_names)}")
    print(f"  [IP Route]   {' -> '.join(vpn_ips)}")
    print(f"  [INFO] All internet traffic now routed through VPN chain\n")

def undo_vpn():
    """Shutdown VPN interfaces, remove routing, and run hooks."""
    global active_vpn_configs, previous_routes, added_routes, vpn_name_list

    run_hook("pre-spin-down")

    print("\n[SHUTDOWN] Cleaning up VPNs...")

    # Clean up manually created WireGuard interfaces
    for vpn_name in vpn_name_list:
        print(f"  - Deactivating VPN [{vpn_name}]...")
        try:
            # Remove resolvconf DNS settings
            subprocess.run(['resolvconf', '-d', vpn_name, '-f'], check=False)
            # Delete the interface
            subprocess.run(['ip', 'link', 'delete', vpn_name], check=False)
        except Exception as e:
            print(f"    [DEBUG] Error cleaning up {vpn_name}: {e}")

    # Clean up the actual network routes we added
    for route in added_routes:
        try:
            # Parse the route string to get just the network part
            route_parts = route.split()
            if len(route_parts) >= 1:
                network = route_parts[0]
                subprocess.run(['ip', 'route', 'del', network], check=True)
                print(f"  - Removed route: {network}")
        except subprocess.CalledProcessError as e:
            if e.returncode == 2:  # Route doesn't exist
                print(f"  - Route {route} already removed")
            else:
                print(f"  - Warning: Failed to remove route {route}: {e}")

    # Clean up iptables rules
    print("  - Cleaning up iptables rules...")
    subprocess.run(['iptables', '-F'], check=True)
    subprocess.run(['iptables', '-t', 'nat', '-F'], check=True)
    subprocess.run(['iptables', '-X'], check=False)  # Don't fail if no custom chains
    subprocess.run(['iptables', '-t', 'nat', '-X'], check=False)
    
    # Restart DNS to restore normal resolution
    try:
        subprocess.run(['systemctl', 'restart', 'systemd-resolved'], check=False)
        print("  - Restarted DNS resolver")
    except:
        pass

    run_hook("post-spin-down")

    active_vpn_configs = []
    previous_routes = []
    added_routes = []
    vpn_name_list = []

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
    print(f"[INFO] VPN-Chainer API running at: http://{server_ip}:5001/rotate_vpn?key={vpn_uuid}\n")
    app.run(host='0.0.0.0', port=5001)
