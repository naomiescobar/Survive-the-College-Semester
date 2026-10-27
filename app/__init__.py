from flask import Flask
from flask_wtf import CSRFProtect
from .config import Config

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    csrf.init_app(app)
    from .auth import auth
    app.register_blueprint(auth)
    # register your routes/blueprints here, for example:
    # from .auth import auth
    # app.register_blueprint(auth)

    return app