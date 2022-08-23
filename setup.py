"""
Setuptools based setup module
"""
from setuptools import setup, find_packages
from pathlib import Path
import versioneer


setup(
    name="pygmailsorter",
    version=versioneer.get_version(),
    description="Assign labels to emails in Google Mail based on their similarity to other emails assigned to the same label.",
    long_description=Path("README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/jan-janssen/pygmailsorter",
    author="Jan Janssen",
    author_email="jan.janssen@outlook.com",
    license="BSD",
    packages=find_packages(exclude=["*tests*"]),
    install_requires=[
        "google-api-python-client==2.58.0",
        "google-auth==2.11.0",
        "google-auth-oauthlib==0.5.2",
        "numpy==1.23.2",
        "tqdm==4.64.0",
        "pandas==1.4.3",
        "scikit-learn==1.1.2",
        "sqlalchemy==1.4.40",
    ],
    cmdclass=versioneer.get_cmdclass(),
)
