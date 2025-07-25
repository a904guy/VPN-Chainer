# VPN-Chainer Changelog

## [Unreleased]

### Changed
- Changed hard-coded wg{i} interface naming to dynamic interface names derived from WireGuard config stems.

### Fixed
- Fixed VPN chaining routing issue where individual host addresses with CIDR notation were being used instead of proper network addresses for inter-VPN routing.
- Added error handling for existing route conflicts - now replaces conflicting routes instead of failing.
- Fixed shutdown cleanup to properly track and remove actual network routes instead of interface addresses.
- **MAJOR FIX**: Completely rewrote VPN chaining logic to properly route internet traffic through the VPN chain - traffic now flows correctly through VPN3 -> VPN2 -> VPN1 -> Internet.
- Added proper default route management using split routing (0.0.0.0/1 + 128.0.0.0/1) to override existing defaults.
- Implemented NAT (Network Address Translation) rules for proper traffic masquerading between VPN interfaces.
- Added IP forwarding configuration for each VPN interface and globally.
- Fixed DNS resolution through VPN chain by restarting DNS resolver after routing changes.
- **MAJOR REWRITE**: Replaced wg-quick usage with manual WireGuard interface creation to avoid routing conflicts.
- Fixed VPN chaining routing by implementing proper interface-to-interface routing instead of IP-based routing.
- Changed Flask server port from 5000 to 5001 to avoid common port conflicts.

---

## Format
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Types of changes
- **Added** for new features.
- **Changed** for changes in existing functionality.
- **Deprecated** for soon-to-be removed features.
- **Removed** for now removed features.
- **Fixed** for any bug fixes.
- **Security** in case of vulnerabilities.
