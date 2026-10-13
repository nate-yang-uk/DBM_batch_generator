import ctypes
import itertools
import re
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD


# ============================================================
# DARK THEME
# ============================================================

BG = "#1e1e1e"
PANEL = "#252526"

TEXT = "#f2f2f2"
MUTED = "#aaaaaa"

ACCENT = "#3a8dde"
ACCENT_HOVER = "#4a9ae8"

BUTTON_BG = "#2d2d30"
BUTTON_ACTIVE = "#3a3a3d"

BORDER = "#666666"

DISABLED_BG = "#333333"
DISABLED_TEXT = "#777777"


# ============================================================
# PARAMETERS
# ============================================================

# Number of frames to register.
#
# Examples:
#
# N_FRAMES = [563]
#
# or:
#
# N_FRAMES = [100, 200, 300, 400, 563]
#
N_FRAMES = [100,200,300]


FULL_FRAME_NCC_LINES_TO_IGNORE = [200]

STRIP_NCC_ROWS_TO_IGNORE = [24, 32]

STRIP_NCC_COLUMNS_TO_IGNORE = [150]

STRIP_NCC_THRESHOLDS = [0.65]

STRIP_MAX_DISPLACEMENTS = [200]

FULL_FRAME_MAX_DISPLACEMENTS = [200]

DCT_PERCENTAGES = [50]

MIN_OVERLAP_STRIP = [4,5]

MIN_OVERLAP_FULL_FRAME = [5]


# ============================================================
# WINDOWS DARK TITLE BAR
# ============================================================

def enable_dark_title_bar(window):
    """
    Enable Windows dark title bar.

    If unsupported, the function quietly does nothing.
    """

    try:
        window.update_idletasks()

        hwnd = ctypes.windll.user32.GetParent(
            window.winfo_id()
        )

        value = ctypes.c_int(1)

        # Newer Windows 10 / Windows 11
        attribute = 20

        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            attribute,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )

        # Some older Windows 10 builds use 19 instead.
        if result != 0:

            attribute = 19

            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )

    except Exception:
        pass


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_number(value):
    """
    Make a number safe for use inside a filename.

    Example:
        0.65 -> 0p65
        -1.5 -> m1p5
    """

    return str(value).replace(".", "p").replace("-", "m")


def shorten_filename(name, max_length=80):
    """
    Shorten very long filenames for display in the GUI only.
    The actual filename is not changed.
    """

    if len(name) <= max_length:
        return name

    start_length = max_length // 2
    end_length = max_length - start_length - 3

    return (
        name[:start_length]
        + "..."
        + name[-end_length:]
    )


def replace_parameter(
    raw_data: bytes,
    parameter_name: str,
    opcode: bytes,
    new_value,
) -> bytes:
    """
    Replace a parameter inside the DMB binary/text structure.

    Supported opcodes:

        I
            Integer
            Example:
            I200

        L
            Python-style long integer
            Example:
            L563L

        F
            Float

        V
            String
    """

    name = re.escape(
        parameter_name.encode("ascii")
    )

    pattern = re.compile(
        rb"("
        rb"S'" + name + rb"'"
        rb"\r?\n"
        rb"p\d+"
        rb"\r?\n"
        + opcode
        + rb")"
        rb"([^\r\n]*)"
        rb"(\r?\n)"
    )

    matches = list(
        pattern.finditer(raw_data)
    )

    # If parameter does not exist, skip it.
    if len(matches) == 0:

        print(
            f"Skipped: {parameter_name} "
            f"(not found in template)"
        )

        return raw_data

    # More than one match is ambiguous.
    if len(matches) > 1:

        raise ValueError(
            f"Expected one occurrence of "
            f"{parameter_name}, "
            f"but found {len(matches)}."
        )

    # --------------------------------------------------------
    # Integer
    # --------------------------------------------------------

    if opcode == b"I":

        value_bytes = str(
            int(new_value)
        ).encode("ascii")

    # --------------------------------------------------------
    # Python long integer
    #
    # DMB example:
    #
    # S'n_frames'
    # p13
    # L563L
    #
    # The pattern already captures the first L opcode,
    # therefore the replacement content should be:
    #
    # 563L
    # --------------------------------------------------------

    elif opcode == b"L":

        value_bytes = (
            f"{int(new_value)}L"
        ).encode("ascii")

    # --------------------------------------------------------
    # Float
    # --------------------------------------------------------

    elif opcode == b"F":

        value_bytes = repr(
            float(new_value)
        ).encode("ascii")

    # --------------------------------------------------------
    # String
    # --------------------------------------------------------

    elif opcode == b"V":

        value_bytes = str(
            new_value
        ).encode("ascii")

    else:

        raise ValueError(
            f"Unsupported opcode: {opcode}"
        )

    modified_data, count = pattern.subn(
        lambda match: (
            match.group(1)
            + value_bytes
            + match.group(3)
        ),
        raw_data,
        count=1,
    )

    if count != 1:

        raise RuntimeError(
            f"Failed to replace "
            f"{parameter_name}."
        )

    return modified_data


