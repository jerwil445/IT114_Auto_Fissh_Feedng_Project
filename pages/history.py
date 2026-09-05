"""History page and its API endpoints."""
from flask import Blueprint, jsonify, render_template, request


def create_blueprint(feeder):
    blueprint = Blueprint("history", __name__)

    @blueprint.get("/history")
    def history_page():
        return render_template("history.html", page="history")

    @blueprint.get("/api/history")
    def history_api():
        before = request.args.get("before", type=int)
        if "before" in request.args and (before is None or before < 1):
            return jsonify(message="Invalid history cursor."), 400
        return jsonify(feeder.history(before=before))


    return blueprint
