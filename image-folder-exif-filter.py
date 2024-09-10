import os
import tkinter as tk
from tkinter import filedialog, ttk, simpledialog, messagebox
from PIL import Image, ExifTags, UnidentifiedImageError
import piexif
import threading
import queue
from datetime import datetime, timedelta
import subprocess


class EnhancedImageExifEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Enhanced Image EXIF Editor")
        self.root.geometry("1400x700")

        self.folder_path = ""
        self.last_folder = os.path.expanduser("~")
        self.images = []
        self.image_queue = queue.Queue()
        self.exif_data = {}
        self.recursive_scan = tk.BooleanVar(value=True)
        self.is_filtered = tk.BooleanVar(value=True)
        self.filter_tag = "DateTimeOriginal"
        self.date_tags = ['DateTimeOriginal', 'DateTimeDigitized',
                          'DateTime', 'CreateDate', 'ModifyDate']
        self.date_discrepancies = {}
        self.discrepancy_threshold = tk.StringVar(value="30")
        self.problematic_files = set()

        self.setup_ui()

    def setup_ui(self):
        # Frame for buttons
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        # Button to select folder
        self.select_folder_btn = tk.Button(
            button_frame, text="Select Folder", command=self.select_folder)
        self.select_folder_btn.pack(side=tk.LEFT, padx=5)

        # Button to open folder and check discrepancies
        self.discrepancy_check_btn = tk.Button(
            button_frame, text="Open Folder and Check Discrepancies", command=self.open_and_check_discrepancies)
        self.discrepancy_check_btn.pack(side=tk.LEFT, padx=5)

        # Checkbox for recursive scanning
        self.recursive_checkbox = tk.Checkbutton(
            button_frame, text="Scan Recursively", variable=self.recursive_scan)
        self.recursive_checkbox.pack(side=tk.LEFT, padx=5)

        # Frame for filter controls
        filter_frame = tk.Frame(self.root)
        filter_frame.pack(pady=10)

        # Toggle filter checkbox
        self.filter_checkbox = tk.Checkbutton(filter_frame, text="Filter (show only missing DateTimeOriginal)",
                                              variable=self.is_filtered, command=self.update_table)
        self.filter_checkbox.pack(side=tk.LEFT, padx=5)

        # Label and Entry for discrepancy threshold
        tk.Label(filter_frame, text="Discrepancy Threshold (days):").pack(
            side=tk.LEFT, padx=5)
        self.threshold_entry = tk.Entry(
            filter_frame, textvariable=self.discrepancy_threshold, width=5)
        self.threshold_entry.pack(side=tk.LEFT, padx=5)

        # Frame for progress bar and label
        self.progress_frame = tk.Frame(self.root)
        self.progress_frame.pack(pady=10)

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, padx=(0, 10))

        # Progress label
        self.progress_label = tk.Label(self.progress_frame, text="")
        self.progress_label.pack(side=tk.LEFT)

        # Table to display images
        columns = ("Filename",) + tuple(self.date_tags) + ("Date Discrepancy",)
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)
        self.tree.pack(expand=True, fill="both")

        # Frame for action buttons
        action_frame = tk.Frame(self.root)
        action_frame.pack(pady=10)

        # Button to edit DateTimeOriginal
        self.edit_btn = tk.Button(
            action_frame, text="Edit DateTimeOriginal", command=self.edit_date_time_original)
        self.edit_btn.pack(side=tk.LEFT, padx=5)

        # Button to show in Finder
        self.show_in_finder_btn = tk.Button(
            action_frame, text="Show in Finder", command=self.show_in_finder)
        self.show_in_finder_btn.pack(side=tk.LEFT, padx=5)

    def select_folder(self):
        self.folder_path = filedialog.askdirectory(initialdir=self.last_folder)
        if self.folder_path:
            self.last_folder = self.folder_path
            self.load_images()

    def open_and_check_discrepancies(self):
        self.folder_path = filedialog.askdirectory(initialdir=self.last_folder)
        if self.folder_path:
            self.last_folder = self.folder_path
            self.load_images(check_discrepancies=True)

    def load_images(self, check_discrepancies=False):
        self.images = []
        self.exif_data = {}
        self.date_discrepancies = {}
        self.problematic_files = set()
        self.tree.delete(*self.tree.get_children())
        self.progress_label.config(text="")

        if self.recursive_scan.get():
            for root, dirs, files in os.walk(self.folder_path):
                if "@eaDir" in dirs:
                    dirs.remove("@eaDir")
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                        self.images.append(os.path.join(root, file))
        else:
            for filename in os.listdir(self.folder_path):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    self.images.append(os.path.join(
                        self.folder_path, filename))

        self.progress_bar["maximum"] = len(self.images)
        self.progress_bar["value"] = 0

        if check_discrepancies:
            threading.Thread(
                target=self.process_images_with_discrepancies, daemon=True).start()
        else:
            threading.Thread(target=self.process_images, daemon=True).start()
        self.root.after(100, self.check_image_queue)

    def process_images(self):
        for i, image_path in enumerate(self.images):
            exif_data = self.get_exif_data(image_path)
            self.exif_data[image_path] = exif_data
            self.image_queue.put((image_path, exif_data, ""))
            self.progress_bar["value"] = i + 1
        self.image_queue.put(None)  # Signal that processing is complete

    def process_images_with_discrepancies(self):
        for i, image_path in enumerate(self.images):
            exif_data = self.get_exif_data(image_path)
            discrepancy = self.check_image_date_discrepancy(
                image_path, exif_data)
            self.exif_data[image_path] = exif_data
            self.date_discrepancies[image_path] = discrepancy
            self.image_queue.put((image_path, exif_data, discrepancy))
            self.progress_bar["value"] = i + 1
        self.image_queue.put(None)  # Signal that processing is complete

    def get_exif_data(self, image_path):
        exif_data = {tag: "" for tag in self.date_tags}
        try:
            with Image.open(image_path) as img:
                exif = {ExifTags.TAGS[k]: v for k, v in img._getexif(
                ).items() if k in ExifTags.TAGS} if img._getexif() else {}
                for tag in self.date_tags:
                    if tag in exif:
                        exif_data[tag] = exif[tag]

            # Add file system dates
            file_stats = os.stat(image_path)
            exif_data['CreateDate'] = datetime.fromtimestamp(
                file_stats.st_ctime).strftime('%Y:%m:%d %H:%M:%S')
            exif_data['ModifyDate'] = datetime.fromtimestamp(
                file_stats.st_mtime).strftime('%Y:%m:%d %H:%M:%S')
        except (AttributeError, UnidentifiedImageError, OSError, ValueError) as e:
            print(f"Error processing {image_path}: {str(e)}")
            self.problematic_files.add(image_path)
        return exif_data

    def check_image_queue(self):
        try:
            while True:
                item = self.image_queue.get_nowait()
                if item is None:  # Processing complete
                    self.update_table()
                    self.progress_label.config(text="Done")
                    return
                image_path, exif_data, discrepancy = item
                filename = os.path.basename(image_path)
                values = [filename] + [exif_data[tag]
                                       for tag in self.date_tags] + [discrepancy]
                item_id = self.tree.insert("", "end", values=values)
                if image_path in self.problematic_files:
                    self.tree.item(item_id, tags=('problematic',))
        except queue.Empty:
            self.root.after(100, self.check_image_queue)

    def update_table(self):
        self.tree.delete(*self.tree.get_children())
        for image_path, exif_data in self.exif_data.items():
            if not self.is_filtered.get() or not exif_data['DateTimeOriginal']:
                filename = os.path.basename(image_path)
                discrepancy = self.date_discrepancies.get(image_path, "")
                values = [filename] + [exif_data[tag]
                                       for tag in self.date_tags] + [discrepancy]
                item_id = self.tree.insert("", "end", values=values)
                if image_path in self.problematic_files:
                    self.tree.item(item_id, tags=('problematic',))
        self.tree.tag_configure('problematic', foreground='red')

    def edit_date_time_original(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning(
                "No Selection", "Please select an image to edit.")
            return

        filename = self.tree.item(selected_item)['values'][0]
        image_path = os.path.join(self.folder_path, filename)

        current_value = self.exif_data[image_path].get('DateTimeOriginal', '')
        new_value = simpledialog.askstring("Edit DateTimeOriginal",
                                           "Enter new DateTimeOriginal (YYYY:MM:DD HH:MM:SS):",
                                           initialvalue=current_value)

        if new_value:
            try:
                # Validate the date format
                datetime.strptime(new_value, '%Y:%m:%d %H:%M:%S')

                # Update EXIF data
                exif_dict = piexif.load(image_path)
                exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = new_value.encode()
                exif_bytes = piexif.dump(exif_dict)

                # Save the updated EXIF data to the image
                piexif.insert(exif_bytes, image_path)

                # Update our local data and the tree view
                self.exif_data[image_path]['DateTimeOriginal'] = new_value
                discrepancy = self.check_image_date_discrepancy(
                    image_path, self.exif_data[image_path])
                self.date_discrepancies[image_path] = discrepancy

                self.update_table()  # Refresh the entire table

                messagebox.showinfo(
                    "Success", f"DateTimeOriginal updated for {filename}")
            except ValueError:
                messagebox.showerror(
                    "Invalid Format", "Please enter the date in the format YYYY:MM:DD HH:MM:SS")
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred: {str(e)}")

    def check_image_date_discrepancy(self, image_path, exif_data):
        try:
            threshold = int(self.discrepancy_threshold.get())
        except ValueError:
            threshold = 30  # Default to 30 days if invalid input

        dates = []
        for tag in self.date_tags:
            if exif_data[tag]:
                try:
                    date = datetime.strptime(
                        exif_data[tag], '%Y:%m:%d %H:%M:%S')
                    dates.append((tag, date))
                except ValueError:
                    pass

        if len(dates) < 2:
            return ""

        max_diff = timedelta(days=0)
        discrepant_tags = []

        for i in range(len(dates)):
            for j in range(i+1, len(dates)):
                diff = abs(dates[i][1] - dates[j][1])
                if diff > timedelta(days=threshold) and diff > max_diff:
                    max_diff = diff
                    discrepant_tags = [dates[i][0], dates[j][0]]

        if discrepant_tags:
            return f"{discrepant_tags[0]} and {discrepant_tags[1]} differ by {max_diff.days} days"
        else:
            return ""

    def show_in_finder(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning(
                "No Selection", "Please select an image to show in Finder.")
            return

        filename = self.tree.item(selected_item)['values'][0]

        # Search for the file in the folder and its subfolders
        for root, dirs, files in os.walk(self.folder_path):
            if filename in files:
                file_path = os.path.join(root, filename)
                if os.path.exists(file_path):
                    subprocess.run(["open", "-R", file_path])
                    return

        messagebox.showerror("Error", f"File not found: {filename}")


if __name__ == "__main__":
    root = tk.Tk()
    app = EnhancedImageExifEditorApp(root)
    root.mainloop()
