"""Car detection using a lazily-loaded YOLOv11n model.

GPU is disabled by default via CUDA_VISIBLE_DEVICES to support older GPUs
like the GTX 1060 whose compute capability (6.1) isn't covered by modern
PyTorch builds.  Remove the env-var line below if you later upgrade to a
compatible GPU.
"""

import os
import threading
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""

_model = None
_model_lock = threading.Lock()


def _get_model():
    """Return the YOLOv11n model, downloading and loading it on first call.

    The model is eagerly warmed up (dummy inference) inside the lock so that
    later concurrent calls to ``count_cars`` share a fully-initialised model.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                import numpy as np
                from ultralytics import YOLO

                _model = YOLO("yolo11n.pt")
                _model(np.zeros((64, 64, 3), dtype=np.uint8), verbose=False)
    return _model


def count_cars(image_path: str | Path, annotate_path: str | Path | None = None) -> int:
    """Run YOLOv11n inference on an image and return the number of 'car' detections.

    If *annotate_path* is given, the image with bounding-box overlays (all
    detected classes, not just cars) is saved to that path.

    This function is synchronous and CPU-bound. Call it via asyncio.to_thread().
    """
    model = _get_model()
    results = model(str(image_path))
    result = results[0]
    car_count = 0
    for i in range(len(result.boxes)):
        cls_id = int(result.boxes.cls[i])
        if result.names[cls_id] == "car":
            car_count += 1

    if annotate_path is not None:
        import cv2

        annotated = result.plot()
        path = Path(annotate_path)
        if not path.suffix:
            path = path.with_suffix(".png")
        cv2.imwrite(str(path), annotated)

    return car_count
