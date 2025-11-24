import secrets
from flask import Flask
from database.mongo_conn import init_app
from controllers.task_controller import task_bp
from controllers.dashboard_controller import dashboard_bp
from controllers.goal_controller import goal_bp  
from controllers.calendar_controller import calendar_bp
from controllers.stats_controller import stats_bp


app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
local, remote = init_app(app)
app.mongo_local = local
app.mongo_remote = remote

app.register_blueprint(task_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(goal_bp) 
app.register_blueprint(calendar_bp) 
app.register_blueprint(stats_bp)


if __name__ == "__main__":
    app.run(debug=True)