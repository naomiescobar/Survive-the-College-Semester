# Survive-the-College-Semester
CSC335 Fall 2026 Final Project

## Setup
1. Create a virtual environment and install packages:
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
2. Create the database by running the CREATE statements in database_setup.sql in MySQL.
3. Copy .env.example to .env and fill in your own values.
   Generate a secret key with:
   python -c "import secrets; print(secrets.token_hex(16))"
4. Run the app: python app.py