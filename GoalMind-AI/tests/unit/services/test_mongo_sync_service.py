from bson import ObjectId

from database import mongo_conn
from services import mongo_sync_service


class TestMongoSyncService:
    def test_sync_to_remote_returns_false_without_remote(self, no_remote):
        assert mongo_sync_service.sync_to_remote("Tasks", {"_id": ObjectId()}) is False

    def test_queue_deletion_records_and_removes_local_target(self, mongo_mock):
        task_id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({"_id": task_id, "contenido": "x"})

        queued = mongo_sync_service.queue_deletion("Tasks", task_id)

        assert queued is True
        assert mongo_mock.local_db["Tasks"].find_one({"_id": task_id}) is None
        assert mongo_mock.local_db["DeleteQueue"].find_one({
            "_id": f"Tasks:{task_id}",
            "collection": "Tasks",
        })

    def test_mongo_conn_reexports_legacy_sync_contract(self):
        assert mongo_conn.sync_to_remote is mongo_sync_service.sync_to_remote
        assert mongo_conn.sync_from_remote is mongo_sync_service.sync_from_remote
        assert mongo_conn.sync_all_collections is mongo_sync_service.sync_all_collections
        assert mongo_conn.sync_local_to_remote is mongo_sync_service.sync_local_to_remote
        assert mongo_conn.queue_deletion is mongo_sync_service.queue_deletion
        assert mongo_conn.flush_deletion_queue is mongo_sync_service.flush_deletion_queue
