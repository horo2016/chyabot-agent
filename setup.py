#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="choyabot-agent-framework",
    version="1.0.0",
    description="ChoyaBot Agent Framework - Robot Agent with dynamic skills",
    author="reeman",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        #"pyyaml>=6.0",
        "requests>=2.28.0",
        "watchdog>=3.0.0",
        #"rospy",           # ROS1
        #"std_msgs",
        #"geometry_msgs",
        "sounddevice==0.5.5",
        "numpy>=1.24.4",
        "pvporcupine==1.9.5",
        "faster-whisper==1.1.0",
        "pyttsx3",
    ],
    entry_points={
        "console_scripts": [
            "choya=choyabot_agent_framework.__main__:main",
        ],
    },
    python_requires=">=3.8",
)