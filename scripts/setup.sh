#!/bin/bash

# VPN-Chainer Complete Setup Script
# This script installs prerequisites, VPN-Chainer, and sets up sudo access

echo "🛡️ VPN-Chainer Complete Setup"
echo "============================="

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a package is installed (apt)
package_installed() {
    dpkg -l "$1" 2>/dev/null | grep -q '^ii'
}

echo "🔍 Checking prerequisites..."

# Check if running as root for apt operations
if [[ $EUID -ne 0 ]]; then
    echo "❌ This script must be run as root (use sudo)"
    echo "   Example: sudo ./setup.sh"
    exit 1
fi

# Update package list
echo "📦 Updating package list..."
apt update

# Check and install WireGuard
if ! package_installed wireguard; then
    echo "📥 Installing WireGuard..."
    apt install -y wireguard
    if package_installed wireguard; then
        echo "✅ WireGuard installed successfully"
    else
        echo "❌ Failed to install WireGuard"
        exit 1
    fi
else
    echo "✅ WireGuard is already installed"
fi

# Check and install resolvconf
if ! package_installed resolvconf; then
    echo "📥 Installing resolvconf..."
    apt install -y resolvconf
    if package_installed resolvconf; then
        echo "✅ resolvconf installed successfully"
    else
        echo "❌ Failed to install resolvconf"
        exit 1
    fi
else
    echo "✅ resolvconf is already installed"
fi

# Check and install iptables
if ! package_installed iptables; then
    echo "📥 Installing iptables..."
    apt install -y iptables
    if package_installed iptables; then
        echo "✅ iptables installed successfully"
    else
        echo "❌ Failed to install iptables"
        exit 1
    fi
else
    echo "✅ iptables is already installed"
fi

# Check and install pipx
if ! package_installed pipx; then
    echo "📥 Installing pipx..."
    apt install -y pipx
    if package_installed pipx; then
        echo "✅ pipx installed successfully"
    else
        echo "❌ Failed to install pipx"
        exit 1
    fi
else
    echo "✅ pipx is already installed"
fi

# Get the actual user (not root) for pipx operations
ACTUAL_USER=${SUDO_USER:-$USER}
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

# Check if vpn-chainer is already installed via pipx
if sudo -u "$ACTUAL_USER" pipx list 2>/dev/null | grep -q "vpn-chainer"; then
    echo "✅ vpn-chainer is already installed via pipx"
else
    echo "📥 Installing vpn-chainer via pipx..."
    sudo -u "$ACTUAL_USER" pipx install vpn-chainer
    if sudo -u "$ACTUAL_USER" pipx list 2>/dev/null | grep -q "vpn-chainer"; then
        echo "✅ vpn-chainer installed successfully via pipx"
    else
        echo "❌ Failed to install vpn-chainer via pipx"
        exit 1
    fi
fi

# Ensure pipx path is configured
echo "🔧 Configuring pipx PATH..."
sudo -u "$ACTUAL_USER" pipx ensurepath

# Get the vpn-chainer path from the actual user's environment
VPN_CHAINER_PATH=$(sudo -u "$ACTUAL_USER" which vpn-chainer 2>/dev/null || echo "$ACTUAL_HOME/.local/bin/vpn-chainer")
echo "✅ Found vpn-chainer at: $VPN_CHAINER_PATH"

# Check if system-wide symlink already exists
if which vpn-chainer &> /dev/null; then
    echo "✅ vpn-chainer is already available system-wide with sudo"
    SUDO_PATH=$(which vpn-chainer)
    echo "   sudo path: $SUDO_PATH"
else
    echo "🔗 Creating system-wide symlink for sudo access..."
    ln -sf "$VPN_CHAINER_PATH" /usr/local/bin/vpn-chainer
    
    if which vpn-chainer &> /dev/null; then
        echo "✅ Successfully created symlink: /usr/local/bin/vpn-chainer -> $VPN_CHAINER_PATH"
    else
        echo "❌ Failed to create symlink"
        exit 1
    fi
fi

echo ""
echo "🎉 Setup complete! VPN-Chainer is ready to use:"
echo ""
echo "📁 Place your WireGuard config files in: /etc/wireguard/"
echo "   Example: /etc/wireguard/server1.conf"
echo ""
echo "🚀 Usage examples:"
echo "   sudo vpn-chainer 2              # Chain 2 random VPNs"
echo "   sudo vpn-chainer 3 --fastest    # Chain 3 fastest VPNs (speed tested)"
echo "   sudo vpn-chainer 1 --auto-install  # Install as system service"
echo ""
echo "🌐 API will be available at: http://your-ip:5000/rotate_vpn?key=<api-key>"
echo ""
