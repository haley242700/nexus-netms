"""Register the development Compose project in UGOS without replacing NEXUS."""
from datetime import datetime
from pathlib import Path
import sqlite3

DB_PATH = Path("/volume1/@appstore/com.ugreen.docker/db/docker_info_log.db")
COMPOSE_PATH = Path("/volume1/docker/dev-workspace/docker-compose.yaml")
BACKUP_DIR = Path("/volume1/docker/backups")


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"docker_info_log-before-dev-workspace-{stamp}.db"
    database = sqlite3.connect(DB_PATH)
    try:
        backup = sqlite3.connect(backup_path)
        database.backup(backup)
        backup.close()
        now = datetime.now().astimezone().isoformat()
        values = (now, 1, str(COMPOSE_PATH), COMPOSE_PATH.read_text(), None, 1, now, "dev-workspace")
        if database.execute("SELECT id FROM compose WHERE name = ?", ("dev-workspace",)).fetchone():
            database.execute(
                "UPDATE compose SET updated_at=?, state=?, path=?, content=?, app_id=?, container_num=? WHERE name=?",
                (now, 1, str(COMPOSE_PATH), COMPOSE_PATH.read_text(), None, 1, "dev-workspace"),
            )
        else:
            database.execute(
                "INSERT INTO compose (created_at, updated_at, name, state, path, content, app_id, container_num) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, now, "dev-workspace", 1, str(COMPOSE_PATH), COMPOSE_PATH.read_text(), None, 1),
            )
        database.commit()
        print("Backup:", backup_path)
        print(database.execute("SELECT name, state, path, container_num FROM compose ORDER BY name").fetchall())
        print("Integrity:", database.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        database.close()


if __name__ == "__main__":
    main()
