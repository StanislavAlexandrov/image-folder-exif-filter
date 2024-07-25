import os
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ExifTags
import threading
import queue

class ImageViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Viewer with EXIF Filter")
        self.root.geometry("800x600")

        self.folder_path = ""
        self.last_folder = os.path.expanduser("~")  # Start with user's home directory
        self.images = []
        self.is_filtered = True
        self.filter_tag = "DateTimeOriginal"
        self.image_queue = queue.Queue()
        self.exif_data = {}

        self.setup_ui()

    def setup_ui(self):
        # Button to select folder
        self.select_folder_btn = tk.Button(self.root, text="Select Folder", command=self.select_folder)
        self.select_folder_btn.pack(pady=10)

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
        self.tree = ttk.Treeview(self.root, columns=("Filename", "Has EXIF Tag"), show="headings")
        self.tree.heading("Filename", text="Filename")
        self.tree.heading("Has EXIF Tag", text="Has EXIF Tag")
        self.tree.pack(expand=True, fill="both")

    def select_folder(self):
        self.folder_path = filedialog.askdirectory(initialdir=self.last_folder)
        if self.folder_path:
            self.last_folder = self.folder_path  # Remember this folder for next time
            self.load_images()

    def load_images(self):
        self.images = []
        self.exif_data = {}
        for filename in os.listdir(self.folder_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                image_path = os.path.join(self.folder_path, filename)
                self.images.append(image_path)
        
        self.progress_bar["maximum"] = len(self.images)
        self.progress_bar["value"] = 0
        
        threading.Thread(target=self.process_images, daemon=True).start()
        self.root.after(100, self.check_image_queue)

    def process_images(self):
        for i, image_path in enumerate(self.images):
            has_tag = self.has_exif_tag(image_path)
            self.exif_data[image_path] = has_tag
            self.image_queue.put((image_path, has_tag))
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
                image_path, has_tag = item
                filename = os.path.basename(image_path)
                self.tree.insert("", "end", values=(filename, "No" if self.is_filtered else ("Yes" if has_tag else "No")))
                self.progress_bar["value"] += 1
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
            if not self.is_filtered or not has_tag:
                filename = os.path.basename(image_path)
                self.tree.insert("", "end", values=(filename, "No" if self.is_filtered else ("Yes" if has_tag else "No")))

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageViewerApp(root)
    root.mainloop()