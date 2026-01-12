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


def main():
    print(__file__)


if __name__ == "__main__":
    main()
