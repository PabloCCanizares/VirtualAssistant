from database.mongo_conn import get_collection, sync_to_remote
from bson import ObjectId
from datetime import datetime


class CategoryModel:
    """Gestion de la coleccion 'Categories' con sincronizacion local/remota."""

    COLLECTION = "Categories"

    # -------------------------------------------------------------
    #  INSERTAR
    # -------------------------------------------------------------
    @staticmethod
    def insert_category(name: str):
        """
        Inserta una categoria en la base local y la sincroniza con la remota.
        Devuelve la categoria insertada con su _id.
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)

        # Verificar que no exista una categoria con el mismo nombre (case-insensitive)
        existing = local_col.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
        if existing:
            return None  # Ya existe

        category_data = {
            "name": name.strip(),
            "created_at": datetime.utcnow()
        }

        result = local_col.insert_one(category_data)
        category_data["_id"] = result.inserted_id

        # Sincronizar con la nube
        sync_to_remote(CategoryModel.COLLECTION, category_data)

        print(f"Categoria insertada: {category_data['_id']} - {name}")
        return category_data

    # -------------------------------------------------------------
    #  OBTENER TODAS
    # -------------------------------------------------------------
    @staticmethod
    def get_all_categories():
        """
        Devuelve todas las categorias ordenadas alfabeticamente por nombre.
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        return list(local_col.find().sort("name", 1))

    # -------------------------------------------------------------
    #  OBTENER POR ID
    # -------------------------------------------------------------
    @staticmethod
    def get_category_by_id(category_id):
        """
        Obtiene una categoria por su _id.
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        return local_col.find_one({"_id": _id})

    # -------------------------------------------------------------
    #  OBTENER POR IDs (MULTIPLES)
    # -------------------------------------------------------------
    @staticmethod
    def get_categories_by_ids(category_ids: list):
        """
        Obtiene multiples categorias por sus _ids.
        Devuelve una lista de categorias.
        """
        if not category_ids:
            return []
        
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        
        # Convertir a ObjectId si es necesario
        object_ids = []
        for cid in category_ids:
            try:
                if isinstance(cid, ObjectId):
                    object_ids.append(cid)
                else:
                    object_ids.append(ObjectId(str(cid)))
            except Exception:
                continue
        
        if not object_ids:
            return []
        
        return list(local_col.find({"_id": {"$in": object_ids}}).sort("name", 1))

    # -------------------------------------------------------------
    #  BUSCAR POR NOMBRE
    # -------------------------------------------------------------
    @staticmethod
    def search_by_name(query: str, limit: int = 20):
        """
        Busca categorias cuyo nombre contenga el texto dado (case-insensitive).
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        
        if not query or not query.strip():
            return list(local_col.find().sort("name", 1).limit(limit))
        
        import re
        regex = re.compile(re.escape(query.strip()), re.IGNORECASE)
        return list(local_col.find({"name": {"$regex": regex}}).sort("name", 1).limit(limit))

    # -------------------------------------------------------------
    #  ACTUALIZAR
    # -------------------------------------------------------------
    @staticmethod
    def update_category(category_id, name: str):
        """
        Actualiza el nombre de una categoria.
        Devuelve la categoria actualizada o None si no se encontro.
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id

        # Verificar que no exista otra categoria con el mismo nombre
        existing = local_col.find_one({
            "name": {"$regex": f"^{name}$", "$options": "i"},
            "_id": {"$ne": _id}
        })
        if existing:
            return None  # Ya existe otra con ese nombre

        updates = {
            "name": name.strip(),
            "updated_at": datetime.utcnow()
        }

        local_col.update_one({"_id": _id}, {"$set": updates})
        updated_category = local_col.find_one({"_id": _id})

        if updated_category:
            sync_to_remote(CategoryModel.COLLECTION, updated_category)
            print(f"Categoria {_id} actualizada: {name}")

        return updated_category

    # -------------------------------------------------------------
    #  ELIMINAR
    # -------------------------------------------------------------
    @staticmethod
    def delete_category(category_id):
        """
        Elimina una categoria tanto en la base local como remota.
        Devuelve True si se elimino, False si no se encontro.
        """
        local_col, remote_col = get_collection(CategoryModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id

        result = local_col.delete_one({"_id": _id})

        if remote_col:
            try:
                remote_col.delete_one({"_id": _id})
                print(f"Categoria eliminada en local y remoto: {_id}")
            except Exception:
                pass
        else:
            print(f"Categoria eliminada solo localmente: {_id}")

        return result.deleted_count > 0

    # -------------------------------------------------------------
    #  VERIFICAR SI EXISTE POR NOMBRE
    # -------------------------------------------------------------
    @staticmethod
    def exists_by_name(name: str) -> bool:
        """
        Verifica si existe una categoria con el nombre dado (case-insensitive).
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        existing = local_col.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
        return existing is not None
