"""Hardware page and its API endpoints."""
from flask import Blueprint, jsonify, render_template, request


def create_blueprint(feeder):
    blueprint = Blueprint("hardware", __name__)

    @blueprint.get("/hardware-test")
    def hardware_page():
        return render_template("hardware.html", page="hardware")

    @blueprint.post("/api/hardware-test/<component>")
    def hardware_test_api(component):
        try:
            if not feeder.begin_test(component):
                return jsonify(message="A feeding or hardware test is already running."), 409
        except ValueError as exc:
            return jsonify(message=str(exc)), 400
        return jsonify(message="Hardware test started."), 202

    @blueprint.post("/api/hardware-test-cancel")
    def cancel_test_api():
        feeder.test_cancel.set()
        return jsonify(message="Stopping tests. Waiting for the current command and its off/stop response.")


    return blueprint
