from flask import Blueprint, jsonify, request

from model.category_model import CategoryModel
from services.user_context import current_user_id

category_bp = Blueprint("category_bp", __name__, url_prefix="/categories")
DEFAULT_USER_ID = current_user_id()


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
        categories = CategoryModel.get_all_categories(usuario_id=current_user_id())
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
        categories = CategoryModel.search_by_name(query, usuario_id=current_user_id())
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
        category = CategoryModel.get_category_by_id(category_id, usuario_id=current_user_id())
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
        if CategoryModel.exists_by_name(name, usuario_id=current_user_id()):
            return jsonify({
                "success": False,
                "message": f"Ya existe una categoria con el nombre '{name}'"
            }), 409

        category = CategoryModel.insert_category(name, usuario_id=current_user_id())
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

        category = CategoryModel.update_category(category_id, name, usuario_id=current_user_id())
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
# API: VERIFICAR USO DE CATEGORIA
# -------------------------------------------------------------
@category_bp.route("/api/usage/<category_id>", methods=["GET"])
def api_get_category_usage(category_id):
    """
    API JSON que devuelve el número de objetivos, tareas y proyectos
    que tienen asignada esta categoría.
    Response: { "success": true, "usage": { "goals": N, "tasks": N, "projects": N, "total": N } }
    """
    try:
        # Verificar que la categoría existe
        category = CategoryModel.get_category_by_id(category_id, usuario_id=current_user_id())
        if not category:
            return jsonify({
                "success": False,
                "message": "Categoria no encontrada"
            }), 404

        usage = CategoryModel.get_category_usage(category_id, usuario_id=current_user_id())
        return jsonify({
            "success": True,
            "category": _serialize_category(category),
            "usage": usage
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error al verificar uso de categoria: {str(e)}"
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
        print(f"[DELETE CATEGORY] Iniciando eliminación de categoria: {category_id}")

        # Verificar que existe
        existing = CategoryModel.get_category_by_id(category_id)
        if not existing:
            print(f"[DELETE CATEGORY] Categoria no encontrada: {category_id}")
            return jsonify({
                "success": False,
                "message": "Categoria no encontrada"
            }), 404

        print(f"[DELETE CATEGORY] Categoria encontrada, procediendo a eliminar: {existing.get('name', 'N/A')}")

        deleted = CategoryModel.delete_category(category_id, usuario_id=current_user_id())

        if not deleted:
            print(f"[DELETE CATEGORY] delete_category retornó False para: {category_id}")
            return jsonify({
                "success": False,
                "message": "No se pudo eliminar la categoria"
            }), 500

        print(f"[DELETE CATEGORY] Categoria eliminada exitosamente: {category_id}")
        return jsonify({
            "success": True,
            "message": "Categoria eliminada correctamente"
        })

    except Exception as e:
        print(f"[DELETE CATEGORY] Excepción al eliminar categoria {category_id}: {str(e)}")
        import traceback
        traceback.print_exc()
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

        categories = CategoryModel.get_categories_by_ids(ids, usuario_id=current_user_id())
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
