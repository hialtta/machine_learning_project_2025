"# machine_learning_project_2025" 
## Setup
1. python -m venv venv
2. venv\Scripts\activate
3. pip install -r requirements.txt
4. buat file .env pada route / isinya:
FLASK_ENV=development
SECRET_KEY=admin
DATABASE_URL=postgresql+pg8000://postgres:admin@localhost:5432/CVProjectDB
OPENAI_API_KEY=your_api_key_here
5. flask run
6. Jangan lupa untuk menyalakan server llama 3 pada env local anda
cmd> ollama run llama3

