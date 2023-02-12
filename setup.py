"""
Setup script for Blackbird Search Engine
"""

from setuptools import setup, find_packages

setup(
    name="blackbird",
    version="1.0.0",
    description="A high-performance code search engine inspired by GitHub's Blackbird",
    author="Blackbird Team",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "gitpython>=3.1.40",
        "pydantic>=2.5.0",
        "python-multipart>=0.0.6",
        "mmh3>=4.0.1",
        "xxhash>=3.4.1",
        "aiosqlite>=0.19.0",
        "python-dotenv>=1.0.0",
        "structlog>=23.2.0",
        "rich>=13.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-benchmark>=4.0.0",
            "pytest-cov>=4.1.0",
            "mypy>=1.7.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "blackbird=blackbird.main:main",
        ]
    },
    include_package_data=True,
    package_data={
        "blackbird": ["web/*"],
    },
)
