from flask import Flask
from config import Config

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register Blueprints
    from app.api.gis_routes import gis_bp
    app.register_blueprint(gis_bp)

    @app.route('/health', methods=['GET'])
    def health_check():
        return {"status": "healthy", "service": "byggsvar-backend"}, 200

    return app