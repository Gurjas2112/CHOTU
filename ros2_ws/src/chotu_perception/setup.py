import os
from glob import glob

from setuptools import setup

package_name = "chotu_perception"

setup(
    name=package_name,
    version="2.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "training"), glob("training/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Gurjas Singh Gandhi",
    maintainer_email="gurjasgandhi76@gmail.com",
    description="YOLOv8n suck/avoid detector for CHOTU",
    license="MIT",
    entry_points={"console_scripts": [
        "yolo_detector_node = chotu_perception.yolo_detector_node:main",
    ]},
)
