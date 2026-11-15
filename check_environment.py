import platform
import sys
from pathlib import Path


def main():
    project_root = Path(__file__).resolve().parent

    required_directories = [
        "data",
        "db/migrations",
        "docs/screenshots",
        "java",
        "models",
        "python",
        "tests",
    ]

    print("Проект: Оптовая торговля офисной мебелью со склада")
    print(f"Версия Python: {platform.python_version()}")
    print(f"Интерпретатор: {sys.executable}")
    print(f"Папка проекта: {project_root}")
    print()

    missing_directories = []

    for directory in required_directories:
        directory_path = project_root / directory

        if directory_path.is_dir():
            print(f"[OK] {directory}")
        else:
            print(f"[НЕТ] {directory}")
            missing_directories.append(directory)

    print()

    if missing_directories:
        print("Создай недостающие папки и повтори проверку.")
    else:
        print("Все необходимые папки созданы.")

    if sys.prefix != sys.base_prefix:
        print("Виртуальное окружение активно.")
    else:
        print("Внимание: выбран Python вне виртуального окружения.")


if __name__ == "__main__":
    main()