from flask import Blueprint, request, jsonify, flash, redirect, url_for
from model.category_model import CategoryModel

category_bp = Blueprint("category_bp", __name__, url_prefix="/categories")


def _serialize_category(category):
    """Convierte una categoria de MongoDB a un dict serializable."""
    if not category:
        return None
    cat_view = dict(category)
    if "_id" in cat_view:
        cat_view["_id"] = str(cat_view["_id"])
    return cat_view


# -------------------------------------------------------------
# API: OBTENER TODAS LAS CATEGORIAS
# -------------------------------------------------------------
@category_bp.route("/api/all", methods=["GET"])
def api_get_all_categories():
    """
    API JSON que devuelve todas las categorias.
    Response: { "success": true, "categories": [...] }
    """
    try:
        categories = CategoryModel.get_all_categories()
        categories_view = [_serialize_category(c) for c in categories]
        return jsonify({
            "success": True,
            "categories": categories_view
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al obtener categorias: {str(e)}"
        }), 500


# -------------------------------------------------------------
# API: BUSCAR CATEGORIAS POR NOMBRE
# -------------------------------------------------------------
@category_bp.route("/api/search", methods=["GET"])
def api_search_categories():
    """
    API JSON que busca categorias por nombre.
    Params: ?q=texto
    Response: { "success": true, "categories": [...] }
    """
    try:
        query = request.args.get("q", "").strip()
        categories = CategoryModel.search_by_name(query)
        categories_view = [_serialize_category(c) for c in categories]
        return jsonify({
            "success": True,
            "categories": categories_view
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al buscar categorias: {str(e)}"
        }), 500


# -------------------------------------------------------------
# API: OBTENER CATEGORIA POR ID
# -------------------------------------------------------------
@category_bp.route("/api/<category_id>", methods=["GET"])
def api_get_category(category_id):
    """
    API JSON que devuelve una categoria por ID.
    Response: { "success": true, "category": {...} }
    """
    try:
        category = CategoryModel.get_category_by_id(category_id)
        if not category:
            return jsonify({
                "success": False,
                "message": "Categoria no encontrada"
            }), 404
        return jsonify({
            "success": True,
            "category": _serialize_category(category)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al obtener categoria: {str(e)}"
        }), 500


# -------------------------------------------------------------
# API: CREAR CATEGORIA
# -------------------------------------------------------------
@category_bp.route("/api/add", methods=["POST"])
def api_add_category():
    """
    API JSON para crear una nueva categoria.
    Body: { "name": "Nombre de la categoria" }
    Response: { "success": true, "category": {...} }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "message": "No se recibieron datos"
            }), 400

        name = data.get("name", "").strip()
        if not name:
            return jsonify({
                "success": False,
                "message": "El nombre de la categoria es obligatorio"
            }), 400

        # Verificar si ya existe
        if CategoryModel.exists_by_name(name):
            return jsonify({
                "success": False,
                "message": f"Ya existe una categoria con el nombre '{name}'"
            }), 409

        category = CategoryModel.insert_category(name)
        if not category:
            return jsonify({
                "success": False,
                "message": "No se pudo crear la categoria"
            }), 500

        return jsonify({
            "success": True,
            "message": "Categoria creada correctamente",
            "category": _serialize_category(category)
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al crear categoria: {str(e)}"
        }), 500


# -------------------------------------------------------------
# API: ACTUALIZAR CATEGORIA
# -------------------------------------------------------------
@category_bp.route("/api/update/<category_id>", methods=["POST", "PUT"])
def api_update_category(category_id):
    """
    API JSON para actualizar una categoria.
    Body: { "name": "Nuevo nombre" }
    Response: { "success": true, "category": {...} }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "message": "No se recibieron datos"
            }), 400

        name = data.get("name", "").strip()
        if not name:
            return jsonify({
                "success": False,
                "message": "El nombre de la categoria es obligatorio"
            }), 400

        # Verificar que existe
        existing = CategoryModel.get_category_by_id(category_id)
        if not existing:
            return jsonify({
                "success": False,
                "message": "Categoria no encontrada"
            }), 404

        category = CategoryModel.update_category(category_id, name)
        if not category:
            return jsonify({
                "success": False,
                "message": f"Ya existe otra categoria con el nombre '{name}'"
            }), 409

        return jsonify({
            "success": True,
            "message": "Categoria actualizada correctamente",
            "category": _serialize_category(category)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al actualizar categoria: {str(e)}"
        }), 500


# -------------------------------------------------------------
# API: ELIMINAR CATEGORIA
# -------------------------------------------------------------
@category_bp.route("/api/delete/<category_id>", methods=["POST", "DELETE"])
def api_delete_category(category_id):
    """
    API JSON para eliminar una categoria.
    Response: { "success": true, "message": "..." }
    """
    try:
        # Verificar que existe
        existing = CategoryModel.get_category_by_id(category_id)
        if not existing:
            return jsonify({
                "success": False,
                "message": "Categoria no encontrada"
            }), 404

        deleted = CategoryModel.delete_category(category_id)
        if not deleted:
            return jsonify({
                "success": False,
                "message": "No se pudo eliminar la categoria"
            }), 500

        return jsonify({
            "success": True,
            "message": "Categoria eliminada correctamente"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al eliminar categoria: {str(e)}"
        }), 500


# -------------------------------------------------------------
# API: OBTENER MULTIPLES CATEGORIAS POR IDs
# -------------------------------------------------------------
@category_bp.route("/api/by-ids", methods=["POST"])
def api_get_categories_by_ids():
    """
    API JSON que devuelve multiples categorias por sus IDs.
    Body: { "ids": ["id1", "id2", ...] }
    Response: { "success": true, "categories": [...] }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "message": "No se recibieron datos"
            }), 400

        ids = data.get("ids", [])
        if not ids:
            return jsonify({
                "success": True,
                "categories": []
            })

        categories = CategoryModel.get_categories_by_ids(ids)
        categories_view = [_serialize_category(c) for c in categories]
        return jsonify({
            "success": True,
            "categories": categories_view
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al obtener categorias: {str(e)}"
        }), 500