# ============================================================
# GENERATE DMB FILES
# ============================================================

def generate_files(template_batch: Path):

    output_dir = template_batch.parent

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_data = (
        template_batch.read_bytes()
    )

    combinations = itertools.product(
        N_FRAMES,
        FULL_FRAME_NCC_LINES_TO_IGNORE,
        STRIP_NCC_ROWS_TO_IGNORE,
        STRIP_NCC_COLUMNS_TO_IGNORE,
        STRIP_NCC_THRESHOLDS,
        STRIP_MAX_DISPLACEMENTS,
        FULL_FRAME_MAX_DISPLACEMENTS,
        DCT_PERCENTAGES,
        MIN_OVERLAP_STRIP,
        MIN_OVERLAP_FULL_FRAME,
    )

    created_files = []

    for (
        n_frames,
        full_frame_ncc_lines,
        strip_ncc_rows,
        strip_ncc_columns,
        strip_ncc_threshold,
        strip_max_displacement,
        full_frame_max_displacement,
        dct_percentage,
        min_overlap_strip,
        min_overlap_full_frame,
    ) in combinations:

        # ----------------------------------------------------
        # Strip geometry
        # ----------------------------------------------------

        lines_per_strip = (
            2 * strip_ncc_rows
        )

        lines_between_strips = (
            lines_per_strip
        )

        modified_data = original_data

        # ====================================================
        # NUMBER OF FRAMES
        # ====================================================

        modified_data = replace_parameter(
            modified_data,
            "n_frames",
            b"L",
            n_frames,
        )

        # ====================================================
        # FULL FRAME NCC
        # ====================================================

        modified_data = replace_parameter(
            modified_data,
            "full_frame_ncc_n_lines_to_ignore",
            b"I",
            full_frame_ncc_lines,
        )

        # ====================================================
        # STRIP GEOMETRY
        # ====================================================

        modified_data = replace_parameter(
            modified_data,
            "frame_strip_lines_between_strips_start",
            b"I",
            lines_between_strips,
        )

        modified_data = replace_parameter(
            modified_data,
            "frame_strip_lines_per_strip",
            b"I",
            lines_per_strip,
        )

        # ====================================================
        # STRIP NCC
        # ====================================================

        modified_data = replace_parameter(
            modified_data,
            "frame_strip_ncc_n_rows_to_ignore",
            b"I",
            strip_ncc_rows,
        )

        modified_data = replace_parameter(
            modified_data,
            "frame_strip_ncc_n_columns_to_ignore",
            b"I",
            strip_ncc_columns,
        )

        modified_data = replace_parameter(
            modified_data,
            "frame_strip_ncc_threshold",
            b"F",
            strip_ncc_threshold,
        )

        # ====================================================
        # DISPLACEMENT
        # ====================================================

        modified_data = replace_parameter(
            modified_data,
            "strip_max_displacement_threshold",
            b"I",
            strip_max_displacement,
        )

        modified_data = replace_parameter(
            modified_data,
            "full_frame_max_displacement_threshold",
            b"I",
            full_frame_max_displacement,
        )

        # ====================================================
        # DCT
        # ====================================================

        modified_data = replace_parameter(
            modified_data,
            "strip_DCT_terms_retained_percentage",
            b"F",
            dct_percentage,
        )

        # ====================================================
        # CROPPING OVERLAP
        # ====================================================

        modified_data = replace_parameter(
            modified_data,
            "min_overlap_for_cropping_strip_image",
            b"I",
            min_overlap_strip,
        )

        modified_data = replace_parameter(
            modified_data,
            "min_overlap_for_cropping_full_frame_image",
            b"I",
            min_overlap_full_frame,
        )

        # ====================================================
        # USER-DEFINED SUFFIX
        # ====================================================

        suffix = (
            f"_nf_{n_frames}"
            f"_ffncc_{full_frame_ncc_lines}"
            f"_rows_{strip_ncc_rows}"
            f"_cols_{strip_ncc_columns}"
            f"_thr_{safe_number(strip_ncc_threshold)}"
            f"_smd_{strip_max_displacement}"
            f"_fmd_{full_frame_max_displacement}"
            f"_dct_{safe_number(dct_percentage)}"
            f"_mos_{min_overlap_strip}"
            f"_mof_{min_overlap_full_frame}"
        )

        modified_data = replace_parameter(
            modified_data,
            "user_defined_suffix",
            b"V",
            suffix,
        )

        # ====================================================
        # SAVE
        # ====================================================

        output_name = (
            f"test{suffix}.dmb"
        )

        output_path = (
            output_dir / output_name
        )

        if output_path.exists():
            output_path.unlink()

        output_path.write_bytes(
            modified_data
        )

        created_files.append(
            output_path
        )

        print(
            f"Created: {output_name} | "
            f"n_frames={n_frames}"
        )

    return created_files


