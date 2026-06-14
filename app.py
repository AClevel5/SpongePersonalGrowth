import os
from flask import Flask, send_from_directory
from config import Config
from extensions import db, limiter


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config.from_object(Config)

    db.init_app(app)
    limiter.init_app(app)

    from routes.auth import auth_bp
    from routes.activities import activities_bp
    from routes.completions import completions_bp
    from routes.todos import todos_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(activities_bp, url_prefix="/api")
    app.register_blueprint(completions_bp, url_prefix="/api")
    app.register_blueprint(todos_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve(path):
        if path and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=8080)
