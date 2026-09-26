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
        page = request.args.get("page", default=1, type=int)
        limit = request.args.get("limit", default=10, type=int)
        kind = request.args.get("kind") or None

        if "before" in request.args and (before is None or before < 1):
            return jsonify(message="Invalid history cursor."), 400
        if page is None or page < 1:
            return jsonify(message="Page must be 1 or greater."), 400
        if limit is None or limit < 1 or limit > 100:
            return jsonify(message="Limit must be between 1 and 100."), 400

        try:
            return jsonify(feeder.history(before=before, page=page if before is None else None, limit=limit, kind=kind))
        except ValueError as exc:
            return jsonify(message=str(exc)), 400


    return blueprint
