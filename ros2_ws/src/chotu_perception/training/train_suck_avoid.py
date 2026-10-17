#!/usr/bin/env python3
"""Fine-tune YOLOv8n on CHOTU's actionable classes (run on the RTX 3060 dev PC).

Dataset layout (YOLO format) - see chotu_suck_avoid.yaml:
    datasets/chotu_suck_avoid/images/{train,val}/*.jpg
    datasets/chotu_suck_avoid/labels/{train,val}/*.txt

Collect frames with the robot camera at 16 cm height / 28 deg tilt (the same
pose CameraModel assumes), label with Roboflow / CVAT / Label Studio.  For
bootstrapping, the VLM-Vac approach (old_essential_docs/essential_research_paper_docs)
can pre-label frames with a vision-language model and you correct them.

Usage:
    pip install ultralytics==8.3.40
    python train_suck_avoid.py --data chotu_suck_avoid.yaml --epochs 80 --device 0
    # -> runs/detect/chotu/weights/best.pt  -> copy to models/chotu_suck_avoid_yolov8n.pt
    python train_suck_avoid.py --export-only runs/detect/chotu/weights/best.pt   # NCNN for the Pi
"""
import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="chotu_suck_avoid.yaml")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)     # fits the 6 GB RTX 3060 laptop GPU
    ap.add_argument("--device", default="0")
    ap.add_argument("--export-only", help="export an existing .pt to NCNN (fast CPU inference on Pi 4)")
    args = ap.parse_args()

    from ultralytics import YOLO

    if args.export_only:
        YOLO(args.export_only).export(format="ncnn", imgsz=320, half=False)
        return
    model = YOLO("yolov8n.pt")
    model.train(data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
                device=args.device, name="chotu", patience=20, cos_lr=True,
                degrees=10, fliplr=0.5, mosaic=1.0, hsv_v=0.4)   # floor/lighting variation
    metrics = model.val()
    print(f"mAP50-95: {metrics.box.map:.3f}  mAP50: {metrics.box.map50:.3f}")
    model.export(format="ncnn", imgsz=320)


if __name__ == "__main__":
    main()
