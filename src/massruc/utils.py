import zipfile


def count_lines(file_path: str) -> int:
    """
    Devuelve el número de lineas que contiene un archivo de texto.
    Args:
        file_path: Ruta del archivo a contar.
    Returns:
        Número de lineas del archivo.
    """
    with open(file_path, "rb") as file:
        lines = 0
        buf_size = 1024 * 1024
        read_f = file.raw.read

        buf = read_f(buf_size)
        while buf:
            lines += buf.count(b"\n")
            buf = read_f(buf_size)
        return lines


def verificador_integridad_zip(path_zip: str) -> bool:
    """
    Verifica si un archivo ZIP esta integro. Devolverá `True` si esta bien o `False` si esta corrupto.
    Args:
        path_zip: Ruta del archivo a verificar.
    Returns:
        Regresa `True` para archivo integro o `False` para archivo corrupto.
    """
    if not zipfile.is_zipfile(path_zip):
        return False

    with zipfile.ZipFile(path_zip, "r") as zf:
        error = zf.testzip()
        if error:
            return False
        else:
            return True


def main():
    print(__file__)


if __name__ == "__main__":
    main()
