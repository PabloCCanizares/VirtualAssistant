import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask

from bootstrap import env_int, load_project_env
from config.storage import configure_storage
from database.mongo_conn import init_app


def _register_blueprints(flask_app: Flask) -> None:
    from controllers.ai_chat_controller import ai_chat_bp
    from controllers.calendar_controller import calendar_bp
    from controllers.category_controller import category_bp
    from controllers.dashboard_controller import dashboard_bp
    from controllers.goal_controller import goal_bp
    from controllers.project_controller import project_bp
    from controllers.stats_controller import stats_bp
    from controllers.task_controller import task_bp
    from controllers.config_controller import config_bp

    flask_app.register_blueprint(task_bp)
    flask_app.register_blueprint(dashboard_bp)
    flask_app.register_blueprint(goal_bp)
    flask_app.register_blueprint(project_bp)
    flask_app.register_blueprint(calendar_bp)
    flask_app.register_blueprint(stats_bp)
    flask_app.register_blueprint(category_bp)
    flask_app.register_blueprint(ai_chat_bp)
    flask_app.register_blueprint(config_bp)


load_project_env(Path(__file__).resolve().parent)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

local, remote = init_app(app)
app.mongo_local = local
app.mongo_remote = remote

configure_storage(app, env_int)
_register_blueprints(app)


@app.context_processor
def inject_now():
    return {"now": datetime.now}


if __name__ == "__main__":
    app.run()
