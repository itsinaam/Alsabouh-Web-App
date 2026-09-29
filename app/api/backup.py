import json
import logging
import uuid
from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import Date, DateTime, Enum as SQLAlchemyEnum, Time

from app.db.base import Base
from app.db.session import get_db
from app.models import DatabaseBackup, GDN, Location, RunPlanner, User
from app.models.vehicle import Vehicle
from app.schema.backup import BackupHistoryResponse
from app.services.storage import storage_service
from app.utils.constants import UserRole
from app.utils.security import require_roles

router = APIRouter(tags=["Database Backup"])

BACKUP_FORMAT = "alsabouh-full-db-backup"
BACKUP_VERSION = 3
logger = logging.getLogger(__name__)


def _self_referencing_columns(table):
    return [
        column
        for column in table.columns
        if any(foreign_key.column.table is table for foreign_key in column.foreign_keys)
    ]


def _restore_value(column, value: Any) -> Any:
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, SQLAlchemyEnum) and column_type.enum_class:
        return column_type.enum_class(value)
    if isinstance(column_type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column_type, Date):
        return date.fromisoformat(value)
    if isinstance(column_type, Time):
        return time.fromisoformat(value)
    return value


def _reset_postgres_sequences(db: Session) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return

    for table in Base.metadata.sorted_tables:
        primary_key = list(table.primary_key.columns)
        if len(primary_key) != 1:
            continue
        column = primary_key[0]
        if column.autoincrement is False:
            continue

        sequence_name = db.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table.fullname, "column_name": column.name},
        ).scalar_one_or_none()
        if sequence_name:
            maximum_id = db.execute(select(func.max(column))).scalar_one()
            db.execute(
                text(
                    "SELECT setval(CAST(:sequence_name AS regclass), :last_value, :is_called)"
                ),
                {
                    "sequence_name": sequence_name,
                    "last_value": maximum_id if maximum_id is not None else 1,
                    "is_called": maximum_id is not None,
                },
            )


@router.get("/full_db_backup", summary="Download a full database backup")
def download_full_db_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    tables = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(select(table)).mappings().all()
        tables[table.name] = jsonable_encoder([dict(row) for row in rows])

    created_at = datetime.now(timezone.utc)
    backup = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": created_at.isoformat(),
        "tables": tables,
    }
    storage_path = f"database-backups/{uuid.uuid4().hex}.json"
    record = DatabaseBackup(
        filename="full_db_backup.json",
        table_count=len(tables),
        storage_path=storage_path,
        created_by_user_id=current_user.id,
        created_at=created_at,
    )
    uploaded = False
    try:
        db.add(record)
        db.flush()
        tables[DatabaseBackup.__tablename__].append(
            {
                "id": record.id,
                "filename": record.filename,
                "table_count": record.table_count,
                "storage_path": record.storage_path,
                "created_by_user_id": record.created_by_user_id,
                "created_at": record.created_at.isoformat(),
            }
        )
        content = json.dumps(backup, ensure_ascii=True, separators=(",", ":"))
        storage_service.upload_backup_file(content.encode("utf-8"), storage_path)
        uploaded = True
        db.commit()
    except Exception as exc:
        db.rollback()
        if uploaded:
            storage_service.delete_backup_file(storage_path)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup could not be saved to secure storage",
        ) from exc

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="full_db_backup.json"'},
    )