# ============================================================
# GUI
# ============================================================

class DMBGeneratorGUI:

    def __init__(self):

        # ----------------------------------------------------
        # Root window
        # ----------------------------------------------------

        self.root = TkinterDnD.Tk()

        self.root.title(
            "DMB Batch Generator"
        )

        self.root.geometry(
            "650x460"
        )

        self.root.minsize(
            600,
            430,
        )

        self.root.configure(
            bg=BG
        )

        self.template_file = None

        # Dark Windows title bar
        enable_dark_title_bar(
            self.root
        )

        # ----------------------------------------------------
        # Main container
        # ----------------------------------------------------

        self.main_frame = tk.Frame(
            self.root,
            bg=BG,
            padx=22,
            pady=22,
        )

        self.main_frame.pack(
            fill="both",
            expand=True,
        )

        # ----------------------------------------------------
        # Title
        # ----------------------------------------------------

        self.title_label = tk.Label(
            self.main_frame,

            text="DMB Batch Generator",

            font=(
                "Segoe UI",
                17,
                "bold",
            ),

            bg=BG,
            fg=TEXT,
        )

        self.title_label.pack(
            pady=(0, 5)
        )

        # ----------------------------------------------------
        # Subtitle
        # ----------------------------------------------------

        self.subtitle_label = tk.Label(
            self.main_frame,

            text=(
                "Select a template or "
                "drop a .dmb file anywhere"
            ),

            font=(
                "Segoe UI",
                9,
            ),

            bg=BG,
            fg=MUTED,
        )

        self.subtitle_label.pack(
            pady=(0, 15)
        )

        # ----------------------------------------------------
        # Select file button
        # ----------------------------------------------------

        self.select_button = tk.Button(
            self.main_frame,

            text="Select .dmb File",

            command=self.select_file,

            width=20,
            height=2,

            font=(
                "Segoe UI",
                10,
            ),

            bg=BUTTON_BG,
            fg=TEXT,

            activebackground=BUTTON_ACTIVE,
            activeforeground=TEXT,

            relief="flat",
            bd=0,

            cursor="hand2",
        )

        self.select_button.pack(
            pady=(0, 14)
        )

        # ----------------------------------------------------
        # Drop area
        # ----------------------------------------------------

        self.drop_canvas = tk.Canvas(
            self.main_frame,

            height=100,

            bg=PANEL,

            highlightthickness=0,
            bd=0,
        )

        self.drop_canvas.pack(
            fill="x",
            padx=20,
            pady=5,
        )

        self.drop_canvas.bind(
            "<Configure>",
            self.draw_drop_box,
        )

        # ----------------------------------------------------
        # Selected filename
        # ----------------------------------------------------

        self.file_label = tk.Label(
            self.main_frame,

            text="No file selected",

            wraplength=560,

            justify="center",

            font=(
                "Segoe UI",
                9,
            ),

            bg=BG,
            fg=MUTED,
        )

        self.file_label.pack(
            pady=(10, 3)
        )

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        self.status_label = tk.Label(
            self.main_frame,

            text="Waiting for template",

            wraplength=560,

            justify="center",

            font=(
                "Segoe UI",
                9,
            ),

            bg=BG,
            fg=MUTED,
        )

        self.status_label.pack(
            pady=(2, 12)
        )

        # ----------------------------------------------------
        # Generate button
        # ----------------------------------------------------

        self.generate_button = tk.Button(
            self.main_frame,

            text="Generate Batch Files",

            command=self.generate,

            state="disabled",

            width=22,
            height=2,

            font=(
                "Segoe UI",
                10,
                "bold",
            ),

            bg=ACCENT,
            fg="white",

            activebackground=ACCENT_HOVER,
            activeforeground="white",

            disabledforeground=DISABLED_TEXT,
            # disabledbackground=DISABLED_BG,

            relief="flat",
            bd=0,

            cursor="hand2",
        )

        self.generate_button.pack()

        # ----------------------------------------------------
        # Drag and drop
        #
        # Register all widgets so the drop works over the
        # entire window, not just over the dashed box.
        # ----------------------------------------------------

        self.drop_widgets = [
            self.root,
            self.main_frame,
            self.title_label,
            self.subtitle_label,
            self.select_button,
            self.drop_canvas,
            self.file_label,
            self.status_label,
            self.generate_button,
        ]

        for widget in self.drop_widgets:

            widget.drop_target_register(
                DND_FILES
            )

            widget.dnd_bind(
                "<<Drop>>",
                self.on_drop,
            )

        # Windows may redraw the native title bar shortly
        # after Tk starts, so apply dark mode once again.
        self.root.after(
            100,
            lambda: enable_dark_title_bar(
                self.root
            ),
        )

    # ========================================================
    # DRAW DROP BOX
    # ========================================================

    def draw_drop_box(
        self,
        event=None,
    ):

        self.drop_canvas.delete(
            "all"
        )

        width = (
            self.drop_canvas.winfo_width()
        )

        height = (
            self.drop_canvas.winfo_height()
        )

        margin = 5

        self.drop_canvas.create_rectangle(
            margin,
            margin,

            width - margin,
            height - margin,

            dash=(7, 5),

            width=2,

            outline=BORDER,
        )

        self.drop_canvas.create_text(
            width / 2,

            height / 2 - 11,

            text="Drag & Drop .dmb File",

            font=(
                "Segoe UI",
                11,
                "bold",
            ),

            fill=TEXT,
        )

        self.drop_canvas.create_text(
            width / 2,

            height / 2 + 17,

            text="Drop anywhere in this window",

            font=(
                "Segoe UI",
                9,
            ),

            fill=MUTED,
        )

    # ========================================================
    # FILE SELECTOR
    # ========================================================

    def select_file(self):

        filename = filedialog.askopenfilename(

            title="Select template .dmb file",

            initialdir=r"C:\Data",

            filetypes=[
                (
                    "DMB files",
                    "*.dmb",
                ),
                (
                    "All files",
                    "*.*",
                ),
            ],
        )

        enable_dark_title_bar(
            self.root
        )

        if filename:

            self.set_template(
                filename
            )

    # ========================================================
    # DRAG AND DROP
    # ========================================================

    def on_drop(
        self,
        event,
    ):

        try:

            files = (
                self.root.tk.splitlist(
                    event.data
                )
            )

        except Exception:

            files = [
                event.data
            ]

        if not files:
            return

        filename = files[0]

        self.set_template(
            filename
        )

    # ========================================================
    # LOAD TEMPLATE
    # ========================================================

    def set_template(
        self,
        filename,
    ):

        filename = (
            str(filename)
            .strip()
            .strip("{}")
        )

        path = Path(
            filename
        )

        if not path.exists():

            messagebox.showerror(
                "File not found",
                f"Could not find:\n\n{path}",
            )

            enable_dark_title_bar(
                self.root
            )

            return

        if not path.is_file():

            messagebox.showwarning(
                "Invalid selection",
                "Please drop a .dmb file, not a folder.",
            )

            enable_dark_title_bar(
                self.root
            )

            return

        if path.suffix.lower() != ".dmb":

            messagebox.showwarning(
                "Invalid file",
                "Please select a .dmb file.",
            )

            enable_dark_title_bar(
                self.root
            )

            return

        self.template_file = path

        self.file_label.config(
            text=shorten_filename(
                path.name
            ),
            fg=TEXT,
        )

        self.status_label.config(
            text=(
                f"Output folder: "
                f"{path.parent}"
            ),
            fg=MUTED,
        )

        self.generate_button.config(
            state="normal"
        )

        # Let Tk recalculate required size
        self.root.update_idletasks()

    # ========================================================
    # GENERATE
    # ========================================================

    def generate(self):

        if self.template_file is None:
            return

        try:

            self.generate_button.config(
                state="disabled"
            )

            self.select_button.config(
                state="disabled"
            )

            self.status_label.config(
                text="Generating...",
                fg=TEXT,
            )

            self.root.update_idletasks()

            created = generate_files(
                self.template_file
            )

            self.status_label.config(
                text=(
                    f"Done. Created "
                    f"{len(created)} files."
                ),
                fg=TEXT,
            )

            messagebox.showinfo(
                "Complete",
                (
                    f"Created "
                    f"{len(created)} DMB files.\n\n"
                    f"Saved in:\n"
                    f"{self.template_file.parent}"
                ),
            )

            enable_dark_title_bar(
                self.root
            )

        except Exception as exc:

            self.status_label.config(
                text="Error",
                fg="#ff7777",
            )

            messagebox.showerror(
                "Error",
                str(exc),
            )

            enable_dark_title_bar(
                self.root
            )

        finally:

            self.generate_button.config(
                state="normal"
            )

            self.select_button.config(
                state="normal"
            )

    # ========================================================
    # RUN
    # ========================================================

    def run(self):

        self.root.mainloop()


# ============================================================
# RUN PROGRAM
# ============================================================

if __name__ == "__main__":

    app = DMBGeneratorGUI()

    app.run()