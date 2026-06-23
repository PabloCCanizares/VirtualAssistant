import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask

from bootstrap import env_int, load_project_env
from config.storage import configure_storage


def _register_blueprints(flask_app: Flask) -> None:
    from controllers.ai_chat_controller import ai_chat_bp
    from controllers.calendar_controller import calendar_bp
    from controllers.category_controller import category_bp
    from controllers.config_controller import config_bp
    from controllers.dashboard_controller import dashboard_bp
    from controllers.goal_controller import goal_bp
    from controllers.project_controller import project_bp
    from controllers.stats_controller import stats_bp
    from controllers.task_controller import task_bp

    flask_app.register_blueprint(task_bp)
    flask_app.register_blueprint(dashboard_bp)
    flask_app.register_blueprint(goal_bp)
    flask_app.register_blueprint(project_bp)
    flask_app.register_blueprint(calendar_bp)
    flask_app.register_blueprint(stats_bp)
    flask_app.register_blueprint(category_bp)
    flask_app.register_blueprint(ai_chat_bp)
    flask_app.register_blueprint(config_bp)


def create_app(base_dir: Path | None = None, *, load_env: bool = True) -> Flask:
    app_base_dir = base_dir or Path(__file__).resolve().parent
    if load_env:
        load_project_env(app_base_dir)

    flask_app = Flask(__name__)
    flask_app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

    from database.mongo_conn import init_app

    local, remote = init_app(flask_app)
    flask_app.mongo_local = local
    flask_app.mongo_remote = remote

    configure_storage(flask_app, env_int)
    _register_blueprints(flask_app)

    @flask_app.context_processor
    def inject_now():
        return {"now": datetime.now}

    return flask_app


app = create_app()


if __name__ == "__main__":
    app.run()
