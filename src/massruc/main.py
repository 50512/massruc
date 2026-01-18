import os
import threading
import time
import tkinter as tk
import zipfile
from tkinter import filedialog, messagebox, scrolledtext, ttk

from massruc import ruc_utils, txt_to_db, utils

# --- CONFIGURACIÓN ---
SUNAT_FOLDER = "./.sunat-datos"
TEMP_DB_TXT = os.path.join(SUNAT_FOLDER, ".padron_txt.tmp")
PATH_PADRON_ZIP = os.path.join(SUNAT_FOLDER, "padron_ruc_sunat.zip")
PATH_PADRON_DB = os.path.join(SUNAT_FOLDER, "padron_ruc_sunat.db")
NOMBRE_PADRON_TABLE = "padron"


class SunatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Validador Masivo SUNAT - Modo Gratuito")
        self.root.geometry("600x550")
        self.root.resizable(False, False)

        # Estilos
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=6, relief="flat", background="#ccc")
        style.configure(
            "Green.Horizontal.TProgressbar", foreground="green", background="green"
        )

        # Variables
        self.archivo_seleccionado = tk.StringVar()
        self.estado_padron = tk.StringVar(value="Verificando padrón...")
        self.columna_busqueda = tk.StringVar(value="Documento")

        # --- INTERFAZ ---
        # 1. Sección Padrón
        frame_padron = tk.LabelFrame(
            root, text="1. Base de Datos SUNAT", padx=10, pady=10
        )
        frame_padron.pack(fill="x", padx=10, pady=5)

        self.lbl_padron = tk.Label(
            frame_padron,
            textvariable=self.estado_padron,
            fg="blue",
            font=("Arial", 9, "bold"),
        )
        self.lbl_padron.pack(side="left")

        self.btn_descargar = tk.Button(
            frame_padron,
            text="Descargar/Actualizar Padrón",
            command=self.iniciar_descarga_thread,
            bg="#f0f0f0",
        )
        self.btn_descargar.pack(side="right")

        # 2. Sección Archivo Excel
        frame_file = tk.LabelFrame(
            root, text="2. Archivo de Clientes - Columna a buscar", padx=10, pady=10
        )
        frame_file.pack(fill="x", padx=10, pady=5)

        tk.Entry(
            frame_file,
            textvariable=self.archivo_seleccionado,
            state="readonly",
            width=50,
        ).pack(side="left", padx=5)
        tk.Entry(
            frame_file,
            textvariable=self.columna_busqueda,
            width=20,
        ).pack(side="left", padx=5)
        tk.Button(
            frame_file,
            text="📂 Seleccionar Excel",
            command=self.seleccionar_excel,
            bg="#2196F3",
            fg="white",
        ).pack(side="right")

        # 3. Sección Procesar
        frame_action = tk.Frame(root, padx=10, pady=10)
        frame_action.pack(fill="x", padx=10, pady=5)

        self.btn_procesar = tk.Button(
            frame_action,
            text="🚀 PROCESAR LISTA",
            command=self.iniciar_procesamiento_thread,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 11, "bold"),
            state="disabled",
            width=30,
        )
        self.btn_procesar.pack(pady=5)

        # Barra de Progreso
        self.progress = ttk.Progressbar(
            root,
            orient="horizontal",
            length=550,
            mode="determinate",
            style="Green.Horizontal.TProgressbar",
        )
        self.progress.pack(pady=5)

        # Consola de Log
        self.log_area = scrolledtext.ScrolledText(
            root, width=70, height=12, state="disabled", font=("Consolas", 9)
        )
        self.log_area.pack(padx=10, pady=5)

        # Verificar estado inicial
        self.verificar_padron_local()

    # --- LÓGICA DE UTILIDAD ---
    def log(self, mensaje):
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, f">> {mensaje}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")
        self.root.update_idletasks()

    def verificar_padron_local(self):
        if not os.path.exists(PATH_PADRON_DB):
            if not os.path.exists(PATH_PADRON_ZIP):
                self.estado_padron.set("❌ Padrón NO encontrado")
                self.lbl_padron.config(fg="red")
            else:
                self.estado_padron.set("⚙️ Optimizando padrón")
                self.lbl_padron.config(fg="#e98000")
                self.iniciar_optimizacion_db_threat()
        else:
            self.estado_padron.set("✅ Padrón SUNAT Listo")
            self.lbl_padron.config(fg="green")
            self.btn_descargar.config(state="normal")

    def update_progress_bar(self, decimal_percentage):
        self.root.after(
            0, lambda: self._set_progress_bar(decimal_percentage=decimal_percentage)
        )

    def _set_progress_bar(self, decimal_percentage):
        percentage = 0
        if decimal_percentage <= 0.0:
            percentage = 0
        elif decimal_percentage >= 1.0:
            percentage = 100
        else:
            percentage = decimal_percentage * 100
        self.progress["value"] = percentage
        self.root.update_idletasks()

    # --- HILOS (THREADS) ---
    def iniciar_descarga_thread(self):
        threading.Thread(target=self.descargar_logica, daemon=True).start()

    def iniciar_procesamiento_thread(self):
        threading.Thread(target=self.procesar_logica, daemon=True).start()

    def iniciar_optimizacion_db_threat(self):
        threading.Thread(target=self.optimizar_db, daemon=True).start()

    # --- LÓGICA PRINCIPAL ---
    def descargar_logica(self):
        # al descargar una nueva base, se elimina la anterior
        if os.path.exists(PATH_PADRON_DB):
            os.remove(PATH_PADRON_DB)

        self.btn_descargar.config(state="disabled")
        self.btn_procesar.config(state="disabled")

        if not os.path.exists(SUNAT_FOLDER):
            os.mkdir(SUNAT_FOLDER)

        try:
            self.log("Iniciando descarga del Padrón SUNAT (300MB+)...")
            ruc_utils.descargar_padron_reducido(
                PATH_PADRON_ZIP, progress_callback=self.update_progress_bar
            )

            if not utils.verificador_integridad_zip(PATH_PADRON_ZIP):
                os.remove(PATH_PADRON_ZIP)
                raise zipfile.BadZipFile(
                    "Archivo dañado, por favor volver a descargar."
                )
            self.log("Descarga completa.")

        except Exception as e:
            self.log(f"❌ Error en descarga: {str(e)}")
            messagebox.showerror("Error", f"Fallo en la descarga: {e}")

        finally:
            self.btn_descargar.config(state="normal")
            if self.archivo_seleccionado.get():
                self.btn_procesar.config(state="normal")
            self.progress["value"] = 0
            self.root.after(0, self.verificar_padron_local)

    def seleccionar_excel(self):
        archivo = filedialog.askopenfilename(
            filetypes=[("Excel Files", "*.xlsx *.xls")]
        )
        if archivo:
            self.archivo_seleccionado.set(archivo)
            self.log(f"Archivo seleccionado: {os.path.basename(archivo)}")
            if os.path.exists(PATH_PADRON_DB):
                self.btn_procesar.config(state="normal")
            else:
                self.log("⚠️ Primero debes descargar el padrón SUNAT.")

    def procesar_logica(self):
        self.btn_procesar.config(state="disabled")
        self.update_progress_bar(0)
        archivo_input = self.archivo_seleccionado.get()

        try:
            self.log("🔎 Iniciando búsqueda...")
            columna_busqueda = self.columna_busqueda.get()
            start_time = time.time()
            # Cargar Excel
            self.log(f"Leyendo Excel: {os.path.basename(archivo_input)}")
            self.log(f"Buscando columna: {columna_busqueda}")
            resultados = ruc_utils.buscar_rucs_desde_excel(
                archivo_input, PATH_PADRON_DB, columna_busqueda, NOMBRE_PADRON_TABLE
            )

            self.log(f"{len(resultados)} registros procesados.")

            # Guardar
            self.update_progress_bar(100)
            self.log("💾 Guardando y formateando Excel...")
            nombre_salida = os.path.splitext(archivo_input)[0] + "_PROCESADO.xlsx"
            ruc_utils.guardar_excel_rucs_formateado(
                resultados, nombre_salida, PATH_PADRON_DB, NOMBRE_PADRON_TABLE
            )

            self.log(f"✅ ¡ÉXITO! Archivo guardado:\n{os.path.basename(nombre_salida)}")
            self.log(
                f"Operación completada en {round(time.time()-start_time,2)} segundos"
            )
            messagebox.showinfo(
                "Proceso Terminado", f"Se generó el archivo:\n{nombre_salida}"
            )
            os.startfile(os.path.dirname(nombre_salida))  # Abrir carpeta

        except Exception as e:
            self.log(f"❌ ERROR CRÍTICO: {str(e)}")
            messagebox.showerror("Error", str(e))

        finally:
            self.btn_procesar.config(state="normal")

    def optimizar_db(self):
        TEMP_SANITIZED_TXT = os.path.join(SUNAT_FOLDER, ".sanitized_db.tmp")
        TEMP_DB = PATH_PADRON_DB + ".tmp"

        try:
            if not os.path.exists(PATH_PADRON_ZIP):
                raise FileNotFoundError(
                    f"No se encontró {PATH_PADRON_ZIP}, por favor descargue el padrón."
                )

            if not zipfile.is_zipfile(PATH_PADRON_ZIP):
                os.remove(PATH_PADRON_ZIP)
                raise zipfile.BadZipFile(
                    "Padrón dañado, por favor vuelva a descargarlo."
                )

            if os.path.exists(TEMP_DB):
                os.remove(TEMP_DB)

            self.log("⚙️ Iniciando optimización...")
            with zipfile.ZipFile(PATH_PADRON_ZIP, "r") as z:
                in_zip_name = z.filelist[0].filename
                z.extractall(SUNAT_FOLDER)
                os.rename(
                    os.path.join(SUNAT_FOLDER, in_zip_name),
                    os.path.relpath(TEMP_DB_TXT),
                )

            self.log("Limpiando base de datos...")
            txt_to_db.sanitize_csv(TEMP_DB_TXT, TEMP_SANITIZED_TXT)
            os.remove(TEMP_DB_TXT)

            self.log("Optimizando base de datos...")
            txt_to_db.convert_txt_to_sql(
                TEMP_SANITIZED_TXT,
                TEMP_DB,
                NOMBRE_PADRON_TABLE,
                chunk_size=10000,
                progress_callback=self.update_progress_bar,
            )
            os.remove(TEMP_SANITIZED_TXT)

            # Si es interrumpe la conversión, el archivo sera solo el temporal
            os.rename(TEMP_DB, PATH_PADRON_DB)
            self.log("✅ Base de datos lista")

        except Exception as e:
            self.log(f"❌ Error en optimización: {str(e)}")
            messagebox.showerror("Error", f"Fallo en la optimización: {e}")

        finally:
            self.root.after(0, self.verificar_padron_local)


def main():
    root = tk.Tk()
    SunatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
