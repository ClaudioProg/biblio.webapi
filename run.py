import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
MANAGE_PATH = BASE_DIR / "manage.py"


def _run_manage(*args: str) -> int:
    command = [sys.executable, str(MANAGE_PATH), *args]
    result = subprocess.run(command, cwd=str(BASE_DIR))
    return result.returncode


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python run.py <comando>")
        print("Comandos disponíveis: dev, migrate, makemigrations, check")
        return 1

    action = sys.argv[1].strip().lower()

    if action == "dev":
        # Atalho de desenvolvimento: valida e sobe o servidor
        check_rc = _run_manage("check")
        if check_rc != 0:
            return check_rc
        migrate_rc = _run_manage("migrate")
        if migrate_rc != 0:
            return migrate_rc
        return _run_manage("runserver")

    if action == "migrate":
        return _run_manage("migrate")

    if action == "makemigrations":
        app_label = sys.argv[2] if len(sys.argv) > 2 else "gestor"
        return _run_manage("makemigrations", app_label)

    if action == "check":
        return _run_manage("check")

    print(f"Comando desconhecido: {action}")
    print("Comandos disponíveis: dev, migrate, makemigrations, check")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
