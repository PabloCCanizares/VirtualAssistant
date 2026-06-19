"""Fixtures comunes a los tests unitarios bajo `tests/unit/`.

Reusa las fixtures compartidas con la suite de integracion (mongomock, GridFS
en memoria, limpieza de estado, variables de entorno para LLM y compatibilidad
con pymongo/mongomock).
"""

from tests._pytest_fixtures import *  # noqa: F401, F403
