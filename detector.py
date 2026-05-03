"""Car detection using a lazily-loaded YOLOv11n model."""

from pathlib import Path

_model = None


def _get_model():
    """Return the YOLOv11n model, downloading and loading it on first call."""
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO("yolo11n.pt")
    return _model


def count_cars(image_path: str | Path) -> int:
    """Run YOLOv11n inference on an image and return the number of 'car' detections.

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
    return car_count
