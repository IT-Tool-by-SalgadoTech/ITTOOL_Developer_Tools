import os
import re

def clean_name(name: str) -> str:
    # Quita numeración inicial tipo: 23.prueba -> prueba
    return re.sub(r'^\s*\d+\.\s*', '', name)

def rename_all(root_path: str) -> None:
    if not os.path.exists(root_path):
        print("La ruta no existe.")
        return

    # Recorre de abajo hacia arriba para renombrar subcarpetas primero
    for current_root, dirs, files in os.walk(root_path, topdown=False):
        # Archivos
        for filename in files:
            old_path = os.path.join(current_root, filename)
            new_name = clean_name(filename)

            if new_name != filename and new_name.strip():
                new_path = os.path.join(current_root, new_name)

                if os.path.exists(new_path):
                    print(f"[SKIP FILE] Ya existe: {new_path}")
                    continue

                try:
                    os.rename(old_path, new_path)
                    print(f"[FILE] {old_path} -> {new_path}")
                except Exception as e:
                    print(f"[ERROR FILE] {old_path}: {e}")

        # Carpetas
        for dirname in dirs:
            old_path = os.path.join(current_root, dirname)
            new_name = clean_name(dirname)

            if new_name != dirname and new_name.strip():
                new_path = os.path.join(current_root, new_name)

                if os.path.exists(new_path):
                    print(f"[SKIP DIR] Ya existe: {new_path}")
                    continue

                try:
                    os.rename(old_path, new_path)
                    print(f"[DIR ] {old_path} -> {new_path}")
                except Exception as e:
                    print(f"[ERROR DIR] {old_path}: {e}")

if __name__ == "__main__":
    print("=== Remove leading numbers from files and folders ===")
    root = input("Enter the folder path: ").strip().strip('"')
    rename_all(root)
    print("\nDone.")
    input("Press Enter to exit...")