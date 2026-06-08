from flask import Blueprint, request, jsonify
from app.services.gis_orchestrator import process_coordinates, process_address

gis_bp = Blueprint('gis', __name__, url_prefix='/api/v1/gis')

@gis_bp.route('/coordinates', methods=['POST'])
async def get_by_coordinates():
    """
    Endpoint to process spatial queries via WGS84 coordinates.
    Expects JSON: {"lat": float, "lng": float}
    """
    data = request.get_json() or {}
    lat = data.get('lat')
    lng = data.get('lng')

    if lat is None or lng is None:
        return jsonify({"status": "error", "message": "Missing 'lat' or 'lng' in request body"}), 400

    try:
        # Pass control to the orchestrator pipeline
        result = await process_coordinates(float(lat), float(lng))
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": "Internal server error during coordinate processing"}), 500

@gis_bp.route('/address', methods=['POST'])
async def get_by_address():
    """
    Endpoint to process spatial queries via free-text address.
    Expects JSON: {"address": "string"}
    """
    data = request.get_json() or {}
    address = data.get('address')

    if not address or not str(address).strip():
        return jsonify({"status": "error", "message": "Missing or empty 'address' in request body"}), 400

    try:
        # Pass control to the address orchestrator pipeline
        result = await process_address(str(address).strip())
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": "Internal server error during address processing"}), 500