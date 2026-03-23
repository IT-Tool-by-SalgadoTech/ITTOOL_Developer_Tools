import os

def natural_list(path):
    try:
        return sorted(os.listdir(path), key=str.lower)
    except Exception:
        return []

def rename_with_global_order(root_path: str) -> None:
    if not os.path.exists(root_path):
        print("La ruta no existe.")
        return

    counter = 1

    # Carpetas y archivos directos del root
    root_items = natural_list(root_path)
    root_dirs = [name for name in root_items if os.path.isdir(os.path.join(root_path, name))]
    root_files = [name for name in root_items if os.path.isfile(os.path.join(root_path, name))]

    # 1) Procesar cada carpeta raíz
    for top_dir in root_dirs:
        top_dir_path = os.path.join(root_path, top_dir)

        # 1A) Primero archivos dentro de subcarpetas/sub-subcarpetas...
        for current_root, dirs, files in os.walk(top_dir_path, topdown=True):
            dirs.sort(key=str.lower)
            files.sort(key=str.lower)

            # Saltar la carpeta raíz misma aquí, porque sus archivos directos van al final
            if os.path.normpath(current_root) == os.path.normpath(top_dir_path):
                continue

            for name in files:
                old_path = os.path.join(current_root, name)

                if name[:1].isdigit():
                    print(f"[SKIP] Ya tiene numeración: {old_path}")
                    continue

                new_name = f"{counter}.{name}"
                new_path = os.path.join(current_root, new_name)

                if os.path.exists(new_path):
                    print(f"[SKIP] Ya existe: {new_path}")
                    counter += 1
                    continue

                try:
                    os.rename(old_path, new_path)
                    print(f"[OK] {old_path} -> {new_path}")
                    counter += 1
                except Exception as e:
                    print(f"[ERROR] {old_path}: {e}")

        # 1B) Luego archivos directos de la carpeta raíz actual
        direct_items = natural_list(top_dir_path)
        direct_files = [name for name in direct_items if os.path.isfile(os.path.join(top_dir_path, name))]

        for name in direct_files:
            old_path = os.path.join(top_dir_path, name)

            if name[:1].isdigit():
                print(f"[SKIP] Ya tiene numeración: {old_path}")
                continue

            new_name = f"{counter}.{name}"
            new_path = os.path.join(top_dir_path, new_name)

            if os.path.exists(new_path):
                print(f"[SKIP] Ya existe: {new_path}")
                counter += 1
                continue

            try:
                os.rename(old_path, new_path)
                print(f"[OK] {old_path} -> {new_path}")
                counter += 1
            except Exception as e:
                print(f"[ERROR] {old_path}: {e}")

    # 2) Al final, si hay archivos directos en la raíz principal, numerarlos
    for name in root_files:
        old_path = os.path.join(root_path, name)

        if name[:1].isdigit():
            print(f"[SKIP] Ya tiene numeración: {old_path}")
            continue

        new_name = f"{counter}.{name}"
        new_path = os.path.join(root_path, new_name)

        if os.path.exists(new_path):
            print(f"[SKIP] Ya existe: {new_path}")
            counter += 1
            continue

        try:
            os.rename(old_path, new_path)
            print(f"[OK] {old_path} -> {new_path}")
            counter += 1
        except Exception as e:
            print(f"[ERROR] {old_path}: {e}")

if __name__ == "__main__":
    print("=== Enumerate files only with ordered folder logic ===")
    root = input("Enter the folder path: ").strip().strip('"')
    rename_with_global_order(root)
    print("\nDone.")
    input("Press Enter to exit...")