#!/usr/bin/env python3
"""
generate_file_list.py
=====================
Genera el file_list.txt para el repositorio ITTOOL_ReadyUSB.

Uso:
  python generate_file_list.py

Puedes dar:
  - La carpeta que CONTIENE ReadyUSB/  (ej: D:\ITTOOL_ReadyUSB)
  - La carpeta ReadyUSB directamente   (ej: D:\ReadyUSB)
"""

import os
import sys


def get_root_folder():
    print("\n=== ITTOOL file_list.txt Generator ===\n")
    print("Ingresa la ruta de la carpeta ReadyUSB o la carpeta que la contiene.")
    print("Ejemplos:")
    print("  D:\\ReadyUSB")
    print("  D:\\ITTOOL_ReadyUSB")
    print("  C:\\Users\\chefm\\Documents\\GitHub\\ITTOOL_ReadyUSB\n")

    while True:
        root = input("Ruta: ").strip().strip('"').strip("'")
        if not root:
            print("  Ruta vacía, intenta de nuevo.")
            continue
        if not os.path.isdir(root):
            print(f"  ERROR: '{root}' no es una carpeta válida.")
            continue

        folder_name = os.path.basename(root.rstrip("/\\"))

        # Case 1: the path itself IS the ReadyUSB folder
        if folder_name == "ReadyUSB":
            readyusb_path = root
            root = os.path.dirname(root)
            print(f"  OK: usando ReadyUSB en '{readyusb_path}'")
            return root, readyusb_path

        # Case 2: the path CONTAINS a ReadyUSB folder
        readyusb_path = os.path.join(root, "ReadyUSB")
        if os.path.isdir(readyusb_path):
            print(f"  OK: encontrada ReadyUSB en '{readyusb_path}'")
            return root, readyusb_path

        print(f"  ERROR: No se encontró ReadyUSB en '{root}'.")
        print("  Da la ruta de la carpeta ReadyUSB directamente,")
        print("  o la carpeta que la contiene.")


def scan_files(readyusb_path, root):
    file_paths = []
    for dirpath, dirnames, filenames in os.walk(readyusb_path):
        dirnames.sort()
        filenames.sort()
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, root)
            rel_path = rel_path.replace("\\", "/")
            file_paths.append(rel_path)
    return file_paths


def show_summary(file_paths):
    folders = {}
    for p in file_paths:
        parts = p.split("/")
        if len(parts) >= 2:
            folder = parts[1]
            folders[folder] = folders.get(folder, 0) + 1

    print(f"\n  Total archivos encontrados: {len(file_paths)}")
    print("\n  Por carpeta:")
    for folder, count in sorted(folders.items()):
        print(f"    {folder:<40} {count} archivos")


def choose_output_location(root):
    print("\n¿Dónde guardar el file_list.txt?")
    print(f"  1. En '{root}' (raíz del repo)")
    print("  2. Elegir otra ubicación")
    print("  3. En la carpeta actual del script")

    while True:
        choice = input("\nOpción (1/2/3): ").strip()
        if choice == "1":
            return os.path.join(root, "file_list.txt")
        elif choice == "2":
            path = input("Ruta completa donde guardar: ").strip().strip('"').strip("'")
            if os.path.isdir(path):
                return os.path.join(path, "file_list.txt")
            else:
                print("  Carpeta no válida.")
        elif choice == "3":
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_list.txt")
        else:
            print("  Opción inválida.")


def main():
    root, readyusb_path = get_root_folder()

    print(f"\n  Escaneando...")
    file_paths = scan_files(readyusb_path, root)

    if not file_paths:
        print("  ERROR: No se encontraron archivos dentro de ReadyUSB/")
        sys.exit(1)

    show_summary(file_paths)

    print("\n¿Quieres excluir alguna carpeta o archivo? (s/n): ", end="")
    if input().strip().lower() == "s":
        print("\nEscribe los nombres a excluir (Enter vacío para terminar):")
        print("Ejemplos: Non_CommercialScripts   Favorites   .ps1")
        exclusions = []
        while True:
            exc = input("  Excluir: ").strip()
            if not exc:
                break
            exclusions.append(exc)
        if exclusions:
            original_count = len(file_paths)
            file_paths = [p for p in file_paths if not any(exc in p for exc in exclusions)]
            print(f"\n  Excluidos: {original_count - len(file_paths)} archivos")
            print(f"  Quedan: {len(file_paths)} archivos")

    output_path = choose_output_location(root)

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        for path in file_paths:
            f.write(path + "\n")

    print(f"\n  ✓ file_list.txt generado con {len(file_paths)} archivos")
    print(f"  ✓ Guardado en: {output_path}")
    print("\n  Próximos pasos:")
    print("  1. Sube los scripts nuevos/modificados a GitHub")
    print("  2. Sube este file_list.txt a la raíz del repo en GitHub")
    print("  3. El ITTool descargará automáticamente la lista actualizada")
    print("\n  Presiona Enter para salir...")
    input()


if __name__ == "__main__":
    main()
