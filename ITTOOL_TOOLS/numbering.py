import os

def natural_list(path):
    try:
        return sorted(os.listdir(path), key=str.lower)
    except Exception:
        return []

# Contador global mutable
state = {"counter": 1}

def rename_file(file_path):
    """Renombra un archivo con el contador global si aún no tiene numeración."""
    folder = os.path.dirname(file_path)
    name = os.path.basename(file_path)

    if name[:1].isdigit():
        print(f"[SKIP] Ya tiene numeración: {file_path}")
        return

    new_name = f"{state['counter']}.{name}"
    new_path = os.path.join(folder, new_name)

    if os.path.exists(new_path):
        print(f"[SKIP] Ya existe: {new_path}")
        state["counter"] += 1
        return

    try:
        os.rename(file_path, new_path)
        print(f"[OK] {file_path} -> {new_path}")
        state["counter"] += 1
    except Exception as e:
        print(f"[ERROR] {file_path}: {e}")


def process_folder(folder_path):
    """
    Procesa una carpeta de forma recursiva:
      1. Entra en cada subcarpeta (ordenadas) y las procesa primero (recursivo)
      2. Luego numera los archivos sueltos de ESTA carpeta
    """
    items = natural_list(folder_path)
    subdirs = [i for i in items if os.path.isdir(os.path.join(folder_path, i))]
    files   = [i for i in items if os.path.isfile(os.path.join(folder_path, i))]

    # 1) Primero procesar subcarpetas (recursivo → profundidad primero)
    for d in subdirs:
        process_folder(os.path.join(folder_path, d))

    # 2) Luego los archivos sueltos de esta carpeta
    for f in files:
        rename_file(os.path.join(folder_path, f))


def rename_with_global_order(root_path: str, start: int = 1) -> None:
    if not os.path.exists(root_path):
        print("La ruta no existe.")
        return

    state["counter"] = start

    items = natural_list(root_path)
    root_dirs  = [i for i in items if os.path.isdir(os.path.join(root_path, i))]
    root_files = [i for i in items if os.path.isfile(os.path.join(root_path, i))]

    # 1) Procesar cada subcarpeta raíz en orden
    for d in root_dirs:
        process_folder(os.path.join(root_path, d))

    # 2) Al final, archivos sueltos en la raíz principal
    for f in root_files:
        rename_file(os.path.join(root_path, f))


if __name__ == "__main__":
    print("=== Enumerate files with deep-first folder logic ===")
    root = input("Enter the folder path: ").strip().strip('"')

    start_input = input("Start numbering from (default 1): ").strip()
    start = int(start_input) if start_input.isdigit() else 1

    rename_with_global_order(root, start)
    print("\nDone.")
    input("Press Enter to exit...")
