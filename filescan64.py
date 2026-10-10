import os
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
import threading

# ============================ МЕТА ============================

NAME    = "Filescan64"
VERSION = "0.9.2"
AUTHOR  = "antony3d"

# ============================ ОКНО ============================

WINDOW_START_W = 800
WINDOW_START_H = 720
# Минимальный размер захардкожен в self.root.minsize()

# ============================ КОНСТАНТЫ ============================

LARGE_FILE_THRESHOLD  = 50 * 1024 * 1024    # 50 МБ — порог для «большого» файла (частые UI-апдейты)
PROGRESS_FILE_MIN     = 100 * 1024 * 1024   # 100 МБ — минимальный размер файла для показа прогрессбара
UI_UPDATE_INTERVAL    = 0.25                 # секунды между промежуточными обновлениями UI
BUFFER_SIZE           = 256 * 1024          # 256 КБ — размер чанка при чтении

SPEED_LABEL_WIDTH     = 14                  # ширина label для значений скорости (символов)
FILE_PROGRESS_HEIGHT  = 28                  # высота зарезервированного места под прогрессбар файла

def human_time(seconds):
    """Форматирует секунды в 'Xm Ys' или 'Xs'."""
    if seconds is None or seconds < 0 or seconds != seconds:  # NaN safety
        return "--"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

class FileScanApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{NAME} v{VERSION} — by {AUTHOR}")
        self.root.geometry(f"{WINDOW_START_W}x{WINDOW_START_H}")
        self.root.minsize(700, 600)

        self.scanning = False
        self.stop_requested = False

        # --- UI LAYOUT ---
        # Выбор директории
        dir_frame = ttk.LabelFrame(root, text=" Startup folder ", padding=10)
        dir_frame.pack(fill="x", padx=10, pady=5)

        self.path_entry = ttk.Entry(dir_frame)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_browse = ttk.Button(dir_frame, text="Browse...", command=self.browse_folder)
        self.btn_browse.pack(side="right")

        # Управление
        ctrl_frame = ttk.Frame(root, padding=5)
        ctrl_frame.pack(fill="x", padx=10)

        self.btn_start = ttk.Button(ctrl_frame, text="Start Scan", command=self.start_scan)
        self.btn_start.pack(side="left", padx=5)

        self.btn_stop = ttk.Button(ctrl_frame, text="Stop", command=self.stop_scan, state="disabled")
        self.btn_stop.pack(side="left", padx=5)

        # Чекбокс «общий прогресс»
        self.show_global_progress = tk.BooleanVar(value=False)
        self.chk_global = ttk.Checkbutton(
            ctrl_frame,
            text="Show global progress (pre-scans tree size)",
            variable=self.show_global_progress,
        )
        self.chk_global.pack(side="left", padx=15)

        # Текущий файл
        file_frame = ttk.LabelFrame(root, text=" Current File ", padding=10)
        file_frame.pack(fill="x", padx=10, pady=5)
        self.lbl_current_file = ttk.Label(file_frame, text="None", font=("Consolas", 9), anchor="w")
        self.lbl_current_file.pack(fill="x")

        # --- Зарезервированное место под прогрессбар текущего файла ---
        # Внешний holder всегда упакован, фиксированной высоты. Внутри — реальные виджеты,
        # которые показываются/скрываются. Благодаря фиксированной высоте holder'а
        # интерфейс не прыгает при появлении/исчезновении прогрессбара.
        self.file_progress_holder = ttk.Frame(file_frame, height=FILE_PROGRESS_HEIGHT)
        self.file_progress_holder.pack(fill="x", pady=(6, 0))
        self.file_progress_holder.pack_propagate(False)

        self.file_progress_frame = ttk.Frame(self.file_progress_holder)
        self.lbl_file_progress = ttk.Label(
            self.file_progress_frame, text="0.0 / 0.0 MB  (0.0%)",
            font=("Consolas", 9)
        )
        self.lbl_file_progress.pack(side="left", padx=(0, 8))
        self.file_progress = ttk.Progressbar(
            self.file_progress_frame, mode="determinate", maximum=100.0
        )
        self.file_progress.pack(side="left", fill="x", expand=True)
        # изначально не упакован внутри holder'а, но holder занимает место

        # Блок статистики скорости текущего файла
        # ВАЖНО: сохраняем ссылку — используется как якорь для вставки tree_progress_frame
        self.speed_frame = ttk.LabelFrame(root, text=" File Performance Statistics ", padding=10)
        self.speed_frame.pack(fill="x", padx=10, pady=5)

        stat_grid = ttk.Frame(self.speed_frame)
        stat_grid.pack(fill="x")

        ttk.Label(stat_grid, text="Min Speed:").grid(row=0, column=0, sticky="w", padx=5)
        self.val_min = ttk.Label(stat_grid, text="0.00", font=("Helvetica", 10, "bold"),
                                 width=SPEED_LABEL_WIDTH, anchor="e")
        self.val_min.grid(row=0, column=1, sticky="e", padx=(5, 20))

        ttk.Label(stat_grid, text="Max Speed:").grid(row=0, column=2, sticky="w", padx=5)
        self.val_max = ttk.Label(stat_grid, text="0.00", font=("Helvetica", 10, "bold"),
                                 width=SPEED_LABEL_WIDTH, anchor="e")
        self.val_max.grid(row=0, column=3, sticky="e", padx=(5, 20))

        ttk.Label(stat_grid, text="Avg Speed (File):").grid(row=0, column=4, sticky="w", padx=5)
        self.val_avg = ttk.Label(stat_grid, text="0.00", font=("Helvetica", 10, "bold"),
                                 width=SPEED_LABEL_WIDTH, anchor="e")
        self.val_avg.grid(row=0, column=5, sticky="e", padx=(5, 20))
        
        # --- Progress bar всего дерева (показываем только если галочка включена) ---
        self.tree_progress_frame = ttk.LabelFrame(root, text=" Global Progress ", padding=10)
        self.lbl_tree_progress = ttk.Label(
            self.tree_progress_frame,
            text="0.0 / 0.0 MB  (0.0%)   ETA: --",
            font=("Consolas", 9),
        )
        self.lbl_tree_progress.pack(anchor="w")
        self.tree_progress = ttk.Progressbar(self.tree_progress_frame, mode="determinate", maximum=100.0)
        self.tree_progress.pack(fill="x", pady=(4, 0))
        # изначально скрыт — не пакуем вообще

        # Общая статистика по дереву
        tree_frame = ttk.LabelFrame(root, text=" Global Tree Statistics ", padding=10)
        tree_frame.pack(fill="x", padx=10, pady=5)

        tree_grid = ttk.Frame(tree_frame)
        tree_grid.pack(fill="x")

        self.lbl_global_stats = ttk.Label(tree_grid, text="Files: 0  |  Folders: 0  |  Read: 0 MB")
        self.lbl_global_stats.pack(side="left", padx=5)

        self.lbl_global_speed = ttk.Label(tree_grid, text="Global Avg Rate: 0.00 MB/s",
                                          font=("Helvetica", 9, "bold"))
        self.lbl_global_speed.pack(side="right", padx=5)

        # Глобальные Min / Max скорости
        range_grid = ttk.Frame(tree_frame)
        range_grid.pack(fill="x", pady=(5, 0))

        ttk.Label(range_grid, text="Global Min Speed:").pack(side="left", padx=5)
        self.val_g_min = ttk.Label(range_grid, text="0.00", font=("Helvetica", 10, "bold"),
                                   width=SPEED_LABEL_WIDTH, anchor="e")
        self.val_g_min.pack(side="left", padx=(5, 25))

        ttk.Label(range_grid, text="Global Max Speed:").pack(side="left", padx=5)
        self.val_g_max = ttk.Label(range_grid, text="0.00", font=("Helvetica", 10, "bold"),
                                   width=SPEED_LABEL_WIDTH, anchor="e")
        self.val_g_max.pack(side="left", padx=(5, 20))

        # Лог ошибок
        log_frame = ttk.LabelFrame(root, text=" Error & Event Log ", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_area = scrolledtext.ScrolledText(log_frame, height=8, font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True)

    # ============================ UI-хелперы ============================

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, os.path.normpath(folder))

    def start_scan(self):
        target = self.path_entry.get().strip()
        if not target or not os.path.exists(target):
            self.log_message("ERROR: Invalid target path.")
            return

        self.scanning = True
        self.stop_requested = False
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_browse.config(state="disabled")
        self.chk_global.config(state="disabled")
        self.log_area.delete("1.0", tk.END)
        self.log_message(f"{NAME} v{VERSION} — by {AUTHOR}")
        self.log_message(f"Starting scan for: {target}")

        threading.Thread(target=self.scan_worker, args=(target,), daemon=True).start()

    def stop_scan(self):
        if self.scanning:
            self.stop_requested = True
            self.log_message("Stop requested by user...")

    def log_message(self, message):
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)

    def format_speed(self, speed_mbs):
        if speed_mbs < 0.1:
            return f"{speed_mbs * 1024:.2f} KB/s"
        return f"{speed_mbs:.2f} MB/s"

    # ============================ Обновление панелей ============================

    def _update_file_stats(self, speeds, bytes_read, start_time):
        if speeds:
            self.val_min.config(text=self.format_speed(min(speeds)))
            self.val_max.config(text=self.format_speed(max(speeds)))
        else:
            self.val_min.config(text="0.00 MB/s")
            self.val_max.config(text="0.00 MB/s")

        total_time = time.perf_counter() - start_time
        if bytes_read > 0 and total_time > 0:
            avg = (bytes_read / 1024 / 1024) / total_time
            self.val_avg.config(text=self.format_speed(avg))
        else:
            self.val_avg.config(text="0.00 MB/s")

    def _update_global_stats(self, file_count, folder_count, total_bytes,
                             start_time, g_min, g_max):
        total_mb = total_bytes / 1024 / 1024
        self.lbl_global_stats.config(
            text=f"Files: {file_count}  |  Folders: {folder_count}  |  Read: {total_mb:.1f} MB"
        )

        elapsed = time.perf_counter() - start_time
        avg = (total_mb / elapsed) if elapsed > 0 else 0
        self.lbl_global_speed.config(text=f"Global Avg Rate: {self.format_speed(avg)}")

        self.val_g_min.config(text=self.format_speed(g_min) if g_min is not None else "0.00 MB/s")
        self.val_g_max.config(text=self.format_speed(g_max) if g_max is not None else "0.00 MB/s")

    def _show_file_progress(self, visible):
        """Показать/скрыть прогрессбар текущего файла.
        Виджеты пакуются внутрь holder'а с фиксированной высотой, поэтому
        остальной интерфейс не сдвигается."""
        if visible and not self.file_progress_frame.winfo_ismapped():
            self.file_progress_frame.pack(fill="x")
        elif not visible and self.file_progress_frame.winfo_ismapped():
            self.file_progress_frame.pack_forget()

    def _update_file_progress(self, bytes_read, file_size):
        if file_size <= 0:
            return
        mb_read = bytes_read / 1024 / 1024
        mb_total = file_size / 1024 / 1024
        pct = min(100.0, 100.0 * bytes_read / file_size)
        self.lbl_file_progress.config(
            text=f"{mb_read:.1f} / {mb_total:.1f} MB  ({pct:.1f}%)"
        )
        self.file_progress["value"] = pct

    def _show_tree_progress(self, visible):
        """Показать/скрыть прогрессбар всего дерева.
        Вставляем перед блоком File Performance Statistics — это стабильный,
        всегда упакованный якорь."""
        if visible and not self.tree_progress_frame.winfo_ismapped():
            self.tree_progress_frame.pack(fill="x", padx=10, pady=5,
                                          before=self.speed_frame)
        elif not visible and self.tree_progress_frame.winfo_ismapped():
            self.tree_progress_frame.pack_forget()

    def _update_tree_progress(self, total_bytes, total_size, start_time):
        if total_size <= 0:
            return
        mb_read = total_bytes / 1024 / 1024
        mb_total = total_size / 1024 / 1024
        pct = min(100.0, 100.0 * total_bytes / total_size)

        elapsed = time.perf_counter() - start_time
        speed_bps = total_bytes / elapsed if elapsed > 0 else 0
        remaining_bytes = max(0, total_size - total_bytes)
        eta = (remaining_bytes / speed_bps) if speed_bps > 0 else None

        self.lbl_tree_progress.config(
            text=f"{mb_read:.1f} / {mb_total:.1f} MB  ({pct:.1f}%)   ETA: {human_time(eta)}"
        )
        self.tree_progress["value"] = pct

    # ============================ Pre-scan: общий размер дерева ============================

    def _calculate_tree_size(self, target_dir):
        """Проходит по дереву и считает суммарный размер файлов.
        Возвращает (total_size, file_count)."""
        total_size = 0
        file_count = 0
        for root_path, dirs, files in os.walk(target_dir):
            if self.stop_requested:
                break
            for f in files:
                fp = os.path.join(root_path, f)
                try:
                    total_size += os.path.getsize(fp)
                    file_count += 1
                except Exception:
                    pass
        return total_size, file_count

    # ============================ Основной цикл сканирования ============================

    def scan_worker(self, target_dir):
        total_bytes = 0
        file_count = 0
        folder_count = 0

        # Pre-scan для глобального прогресса
        tree_total_size = 0
        if self.show_global_progress.get():
            self.log_message("Calculating tree size for global progress...")
            self._show_tree_progress(True)
            t_pre = time.perf_counter()
            tree_total_size, _ = self._calculate_tree_size(target_dir)
            pre_time = time.perf_counter() - t_pre
            self.log_message(
                f"Tree size: {tree_total_size / 1024 / 1024:.1f} MB "
                f"({tree_total_size / 1024 / 1024 / 1024:.2f} GB), pre-scan took {pre_time:.1f}s"
            )
            if self.stop_requested:
                self._finish_scan(aborted=True)
                return
        else:
            self._show_tree_progress(False)

        global_start_time = time.perf_counter()
        global_min_speed = None
        global_max_speed = None

        for root_path, dirs, files in os.walk(target_dir):
            if self.stop_requested:
                break

            folder_count += len(dirs)

            for file in files:
                if self.stop_requested:
                    break

                file_path = os.path.join(root_path, file)
                file_count += 1

                display_path = file_path if len(file_path) < 75 else "..." + file_path[-72:]
                self.lbl_current_file.config(text=display_path)

                try:
                    file_size = os.path.getsize(file_path)
                except Exception:
                    file_size = 0
                is_large = file_size > LARGE_FILE_THRESHOLD
                show_progress_bar = file_size > PROGRESS_FILE_MIN

                # Показать/скрыть прогрессбар текущего файла
                self._show_file_progress(show_progress_bar)
                if show_progress_bar:
                    self._update_file_progress(0, file_size)

                file_bytes_read = 0
                file_speeds = []
                file_start_time = time.perf_counter()
                last_ui_update = file_start_time

                try:
                    with open(file_path, 'rb') as f:
                        while True:
                            if self.stop_requested:
                                break

                            chunk_start = time.perf_counter()
                            chunk = f.read(BUFFER_SIZE)
                            chunk_end = time.perf_counter()

                            if not chunk:
                                break

                            chunk_len = len(chunk)
                            file_bytes_read += chunk_len
                            total_bytes += chunk_len

                            chunk_time = chunk_end - chunk_start
                            if chunk_time > 0:
                                speed_mbs = (chunk_len / 1024 / 1024) / chunk_time
                                file_speeds.append(speed_mbs)

                                if global_min_speed is None or speed_mbs < global_min_speed:
                                    global_min_speed = speed_mbs
                                if global_max_speed is None or speed_mbs > global_max_speed:
                                    global_max_speed = speed_mbs

                            now_ui = time.perf_counter()
                            if is_large and (now_ui - last_ui_update) >= UI_UPDATE_INTERVAL:
                                self._update_file_stats(file_speeds, file_bytes_read, file_start_time)
                                self._update_global_stats(file_count, folder_count, total_bytes,
                                                          global_start_time,
                                                          global_min_speed, global_max_speed)
                                if show_progress_bar:
                                    self._update_file_progress(file_bytes_read, file_size)
                                if self.show_global_progress.get() and tree_total_size > 0:
                                    self._update_tree_progress(total_bytes, tree_total_size,
                                                               global_start_time)
                                last_ui_update = now_ui

                    # Финальные обновления для файла
                    self._update_file_stats(file_speeds, file_bytes_read, file_start_time)
                    self._update_global_stats(file_count, folder_count, total_bytes,
                                              global_start_time,
                                              global_min_speed, global_max_speed)
                    if show_progress_bar:
                        self._update_file_progress(file_bytes_read, file_size)
                    if self.show_global_progress.get() and tree_total_size > 0:
                        self._update_tree_progress(total_bytes, tree_total_size,
                                                   global_start_time)

                except Exception as e:
                    self.log_message(f"ERROR reading [{file}]: {str(e)}")

        # Скрываем прогрессбар файла после завершения
        self._show_file_progress(False)

        self._finish_scan(aborted=self.stop_requested)

    def _finish_scan(self, aborted):
        self.scanning = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.btn_browse.config(state="normal")
        self.chk_global.config(state="normal")
        self.lbl_current_file.config(text="Done.")
        if aborted:
            self.log_message("Scan aborted by user.")
        else:
            self.log_message("Scan finished successfully.")

if __name__ == "__main__":
    root = tk.Tk()
    app = FileScanApp(root)
    root.mainloop()
