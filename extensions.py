from flask_socketio import SocketIO
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

socketio = SocketIO(cors_allowed_origins="*")
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
