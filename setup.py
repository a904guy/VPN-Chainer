from setuptools import setup, find_packages

setup(
    name='vpn-chainer',
    version='1.1.0',
    description='A tool to chain multiple WireGuard VPNs and rotate them dynamically via API.',
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author='Andy Hawkins',
    author_email='andy+vpnchainer@hawkins.app',
    url='https://github.com/a904guy/VPN-Chainer',
    packages=find_packages(),
    scripts=['vpn-chainer.py'],
    install_requires=[
        'Flask',
        'setproctitle',
        'speedtest-cli'
    ],
    entry_points={
        'console_scripts': [
            'vpn-chainer = vpn-chainer.main:main',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Topic :: Internet :: Proxy Servers',
        'Topic :: Security',
        'Topic :: System :: Networking',
    ],
    python_requires='>=3.6',
    include_package_data=True,
)