@router.get(
    "/full_db_backup/history",
    response_model=BackupHistoryResponse,
    summary="List full database backups",
)
def list_full_db_backups(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    total = db.query(func.count(DatabaseBackup.id)).scalar() or 0
    rows = (
        db.query(DatabaseBackup, User.full_name)
        .outerjoin(User, User.id == DatabaseBackup.created_by_user_id)
        .order_by(DatabaseBackup.created_at.desc(), DatabaseBackup.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    items = []
    for backup, full_name in rows:
        download_url = (
            str(request.url_for("download_stored_backup", backup_id=backup.id))
            if backup.storage_path
            else None
        )
        items.append(
            {
                "id": backup.id,
                "filename": backup.filename,
                "table_count": backup.table_count,
                "created_at": backup.created_at,
                "download_url": download_url,
                "created_by_user_id": backup.created_by_user_id,
                "created_by_name": full_name,
            }
        )
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


@router.delete(
    "/full_db_backup/history/{backup_id}",
    summary="Delete a database backup and its stored file",
)
def delete_full_db_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    backup = db.query(DatabaseBackup).filter(DatabaseBackup.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup record not found")

    if backup.storage_path and not storage_service.delete_backup_file(backup.storage_path):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Backup file could not be deleted from storage; history record was kept",
        )

    try:
        db.delete(backup)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Backup file was deleted, but its history record could not be deleted",
        ) from exc

    return {"message": "Backup deleted successfully", "backup_id": backup_id}


@router.get(
    "/full_db_backup/{backup_id}/download",
    name="download_stored_backup",
    summary="Download a stored database backup",
)
def download_stored_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    backup = db.query(DatabaseBackup).filter(DatabaseBackup.id == backup_id).first()
    if not backup or not backup.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")

    try:
        content = storage_service.download_backup_file(backup.storage_path)
    except Exception as exc:
        logger.exception("Could not download backup %s from storage", backup_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Backup file could not be retrieved from storage",
        ) from exc

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="full_db_backup.json"'},
    )


@router.post("/full_db_backup", summary="Restore a full database backup")
async def restore_full_db_backup(
    backup_file: UploadFile = File(..., description="JSON file downloaded from GET /full_db_backup"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    try:
        backup = json.loads(await backup_file.read())
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Backup file must contain valid JSON")

    if (
        not isinstance(backup, dict)
        or backup.get("format") != BACKUP_FORMAT
        or backup.get("version") not in {1, 2, BACKUP_VERSION}
        or not isinstance(backup.get("tables"), dict)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported or invalid backup format")

    tables = {table.name: table for table in Base.metadata.sorted_tables}
    backup_tables = backup["tables"]
    legacy_tables = set(tables) - {DatabaseBackup.__tablename__}
    if backup.get("version") == 1 and set(backup_tables) == legacy_tables:
        backup_tables[DatabaseBackup.__tablename__] = []
    if set(backup_tables) != set(tables):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Backup tables do not match this application")

    normalized_rows = {}
    deferred_self_references = {}
    for table_name, table in tables.items():
        rows = backup_tables[table_name]
        if not isinstance(rows, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid rows for table {table_name}")

        self_columns = _self_referencing_columns(table)
        if any(not column.nullable for column in self_columns):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot restore non-nullable self-reference in table {table_name}",
            )

        normalized_rows[table_name] = []
        deferred_self_references[table_name] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) - set(table.c.keys()):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid row data for table {table_name}")
            try:
                restored_row = {
                    key: _restore_value(table.c[key], value)
                    for key, value in row.items()
                }
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid value in table {table_name}",
                ) from exc
            if not all(column.name in restored_row for column in table.primary_key.columns):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing primary key in table {table_name}")

            references = {column.name: restored_row[column.name] for column in self_columns if restored_row.get(column.name) is not None}
            for column_name in references:
                restored_row[column_name] = None
            normalized_rows[table_name].append(restored_row)
            if references:
                deferred_self_references[table_name].append((row, references))

    try:
        db.rollback()
        with db.begin():
            for table in tables.values():
                self_columns = _self_referencing_columns(table)
                if self_columns:
                    db.execute(update(table).values({column.name: None for column in self_columns}))

            for table in reversed(list(Base.metadata.sorted_tables)):
                db.execute(delete(table))

            for table in Base.metadata.sorted_tables:
                rows = normalized_rows[table.name]
                if rows:
                    db.execute(table.insert(), rows)

            for table_name, references_by_row in deferred_self_references.items():
                table = tables[table_name]
                primary_key = list(table.primary_key.columns)
                for original_row, references in references_by_row:
                    criteria = and_(*(column == original_row[column.name] for column in primary_key))
                    db.execute(update(table).where(criteria).values(references))

            _reset_postgres_sequences(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Backup data could not be restored; the database transaction was rolled back",
        ) from exc

    return {"message": "Database restored successfully", "tables_restored": len(tables)}