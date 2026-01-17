from flask import Flask
from config import Config
from .models import db

def create_app():
    app = Flask(__name__)

    # # Config dasar (bisa dipindah ke config.py)
    # app.config['SECRET_KEY'] = 'firstflaskapp'
    # app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql+pg8000://username:password@localhost:5432/nama_database"

    app.config.from_object(Config)

    # Init DB
    db.init_app(app)

    # Import routes
    from .routes import main
    app.register_blueprint(main)

    return app