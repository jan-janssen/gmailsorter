"""
Setuptools based setup module
"""
from setuptools import setup, find_packages
from pathlib import Path
import versioneer


setup(
    name="gmailsorter",
    version=versioneer.get_version(),
    description="Assign labels to emails in Google Mail based on their similarity to other emails assigned to the same label.",
    long_description=Path("README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/jan-janssen/gmailsorter",
    author="Jan Janssen",
    author_email="jan.janssen@outlook.com",
    license="BSD",
    packages=find_packages(exclude=["*tests*"]),
    package_data={
        'gmailsorter': [
            'webapp/static/css/*.css',
            'webapp/static/fonts/poppins/*.ttf',
            'webapp/static/images/*.jpg',
            'webapp/static/images/icons/*.ico',
            'webapp/templates/*.html'
        ],
    },
    install_requires=[
        "google-api-python-client==2.93.0",
        "google-auth==2.22.0",
        "google-auth-oauthlib==1.0.0",
        "numpy==1.25.1",
        "tqdm==4.65.0",
        "pandas==2.0.3",
        "scikit-learn==1.3.0",
        "sqlalchemy==2.0.18",
    ],
    extras_require={
        "webapp": ['gunicorn==20.1.0', "flask==2.3.2", "flask-login==0.6.2"],
    },
    cmdclass=versioneer.get_cmdclass(),
    entry_points={
            "console_scripts": [
                'gmailsorter=gmailsorter.__main__:command_line_parser',
                'gmailsorter-daemon=gmailsorter.daemon.__main__:command_line_parser',
                'gmailsorter-app=gmailsorter.webapp.app:run_app'
            ]
    }
)
