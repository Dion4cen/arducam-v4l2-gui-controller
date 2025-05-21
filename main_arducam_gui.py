import cv2
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, W, E
from PIL import Image, ImageTk
import threading
import time
from datetime import datetime
import os
import sys
import subprocess

class ArducamGUIController:
    def __init__(self, root, device_index=0, initial_exposure=7000, initial_framerate=30):
        self.root = root
        self.root.title("Arducam V4L2 GUI Controller")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.device_index = device_index
        # Validate initial values against known ranges from v4l2-ctl
        self.initial_exposure = max(1, min(initial_exposure, 65523)) # min=1, max=65523
        self.initial_framerate = max(5, min(initial_framerate, 120)) # min=5, max=120

        self.cap = None
        self.capture_thread = None
        self.running = True
        self.frame = None  # Stores the latest OpenCV frame

        # Tkinter variables for camera properties (bound to sliders AND entry fields)
        self.exposure_var = tk.IntVar(value=self.initial_exposure)
        self.framerate_var = tk.IntVar(value=self.initial_framerate)

        # These variables hold the *desired* values that will be pushed to the camera
        # They are updated only when an "Apply" button is pressed or initially on camera open.
        self._desired_exposure = self.initial_exposure
        self._desired_framerate = self.initial_framerate

        # Video recording variables
        self.is_recording = False
        self.video_writer = None
        self.fourcc = cv2.VideoWriter_fourcc(*'MJPG') 
        self.record_fps_target = self._desired_framerate # Target FPS for video writer
        self.camera_resolution = (640, 480) # Default, will be updated by camera

        self.create_widgets()
        self.open_camera()
        self.start_capture_thread()

    def create_widgets(self):
        # --- Control Frame ---
        control_frame = ttk.LabelFrame(self.root, text="Camera Controls")
        control_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # Row 0: Exposure
        ttk.Label(control_frame, text="Exposure (us):").grid(row=0, column=0, padx=5, pady=2, sticky=W)
        self.exposure_scale = ttk.Scale(control_frame, from_=1, to=65523, orient="horizontal",
                                         variable=self.exposure_var, length=200) # Removed command
        self.exposure_scale.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        
        # New: Exposure Entry
        self.exposure_entry = ttk.Entry(control_frame, textvariable=self.exposure_var, width=8)
        self.exposure_entry.grid(row=0, column=2, padx=5, pady=2)
        
        # New: Exposure Apply Button
        ttk.Button(control_frame, text="Apply Exposure", command=self.apply_exposure).grid(row=0, column=3, padx=5, pady=2)


        # Row 1: Framerate
        ttk.Label(control_frame, text="Frame Rate (FPS):").grid(row=1, column=0, padx=5, pady=2, sticky=W)
        self.framerate_scale = ttk.Scale(control_frame, from_=5, to=120, orient="horizontal",
                                          variable=self.framerate_var, length=200) # Removed command
        self.framerate_scale.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        
        # New: Framerate Entry
        self.framerate_entry = ttk.Entry(control_frame, textvariable=self.framerate_var, width=8)
        self.framerate_entry.grid(row=1, column=2, padx=5, pady=2)

        # New: Framerate Apply Button
        ttk.Button(control_frame, text="Apply Framerate", command=self.apply_framerate).grid(row=1, column=3, padx=5, pady=2)
        
        control_frame.columnconfigure(1, weight=1) # Allow slider to expand

        # --- Action Buttons Frame ---
        button_frame = ttk.Frame(self.root)
        button_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        ttk.Button(button_frame, text="Capture Image", command=self.save_image).pack(side="left", padx=5, fill="x", expand=True)
        self.record_button = ttk.Button(button_frame, text="Start Recording", command=self.toggle_recording)
        self.record_button.pack(side="left", padx=5, fill="x", expand=True)
        
        # New: Quit Button
        self.quit_button = ttk.Button(button_frame, text="Quit", command=self.on_closing, style="Red.TButton")
        self.quit_button.pack(side="left", padx=5, fill="x", expand=True)


        # --- Video Preview Frame ---
        self.canvas_width = 640
        self.canvas_height = 480
        self.canvas = tk.Canvas(self.root, width=self.canvas_width, height=self.canvas_height, bg="black")
        self.canvas.grid(row=2, column=0, padx=10, pady=10)

    def _set_v4l2_control(self, control_name, value):
        """Helper to set a V4L2 control using v4l2-ctl subprocess."""
        command = [
            'v4l2-ctl',
            '-d', str(self.device_index),
            '-c', f"{control_name}={value}"
        ]
        try:
            # Use check_output for potential errors, but don't print stdout/stderr
            # unless an error occurs or for debugging.
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # print(f"Successfully ran: {' '.join(command)}") # Uncomment for verbose debugging
        except subprocess.CalledProcessError as e:
            print(f"Error setting V4L2 control '{control_name}={value}':")
            print(f"Command: {' '.join(e.cmd)}")
            print(f"Stdout: {e.stdout.decode().strip()}")
            print(f"Stderr: {e.stderr.decode().strip()}")
            # We don't want a pop-up every loop if an error happens.
            # messagebox.showerror("V4L2 Control Error", 
            #                      f"Failed to set {control_name} to {value}:\n{e.stderr.decode().strip()}")
        except FileNotFoundError:
            messagebox.showerror("Error", "v4l2-ctl command not found. Please install v4l2-utils (sudo apt install v4l2-utils).")
            self.running = False # Critical error, stop the application.


    def open_camera(self):
        print(f"Attempting to open camera device: {self.device_index} with CAP_V4L2 backend")
        self.cap = cv2.VideoCapture(self.device_index, cv2.CAP_V4L2)

        if not self.cap.isOpened():
            messagebox.showerror("Camera Error", f"Failed to open camera device {self.device_index}. "
                                                 "Please check device index and permissions.")
            self.running = False
            return

        # Set initial settings using v4l2-ctl subprocess command
        print(f"Setting initial exposure via v4l2-ctl to {self._desired_exposure} us")
        self._set_v4l2_control("exposure", self._desired_exposure)
        
        print(f"Setting initial framerate via v4l2-ctl to {self._desired_framerate} FPS")
        self._set_v4l2_control("frame_rate", self._desired_framerate)

        # Get actual camera resolution once camera is open
        # Note: CV_CAP_PROP_FPS and CV_CAP_PROP_EXPOSURE might still report default/0
        # values from OpenCV's side if not properly mapped internally by the driver,
        # but the v4l2-ctl commands are what actually change the hardware.
        self.camera_resolution = (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), 
                                  int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        print(f"Camera resolution detected: {self.camera_resolution[0]}x{self.camera_resolution[1]}")

    def start_capture_thread(self):
        if not self.running:
            return
        self.capture_thread = threading.Thread(target=self.update_frame_loop, daemon=True)
        self.capture_thread.start()

    def update_frame_loop(self):
        frame_count = 0
        start_time = time.time()
        
        # Keep track of last values *actually pushed* to v4l2-ctl to avoid spamming the command
        last_pushed_exposure = -1
        last_pushed_framerate = -1

        while self.running:
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1) 
                continue

            # Continuously ensure the camera is set to the desired values
            # These are pushed via v4l2-ctl, not OpenCV's cap.set()
            if self._desired_exposure != last_pushed_exposure:
                self._set_v4l2_control("exposure", self._desired_exposure)
                last_pushed_exposure = self._desired_exposure

            if self._desired_framerate != last_pushed_framerate:
                self._set_v4l2_control("frame_rate", self._desired_framerate)
                last_pushed_framerate = self._desired_framerate


            ret, frame = self.cap.read()
            if not ret:
                print("Failed to grab frame. Camera might be disconnected or error occurred.")
                time.sleep(1)
                continue

            self.frame = frame  # Store the latest frame

            # If recording, write frame to video file
            if self.is_recording and self.video_writer is not None and self.video_writer.isOpened():
                self.video_writer.write(frame)

            # Update FPS calculation in terminal
            frame_count += 1
            elapsed_time = time.time() - start_time
            if elapsed_time >= 1.0:
                fps = frame_count / elapsed_time
                print(f"Live Stream FPS: {fps:.2f} (Desired: {self._desired_framerate:.0f})")
                frame_count = 0
                start_time = time.time()

            # Prepare frame for Tkinter display (in main thread using after())
            if frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                h, w = frame_rgb.shape[:2]
                display_w, display_h = w, h 

                if w > self.canvas_width or h > self.canvas_height:
                    aspect_ratio = w / h
                    if aspect_ratio > (self.canvas_width / self.canvas_height):
                        display_w = self.canvas_width
                        display_h = int(self.canvas_width / aspect_ratio)
                    else:
                        display_h = self.canvas_height
                        display_w = int(self.canvas_height * aspect_ratio)
                
                display_frame_resized = cv2.resize(frame_rgb, (display_w, display_h))
                img = Image.fromarray(display_frame_resized)
                img_tk = ImageTk.PhotoImage(image=img)
                
                self.root.after(0, self.update_canvas, img_tk, display_w, display_h)

            time.sleep(0.01) # Small delay to yield CPU

        print("Capture thread stopped.")
        self.release_resources()

    def update_canvas(self, img_tk, img_w, img_h):
        self.photo = img_tk
        x_center = self.canvas_width // 2
        y_center = self.canvas_height // 2
        self.canvas.delete("all")
        self.canvas.create_image(x_center, y_center, image=self.photo, anchor=tk.CENTER)

    # Method to apply exposure setting (triggered by button)
    def apply_exposure(self):
        try:
            val = self.exposure_var.get()
            # Enforce range for user input, clamp if out of bounds
            val = max(1, min(val, 65523)) # Apply the known V4L2 range
            self.exposure_var.set(val) # Update entry/slider if value was clamped

            if val != self._desired_exposure: # Only update if new desired value is different
                self._desired_exposure = val # Store the new *target* value
                print(f"Exposure 'Apply' clicked. Desired exposure set to: {val} us")
        except tk.TclError: # Catches non-integer input in Entry
            messagebox.showerror("Invalid Input", "Please enter an integer value for exposure.")

    # Method to apply framerate setting (triggered by button)
    def apply_framerate(self):
        try:
            val = self.framerate_var.get()
            # Enforce range for user input, clamp if out of bounds
            val = max(5, min(val, 120)) # Apply the known V4L2 range
            self.framerate_var.set(val) # Update entry/slider if value was clamped

            if val != self._desired_framerate:
                self._desired_framerate = val # Store the new *target* value
                self.record_fps_target = val # Also update target for recording
                print(f"Framerate 'Apply' clicked. Desired framerate set to: {val} FPS")
        except tk.TclError: # Catches non-integer input in Entry
            messagebox.showerror("Invalid Input", "Please enter an integer value for framerate.")

    def save_image(self):
        if self.frame is not None:
            output_dir = "captured_images"
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(output_dir, f"capture_{timestamp}.png")
            try:
                cv2.imwrite(filename, self.frame)
                messagebox.showinfo("Image Saved", f"Image saved as {filename}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save image: {e}")
        else:
            messagebox.showwarning("No Frame", "No frame available to save.")

    def toggle_recording(self):
        if not self.is_recording:
            if self.cap is None or not self.cap.isOpened():
                messagebox.showerror("Recording Error", "Camera is not open!")
                return

            output_dir = "recorded_videos"
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            initial_filename = f"video_{timestamp}.avi"

            video_filepath = filedialog.asksaveasfilename(
                initialdir=output_dir,
                initialfile=initial_filename,
                defaultextension=".avi",
                filetypes=[("AVI files", "*.avi"), ("All files", "*.*")]
            )
            if not video_filepath: 
                return

            try:
                width, height = self.camera_resolution
                # Use _desired_framerate for recording target FPS as this is what we're applying
                record_fps = self._desired_framerate if self._desired_framerate > 0 else 30 
                
                self.video_writer = cv2.VideoWriter(video_filepath, self.fourcc, 
                                                    record_fps, (width, height))
                
                if not self.video_writer.isOpened():
                    raise IOError("Failed to open video writer. Check codec (MJPG recommended) and permissions.")

                self.is_recording = True
                self.record_button.config(text="Stop Recording", style="Red.TButton")
                print(f"Recording started to {video_filepath} at {record_fps} FPS. Resolution: {width}x{height}")
            except Exception as e:
                messagebox.showerror("Recording Error", f"Failed to start recording: {e}")
                if self.video_writer: self.video_writer.release()
                self.video_writer = None
        else:
            self.is_recording = False
            self.record_button.config(text="Start Recording", style="TButton")
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            print("Recording stopped.")
            messagebox.showinfo("Recording Stopped", "Video recording has been stopped.")

    def release_resources(self):
        if self.cap:
            self.cap.release()
            print("Camera released.")
        if self.is_recording and self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            print("Video writer released upon exit.")

    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit the application?"):
            self.running = False
            if self.capture_thread and self.capture_thread.is_alive():
                self.capture_thread.join(timeout=5)
                if self.capture_thread.is_alive():
                    print("Warning: Capture thread did not terminate cleanly.")
            self.root.destroy()

