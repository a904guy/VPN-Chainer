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
vpn_ip_list = []  # List of pure VPN IPs (without CIDR) for gateway referencing
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

def configure_dns(vpn_name, dns_server):
    """Configure DNS for VPN interface using available resolver."""
    try:
        # Try resolvconf first (if available)
        if subprocess.run(['which', 'resolvconf'], capture_output=True).returncode == 0:
            subprocess.run(['resolvconf', '-a', vpn_name, '-m', '0', '-x'], 
                         input=f'nameserver {dns_server}\n', text=True, check=False)
        # Fallback to systemd-resolved
        elif subprocess.run(['systemctl', 'is-active', 'systemd-resolved'], capture_output=True).returncode == 0:
            # For systemd-resolved, we can use resolvectl to set DNS for the interface
            subprocess.run(['resolvectl', 'dns', vpn_name, dns_server], check=False)
    except Exception as e:
        print(f"[WARNING] Could not configure DNS for {vpn_name}: {e}")

def remove_dns(vpn_name):
    """Remove DNS configuration for VPN interface."""
    try:
        # Try resolvconf first (if available)
        if subprocess.run(['which', 'resolvconf'], capture_output=True).returncode == 0:
            subprocess.run(['resolvconf', '-d', vpn_name, '-f'], check=False)
        # Fallback to systemd-resolved
        elif subprocess.run(['systemctl', 'is-active', 'systemd-resolved'], capture_output=True).returncode == 0:
            # For systemd-resolved, revert DNS for the interface
            subprocess.run(['resolvectl', 'revert', vpn_name], check=False)
    except Exception as e:
        print(f"[WARNING] Could not remove DNS for {vpn_name}: {e}")

