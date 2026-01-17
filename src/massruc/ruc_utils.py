import sqlite3
from typing import Any, Callable, Sequence

import pandas as pd
import requests
from rich.progress import Progress

URL_PADRON = "https://www.sunat.gob.pe/descargaPRR/padron_reducido_ruc.zip"
RUC_QUERY_ERRORS = {
    "NOT_FOUND": {"text": "NO SE ENCONTRÓ", "color": "#FFC052".removeprefix("#")},
    "INVALID_FORMAT": {"text": "RUC INVÁLIDO", "color": "#FF5252".removeprefix("#")},
}


def obtener_cabecera_db(
    path_db: str, table_name: str = "main_table", num_columns: int = 4
) -> list[str]:
    """
    Obtiene la cabecera de las primeras `num_columns` columnas de la base de datos con un máximo de 15
    Args:
        path_db: Ruta del padrón ruc reducido (SQL).
        table_name: Nombre de la tabla a consultar.
        num_columns: Número de columnas a consular.
    Returns:
        Lista con los nombres de las cabeceras.
    """
    con = sqlite3.connect(path_db)
    cursor = con.cursor()
    cursor.execute(f"SELECT name FROM pragma_table_info('{table_name}')")
    res = cursor.fetchall()
    res = [r[0] for r in res]
    res = res[:num_columns]

    return res


def descargar_padron_reducido(
    output_file: str = "padron_reducido_ruc.zip",
    progress_callback: Callable[[float], None] | None = None,
) -> str:
    """
    Descarga el padrón RUC reducido oficial de la SUNAT (URL en `URL_PADRON`) y lo guarda en `output_file`, que por defecto es `padron_reducido_ruc.zip`.

    Args:
        output_file: Ruta o nombre del archivo destino (.zip).
        progress_callback: Función que recibe un `float` (0.0 - 1.0) para reportar el progreso de la descarga.

    Returns:
        Ruta del archivo descargado.
    """
    response = requests.get(URL_PADRON, stream=True)
    response.raise_for_status()

    total_length = response.headers.get("content-length")
    dl = 0
    with open(output_file, "wb") as f:
        with Progress() as bar:
            tarea = None

            if total_length is not None:
                total_length = int(total_length)
                tarea = bar.add_task("Descargando padrón", total=total_length)
            else:
                total_length = None
                tarea = bar.add_task(
                    "Descargando padrón (tamaño desconocido)", total=None
                )

            for data in response.iter_content(chunk_size=8192):
                dl += len(data)
                f.write(data)

                if total_length:
                    bar.update(tarea, completed=dl)
                    if progress_callback:
                        porcentaje = dl / total_length
                        progress_callback(porcentaje)
                else:
                    bar.update(tarea, advance=len(data))
                    if progress_callback:
                        progress_callback(0)

    return output_file


def buscar_rucs(
    lista_rucs: Sequence[str | int],
    path_db: str,
    table_name: str = "main_table",
    num_columns: int = 4,
) -> list[tuple[Any, ...] | None]:
    """
    Devuelve una lista de tuplas que contienen la información de los RUC's buscados
    Args:
        lista_rucs: Lista con los documentos (RUC o DNI) a buscar.
        path_db: Ruta del padrón ruc reducido (SQL).
        table_name: Nombre de la tabla a consultar.
        num_columns: Número de columnas a guardar (las primeras `num_columns`)

    Returns:
        Lista de tuplas `(ruc, nombre_o_razón_social, estado_de_contribuyente, condición_de_domicilio)` por defecto de los RUC's encontrados.

        Se pueden solicitar más columnas de la tabla con `num_columns` hasta un máximo de 15
    """
    rucs_enteros = [int(ruc) for ruc in limpiar_rucs(lista_rucs)]
    CHUNK_SQL_SIZE = 900

    db_cache = {}

    con = sqlite3.connect(path_db)
    cursor = con.cursor()
    try:
        for i in range(0, len(rucs_enteros), CHUNK_SQL_SIZE):
            lote = rucs_enteros[i : i + CHUNK_SQL_SIZE]

            placeholder = ",".join("?" * len(lote))
            consulta = f"SELECT * FROM {table_name} WHERE ruc IN ({placeholder})"

            cursor.execute(consulta, lote)
            filas = cursor.fetchall()

            if cursor.description and num_columns > cursor.description:
                num_columns = cursor.description

            for fila in filas:
                db_cache[fila[0]] = fila[:num_columns]

    except Exception as e:
        print(f"Error en consulta DB: {e}")
        return []

    finally:
        con.close()

    resultados_finales = []

    for ruc_listado in lista_rucs:
        ruc_limpio = limpiar_ruc(ruc_listado)
        ruc_failed = None

        if not ruc_limpio:
            ruc_failed = RUC_QUERY_ERRORS["INVALID_FORMAT"]["text"]
        elif int(ruc_limpio) not in db_cache:
            ruc_failed = RUC_QUERY_ERRORS["NOT_FOUND"]["text"]
        else:
            tupla_final = (ruc_listado,) + db_cache[int(ruc_limpio)]
            resultados_finales.append(tupla_final)

        if ruc_failed:
            tupla_vacia = (
                (
                    ruc_listado,
                    limpiar_ruc(ruc_limpio),
                )
                + (ruc_failed,)
                + ("-",) * (num_columns - 2)
            )
            resultados_finales.append(tupla_vacia)

    return resultados_finales


