# setup.py
from setuptools import setup, find_packages

setup(
    name="vinpave",
    version="2.1",
    author="Vineeth Kumar Peta",
    description="Professional Pavement Design Software - IITPAVE Integration",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/YOUR_USERNAME/vinpave",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Civil Engineers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.21.0",
        "matplotlib>=3.5.0", 
        "pandas>=1.3.0",
    ],
    entry_points={
        "console_scripts": [
            "vinpave=vinpave:main",
        ],
    },
)