if __name__ == "__main__":
    device_index = 0
    initial_exposure = 800  # v4l2-ctl default
    initial_framerate = 60 # v4l2-ctl default

    # Command-line argument parsing
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '-v':
            if i + 1 < len(sys.argv) and sys.argv[i+1].isdigit(): # Check if next arg is a digit
                try:
                    device_index = int(sys.argv[i+1])
                    i += 1
                except ValueError:
                    print(f"Warning: Invalid device index '{sys.argv[i+1]}'. Using default 0.")
            else:
                print("Warning: -v requires a device index (e.g., -v 0). Using default 0.")
        elif arg == '--exposure':
            if i + 1 < len(sys.argv) and sys.argv[i+1].isdigit():
                try:
                    initial_exposure = int(sys.argv[i+1])
                    i += 1
                except ValueError:
                    print(f"Warning: Invalid exposure value '{sys.argv[i+1]}'. Using default {initial_exposure}.")
            else:
                print("Warning: --exposure requires a numerical value.")
        elif arg == '--framerate':
            if i + 1 < len(sys.argv) and sys.argv[i+1].isdigit():
                try:
                    initial_framerate = int(sys.argv[i+1])
                    i += 1
                except ValueError:
                    print(f"Warning: Invalid framerate value '{sys.argv[i+1]}'. Using default {initial_framerate}.")
            else:
                print("Warning: --framerate requires a numerical value.")
        i += 1

    print(f"Starting Arducam GUI with: Device={device_index}, "
          f"Initial Exposure={initial_exposure}us, Initial Framerate={initial_framerate}FPS")

    root = tk.Tk()
    
    style = ttk.Style()
    style.configure('Red.TButton', background='red', foreground='red',
                    font=('Arial', 10, 'bold'))
    style.map('Red.TButton',
              background=[('active', 'darkred'), ('!disabled', 'red')],
              foreground=[('active', 'white'), ('!disabled', 'white')])

    app = ArducamGUIController(root, device_index, initial_exposure, initial_framerate)
    root.mainloop()