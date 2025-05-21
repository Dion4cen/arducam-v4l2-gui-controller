# Arducam V4L2 GUI Controller for Jetson Device

**This project is optimized based on user-provided `v4l2-ctl` output. It directly controls camera exposure and frame rate by calling the system's `v4l2-ctl` command, effectively solving the issue of OpenCV versions not supporting `CAP_PROP_RAW_V4L2_CONTROL`. The latest version introduces manual input fields for exposure and frame rate values, activated by an "Apply" button.**

---

## 🎯 Key Features

*   **GUI Interactive Interface**: Provides an intuitive user interface for camera control.
*   **Exposure Control**: Sets camera exposure values (in microseconds μs) **by calling the `v4l2-ctl` command**. Offers both **slider and manual input field** options, with values applied by clicking the **“Apply Exposure” button**. Slider range is set from `1` to `65523`.
*   **Frame Rate Control**: Sets camera frame rate (FPS) **by calling the `v4l2-ctl` command**. Offers both **slider and manual input field** options, with values applied by clicking the **“Apply Framerate” button**. Slider range is set from `5` to `120`.
*   **Parameter Persistence**: Continuously applies and adjusts camera parameters in the background via periodic `v4l2-ctl` command execution, preventing parameters from reverting to default values.
*   **Real-time Video Preview**: Displays a live video stream from the camera within the GUI window.
*   **Image Capture**: Save the current video frame as a PNG image with a click of a button. Default save location is `./captured_images/`.
*   **Video Recording**: Start/stop recording the video stream as an AVI file (MJPG codec) by clicking a button.
*   **Command Line Arguments**: Supports specifying camera device ID, initial exposure, and frame rate via command-line arguments.

---

## 🚀 Compatibility

*   **Hardware**: NVIDIA Jetson NX/Nano, Jetson Orin Nano/NX (or any other Linux system supporting V4L2).
*   **Software**: Python 3.x, OpenCV, **`v4l2-utils` package**.

---

## 📋 Prerequisites

On your Jetson Orin Device, please ensure the following software is installed:

*   **Python 3.x**
*   **pip** (Python package manager)
*   **OpenCV for Python**: Usually pre-installed on Jetson systems or available via Jetson Pytorch containers.
*   **v4l2-utils**: This package provides the `v4l2-ctl` command. If not already installed on your system, install it using:

    ```bash
    sudo apt update
    sudo apt install v4l2-utils
    ```

Install Python libraries:
```bash
sudo apt install python3-opencv
pip install numpy Pillow
```
---

## 🛠️ Installation and Running
1. Clone the repository:
```
git clone https://github.com/Dion4cen/arducam-v4l2-gui-controller.git
cd arducam-v4l2-gui-controller
```
2. Run the application:
You can start with the default settings 
```
python3 main_arducam_gui.py
```
Or specify the camera device, initial exposure, and frame rate via command-line arguments:
```
python3 main_arducam_gui.py -v 0 --exposure 7000 --framerate 30
```
+ **-v** <device_index>: Must be followed by a number. Specifies the camera device index (e.g., 0 for /dev/video0, 1 for /dev/video1).

+ **--exposur**e <value>: Sets the initial exposure value (range 1 to 65523 based on v4l2-ctl output, in microseconds).

+ **--framerate** <value>: Sets the initial frame rate (FPS, range 5 to 35 based on v4l2-ctl output).
