"""Package setup for Full SEO Automation."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [
        line.strip()
        for line in fh
        if line.strip() and not line.startswith("#")
    ]

# Separate test dependencies
test_requirements = [
    "pytest>=8.0.0,<9.0",
    "pytest-asyncio>=0.23.0,<1.0",
    "pytest-cov>=4.1.0,<6.0",
]

setup(
    name="full-seo-automation",
    version="1.0.0",
    author="SEO Automation Team",
    author_email="seo-automation@example.com",
    description=(
        "A comprehensive, AI-powered SEO automation platform — "
        "research, content, audits, rank tracking & reporting."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/loydz21/Full-SEO-Automation",
    project_urls={
        "Bug Tracker": "https://github.com/loydz21/Full-SEO-Automation/issues",
        "Source Code": "https://github.com/loydz21/Full-SEO-Automation",
    },
    packages=find_packages(exclude=["tests", "tests.*", "docs", "scripts"]),
    python_requires=">=3.10",
    install_requires=[r for r in requirements if "pytest" not in r],
    extras_require={
        "test": test_requirements,
        "dev": test_requirements + [
            "black",
            "flake8",
            "isort",
            "mypy",
        ],
    },
    entry_points={
        "console_scripts": [
            "seo=src.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.yaml", "*.yml", "*.json", "*.html", "*.jinja2", "*.j2"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Topic :: Internet :: WWW/HTTP :: Indexing/Search",
        "Topic :: Internet :: WWW/HTTP :: Site Management",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Framework :: Pytest",
        "Typing :: Typed",
    ],
    keywords=[
        "seo", "automation", "keyword-research", "content-generation",
        "rank-tracking", "technical-audit", "link-building", "local-seo",
        "ai", "openai", "gemini", "streamlit", "dashboard",
    ],
)
