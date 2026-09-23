"""Dashboard page and its API endpoints."""
from flask import Blueprint, jsonify, render_template, request


def create_blueprint(feeder):
    blueprint = Blueprint("dashboard", __name__)

    @blueprint.get("/dashboard")
    def home():
        return render_template("dashboard.html", page="dashboard")

    @blueprint.get("/api/monitor")
    def monitor_api():
        feeder.start()
        return jsonify(feeder.snapshot())


    return blueprint
