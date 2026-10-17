# models/

Trained weights are not committed (size). Put here:

| File | Produced by | Used by |
|------|-------------|---------|
| `chotu_suck_avoid_yolov8n.pt` | `ros2_ws/src/chotu_perception/training/train_suck_avoid.py` on the RTX 3060 | `yolo_detector_node` (dev / GPU) |
| `chotu_suck_avoid_yolov8n_ncnn_model/` | same script (`--export-only`) | `yolo_detector_node` on the Raspberry Pi 4 (CPU) |

Without a custom model the node falls back to the stock COCO `yolov8n.pt`
(downloaded automatically by Ultralytics). In that mode it only produces
`avoid` detections for furniture, people and pets.
