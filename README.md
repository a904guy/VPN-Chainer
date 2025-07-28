# **VPN-Chainer 🛡️**

## *A powerful WireGuard VPN chaining tool with dynamic routing, automated service control, and API support.*

![VPN-Chainer](https://img.shields.io/badge/Built%20for-Debian%20%7C%20Ubuntu-blue.svg?style=flat-square)
![WireGuard](https://img.shields.io/badge/Powered%20by-WireGuard-orange.svg?style=flat-square)
![Python](https://img.shields.io/badge/Made%20with-Python%203-yellow.svg?style=flat-square)
![PyPI](https://img.shields.io/badge/Available%20on-PyPI-green.svg?style=flat-square)

## **🔹 Overview**

VPN-Chainer allows you to **chain multiple WireGuard VPNs together**, dynamically reordering routes for improved anonymity and security. It includes **auto-installation as a system service**, API-based VPN rotation, and a customizable **pre/post spin-up/down hook system**.

Now, you can **optionally test VPN speeds** and **select the fastest VPNs** using `--fastest`.  

**📦 Available on PyPI** - Install easily with `pip install vpn-chainer`  

---

## **⚡ Features**

✅ **Multi-Hop VPN Chaining** – Connect through multiple WireGuard VPNs in random order.  
✅ **Speed-Tested VPN Selection** – Use `--fastest` to pick the top VPNs based on download speed.  
✅ **Automatic Routing & Firewall Rules** – Seamless packet forwarding between VPN interfaces.  
✅ **Pre/Post Execution Hooks** – Run custom scripts **before and after** VPN chain events.  
✅ **Remote API Support** – Securely rotate VPNs via a web API.  
✅ **Auto-Installation as a Systemd Service** – Persistently run VPN-Chainer in the background.  

---

## **🚀 Installation**

### **🌟 Automated Setup Script (Recommended)**

This script automatically installs all prerequisites (WireGuard, systemd-resolved, iptables), VPN-Chainer via pipx, and sets up sudo access:

```bash
curl -s https://raw.githubusercontent.com/a904guy/VPN-Chainer/main/scripts/setup.sh | sudo bash
```

### ** Prerequisites (Manual Installation)**

If you prefer manual installation, ensure you have **Python 3** and **WireGuard** installed:

```bash
sudo apt update  
sudo apt install -y python3 python3-pip wireguard  
```

### ** Install VPN-Chainer from PyPI**

**Easy installation via pip:**

```bash
sudo pip install vpn-chainer
```

### ** Alternative: Install from Source**

If you prefer to install from source:

```bash
git clone https://github.com/a904guy/VPN-Chainer.git  
cd VPN-Chainer  
sudo python3 setup.py install
```

---

## **🛠️ Usage**

### **🔹 Basic Usage**

```bash
sudo vpn-chainer <number_of_vpns>  
```

For example, to create a **3-hop VPN chain**:  

```bash
sudo vpn-chainer 3  
```

### **🔹 Use Speed Testing to Select Fastest VPNs**

To **test all VPNs first** and **pick the top N fastest VPNs**, use `--fastest`:  

```bash
sudo vpn-chainer 3 --fastest  
```

🚀 **This will:**
- Test **all available VPNs** in `/etc/wireguard/`
- Select **the top 3 fastest VPNs**
- Use them in the **VPN chain**

### **🔹 Install as a Systemd Service**

Automatically install and enable the VPN-Chainer service:  

```bash
sudo vpn-chainer 3 --auto-install  
```

Once installed, it will **start automatically on boot**.

To **stop or restart** the service:  

```bash
sudo systemctl stop vpn-chainer  
sudo systemctl restart vpn-chainer  
```

To **view logs**:  

```bash
sudo journalctl -u vpn-chainer -f  
```

---

## **📋 Example Execution**

Here's what a typical VPN-Chainer session looks like when chaining 5 VPNs: (Note: PII has been randomized)

```bash
$ sudo vpn-chainer 5
[HOOK] No pre-spin-up script found. Skipping.
[DEBUG] Checking directory: /etc/wireguard
[DEBUG] Found 12 config files

[SETUP] Establishing VPN Chain...
  [INFO] Saved original default route: default via 192.168.1.1 dev eth0 proto dhcp src 192.168.1.100 metric 100
  [INFO] Parsed gateway: 192.168.1.1, interface: eth0
  [INFO] VPN Chain Order: Singapore -> Germany -> Netherlands -> Canada -> Japan
  [INFO] Endpoint IPs: 45.76.123.45 -> 185.220.101.67 -> 91.132.144.89 -> 198.244.131.205 -> 103.195.236.78
  - Setting up VPN [Singapore] at 10.13.9.142/24...
net.ipv4.conf.Singapore.forwarding = 1
    [INFO] Waiting for WireGuard handshake...
    [ROUTE] Setting up first VPN Singapore
    [ROUTE] Adding endpoint route for 45.76.123.45 via original gateway
  - Setting up VPN [Germany] at 10.13.79.88/24...
net.ipv4.conf.Germany.forwarding = 1
    [INFO] Waiting for WireGuard handshake...
    [ROUTE] Setting up chaining: Germany -> Singapore -> Internet
    [ROUTE] Adding endpoint route for 185.220.101.67 through Singapore
  - Setting up VPN [Netherlands] at 10.13.58.203/24...
net.ipv4.conf.Netherlands.forwarding = 1
    [INFO] Waiting for WireGuard handshake...
    [ROUTE] Setting up chaining: Netherlands -> Germany -> Internet
    [ROUTE] Adding endpoint route for 91.132.144.89 through Germany
  - Setting up VPN [Canada] at 10.13.114.51/24...
net.ipv4.conf.Canada.forwarding = 1
    [INFO] Waiting for WireGuard handshake...
    [ROUTE] Setting up chaining: Canada -> Netherlands -> Internet
    [ROUTE] Adding endpoint route for 198.244.131.205 through Netherlands
  - Setting up VPN [Japan] at 10.13.80.177/24...
net.ipv4.conf.Japan.forwarding = 1
    [INFO] Waiting for WireGuard handshake...
    [ROUTE] Setting up chaining: Japan -> Canada -> Internet
    [ROUTE] Adding endpoint route for 103.195.236.78 through Canada

  [FINAL ROUTE] Routing all internet traffic through final VPN: Japan
  [FINAL ROUTE] Added internet routes through Japan
net.ipv4.ip_forward = 1
[HOOK] No post-spin-up script found. Skipping.

[INFO] VPN Chain Established Successfully!
  [VPN Route]  Singapore -> Germany -> Netherlands -> Canada -> Japan
  [IP Route]   10.13.9.142/24 -> 10.13.79.88/24 -> 10.13.58.203/24 -> 10.13.114.51/24 -> 10.13.80.177/24
  [INFO] All internet traffic now routed through VPN chain

[INFO] VPN-Chainer API running at: http://192.168.1.100:5000/rotate_vpn?key=a1b2c3d4-e5f6-7890-abcd-ef1234567890

 * Serving Flask app 'vpn_chainer.vpn_chainer'
 * Debug mode: off
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://10.13.80.177:5000
Press CTRL+C to quit
^C[HOOK] No pre-spin-down script found. Skipping.

[SHUTDOWN] Cleaning up VPNs...
  - Deactivating VPN [Singapore]...
  - Deactivating VPN [Germany]...
  - Deactivating VPN [Netherlands]...
  - Deactivating VPN [Canada]...
  - Deactivating VPN [Japan]...
  - Removed route: 45.76.123.45 via 192.168.1.1
  - Route 185.220.101.67 dev Singapore already removed
  - Route 91.132.144.89 dev Germany already removed
  - Route 198.244.131.205 dev Netherlands already removed
  - Route 103.195.236.78 dev Canada already removed
  - Route 0.0.0.0/1 dev Japan already removed
  - Route 128.0.0.0/1 dev Japan already removed
  - Cleaning up iptables rules...
  - Restarted DNS resolver
[HOOK] No post-spin-down script found. Skipping.
```

**Key Points from the Output:**
- 🔍 **Discovery**: Found 12 WireGuard config files in `/etc/wireguard/`
- 🌐 **Chain Creation**: Established 5-hop VPN chain: Singapore → Germany → Netherlands → Canada → Japan
- 🔒 **Security**: Each VPN's endpoint is routed through the previous VPN to prevent leaks
- 📡 **API Access**: Web API available for remote VPN rotation with unique key
- 🧹 **Clean Shutdown**: Proper cleanup when interrupted with Ctrl+C

---

## **🔗 API Usage**

### **Rotate VPN Remotely**

VPN-Chainer provides an **API to trigger VPN rotations**. The API key is displayed on startup:

```bash
[INFO] VPN-Chainer API running at:  
🔗 http://127.0.0.1:5000/rotate_vpn?key=6a1f-45e9...  
```

To rotate VPNs:  

```bash
curl -X GET "http://127.0.0.1:5000/rotate_vpn?key=YOUR_API_KEY"  
```

This will:
- **Tear down** the current VPN chain.  
- **Randomly select new VPN configs** *(or use fastest if started with `--fastest`)*.  
- **Reestablish routing and firewall rules**.  

---

## **⚙️ Hook System (Pre/Post Execution Scripts)**

VPN-Chainer allows you to **run scripts before and after VPN activation/deactivation**.

### **🔹 Hook Script Locations**

Scripts should be placed in:

```bash
/etc/vpn-chainer/hooks/  
```

| Hook Script Name       | Triggered When |
|------------------------|------------------------------------|
| pre-spin-up.sh      | Before the VPN chain starts |
| post-spin-up.sh     | After the VPN chain is established |
| pre-spin-down.sh    | Before VPNs are torn down |
| post-spin-down.sh   | After all VPNs have shut down |

### **🔹 Example Hook: Restart Tor After VPN Starts**

Edit `/etc/vpn-chainer/hooks/post-spin-up.sh`:  

```bash
# !/bin/bash  

echo "[HOOK] Restarting Tor for anonymity..."  
systemctl restart tor  
```

Then **enable the hook**:  

```bash
chmod +x /etc/vpn-chainer/hooks/post-spin-up.sh  
```

---

## **📂 Configuration Files**

VPN-Chainer automatically selects **random WireGuard config files** from:  
/etc/wireguard/*.conf  

Ensure that **at least the number of VPN configs requested exists**.
Additionally the **Address** line is required.

Example VPN config:

```yaml
[Interface]  
PrivateKey = <YOUR_PRIVATE_KEY>  
Address = 10.13.36.109/24  
DNS = 10.8.0.1  

[Peer]  
PublicKey = <PEER_PUBLIC_KEY>  
Endpoint = 10.10.10.24:51820  
AllowedIPs = 0.0.0.0/0  
PersistentKeepalive = 25  
```

---

## **❓ Troubleshooting**

### **🔸 VPN Doesn't Start**

- Check that you have **WireGuard installed**:  

```bash
which wg  
```

If missing, install it:  

```bash
sudo apt install wireguard  
```

- Ensure you have **enough VPN config files** in `/etc/wireguard/`.

### **🔸 Systemd Service Not Running**

- Check status:  

```bash
sudo systemctl status vpn-chainer  
```

- Restart it:  

```bash
sudo systemctl restart vpn-chainer  
```

### **🔸 API Not Responding**

- Ensure VPN-Chainer is running:  

```bash
sudo systemctl status vpn-chainer  
```

- Check firewall rules (port `5000` must be open):  

```bash
sudo ufw allow 5000/tcp  
```

---

## **📜 Roadmap**

✔️ **Multi-Hop Randomization**  
✔️ **Pre/Post Execution Hooks**  
✔️ **Auto-Install as a Systemd Service**  
✔️ **Speed-Tested VPN Selection (`--fastest`) (Added in v1.1)**  
🔜 **Web Dashboard for Control & Logs**  
🔜 **VPN Failover Detection ❓❓**  
🔜 **Split-Tunneling (Selective Routing) ❓❓**  
🔜 **Submit Your Ideas Via Issues**  

---

## **🤝 Contributing**

Want to improve VPN-Chainer? Contributions are welcome! Fork the repository and submit a PR.

1. **Fork & Clone**  
git clone https://github.com/a904guy/VPN-Chainer.git 
cd vpn-chainer  

2. **Make Changes & Test**  
sudo python3 vpn-chainer.py 3  

3. **Submit a Pull Request**  

---

## **📜 License**

This project is licensed under the **MIT License**.

---

## **👨‍💻 Author**

💡 Created by **Andy Hawkins**  
🌐 GitHub: [a904guy GitHub Profile](https://github.com/a904guy)  

---

🚀 **VPN-Chainer is your ultimate tool for anonymous, multi-hop VPN tunneling!** 🔥
💬 Have questions or feature requests? Open an **Issue** on GitHub! 😎

