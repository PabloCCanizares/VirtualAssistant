from database.mongo_conn import get_collection, sync_to_remote, sync_from_remote
from bson import ObjectId
from datetime import datetime

class GoalModel:
    """Gestión de la colección 'Goals'."""
    COLLECTION = "Goals"

    @staticmethod
    def get_by_user_id(user_id):
        """
        Devuelve la lista de goals para un usuario dado.
        - user_id: str | ObjectId
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)

        uid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id

        # La colección de ejemplo muestra id_usuario como ObjectId
        # Orden sugerido: por fecha_inicio descendente (ajústalo si prefieres)
        cursor = local_col.find({"id_usuario": uid}).sort("fecha_inicio", -1)
        return list(cursor)
    

    # -------------------------------------------------------------
    #  OBTENER TODAS
    # -------------------------------------------------------------
    @staticmethod
    def get_all_goals():
        """
        Devuelve todas las tareas almacenadas localmente.
        (No descarga desde remoto automáticamente.)
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        return list(local_col.find())
    
    @staticmethod
    def insert_goal(goal_data):
        """
        Inserta un objetivo en la base local y lo sincroniza con la remota si está disponible.
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)

        # Insertar en local
        result = local_col.insert_one(goal_data)
        goal_data["_id"] = result.inserted_id

        # Sincronizar con la nube
        sync_to_remote(GoalModel.COLLECTION, goal_data)

        print(f"🎯 Objetivo insertado localmente y sincronizado: {goal_data['_id']}")
        return goal_data
    
    
    @staticmethod
    def update_goal(goal_id, updates: dict):
        """
        Actualiza un objetivo localmente y sincroniza los cambios con la base remota.
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        _id = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id

        # --- Normalización suave de campos si existen en 'updates'
        norm = dict(updates) if updates else {}

        # Fechas (acepta 'YYYY-MM-DD' o ISO 8601)
        def _parse_date(v):
            if not v:
                return None
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v).replace("Z", "").strip())
            except Exception:
                return None

        if "fecha_inicio" in norm:
            norm["fecha_inicio"] = _parse_date(norm["fecha_inicio"])
        if "fecha_fin" in norm:
            norm["fecha_fin"] = _parse_date(norm["fecha_fin"])

        # id_usuario → ObjectId si viene
        if "id_usuario" in norm and norm["id_usuario"]:
            try:
                norm["id_usuario"] = ObjectId(str(norm["id_usuario"]))
            except Exception:
                norm["id_usuario"] = None  

        # progreso → int si viene
        if "progreso" in norm and norm["progreso"] is not None:
            try:
                norm["progreso"] = int(norm["progreso"])
            except Exception:
                pass

        # sello de actualización
        norm["updated_at"] = datetime.utcnow()

        # --- Actualizar en local
        local_col.update_one({"_id": _id}, {"$set": norm})

        # Obtener el documento actualizado
        updated_goal = local_col.find_one({"_id": _id})

        # Sincronizar con la nube
        sync_to_remote(GoalModel.COLLECTION, updated_goal)

        print(f"♻️ Objetivo {_id} actualizado y sincronizado.")
        return updated_goal
    

    @staticmethod
    def find_by_category(categoria: str):
        local_col, _ = get_collection(GoalModel.COLLECTION)
        # Busca por coincidencia exacta; si prefieres regex/insensitive, adáptalo
        return list(local_col.find({"categoria": categoria}).sort("created_at", -1))

    @staticmethod
    def delete_goals_by_ids(ids):
        # acepta lista de strings
        object_ids = []
        for s in ids:
            try:
                object_ids.append(ObjectId(s))
            except Exception:
                continue
        if not object_ids:
            return 0
        local_col, _ = get_collection(GoalModel.COLLECTION)
        res = local_col.delete_many({"_id": {"$in": object_ids}})
        return res.deleted_count
    

  