def list_vpn_configs():
    """List all available VPN config files."""
    try:
        wg_path = Path(WG_CONFIG_DIR)
        print(f"[DEBUG] Checking directory: {wg_path}")
        print(f"[DEBUG] Directory exists: {wg_path.exists()}")
        print(f"[DEBUG] Directory is readable: {wg_path.is_dir()}")
        
        configs = list(wg_path.glob('*.conf'))
        print(f"[DEBUG] Found {len(configs)} config files")
        
        if not configs:
            print(f"[ERROR] No WireGuard config files found in {WG_CONFIG_DIR}")
            print(f"[INFO] Please ensure config files exist and have .conf extension")
            # Let's list what files are actually there
            try:
                all_files = list(wg_path.iterdir())
                print(f"[DEBUG] Files in directory: {[f.name for f in all_files]}")
            except Exception as e:
                print(f"[DEBUG] Could not list directory contents: {e}")
        
        return configs
    except PermissionError:
        print(f"[ERROR] Permission denied accessing {WG_CONFIG_DIR}")
        print(f"[INFO] This script must be run as root (try: sudo")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to access {WG_CONFIG_DIR}: {e}")
        sys.exit(1)

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
    global active_vpn_configs, previous_routes, added_routes, vpn_name_list, vpn_ip_list

    run_hook("pre-spin-up")

    active_vpn_configs = select_vpn_configs(vpn_count, fastest=use_fastest)

    # Build list of vpn interface names at start of chaining routine
    vpn_name_list = [config_file.stem for config_file in active_vpn_configs]
    
    previous_routes = []
    added_routes = []
    vpn_ip_list = []  # Initialize list for pure IPs (without CIDR)
    print("\n[SETUP] Establishing VPN Chain...")

    vpn_names = []
    vpn_ips = []
    original_default_route = None
    
    # Save original default route before we modify anything
    original_default_route = None
    default_gateway = None
    default_iface = None
    try:
        result = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True, check=True)
        if result.stdout.strip():
            original_default_route = result.stdout.strip()
            print(f"  [INFO] Saved original default route: {original_default_route}")
            
            # Parse the route properly - format: "default via <gateway> dev <interface> ..."
            route_parts = original_default_route.split()
            try:
                via_index = route_parts.index('via')
                dev_index = route_parts.index('dev')
                if via_index + 1 < len(route_parts) and dev_index + 1 < len(route_parts):
                    default_gateway = route_parts[via_index + 1]
                    default_iface = route_parts[dev_index + 1]
                    print(f"  [INFO] Parsed gateway: {default_gateway}, interface: {default_iface}")
                else:
                    print("  [WARNING] Could not parse gateway and interface from default route")
            except (ValueError, IndexError) as e:
                print(f"  [WARNING] Error parsing default route: {e}")
    except subprocess.CalledProcessError:
        print("  [WARNING] Could not detect original default route")
    
    # Pre-parse all VPN configs to extract endpoints for proper chaining
    vpn_endpoints = []
    for config_file in active_vpn_configs:
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
        
        peer_config = config_data.get('Peer', {})
        endpoint = peer_config.get('Endpoint')
        if endpoint:
            endpoint_ip = endpoint.split(':')[0]
            vpn_endpoints.append(endpoint_ip)
        else:
            vpn_endpoints.append(None)
    
    print(f"  [INFO] VPN Chain Order: {' -> '.join(vpn_name_list)}")
    print(f"  [INFO] Endpoint IPs: {' -> '.join([str(e) for e in vpn_endpoints])}")

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
        
        # Extract pure IP without CIDR and add to vpn_ip_list for gateway referencing
        if address:
            pure_ip = address.split('/')[0]  # Strip CIDR notation
            vpn_ip_list.append(pure_ip)
        
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
        configure_dns(vpn_name, dns)

        if i > 0:
            # For chained VPNs: route this VPN's endpoint through the previous VPN
            previous_vpn_name = vpn_name_list[i-1]
            
            print(f"    [ROUTE] Setting up chaining: {vpn_name} -> {previous_vpn_name} -> Internet")
            
            # Route this VPN's endpoint through the previous VPN interface to create proper chaining
            endpoint_ip = endpoint.split(':')[0]  # Extract IP from endpoint
            print(f"    [ROUTE] Adding endpoint route for {endpoint_ip} through {previous_vpn_name}")
            try:
                subprocess.run(['ip', 'route', 'add', endpoint_ip, 'dev', previous_vpn_name], check=True)
                added_routes.append(f'{endpoint_ip} dev {previous_vpn_name}')
            except subprocess.CalledProcessError as e:
                if e.returncode == 2:
                    print(f"    [INFO] Endpoint route already exists")
                else:
                    print(f"    [WARNING] Could not add endpoint route: {e}")
            
            # Set up iptables rules for forwarding between VPN interfaces
            subprocess.run(['iptables', '-A', 'FORWARD', '-i', vpn_name, '-o', previous_vpn_name, '-j', 'ACCEPT'], check=True)
            subprocess.run(['iptables', '-A', 'FORWARD', '-i', previous_vpn_name, '-o', vpn_name, '-j', 'ACCEPT'], check=True)
            # NAT traffic going from this VPN to the previous one
            subprocess.run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', previous_vpn_name, '-j', 'MASQUERADE'], check=True)
        
        elif i == 0:
            # First VPN: route its endpoint through original gateway and set up NAT
            print(f"    [ROUTE] Setting up first VPN {vpn_name}")
            
            # Route the first VPN's endpoint through the original gateway to avoid loops
            endpoint_ip = endpoint.split(':')[0]  # Extract IP from endpoint
            print(f"    [ROUTE] Adding endpoint route for {endpoint_ip} via original gateway")
            try:
                # Route WireGuard endpoint traffic through original default route
                if default_gateway and default_iface:
                    subprocess.run(['ip', 'route', 'add', endpoint_ip, 'via', default_gateway, 'dev', default_iface], check=True)
                    added_routes.append(f'{endpoint_ip} via {default_gateway} dev {default_iface}')
                else:
                    print(f"    [WARNING] Could not add endpoint route: missing gateway or interface info")
            except subprocess.CalledProcessError as e:
                if e.returncode == 2:
                    print(f"    [INFO] Endpoint route already exists")
                else:
                    print(f"    [WARNING] Could not add endpoint route: {e}")
            
            # Set up NAT for the first VPN
            subprocess.run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', vpn_name, '-j', 'MASQUERADE'], check=True)

        previous_routes.append(address)

    # After all VPNs are set up, route all internet traffic through the LAST VPN in the chain
    if vpn_count > 0:
        last_vpn_name = vpn_name_list[-1]
        print(f"\n  [FINAL ROUTE] Routing all internet traffic through final VPN: {last_vpn_name}")
        try:
            # Use split default routes to override existing default - route through the last VPN
            subprocess.run(['ip', 'route', 'add', '0.0.0.0/1', 'dev', last_vpn_name], check=True)
            subprocess.run(['ip', 'route', 'add', '128.0.0.0/1', 'dev', last_vpn_name], check=True)
            added_routes.extend([f'0.0.0.0/1 dev {last_vpn_name}', f'128.0.0.0/1 dev {last_vpn_name}'])
            print(f"  [FINAL ROUTE] Added internet routes through {last_vpn_name}")
        except subprocess.CalledProcessError as e:
            if e.returncode == 2:
                print(f"  [INFO] Default routes already exist, replacing...")
                subprocess.run(['ip', 'route', 'replace', '0.0.0.0/1', 'dev', last_vpn_name], check=True)
                subprocess.run(['ip', 'route', 'replace', '128.0.0.0/1', 'dev', last_vpn_name], check=True)
                added_routes.extend([f'0.0.0.0/1 dev {last_vpn_name}', f'128.0.0.0/1 dev {last_vpn_name}'])
                print(f"  [FINAL ROUTE] Replaced internet routes through {last_vpn_name}")
            else:
                raise

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
    global active_vpn_configs, previous_routes, added_routes, vpn_name_list, vpn_ip_list

    run_hook("pre-spin-down")

    print("\n[SHUTDOWN] Cleaning up VPNs...")

    # Clean up manually created WireGuard interfaces
    for vpn_name in vpn_name_list:
        print(f"  - Deactivating VPN [{vpn_name}]...")
        try:
            # Remove DNS settings
            remove_dns(vpn_name)
            # Delete the interface
            subprocess.run(['ip', 'link', 'delete', vpn_name], check=False)
        except Exception as e:
            print(f"    [DEBUG] Error cleaning up {vpn_name}: {e}")

    # Clean up the actual network routes we added
    for route in added_routes:
        try:
            # Parse the route string to reconstruct the delete command
            route_parts = route.split()
            if len(route_parts) >= 1:
                network = route_parts[0]
                delete_cmd = ['ip', 'route', 'del', network]
                
                # Check if route has 'via' clause and add it to delete command
                if 'via' in route_parts:
                    via_index = route_parts.index('via')
                    if via_index + 1 < len(route_parts):
                        gateway = route_parts[via_index + 1]
                        delete_cmd.extend(['via', gateway])
                
                subprocess.run(delete_cmd, check=True)
                print(f"  - Removed route: {' '.join(delete_cmd[3:])}")
        except subprocess.CalledProcessError as e:
            if e.returncode == 2:  # Route doesn't exist (idempotent)
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
    vpn_ip_list = []

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


def main():
    """Main entry point for the vpn-chainer command."""
    global vpn_count, use_fastest
    
    setproctitle("VPN-Chainer")

    check_and_install('wg', 'wireguard')
    # Check for DNS resolver (prefer systemd-resolved, fallback to resolvconf)
    if not subprocess.run(['which', 'resolvconf'], capture_output=True).returncode == 0:
        if not subprocess.run(['systemctl', 'is-active', 'systemd-resolved'], capture_output=True).returncode == 0:
            print("[INFO] No DNS resolver found. Installing systemd-resolved...")
            subprocess.run(['apt', 'update'], check=True)
            subprocess.run(['apt', 'install', '-y', 'systemd-resolved'], check=True)
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
    try:
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"[ERROR] Flask app failed to start: {e}")
        undo_vpn()
        sys.exit(1)


if __name__ == "__main__":
    main()
