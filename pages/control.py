"""Control page and its API endpoints."""
from flask import Blueprint, jsonify, render_template, request


def create_blueprint(feeder):
    blueprint = Blueprint("control", __name__)

    @blueprint.get("/control")
    def control_page():
        return render_template("control.html", page="control")

    @blueprint.route("/api/settings", methods=["GET", "POST"])
    def settings_api():
        if request.method == "GET":
            return jsonify(feeder.settings())
        try:
            return jsonify(feeder.save(request.get_json(silent=True)))
        except ValueError as exc:
            return jsonify(message=str(exc)), 400

    @blueprint.post("/api/feed")
    def feed_api():
        if not feeder.begin_feed():
            return jsonify(message="A feeding is already in progress."), 409
        return jsonify(message="Dispensing requested. Watch the status for confirmation."), 202


    return blueprint
