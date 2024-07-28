import os
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ExifTags
import threading
import queue
from datetime import datetime, timedelta

class ImageViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Viewer with EXIF Filter and Date Discrepancy Check")
        self.root.geometry("1000x700")

        self.folder_path = ""
        self.last_folder = os.path.expanduser("~")
        self.images = []
        self.is_filtered = True
        self.filter_tag = "DateTimeOriginal"
        self.image_queue = queue.Queue()
        self.exif_data = {}
        self.recursive_scan = tk.BooleanVar()
        self.date_discrepancies = {}
        self.discrepancy_threshold = tk.StringVar(value="30")  # Default to 30 days

        self.setup_ui()

    def setup_ui(self):
        # Frame for buttons
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        # Button to select folder
        self.select_folder_btn = tk.Button(button_frame, text="Select Folder", command=self.select_folder)
        self.select_folder_btn.pack(side=tk.LEFT, padx=5)

        # New button to open folder and check discrepancies
        self.discrepancy_check_btn = tk.Button(button_frame, text="Open Folder and Check Discrepancies", command=self.open_and_check_discrepancies)
        self.discrepancy_check_btn.pack(side=tk.LEFT, padx=5)

        # Frame for filter controls
        filter_frame = tk.Frame(self.root)
        filter_frame.pack(pady=10)

        # Entry for EXIF tag
        self.tag_entry = tk.Entry(filter_frame, width=20)
        self.tag_entry.insert(0, self.filter_tag)
        self.tag_entry.pack(side=tk.LEFT, padx=5)

        # Toggle filter button
        self.filter_btn = tk.Button(filter_frame, text="Toggle Filter (ON)", command=self.toggle_filter)
        self.filter_btn.pack(side=tk.LEFT, padx=5)

        # Checkbox for recursive scanning
        self.recursive_checkbox = tk.Checkbutton(filter_frame, text="Scan Recursively", variable=self.recursive_scan)
        self.recursive_checkbox.pack(side=tk.LEFT, padx=5)

        # Label and Entry for discrepancy threshold
        tk.Label(filter_frame, text="Discrepancy Threshold (days):").pack(side=tk.LEFT, padx=5)
        self.threshold_entry = tk.Entry(filter_frame, textvariable=self.discrepancy_threshold, width=5)
        self.threshold_entry.pack(side=tk.LEFT, padx=5)

        # Frame for progress bar and label
        self.progress_frame = tk.Frame(self.root)
        self.progress_frame.pack(pady=10)

        # Progress bar
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, padx=(0, 10))

        # Progress label
        self.progress_label = tk.Label(self.progress_frame, text="")
        self.progress_label.pack(side=tk.LEFT)

        # Table to display images
        self.tree = ttk.Treeview(self.root, columns=("Filename", "Has EXIF Tag", "Date Discrepancy"), show="headings")
        self.tree.heading("Filename", text="Filename")
        self.tree.heading("Has EXIF Tag", text="Has EXIF Tag")
        self.tree.heading("Date Discrepancy", text="Date Discrepancy")
        self.tree.pack(expand=True, fill="both")

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
                    self.images.append(os.path.join(self.folder_path, filename))

        self.progress_bar["maximum"] = len(self.images)
        self.progress_bar["value"] = 0
        
        if check_discrepancies:
            threading.Thread(target=self.process_images_with_discrepancies, daemon=True).start()
        else:
            threading.Thread(target=self.process_images, daemon=True).start()
        self.root.after(100, self.check_image_queue)

    def process_images(self):
        for i, image_path in enumerate(self.images):
            has_tag = self.has_exif_tag(image_path)
            self.exif_data[image_path] = has_tag
            self.image_queue.put((image_path, has_tag, ""))
            self.progress_bar["value"] = i + 1
        self.image_queue.put(None)  # Signal that processing is complete

    def process_images_with_discrepancies(self):
        for i, image_path in enumerate(self.images):
            has_tag = self.has_exif_tag(image_path)
            discrepancy = self.check_image_date_discrepancy(image_path)
            self.exif_data[image_path] = has_tag
            self.date_discrepancies[image_path] = discrepancy
            self.image_queue.put((image_path, has_tag, discrepancy))
            self.progress_bar["value"] = i + 1
        self.image_queue.put(None)  # Signal that processing is complete

    def check_image_queue(self):
        try:
            while True:
                item = self.image_queue.get_nowait()
                if item is None:  # Processing complete
                    self.update_table()
                    self.progress_label.config(text="Done")
                    return
                image_path, has_tag, discrepancy = item
                filename = os.path.basename(image_path)
                self.tree.insert("", "end", values=(filename, "Yes" if has_tag else "No", discrepancy))
        except queue.Empty:
            self.root.after(100, self.check_image_queue)

    def has_exif_tag(self, image_path):
        try:
            with Image.open(image_path) as img:
                exif = {ExifTags.TAGS[k]: v for k, v in img._getexif().items() if k in ExifTags.TAGS}
                return self.filter_tag in exif
        except:
            return False

    def toggle_filter(self):
        self.is_filtered = not self.is_filtered
        self.filter_tag = self.tag_entry.get()
        self.filter_btn.config(text=f"Toggle Filter ({'ON' if self.is_filtered else 'OFF'})")
        self.update_table()

    def update_table(self):
        self.tree.delete(*self.tree.get_children())
        for image_path, has_tag in self.exif_data.items():
            if not self.is_filtered or has_tag:
                filename = os.path.basename(image_path)
                discrepancy = self.date_discrepancies.get(image_path, "")
                self.tree.insert("", "end", values=(filename, "Yes" if has_tag else "No", discrepancy))

    def check_image_date_discrepancy(self, image_path):
        try:
            threshold = int(self.discrepancy_threshold.get())
        except ValueError:
            threshold = 30  # Default to 30 days if invalid input

        try:
            with Image.open(image_path) as img:
                exif = {ExifTags.TAGS[k]: v for k, v in img._getexif().items() if k in ExifTags.TAGS}
                
                date_tags = ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']
                dates = []

                for tag in date_tags:
                    if tag in exif:
                        try:
                            date = datetime.strptime(exif[tag], '%Y:%m:%d %H:%M:%S')
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
        except:
            return ""

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageViewerApp(root)
    root.mainloop()