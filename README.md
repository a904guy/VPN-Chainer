# **VPN-Chainer 🛡️**

## *A powerful WireGuard VPN chaining tool with dynamic routing, automated service control, and API support.*

![VPN-Chainer](https://img.shields.io/badge/Built%20for-Debian%20%7C%20Ubuntu-blue.svg?style=flat-square)
![WireGuard](https://img.shields.io/badge/Powered%20by-WireGuard-orange.svg?style=flat-square)
![Python](https://img.shields.io/badge/Made%20with-Python%203-yellow.svg?style=flat-square)

## **🔹 Overview**

VPN-Chainer allows you to **chain multiple WireGuard VPNs together**, dynamically reordering routes for improved anonymity and security. It includes **auto-installation as a system service**, API-based VPN rotation, and a customizable **pre/post spin-up/down hook system**.

Now, you can **optionally test VPN speeds** and **select the fastest VPNs** using `--fastest`.  

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

### **1️⃣ Prerequisites**

Ensure you have **Python 3** and **WireGuard** installed:

```bash
sudo apt update  
sudo apt install -y python3 python3-pip wireguard  
```

### **2️⃣ Clone & Install VPN-Chainer**

```bash
git clone https://github.com/a904guy/VPN-Chainer.git  
cd vpn-chainer  
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

