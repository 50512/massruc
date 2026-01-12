import sqlite3

import requests
from rich.progress import Progress

URL_PADRON = "https://www.sunat.gob.pe/descargaPRR/padron_reducido_ruc.zip"
RUC_QUERY_ERRORS = {
    "NOT_FOUND": {"text": "NO SE ENCONTRÓ", "color": "#FFC052".removeprefix("#")},
    "INVALID_FORMAT": {"text": "RUC INVÁLIDO", "color": "#FF5252".removeprefix("#")},
}


def descargar_padron_reducido(
    output_file="padron_reducido_ruc.zip", progress_callback=None
):
    """
    Descarga el padrón RUC reducido oficial de la SUNAT (URL en `URL_PADRON`) y lo guarda en `output_file`, que por defecto es `padron_reducido_ruc.zip`

    Args:
        output_file (str): Ruta o nombre del archivo destino (.zip).
        progress_callback (callable, optional): Función que recibe un `float` (0.0 - 1.0) para reportar el progreso de la descarga.

    Returns:
        str: Ruta del archivo descargado.
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


def buscar_rucs(lista_rucs, path_db, table_name="main_table"):
    """
    Recibe una lista de rucs:str, verifica si son validos y los busca en la base de datos.
    Devuelve la lista original completa, seguida de la versión limpia de cada ruc, si es que hubiera, y la información extraída de la DB
    """
    rucs_enteros = [int(ruc) for ruc in limpiar_rucs(lista_rucs)]
    CHUNK_SQL_SIZE = 900

    db_cache = {}

    con = sqlite3.connect(path_db)
    cursor = con.cursor()
    num_columnas = 0
    try:
        for i in range(0, len(rucs_enteros), CHUNK_SQL_SIZE):
            lote = rucs_enteros[i : i + CHUNK_SQL_SIZE]

            placeholder = ",".join("?" * len(lote))
            consulta = f"SELECT * FROM {table_name} WHERE ruc IN ({placeholder})"

            cursor.execute(consulta, lote)
            filas = cursor.fetchall()

            if num_columnas == 0 and cursor.description:
                num_columnas = len(cursor.description)

            for fila in filas:
                db_cache[fila[0]] = fila

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
                + ("-",) * (num_columnas - 2)
            )
            resultados_finales.append(tupla_vacia)

    return resultados_finales


def buscar_ruc(
    doc_number: str | int, path_db: str, table_name: str = "main_table"
) -> tuple | None:
    """
    Docstring for buscar_ruc

    Args:
        doc_number: Número de documento (RUC o DNI)
        path_db: Ruta del padrón ruc reducido (SQL)
        table_name: Nombre de la tabla a consultar

    Returns:
        Tupla que contiene el resultado de la consulta `(ruc, nombre_o_razón_social, estado_de_contribuyente, condición_de_domicilio)` o `None` en caso de no encontrarlo
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

    res = cursor.fetchone()
    cursor.close()
    return res if res else None


def limpiar_rucs(lista_rucs):
    rucs_limpios = []
    for doc in lista_rucs:
        ruc_final = limpiar_ruc(doc)
        if ruc_final:
            rucs_limpios.append(ruc_final)

    return rucs_limpios


def limpiar_ruc(ruc):
    ruc = str(ruc).strip()
    ruc_final = ""

    # Lógica de conversión
    if len(ruc) == 11 and ruc.isdigit():
        digito = digito_verificador_ruc(ruc)

        # corrige el digito de verificación del RUC ingresado de ser necesario
        if not ruc.endswith(str(digito)):
            ruc_final = ruc.removesuffix(ruc[10]) + str(digito)
        else:
            ruc_final = ruc

    # para encontrar RUC 10 con solo el DNI
    elif len(ruc) == 8 and ruc.isdigit():
        base = "10" + ruc
        digito = digito_verificador_ruc(base)
        ruc_final = base + str(digito)

    return ruc_final if ruc_final else None


def digito_verificador_ruc(ruc_base):
    factores = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(ruc_base[i]) * factores[i] for i in range(10))
    residuo = suma % 11
    diferencia = 11 - residuo
    return diferencia - 10 if diferencia >= 10 else diferencia


if __name__ == "__main__":
    print(digito_verificador_ruc(input("Ingrese ruc: ")))
