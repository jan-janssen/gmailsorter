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
        "google-api-python-client==2.65.0",
        "google-auth==2.14.1",
        "google-auth-oauthlib==0.7.0",
        "numpy==1.23.4",
        "tqdm==4.64.1",
        "pandas==1.5.1",
        "scikit-learn==1.1.3",
        "sqlalchemy==1.4.42",
    ],
    cmdclass=versioneer.get_cmdclass(),
)