def buscar_ruc(
    doc_number: str | int,
    path_db: str,
    table_name: str = "main_table",
    num_columns: int = 4,
) -> tuple | None:
    """
    Devuelve una tupla con los datos del RUC consultado o `None` en caso de no encontrarlo

    Args:
        doc_number: Número de documento (RUC o DNI)
        path_db: Ruta del padrón ruc reducido (SQL)
        table_name: Nombre de la tabla a consultar
        num_columns: Número de columnas a consultar

    Returns:
        Tupla que contiene el resultado de la consulta `(ruc, nombre_o_razón_social, estado_de_contribuyente, condición_de_domicilio)` o `None` en caso de no encontrarlo.

        Se pueden consultar mas columnas con `num_columns` hasta un máximo de 15
    """
    ruc_buscado = limpiar_ruc(doc_number)
    if not ruc_buscado:
        return None
    else:
        ruc_buscado = int(ruc_buscado)

    con = sqlite3.connect(path_db)
    cursor = con.cursor()

    consulta = f"SELECT * FROM {table_name} WHERE ruc = {ruc_buscado}"
    cursor.execute(consulta)

    res = cursor.fetchone()[:num_columns]
    cursor.close()
    return res if res else None


def buscar_rucs_desde_excel(
    excel_path: str,
    path_db: str,
    column_name: str = "Documento",
    table_name: str = "main_table",
) -> list[tuple[Any, ...]]:
    """
    Realiza búsqueda masiva de los RUC's obtenidos desde un excel.

    Args:
        excel_path: Ruta del archivo Excel de entrada.
        path_db: Ruta de la base de datos del padrón RUC.
        column_name: Nombre de la columna de Excel que contiene los números de documento (RUC o DNI) a verificar.
        table_name: Nombre de la tabla a buscar.
    Returns:
        Regresa una lista de tuplas de todos los RUC's buscados, y si es que se encontró, sus datos solicitados.
    """
    df_user = pd.read_excel(excel_path, dtype=str)

    # Buscar columna
    col_doc = next(
        (
            c
            for c in df_user.columns
            if str(c).strip().lower() == column_name.strip().lower()
        ),
        None,
    )
    if not col_doc:
        raise LookupError(f"No se encontró columna '{column_name}' en el Excel.")

    # Procesar
    total_filas = len(df_user)
    print(f"Analizando {total_filas} registros...")
    resultados = buscar_rucs(df_user[col_doc], path_db, table_name)
    resultados = [map(str, res) for res in resultados]
    return resultados


def limpiar_rucs(lista_rucs: Sequence[int | str]) -> list[str | None]:
    """
    Devuelve una lista con los RUC's corregidos y válidos, o una lista vacía en caso de no haber ninguno válido

    Args:
        lista_rucs: Lista con los documentos (RUC o DNI) a limpiar

    Returns:
        Lista de RUC's corregidos y válidos
    """
    rucs_limpios = []
    for doc in lista_rucs:
        ruc_final = limpiar_ruc(doc)
        if ruc_final:
            rucs_limpios.append(ruc_final)

    return rucs_limpios


def limpiar_ruc(num_doc: int | str) -> str | None:
    """
    Limpia el RUC o DNI ingresado, corrige su dígito verificador y devuelve la versión 'limpia' o `None` en caso de ser inválido

    Args:
        num_doc: Número de documento (RUC o DNI) a limpiar

    Returns
        RUC corregido o `None` en caso de no poder corregirse
    """
    num_doc = str(num_doc).strip()
    ruc_final = ""

    # Lógica de conversión
    if len(num_doc) == 11 and num_doc.isdigit():
        digito = digito_verificador_ruc(num_doc)

        # corrige el digito de verificación del RUC ingresado de ser necesario
        if not num_doc.endswith(str(digito)):
            ruc_final = num_doc.removesuffix(num_doc[10]) + str(digito)
        else:
            ruc_final = num_doc

    # para encontrar RUC 10 con solo el DNI
    elif len(num_doc) == 8 and num_doc.isdigit():
        base = "10" + num_doc
        digito = digito_verificador_ruc(base)
        ruc_final = base + str(digito)

    return ruc_final if ruc_final else None


def digito_verificador_ruc(ruc_base: int | str) -> int:
    """
    Devuelve el dígito verificador del RUC ingresado
    Args:
        ruc_base: RUC del cual se obtendrá el dígito verificador
    Returns:
        Dígito verificador
    """
    factores = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(ruc_base[i]) * factores[i] for i in range(10))
    residuo = suma % 11
    diferencia = 11 - residuo
    return diferencia - 10 if diferencia >= 10 else diferencia


if __name__ == "__main__":
    print(digito_verificador_ruc(input("Ingrese ruc: ")))
